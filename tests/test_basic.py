"""Unit tests for SSH MCP Server."""

from unittest.mock import MagicMock, patch

import pytest


class TestSSHMCPServer:
    """Tests for SSHMCPServer initialization."""

    @patch("mcp_ssh_multi.server.get_global_settings")
    @patch("mcp_ssh_multi.server.FastMCP")
    def test_server_creation(self, mock_fastmcp, mock_settings):
        """Server creates with settings and FastMCP."""
        mock_settings.return_value = MagicMock(
            mcp_server_name="ssh-mcp",
            mcp_server_version="0.1.0",
            ssh_servers_file="ssh_servers.yaml",
        )
        mock_mcp_instance = MagicMock()
        mock_fastmcp.return_value = mock_mcp_instance

        from mcp_ssh_multi.server import SSHMCPServer

        server = SSHMCPServer()

        assert server.mcp is mock_mcp_instance
        mock_fastmcp.assert_called_once_with(
            name="ssh-mcp",
            version="0.1.0",
        )


class TestErrorCodes:
    """Tests for structured error handling."""

    def test_create_error_response(self):
        """Error response has correct structure."""
        from mcp_ssh_multi.errors import ErrorCode, create_error_response

        result = create_error_response(
            ErrorCode.CONNECTION_FAILED,
            "Connection refused",
        )

        assert result["success"] is False
        assert result["error"]["code"] == "CONNECTION_FAILED"
        assert result["error"]["message"] == "Connection refused"

    def test_create_server_not_found_error(self):
        """Server not found error includes server name."""
        from mcp_ssh_multi.errors import create_server_not_found_error

        result = create_server_not_found_error("nonexistent")

        assert result["success"] is False
        assert "nonexistent" in result["error"]["message"]
        assert result["server_name"] == "nonexistent"

    def test_exception_to_structured_error_timeout(self):
        """Timeout exceptions map to TIMEOUT error code."""
        from mcp_ssh_multi.errors import exception_to_structured_error

        result = exception_to_structured_error(TimeoutError("connection timeout"))

        assert result["success"] is False
        assert result["error"]["code"] == "CONNECTION_TIMEOUT"

    def test_exception_to_structured_error_generic(self):
        """Generic exceptions map to INTERNAL_ERROR."""
        from mcp_ssh_multi.errors import exception_to_structured_error

        result = exception_to_structured_error(RuntimeError("something broke"))

        assert result["success"] is False
        assert result["error"]["code"] == "INTERNAL_ERROR"


class TestConfig:
    """Tests for configuration loading."""

    def test_default_settings(self):
        """Default settings are valid."""
        from mcp_ssh_multi.config import Settings

        settings = Settings()  # type: ignore[call-arg]

        assert settings.timeout == 30
        assert settings.log_level == "INFO"
        assert settings.mcp_server_name == "ssh-mcp"

    def test_log_level_validation(self):
        """Invalid log levels are rejected."""
        from mcp_ssh_multi.config import Settings

        with pytest.raises(ValueError):
            Settings(LOG_LEVEL="INVALID")  # type: ignore[call-arg]


class TestSSHConnectionPool:
    """Tests for SSHConnectionPool."""

    def test_from_yaml_missing_file(self):
        """Missing YAML file returns empty pool."""
        from mcp_ssh_multi.client.ssh_client import SSHConnectionPool

        pool = SSHConnectionPool.from_yaml("/nonexistent/path.yaml")

        assert len(pool.servers) == 0

    def test_list_servers_empty(self):
        """Empty pool returns empty list."""
        from mcp_ssh_multi.client.ssh_client import SSHConnectionPool

        pool = SSHConnectionPool()

        assert pool.list_servers() == []

    def test_get_server_config_not_found(self):
        """Non-existent server returns None."""
        from mcp_ssh_multi.client.ssh_client import SSHConnectionPool

        pool = SSHConnectionPool()

        assert pool.get_server_config("nonexistent") is None
