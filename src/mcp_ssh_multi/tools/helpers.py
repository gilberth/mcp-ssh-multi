"""
Reusable helper functions for SSH MCP tools.
"""

import functools
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Maximum allowed path length for remote file operations
_MAX_PATH_LENGTH = 4096


def validate_remote_path(path: str) -> str | None:
    """Validate a remote file path for basic safety.

    This prevents null byte injection and excessively long paths.
    Note: Path traversal (../) is NOT blocked because these tools are
    designed to access arbitrary locations on remote servers.

    Returns None if the path is safe, or an error message if not.
    """
    if not path:
        return "Path cannot be empty"
    if len(path) > _MAX_PATH_LENGTH:
        return f"Path too long (max {_MAX_PATH_LENGTH} chars)"
    if "\x00" in path:
        return "Path contains null bytes"
    return None


def log_tool_usage(func: Any) -> Any:
    """Decorator to automatically log MCP tool usage."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        tool_name = func.__name__
        success = True

        try:
            result = await func(*args, **kwargs)
            return result
        except Exception:
            success = False
            raise
        finally:
            elapsed_ms = (time.time() - start_time) * 1000
            status = "OK" if success else "FAILED"
            logger.info(f"[{tool_name}] {status} ({elapsed_ms:.0f}ms)")

    return wrapper
