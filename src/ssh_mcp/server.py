"""
Core SSH MCP Server implementation.

Implements lazy initialization pattern for improved startup time:
- Settings and FastMCP server are created immediately (fast)
- SSHConnectionPool is created lazily on first tool access
- Tool modules are discovered at startup but imported on first use
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastmcp import FastMCP

from .config import get_global_settings

if TYPE_CHECKING:
    from .client.ssh_client import SSHConnectionPool
    from .tools.registry import ToolsRegistry

logger = logging.getLogger(__name__)


class SSHMCPServer:
    """SSH MCP Server with lazy initialization.

    Uses lazy initialization to improve startup time:
    - Pool is created on first access from YAML config
    - Tool modules are discovered at startup but imported when first called
    """

    def __init__(self) -> None:
        """Initialize the SSH MCP server with lazy loading support."""
        # Load settings first (fast operation)
        self.settings = get_global_settings()

        # Lazy initialization placeholders
        self._pool: SSHConnectionPool | None = None
        self._tools_registry: ToolsRegistry | None = None

        # Create FastMCP server
        self.mcp = FastMCP(
            name=self.settings.mcp_server_name,
            version=self.settings.mcp_server_version,
        )

        # Register all tools
        self._initialize_server()

    @property
    def pool(self) -> SSHConnectionPool:
        """Lazily create and return the SSH connection pool."""
        if self._pool is None:
            from .client.ssh_client import SSHConnectionPool

            self._pool = SSHConnectionPool.from_yaml(self.settings.ssh_servers_file)
            logger.debug(
                f"Lazily created SSHConnectionPool from {self.settings.ssh_servers_file}"
            )
        return self._pool

    @property
    def tools_registry(self) -> ToolsRegistry:
        """Lazily create and return the tools registry."""
        if self._tools_registry is None:
            from .tools.registry import ToolsRegistry

            self._tools_registry = ToolsRegistry(self)
            logger.debug("Lazily created ToolsRegistry")
        return self._tools_registry

    def _initialize_server(self) -> None:
        """Initialize all server components."""
        self.tools_registry.register_all_tools()

    async def close(self) -> None:
        """Close the MCP server and cleanup resources."""
        if self._pool is not None:
            await self._pool.disconnect_all()
        logger.info("SSH MCP Server closed")
