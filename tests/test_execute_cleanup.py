"""Tests for bounded command output and process cleanup."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mcp_ssh_multi.client.ssh_client import ServerConfig, SSHConnectionPool


class ChunkReader:
    """Async reader which yields predefined chunks."""

    def __init__(self, chunks):
        self._chunks = iter(chunks)

    async def read(self, _size):
        await asyncio.sleep(0)
        return next(self._chunks, b"")


def make_pool(process, max_output_bytes=1024):
    pool = SSHConnectionPool(
        servers={"test": ServerConfig(name="test", host="localhost")},
        max_output_bytes=max_output_bytes,
    )
    conn = MagicMock()
    conn.is_closed.return_value = False
    conn.create_process = AsyncMock(return_value=process)
    conn.wait_closed = AsyncMock()
    pool._connections["test"] = conn
    return pool, conn


@pytest.mark.asyncio
async def test_timeout_terminates_and_closes_process():
    """A timed out command doesn't leave its SSH channel open."""
    process = MagicMock()
    process.stdout = ChunkReader([])
    process.stderr = ChunkReader([])
    never_closed = asyncio.Event()
    process.wait_closed = AsyncMock(side_effect=never_closed.wait)
    process.terminate.side_effect = never_closed.set
    pool, _ = make_pool(process)

    with pytest.raises(TimeoutError, match="timed out"):
        await pool.execute("test", "sleep infinity", timeout=0.01)

    process.terminate.assert_called_once()
    process.close.assert_called_once()


@pytest.mark.asyncio
async def test_output_limit_terminates_process_and_marks_result_truncated():
    """Output is bounded while it is read, rather than truncated afterward."""
    process = MagicMock()
    process.stdout = ChunkReader([b"12345", b"67890", b"extra"])
    process.stderr = ChunkReader([])
    closed = asyncio.Event()

    async def wait_closed():
        await closed.wait()

    process.wait_closed = AsyncMock(side_effect=wait_closed)
    process.exit_status = None
    process.terminate.side_effect = closed.set
    pool, _ = make_pool(process, max_output_bytes=10)

    result = await pool.execute("test", "unbounded output")

    assert result["stdout"] == "1234567890"
    assert result["truncated"] is True
    assert result["exit_code"] == -1
    process.terminate.assert_called_once()
    process.close.assert_called_once()


@pytest.mark.asyncio
async def test_output_at_exact_limit_is_not_marked_truncated():
    process = MagicMock()
    process.stdout = ChunkReader([b"1234567890"])
    process.stderr = ChunkReader([])
    process.wait_closed = AsyncMock()
    process.exit_status = 0
    pool, _ = make_pool(process, max_output_bytes=10)

    result = await pool.execute("test", "finite output")

    assert result["stdout"] == "1234567890"
    assert result["truncated"] is False
    process.terminate.assert_not_called()
