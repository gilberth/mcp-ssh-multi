"""
Command execution tool: ssh_execute.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ..errors import (
    create_command_error,
    create_server_not_found_error,
    exception_to_structured_error,
)
from .helpers import log_tool_usage

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..client.ssh_client import SSHConnectionPool


def register_execute_tools(mcp: FastMCP, pool: SSHConnectionPool) -> None:
    """Register command execution tools."""

    @mcp.tool(annotations={"destructiveHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_execute(
        server_name: Annotated[
            str,
            Field(description="Server name to execute on (from ssh_list_servers)"),
        ],
        command: Annotated[
            str,
            Field(description="Shell command to execute"),
        ],
        timeout: Annotated[
            int,
            Field(
                description="Command timeout in seconds (default: 30)",
                default=30,
            ),
        ] = 30,
    ) -> dict[str, Any]:
        """Execute a command on a remote SSH server.

        Runs the given shell command on the specified server and returns
        stdout, stderr, and exit code. Connections are established
        automatically and reused.

        EXAMPLES:
        - Run command: ssh_execute("proxmox", "uptime")
        - With timeout: ssh_execute("truenas", "zpool status", timeout=60)
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)

        try:
            result = await pool.execute(server_name, command, timeout=timeout)

            return {
                "success": True,
                "server_name": server_name,
                "command": command,
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "exit_code": result["exit_code"],
            }
        except TimeoutError:
            return create_command_error(
                server_name,
                command,
                f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "command": command}
            )
