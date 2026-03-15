"""MCP SSH Multi - Entry points for stdio and HTTP transports."""

import asyncio
import logging
import os
import secrets
import signal
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Shutdown configuration
SHUTDOWN_TIMEOUT_SECONDS = 2.0

# Data directory for persisted state
_DATA_DIR = Path.home() / ".ssh-mcp"

# Global shutdown state
_shutdown_event: asyncio.Event | None = None
_shutdown_in_progress = False

# Lazy server creation
_server = None


def _create_server() -> Any:
    """Create server instance (deferred to avoid import during smoke test)."""
    from mcp_ssh_multi.server import SSHMCPServer

    return SSHMCPServer()


def _get_server() -> Any:
    """Get the server instance, creating if needed."""
    global _server
    if _server is None:
        _server = _create_server()
    return _server


def _get_mcp() -> Any:
    """Get the MCP instance, creating server if needed."""
    return _get_server().mcp


class _DeferredMCP:
    """Wrapper that defers MCP creation until actually accessed."""

    def __getattr__(self, name: str) -> Any:
        return getattr(_get_mcp(), name)

    def run(self, *args: Any, **kwargs: Any) -> Any:
        return _get_mcp().run(*args, **kwargs)


# For module-level access (e.g., fastmcp referencing mcp_ssh_multi.__main__:mcp)
mcp = _DeferredMCP()


_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _setup_logging(log_level_str: str, force: bool = False) -> None:
    """Configure root logger with consistent timestamp format."""
    logging.basicConfig(
        level=getattr(logging, log_level_str),
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt=_LOG_DATE_FORMAT,
        force=force,
    )


# ---------------------------------------------------------------------------
# Secret path management
# ---------------------------------------------------------------------------


def _generate_secret_path() -> str:
    """Generate a secure random path with 128-bit entropy.

    Format: /private_<22-char-urlsafe-token>
    Example: /private_zctpwlX7ZkIAr7oqdfLPxw
    """
    return "/private_" + secrets.token_urlsafe(16)


def _get_or_create_secret_path() -> str:
    """Get existing secret path or create a new one.

    Priority:
        1. MCP_SECRET_PATH env var (explicit user override)
        2. Persisted path in ~/.ssh-mcp/secret_path.txt (survives restarts)
        3. Auto-generate, persist, and return a new random path

    Returns:
        The secret path to use for the HTTP endpoint.
    """
    # 1. Explicit env var override
    env_path = os.getenv("MCP_SECRET_PATH", "").strip()
    if env_path:
        if not env_path.startswith("/"):
            env_path = "/" + env_path
        logger.info("Using secret path from MCP_SECRET_PATH env var")
        return env_path

    # 2. Check persisted file
    secret_file = _DATA_DIR / "secret_path.txt"
    if secret_file.exists():
        try:
            stored_path = secret_file.read_text().strip()
            if stored_path:
                logger.info("Using existing auto-generated secret path")
                return stored_path
        except Exception as e:
            logger.error(f"Failed to read stored secret path: {e}")

    # 3. Generate new secret path and persist
    new_path = _generate_secret_path()
    logger.info("Generated new secret path with 128-bit entropy")
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(new_path)
        logger.debug(f"Secret path persisted to {secret_file}")
    except Exception as e:
        logger.error(f"Failed to save secret path: {e}")
        # Return the path anyway - it will work for this session

    return new_path


def _print_secret_path_banner(port: int, path: str) -> None:
    """Print the secret path banner so the user can copy the URL."""
    divider = "=" * 72
    logger.info(divider)
    logger.info("")
    logger.info(f"  SSH MCP Server URL: http://<host>:{port}{path}")
    logger.info("")
    logger.info(f"     Secret Path: {path}")
    logger.info("")
    logger.info("  IMPORTANT: Copy this exact URL - the secret path is required!")
    logger.info(f"  This path is persisted to {_DATA_DIR / 'secret_path.txt'}")
    logger.info("")
    logger.info(divider)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------


async def _cleanup_resources() -> None:
    """Clean up all server resources gracefully."""
    global _server

    logger.info("Cleaning up server resources...")

    if _server is not None:
        try:
            await _server.close()
            logger.debug("Server closed")
        except Exception as e:
            logger.debug(f"Server cleanup: {e}")

    logger.info("Server resources cleaned up")


def _signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals (SIGTERM, SIGINT).

    Initiates graceful shutdown on first signal.
    On second signal, forces immediate exit.
    """
    global _shutdown_in_progress, _shutdown_event

    sig_name = signal.Signals(signum).name

    if _shutdown_in_progress:
        logger.warning(f"Received {sig_name} again, forcing exit")
        sys.exit(1)

    _shutdown_in_progress = True
    logger.info(f"Received {sig_name}, initiating graceful shutdown...")

    if _shutdown_event is not None:
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(_shutdown_event.set)
        except RuntimeError:
            sys.exit(0)


def _setup_signal_handlers() -> None:
    """Set up signal handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)


async def _run_with_graceful_shutdown() -> None:
    """Run the MCP server with graceful shutdown support."""
    global _shutdown_event

    _shutdown_event = asyncio.Event()

    server_task = asyncio.create_task(_get_mcp().run_async())
    shutdown_task = asyncio.create_task(_shutdown_event.wait())

    try:
        done, pending = await asyncio.wait(
            [server_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if shutdown_task in done:
            logger.info("Shutdown signal received, stopping server...")
            server_task.cancel()
            try:
                await asyncio.wait_for(server_task, timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except TimeoutError:
                logger.warning("Server did not stop within timeout")
            except asyncio.CancelledError:
                pass

    except asyncio.CancelledError:
        logger.info("Server task cancelled")
    finally:
        try:
            await asyncio.wait_for(
                _cleanup_resources(), timeout=SHUTDOWN_TIMEOUT_SECONDS
            )
        except TimeoutError:
            logger.warning("Resource cleanup timed out")

        for task in [server_task, shutdown_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def main() -> None:
    """Run server via CLI using FastMCP's stdio transport."""
    # Handle --version flag early
    if "--version" in sys.argv or "-V" in sys.argv:
        from importlib.metadata import version

        print(f"mcp-ssh-multi {version('mcp-ssh-multi')}")
        sys.exit(0)

    # Configure logging before server creation
    from mcp_ssh_multi.config import get_global_settings

    settings = get_global_settings()
    _setup_logging(settings.log_level)

    # Set up signal handlers
    _setup_signal_handlers()

    # Run with graceful shutdown support
    try:
        asyncio.run(_run_with_graceful_shutdown())
    except KeyboardInterrupt:
        logger.info("Interrupted, exiting")
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

    sys.exit(0)


async def _run_http_with_graceful_shutdown(
    host: str,
    port: int,
    path: str,
) -> None:
    """Run HTTP server with graceful shutdown support."""
    global _shutdown_event

    _shutdown_event = asyncio.Event()

    server_task = asyncio.create_task(
        _get_mcp().run_async(
            transport="streamable-http",
            host=host,
            port=port,
            path=path,
            stateless_http=True,
        )
    )

    shutdown_task = asyncio.create_task(_shutdown_event.wait())

    try:
        done, pending = await asyncio.wait(
            [server_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        if shutdown_task in done:
            logger.info("Shutdown signal received, stopping HTTP server...")
            server_task.cancel()
            try:
                await asyncio.wait_for(server_task, timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except TimeoutError:
                logger.warning("HTTP server did not stop within timeout")
            except asyncio.CancelledError:
                pass

    except asyncio.CancelledError:
        logger.info("HTTP server task cancelled")
    finally:
        try:
            await asyncio.wait_for(
                _cleanup_resources(), timeout=SHUTDOWN_TIMEOUT_SECONDS
            )
        except TimeoutError:
            logger.warning("Resource cleanup timed out")

        for task in [server_task, shutdown_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def main_web() -> None:
    """Run server over HTTP for web-capable MCP clients.

    The endpoint is protected with an auto-generated secret path.
    Override with MCP_SECRET_PATH env var if needed.

    Environment:
    - SSH_SERVERS_FILE (optional, default: ssh_servers.yaml)
    - MCP_PORT (optional, default: 8086)
    - MCP_SECRET_PATH (optional, overrides auto-generated path)
    """
    # Configure logging
    from mcp_ssh_multi.config import get_global_settings

    settings = get_global_settings()
    _setup_logging(settings.log_level)

    port = int(os.getenv("MCP_PORT", "8086"))
    path = _get_or_create_secret_path()

    # Display the URL so the user can copy it
    _print_secret_path_banner(port, path)

    # Set up signal handlers
    _setup_signal_handlers()

    # Run HTTP server
    try:
        asyncio.run(
            _run_http_with_graceful_shutdown(
                host="0.0.0.0",
                port=port,
                path=path,
            )
        )
    except KeyboardInterrupt:
        logger.info("Interrupted, exiting")
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"HTTP server error: {e}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
