"""
Reusable helper functions for SSH MCP tools.
"""

import functools
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


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
