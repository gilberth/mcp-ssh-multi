"""
Structured error handling for SSH MCP Server.

Provides standardized error codes, error response models, and helper
functions for creating consistent, informative error responses across all MCP tools.
"""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Standard error codes for SSH MCP operations."""

    # Connection errors
    CONNECTION_FAILED = "CONNECTION_FAILED"
    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    CONNECTION_AUTH_FAILED = "CONNECTION_AUTH_FAILED"
    CONNECTION_NOT_FOUND = "CONNECTION_NOT_FOUND"

    # Server errors
    SERVER_NOT_CONFIGURED = "SERVER_NOT_CONFIGURED"
    SERVER_NOT_CONNECTED = "SERVER_NOT_CONNECTED"

    # Command errors
    COMMAND_FAILED = "COMMAND_FAILED"
    COMMAND_TIMEOUT = "COMMAND_TIMEOUT"

    # File errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_TRANSFER_FAILED = "FILE_TRANSFER_FAILED"
    FILE_PERMISSION_DENIED = "FILE_PERMISSION_DENIED"

    # Validation errors
    VALIDATION_FAILED = "VALIDATION_FAILED"
    VALIDATION_INVALID_PARAMETER = "VALIDATION_INVALID_PARAMETER"
    VALIDATION_MISSING_PARAMETER = "VALIDATION_MISSING_PARAMETER"

    # Config errors
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_FILE_NOT_FOUND = "CONFIG_FILE_NOT_FOUND"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"


DEFAULT_SUGGESTIONS: dict[ErrorCode, list[str]] = {
    ErrorCode.CONNECTION_FAILED: [
        "Check if the SSH server is running and accessible",
        "Verify the hostname and port in ssh_servers.yaml",
        "Check network connectivity to the server",
    ],
    ErrorCode.CONNECTION_TIMEOUT: [
        "The SSH server may be overloaded or unreachable",
        "Check network latency to the server",
        "Try increasing the SSH_TIMEOUT value",
    ],
    ErrorCode.CONNECTION_AUTH_FAILED: [
        "Verify the SSH credentials (username, password, or key)",
        "Check that the SSH key file exists and has correct permissions",
        "Ensure the user is allowed to connect via SSH",
    ],
    ErrorCode.CONNECTION_NOT_FOUND: [
        "Use ssh_list_servers to see available server names",
        "Check the server name spelling",
        "Verify ssh_servers.yaml contains this server",
    ],
    ErrorCode.SERVER_NOT_CONFIGURED: [
        "Add server configuration to ssh_servers.yaml",
        "Set SSH_SERVERS_FILE environment variable if using a custom path",
    ],
    ErrorCode.SERVER_NOT_CONNECTED: [
        "The server connection was lost or never established",
        "Try re-executing the command (auto-reconnect will be attempted)",
    ],
    ErrorCode.COMMAND_FAILED: [
        "Check the command syntax",
        "Verify the user has permission to run this command",
        "Check server logs for more details",
    ],
    ErrorCode.COMMAND_TIMEOUT: [
        "The command took too long to complete",
        "Try increasing the timeout parameter",
        "Consider running the command in the background",
    ],
    ErrorCode.FILE_NOT_FOUND: [
        "Verify the file path exists on the remote server",
        "Check for typos in the file path",
        "Use ssh_list_dir to browse the directory",
    ],
    ErrorCode.FILE_TRANSFER_FAILED: [
        "Check file permissions on source and destination",
        "Verify sufficient disk space on the target",
        "Check network stability during transfer",
    ],
    ErrorCode.CONFIG_FILE_NOT_FOUND: [
        "Create ssh_servers.yaml with your server configurations",
        "Set SSH_SERVERS_FILE to point to your config file",
        "Copy from ssh_servers.yaml.example",
    ],
}


def create_error_response(
    code: ErrorCode,
    message: str,
    details: str | None = None,
    suggestions: list[str] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a structured error response.

    Args:
        code: Error code from ErrorCode enum.
        message: Human-readable error message.
        details: Additional details about the error.
        suggestions: List of suggestions to resolve the error.
        context: Additional context data.

    Returns:
        Structured error response dictionary with success=False.
    """
    error_suggestions = (
        suggestions if suggestions else DEFAULT_SUGGESTIONS.get(code, [])
    )

    error_dict: dict[str, Any] = {
        "code": code.value,
        "message": message,
    }

    if details:
        error_dict["details"] = details

    if error_suggestions:
        error_dict["suggestion"] = error_suggestions[0]
        if len(error_suggestions) > 1:
            error_dict["suggestions"] = error_suggestions

    response: dict[str, Any] = {
        "success": False,
        "error": error_dict,
    }

    if context:
        response.update(context)

    return response


def create_connection_error(
    server_name: str,
    message: str,
    details: str | None = None,
    timeout: bool = False,
    auth_failed: bool = False,
) -> dict[str, Any]:
    """Create a connection error response."""
    if auth_failed:
        code = ErrorCode.CONNECTION_AUTH_FAILED
    elif timeout:
        code = ErrorCode.CONNECTION_TIMEOUT
    else:
        code = ErrorCode.CONNECTION_FAILED
    return create_error_response(
        code, message, details, context={"server_name": server_name}
    )


def create_server_not_found_error(server_name: str) -> dict[str, Any]:
    """Create a server not found error response."""
    return create_error_response(
        ErrorCode.CONNECTION_NOT_FOUND,
        f"Server '{server_name}' not found in configuration",
        context={"server_name": server_name},
    )


def create_command_error(
    server_name: str,
    command: str,
    message: str,
    exit_code: int | None = None,
    stderr: str | None = None,
) -> dict[str, Any]:
    """Create a command execution error response."""
    context: dict[str, Any] = {"server_name": server_name, "command": command}
    if exit_code is not None:
        context["exit_code"] = exit_code
    if stderr:
        context["stderr"] = stderr
    return create_error_response(ErrorCode.COMMAND_FAILED, message, context=context)


def create_validation_error(
    message: str,
    parameter: str | None = None,
    details: str | None = None,
) -> dict[str, Any]:
    """Create a validation error response."""
    context: dict[str, Any] = {}
    if parameter:
        context["parameter"] = parameter
    return create_error_response(
        ErrorCode.VALIDATION_FAILED, message, details, context=context or None
    )


def exception_to_structured_error(
    error: Exception,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert an exception to a structured error response."""
    error_str = str(error).lower()
    error_msg = str(error)

    if "timeout" in error_str:
        return create_error_response(
            ErrorCode.CONNECTION_TIMEOUT, error_msg, context=context
        )
    elif "auth" in error_str or "permission" in error_str:
        return create_error_response(
            ErrorCode.CONNECTION_AUTH_FAILED, error_msg, context=context
        )
    elif "connection" in error_str or "connect" in error_str:
        return create_error_response(
            ErrorCode.CONNECTION_FAILED, error_msg, context=context
        )
    elif "not found" in error_str or "no such file" in error_str:
        return create_error_response(
            ErrorCode.FILE_NOT_FOUND, error_msg, context=context
        )
    else:
        return create_error_response(
            ErrorCode.INTERNAL_ERROR,
            error_msg,
            details="An unexpected error occurred",
            context=context,
        )
