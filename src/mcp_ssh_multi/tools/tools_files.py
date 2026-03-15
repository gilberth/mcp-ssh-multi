"""
File operation tools: ssh_upload, ssh_download, ssh_file_exists,
ssh_list_dir, ssh_read_file, ssh_write_file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import Field

from ..errors import (
    ErrorCode,
    create_error_response,
    create_server_not_found_error,
    exception_to_structured_error,
)
from .helpers import log_tool_usage, validate_remote_path

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from ..client.ssh_client import SSHConnectionPool


def register_files_tools(mcp: FastMCP, pool: SSHConnectionPool) -> None:
    """Register file operation tools."""

    @mcp.tool(annotations={"destructiveHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_upload(
        server_name: Annotated[
            str, Field(description="Target server name")
        ],
        local_path: Annotated[
            str, Field(description="Local file path to upload")
        ],
        remote_path: Annotated[
            str, Field(description="Remote destination path")
        ],
    ) -> dict[str, Any]:
        """Upload a file to a remote server via SFTP.

        EXAMPLES:
        - ssh_upload("proxmox", "/tmp/config.yaml", "/etc/app/config.yaml")
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        path_err = validate_remote_path(remote_path)
        if path_err:
            return create_error_response(
                ErrorCode.VALIDATION_INVALID_PARAMETER,
                f"Invalid remote path: {path_err}",
                context={"remote_path": remote_path},
            )
        try:
            result = await pool.upload_file(server_name, local_path, remote_path)
            return {"success": True, "server_name": server_name, **result}
        except FileNotFoundError as e:
            return create_error_response(
                ErrorCode.FILE_NOT_FOUND,
                str(e),
                context={"server_name": server_name, "local_path": local_path},
            )
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name}
            )

    @mcp.tool(annotations={"openWorldHint": True})
    @log_tool_usage
    async def ssh_download(
        server_name: Annotated[
            str, Field(description="Source server name")
        ],
        remote_path: Annotated[
            str, Field(description="Remote file path to download")
        ],
        local_path: Annotated[
            str, Field(description="Local destination path")
        ],
    ) -> dict[str, Any]:
        """Download a file from a remote server via SFTP.

        EXAMPLES:
        - ssh_download("truenas", "/var/log/syslog", "/tmp/syslog.txt")
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        path_err = validate_remote_path(remote_path)
        if path_err:
            return create_error_response(
                ErrorCode.VALIDATION_INVALID_PARAMETER,
                f"Invalid remote path: {path_err}",
                context={"remote_path": remote_path},
            )
        try:
            result = await pool.download_file(server_name, remote_path, local_path)
            return {"success": True, "server_name": server_name, **result}
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "remote_path": remote_path}
            )

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_file_exists(
        server_name: Annotated[
            str, Field(description="Server name")
        ],
        remote_path: Annotated[
            str, Field(description="Remote path to check")
        ],
    ) -> dict[str, Any]:
        """Check if a file or directory exists on a remote server.

        Returns existence status, type (file/directory), size, and permissions.

        EXAMPLES:
        - ssh_file_exists("proxmox", "/etc/pve/qemu-server/100.conf")
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        path_err = validate_remote_path(remote_path)
        if path_err:
            return create_error_response(
                ErrorCode.VALIDATION_INVALID_PARAMETER,
                f"Invalid remote path: {path_err}",
                context={"remote_path": remote_path},
            )
        try:
            result = await pool.file_exists(server_name, remote_path)
            return {"success": True, "server_name": server_name, **result}
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "remote_path": remote_path}
            )

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_list_dir(
        server_name: Annotated[
            str, Field(description="Server name")
        ],
        remote_path: Annotated[
            str,
            Field(
                description="Remote directory path (default: home directory)",
                default=".",
            ),
        ] = ".",
    ) -> dict[str, Any]:
        """List contents of a remote directory.

        Returns file names, types, sizes, and permissions.

        EXAMPLES:
        - ssh_list_dir("truenas", "/mnt/data")
        - ssh_list_dir("proxmox")  # lists home directory
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        path_err = validate_remote_path(remote_path)
        if path_err:
            return create_error_response(
                ErrorCode.VALIDATION_INVALID_PARAMETER,
                f"Invalid remote path: {path_err}",
                context={"remote_path": remote_path},
            )
        try:
            entries = await pool.list_dir(server_name, remote_path)
            return {
                "success": True,
                "server_name": server_name,
                "path": remote_path,
                "entries": entries,
                "total": len(entries),
            }
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "remote_path": remote_path}
            )

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_read_file(
        server_name: Annotated[
            str, Field(description="Server name")
        ],
        remote_path: Annotated[
            str, Field(description="Remote file path to read")
        ],
        max_size: Annotated[
            int,
            Field(
                description="Max file size in bytes (default: 1MB)",
                default=1_000_000,
            ),
        ] = 1_000_000,
    ) -> dict[str, Any]:
        """Read a text file from a remote server.

        Returns the file contents as a string. For binary or large files,
        use ssh_download instead.

        EXAMPLES:
        - ssh_read_file("proxmox", "/etc/hostname")
        - ssh_read_file("truenas", "/var/log/messages", max_size=5000000)
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        path_err = validate_remote_path(remote_path)
        if path_err:
            return create_error_response(
                ErrorCode.VALIDATION_INVALID_PARAMETER,
                f"Invalid remote path: {path_err}",
                context={"remote_path": remote_path},
            )
        try:
            content = await pool.read_file(server_name, remote_path, max_size=max_size)
            return {
                "success": True,
                "server_name": server_name,
                "path": remote_path,
                "content": content,
                "size_bytes": len(content.encode("utf-8")),
            }
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "remote_path": remote_path}
            )

    @mcp.tool(annotations={"destructiveHint": True, "openWorldHint": True})
    @log_tool_usage
    async def ssh_write_file(
        server_name: Annotated[
            str, Field(description="Server name")
        ],
        remote_path: Annotated[
            str, Field(description="Remote file path to write")
        ],
        content: Annotated[
            str, Field(description="Content to write to the file")
        ],
    ) -> dict[str, Any]:
        """Write content to a file on a remote server.

        Creates or overwrites the file with the given content.

        EXAMPLES:
        - ssh_write_file("proxmox", "/tmp/test.txt", "Hello World")
        """
        if not pool.get_server_config(server_name):
            return create_server_not_found_error(server_name)
        path_err = validate_remote_path(remote_path)
        if path_err:
            return create_error_response(
                ErrorCode.VALIDATION_INVALID_PARAMETER,
                f"Invalid remote path: {path_err}",
                context={"remote_path": remote_path},
            )
        try:
            result = await pool.write_file(server_name, remote_path, content)
            return {"success": True, "server_name": server_name, **result}
        except Exception as e:
            return exception_to_structured_error(
                e, context={"server_name": server_name, "remote_path": remote_path}
            )
