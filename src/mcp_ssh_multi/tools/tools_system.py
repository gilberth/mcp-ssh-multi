"""
System tools: ssh_tail_log, ssh_process_list.
"""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ..errors import create_server_not_found_error, exception_to_structured_error
from .helpers import log_tool_usage

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..client.ssh_client import SSHConnectionPool


_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")
_SAFE_FILTER_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")


def _validate_log_path(path: str) -> str | None:
    """Validate and sanitize a log file path.

    Returns None if the path is safe, or an error message if not.
    """
    if not path or len(path) > 512:
        return "Path is empty or too long (max 512 chars)"
    if not path.startswith("/"):
        return "Path must be absolute (start with /)"
    if ".." in path:
        return "Path traversal (..) is not allowed"
    if not _SAFE_PATH_RE.match(path):
        return "Path contains invalid characters (only alphanumerics, '.', '_', '-', '/' allowed)"
    return None


def _validate_filter_name(name: str) -> str | None:
    """Validate a process filter name.

    Returns None if the name is safe, or an error message if not.
    """
    if not name or len(name) > 128:
        return "Filter is empty or too long (max 128 chars)"
    if not _SAFE_FILTER_RE.match(name):
        return "Filter contains invalid characters (only alphanumerics, '.', '_', '-', '/' allowed)"
    return None


def register_system_tools(mcp: FastMCP, pool: SSHConnectionPool) -> None:
    """Register system monitoring tools."""

    @mcp.tool(annotations={"readOnlyHint": True})
    @log_tool_usage
    async def ssh_tail_log(
        server_name: Annotated[
            str, Field(description="Server name")
        ],
        log_path: Annotated[
            str,
            Field(
                description="Path to log file (default: /var/log/syslog)",
                default="/var/log/syslog",
            ),
        ] = "/var/log/syslog",
        lines: Annotated[
            int,
            Field(
                description="Number of lines to tail (default: 50)",
                default=50,
            ),
        ] = 50,
    ) -> dict[str, Any]:
        """Tail a log file on a remote server.

        Returns the last N lines of the specified log file.

        EXAMPLES:
        - ssh_tail_log("proxmox")
        - ssh_tail_log("truenas", "/var/log/messages", lines=100)
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)

        # Validate log_path to prevent command injection
        path_error = _validate_log_path(log_path)
        if path_error:
            return {
                "success": False,
                "error": f"Invalid log path: {path_error}",
                "error_code": "INVALID_INPUT",
            }

        # Clamp lines to a reasonable range
        lines = max(1, min(lines, 10000))

        try:
            safe_path = shlex.quote(log_path)
            result = await pool.execute(
                server_name, f"tail -n {lines} {safe_path}", timeout=15
            )
            return {
                "success": True,
                "server_name": server_name,
                "log_path": log_path,
                "lines_requested": lines,
                "content": result["stdout"],
                "stderr": result["stderr"] if result["stderr"] else None,
            }
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "log_path": log_path}
            )

    @mcp.tool(annotations={"readOnlyHint": True})
    @log_tool_usage
    async def ssh_process_list(
        server_name: Annotated[
            str, Field(description="Server name")
        ],
        filter_name: Annotated[
            str | None,
            Field(
                description="Optional: filter processes by name (grep pattern)",
                default=None,
            ),
        ] = None,
    ) -> dict[str, Any]:
        """List running processes on a remote server.

        Returns process list sorted by CPU usage. Optionally filter by name.

        EXAMPLES:
        - ssh_process_list("proxmox")
        - ssh_process_list("truenas", filter_name="zfs")
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        try:
            if filter_name:
                # Validate filter_name to prevent command injection
                filter_error = _validate_filter_name(filter_name)
                if filter_error:
                    return {
                        "success": False,
                        "error": f"Invalid filter: {filter_error}",
                        "error_code": "INVALID_INPUT",
                    }
                safe_filter = shlex.quote(filter_name)
                cmd = f"ps aux | head -1; ps aux | grep -i {safe_filter} | grep -v grep"
            else:
                cmd = "ps aux --sort=-%cpu | head -30"

            result = await pool.execute(server_name, cmd, timeout=15)
            return {
                "success": True,
                "server_name": server_name,
                "filter": filter_name,
                "output": result["stdout"],
            }
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name}
            )
