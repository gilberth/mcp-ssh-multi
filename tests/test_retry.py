"""Tests for connection retry and per-server locking."""

from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from mcp_ssh_multi.client.ssh_client import ServerConfig, SSHConnectionPool


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

        mock_result = MagicMock()
        mock_result.stdout = "ok"
        mock_result.stderr = ""
        mock_result.exit_status = 0

        # First call: raises ConnectionLost. Second call: works.
        bad_conn = AsyncMock()
        bad_conn.is_closed.return_value = True
        bad_conn.run.side_effect = asyncssh.ConnectionLost("lost")

        good_conn = AsyncMock()
        good_conn.is_closed.return_value = False
        good_conn.run.return_value = mock_result

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

        bad_conn = AsyncMock()
        bad_conn.is_closed.return_value = False
        bad_conn.run.side_effect = asyncssh.ConnectionLost("lost")

        with patch("asyncssh.connect", AsyncMock(return_value=bad_conn)):
            pool._connections["test"] = bad_conn

            with pytest.raises(asyncssh.ConnectionLost):
                await pool.execute("test", "echo ok")
