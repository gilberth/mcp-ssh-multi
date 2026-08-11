"""Tests for connection retry and per-server locking."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from mcp_ssh_multi.client.ssh_client import ServerConfig, SSHConnectionPool


class BytesReader:
    """Minimal async byte stream used by process mocks."""

    def __init__(self, content: bytes = b""):
        self._content = content

    async def read(self, size: int) -> bytes:
        content, self._content = self._content[:size], self._content[size:]
        return content


def make_process(stdout: bytes = b"ok", stderr: bytes = b"", exit_status: int = 0):
    process = MagicMock()
    process.stdout = BytesReader(stdout)
    process.stderr = BytesReader(stderr)
    process.exit_status = exit_status
    process.wait_closed = AsyncMock(return_value=None)
    return process


class TestPerServerLock:
    def test_get_lock_returns_same_lock_for_same_server(self):
        pool = SSHConnectionPool()
        lock1 = pool._get_server_lock("server1")
        lock2 = pool._get_server_lock("server1")
        assert lock1 is lock2

    def test_get_lock_returns_different_lock_for_different_servers(self):
        pool = SSHConnectionPool()
        lock1 = pool._get_server_lock("server1")
        lock2 = pool._get_server_lock("server2")
        assert lock1 is not lock2


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_execute_retries_on_connection_lost(self):
        """execute() should retry once if connection was lost."""
        pool = SSHConnectionPool(
            servers={"test": ServerConfig(name="test", host="localhost")}
        )

        # First call: raises ConnectionLost. Second call: works.
        bad_conn = MagicMock()
        bad_conn.is_closed.return_value = True
        bad_conn.create_process = AsyncMock(side_effect=asyncssh.ConnectionLost("lost"))
        bad_conn.wait_closed = AsyncMock()

        good_conn = MagicMock()
        good_conn.is_closed.return_value = False
        good_conn.create_process = AsyncMock(return_value=make_process())
        good_conn.wait_closed = AsyncMock()

        with patch("asyncssh.connect", AsyncMock(return_value=good_conn)):
            # Pre-load the bad connection so connect() returns it first
            pool._connections["test"] = bad_conn
            # bad_conn.is_closed() returns True, so connect() will create new one
            # But actually bad_conn.run raises ConnectionLost before that
            # So we need bad_conn to appear valid initially
            bad_conn.is_closed.return_value = False

            result = await pool.execute("test", "echo ok")
            assert result["stdout"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_does_not_retry_twice(self):
        """execute() should not retry more than once."""
        pool = SSHConnectionPool(
            servers={"test": ServerConfig(name="test", host="localhost")}
        )

        bad_conn = MagicMock()
        bad_conn.is_closed.return_value = False
        bad_conn.create_process = AsyncMock(side_effect=asyncssh.ConnectionLost("lost"))
        bad_conn.wait_closed = AsyncMock()

        with patch("asyncssh.connect", AsyncMock(return_value=bad_conn)):
            pool._connections["test"] = bad_conn

            with pytest.raises(asyncssh.ConnectionLost):
                await pool.execute("test", "echo ok")
