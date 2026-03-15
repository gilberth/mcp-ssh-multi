"""Tests for pagination in list_dir."""

from unittest.mock import AsyncMock, MagicMock

import asyncssh
import pytest

from mcp_ssh_multi.client.ssh_client import SSHConnectionPool, ServerConfig


class AsyncIteratorMock:
    """Mock async iterator for SFTP scandir."""

    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration


def _make_dir_entry(name: str, is_dir: bool = False):
    """Create a mock SFTP directory entry."""
    entry = MagicMock()
    entry.filename = name
    entry.attrs = MagicMock()
    entry.attrs.type = (
        asyncssh.FILEXFER_TYPE_DIRECTORY if is_dir else asyncssh.FILEXFER_TYPE_REGULAR
    )
    entry.attrs.size = 100
    entry.attrs.permissions = 0o644
    return entry


def _make_pool_with_mock_sftp(entries):
    """Create a pool with a mocked SFTP connection."""
    pool = SSHConnectionPool(
        servers={"test": ServerConfig(name="test", host="localhost")}
    )

    mock_conn = MagicMock()
    mock_sftp = AsyncMock()
    mock_sftp.scandir = MagicMock(return_value=AsyncIteratorMock(entries))
    mock_conn.start_sftp_client.return_value.__aenter__ = AsyncMock(
        return_value=mock_sftp
    )
    mock_conn.start_sftp_client.return_value.__aexit__ = AsyncMock(
        return_value=False
    )
    mock_conn.is_closed.return_value = False
    pool._connections["test"] = mock_conn

    return pool


class TestListDirPagination:
    @pytest.mark.asyncio
    async def test_list_dir_with_limit(self):
        """list_dir respects limit parameter."""
        entries = [_make_dir_entry(f"file{i}.txt") for i in range(20)]
        pool = _make_pool_with_mock_sftp(entries)

        result = await pool.list_dir("test", "/tmp", limit=5)
        assert len(result["entries"]) == 5
        assert result["total"] == 20
        assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_list_dir_with_offset(self):
        """list_dir respects offset parameter."""
        entries = [_make_dir_entry(f"file{i}.txt") for i in range(20)]
        pool = _make_pool_with_mock_sftp(entries)

        result = await pool.list_dir("test", "/tmp", limit=5, offset=15)
        assert len(result["entries"]) == 5
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_dir_no_pagination(self):
        """list_dir returns all entries when limit=0."""
        entries = [_make_dir_entry(f"file{i}.txt") for i in range(10)]
        pool = _make_pool_with_mock_sftp(entries)

        result = await pool.list_dir("test", "/tmp", limit=0)
        assert len(result["entries"]) == 10
        assert result["total"] == 10
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_list_dir_offset_beyond_entries(self):
        """list_dir returns empty when offset exceeds total."""
        entries = [_make_dir_entry(f"file{i}.txt") for i in range(5)]
        pool = _make_pool_with_mock_sftp(entries)

        result = await pool.list_dir("test", "/tmp", limit=10, offset=10)
        assert len(result["entries"]) == 0
        assert result["total"] == 5
        assert result["has_more"] is False
