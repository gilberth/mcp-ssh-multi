"""
Connection management tools: ssh_list_servers, ssh_disconnect.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from .helpers import log_tool_usage

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..client.ssh_client import SSHConnectionPool


def register_connection_tools(mcp: FastMCP, pool: SSHConnectionPool) -> None:
    """Register connection management tools."""

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_list_servers(
        _placeholder: Annotated[
            bool,
            Field(description="Placeholder. Always pass true."),
        ] = True,
    ) -> dict[str, Any]:
        """List all configured SSH servers with connection status.

        Returns server names, hosts, usernames, descriptions, and whether
        each server currently has an active connection.

        EXAMPLES:
        - List all servers: ssh_list_servers()
        """
        servers = pool.list_servers()
        return {
            "success": True,
            "servers": servers,
            "total": len(servers),
        }

    @mcp.tool(annotations={"idempotentHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_disconnect(
        server_name: Annotated[
            str,
            Field(description="Server name to disconnect from (from ssh_list_servers)"),
        ],
    ) -> dict[str, Any]:
        """Disconnect from a specific SSH server.

        Closes the active SSH connection to the named server.
        The connection will be re-established automatically on next command.

        EXAMPLES:
        - Disconnect: ssh_disconnect("proxmox")
        """
        disconnected = await pool.disconnect(server_name)
        if disconnected:
            return {
                "success": True,
                "message": f"Disconnected from {server_name}",
                "server_name": server_name,
            }
        return {
            "success": True,
            "message": f"Server {server_name} was not connected",
            "server_name": server_name,
        }
