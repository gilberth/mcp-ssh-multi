"""
Async SSH client manager for multi-server connections.

Manages SSH connections to multiple servers defined in a YAML configuration file.
Uses asyncssh for non-blocking SSH operations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncssh
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ServerConfig:
    """Configuration for a single SSH server."""

    name: str
    host: str
    port: int = 22
    username: str = "root"
    password: str | None = None
    key_file: str | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> ServerConfig:
        """Create ServerConfig from a dictionary."""
        return cls(
            name=name,
            host=data["host"],
            port=data.get("port", 22),
            username=data.get("username", "root"),
            password=data.get("password"),
            key_file=data.get("key_file"),
            description=data.get("description", ""),
        )


@dataclass
class SSHConnectionPool:
    """Manages a pool of SSH connections to configured servers."""

    servers: dict[str, ServerConfig] = field(default_factory=dict)
    _connections: dict[str, asyncssh.SSHClientConnection] = field(
        default_factory=dict, repr=False
    )
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict, repr=False)

    def _get_server_lock(self, server_name: str) -> asyncio.Lock:
        """Get or create a lock for a specific server."""
        if server_name not in self._locks:
            self._locks[server_name] = asyncio.Lock()
        return self._locks[server_name]

    @classmethod
    def from_yaml(cls, config_path: str) -> SSHConnectionPool:
        """Load server configurations from a YAML file.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            SSHConnectionPool with loaded server configurations.

        Raises:
            FileNotFoundError: If the config file does not exist.
            ValueError: If the config file is invalid.
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"SSH servers config not found: {config_path}")
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f)

        if not raw or "servers" not in raw:
            logger.warning(f"No 'servers' key in {config_path}")
            return cls()

        servers: dict[str, ServerConfig] = {}
        for name, data in raw["servers"].items():
            try:
                servers[name] = ServerConfig.from_dict(name, data)
                logger.debug(f"Loaded server config: {name} ({data['host']})")
            except (KeyError, TypeError) as e:
                logger.error(f"Invalid server config for '{name}': {e}")

        logger.info(f"Loaded {len(servers)} server configurations from {config_path}")
        return cls(servers=servers)

    def list_servers(self) -> list[dict[str, Any]]:
        """List all configured servers with connection status.

        Returns:
            List of server info dictionaries.
        """
        result = []
        for name, config in self.servers.items():
            connected = name in self._connections and not self._connections[name].is_closed()
            result.append(
                {
                    "name": name,
                    "host": config.host,
                    "port": config.port,
                    "username": config.username,
                    "description": config.description,
                    "connected": connected,
                }
            )
        return result

    def get_server_config(self, server_name: str) -> ServerConfig | None:
        """Get configuration for a specific server."""
        return self.servers.get(server_name)

    async def connect(self, server_name: str) -> asyncssh.SSHClientConnection:
        """Connect to a server, reusing existing connections when possible.

        Args:
            server_name: Name of the server to connect to.

        Returns:
            An active SSH connection.

        Raises:
            ValueError: If the server is not configured.
            asyncssh.Error: If the connection fails.
        """
        lock = self._get_server_lock(server_name)
        async with lock:
            # Check for existing valid connection
            if server_name in self._connections:
                conn = self._connections[server_name]
                if not conn.is_closed():
                    return conn
                # Connection was closed, remove it
                del self._connections[server_name]
                logger.debug(f"Removed stale connection to {server_name}")

            config = self.servers.get(server_name)
            if config is None:
                raise ValueError(f"Server '{server_name}' not found in configuration")

            # Build connection options
            connect_kwargs: dict[str, Any] = {
                "host": config.host,
                "port": config.port,
                "username": config.username,
                # SECURITY NOTE: known_hosts=None disables host key verification.
                # This makes connections vulnerable to MITM attacks. In production,
                # consider setting known_hosts to a file path or using
                # asyncssh.read_known_hosts() for proper host key verification.
                "known_hosts": None,
            }

            if config.key_file:
                key_path = Path(config.key_file).expanduser()
                if key_path.exists():
                    connect_kwargs["client_keys"] = [str(key_path)]
                else:
                    logger.warning(
                        f"Key file not found: {config.key_file}, "
                        f"falling back to password auth"
                    )

            if config.password:
                connect_kwargs["password"] = config.password

            logger.info(f"Connecting to {server_name} ({config.host}:{config.port})")
            conn = await asyncssh.connect(**connect_kwargs)
            self._connections[server_name] = conn
            logger.info(f"Connected to {server_name}")
            return conn

    async def disconnect(self, server_name: str) -> bool:
        """Disconnect from a specific server.

        Args:
            server_name: Name of the server to disconnect from.

        Returns:
            True if disconnected, False if not connected.
        """
        lock = self._get_server_lock(server_name)
        async with lock:
            conn = self._connections.pop(server_name, None)
            if conn is not None:
                conn.close()
                logger.info(f"Disconnected from {server_name}")
                return True
            return False

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for name in list(self._connections.keys()):
            await self.disconnect(name)
        logger.info("Disconnected from all servers")

    async def execute(
        self,
        server_name: str,
        command: str,
        timeout: int = 30,
        _retried: bool = False,
    ) -> dict[str, Any]:
        """Execute a command on a remote server.

        Retries once on connection failure (stale connection).

        Args:
            server_name: Name of the server to execute on.
            command: Command string to execute.
            timeout: Command timeout in seconds.

        Returns:
            Dictionary with stdout, stderr, and exit_code.
        """
        conn = await self.connect(server_name)

        try:
            result = await asyncio.wait_for(
                conn.run(command, check=False),
                timeout=timeout,
            )
        except TimeoutError as err:
            raise TimeoutError(
                f"Command timed out after {timeout}s on {server_name}: {command}"
            ) from err
        except (asyncssh.ConnectionLost, asyncssh.DisconnectError, OSError) as err:
            if _retried:
                raise
            # Remove stale connection and retry once
            logger.warning(f"Connection lost to {server_name}, retrying: {err}")
            async with self._get_server_lock(server_name):
                self._connections.pop(server_name, None)
            return await self.execute(
                server_name, command, timeout=timeout, _retried=True
            )

        return {
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "exit_code": result.exit_status or 0,
        }

    async def upload_file(
        self,
        server_name: str,
        local_path: str,
        remote_path: str,
    ) -> dict[str, Any]:
        """Upload a file to a remote server via SFTP.

        Args:
            server_name: Target server name.
            local_path: Local file path.
            remote_path: Remote destination path.

        Returns:
            Dictionary with transfer result.
        """
        local = Path(local_path)
        if not local.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        conn = await self.connect(server_name)

        async with conn.start_sftp_client() as sftp:
            await sftp.put(local_path, remote_path)

        file_size = local.stat().st_size
        logger.info(
            f"Uploaded {local_path} -> {server_name}:{remote_path} ({file_size} bytes)"
        )

        return {
            "local_path": local_path,
            "remote_path": remote_path,
            "size_bytes": file_size,
        }

    async def download_file(
        self,
        server_name: str,
        remote_path: str,
        local_path: str,
    ) -> dict[str, Any]:
        """Download a file from a remote server via SFTP.

        Args:
            server_name: Source server name.
            remote_path: Remote file path.
            local_path: Local destination path.

        Returns:
            Dictionary with transfer result.
        """
        conn = await self.connect(server_name)

        # Ensure local directory exists
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)

        async with conn.start_sftp_client() as sftp:
            await sftp.get(remote_path, local_path)

        file_size = local.stat().st_size
        logger.info(
            f"Downloaded {server_name}:{remote_path} -> {local_path} ({file_size} bytes)"
        )

        return {
            "remote_path": remote_path,
            "local_path": local_path,
            "size_bytes": file_size,
        }

    async def read_file(
        self,
        server_name: str,
        remote_path: str,
        max_size: int = 1_000_000,
    ) -> str:
        """Read a file from a remote server.

        Args:
            server_name: Source server name.
            remote_path: Remote file path.
            max_size: Maximum file size to read in bytes (default 1MB).

        Returns:
            File contents as string.
        """
        conn = await self.connect(server_name)

        async with conn.start_sftp_client() as sftp:
            attrs = await sftp.stat(remote_path)
            if attrs.size and attrs.size > max_size:
                raise ValueError(
                    f"File too large ({attrs.size} bytes, max {max_size}). "
                    f"Use ssh_download to transfer large files."
                )
            async with sftp.open(remote_path, "r") as f:
                content = await f.read()

        return content if isinstance(content, str) else content.decode("utf-8", errors="replace")

    async def write_file(
        self,
        server_name: str,
        remote_path: str,
        content: str,
    ) -> dict[str, Any]:
        """Write content to a file on a remote server.

        Args:
            server_name: Target server name.
            remote_path: Remote file path.
            content: Content to write.

        Returns:
            Dictionary with write result.
        """
        conn = await self.connect(server_name)

        async with conn.start_sftp_client() as sftp:
            async with sftp.open(remote_path, "w") as f:
                await f.write(content)

        size = len(content.encode("utf-8"))
        logger.info(f"Wrote {size} bytes to {server_name}:{remote_path}")

        return {
            "remote_path": remote_path,
            "size_bytes": size,
        }

    async def file_exists(
        self,
        server_name: str,
        remote_path: str,
    ) -> dict[str, Any]:
        """Check if a file or directory exists on a remote server.

        Args:
            server_name: Server name.
            remote_path: Remote path to check.

        Returns:
            Dictionary with exists status and file info.
        """
        conn = await self.connect(server_name)

        async with conn.start_sftp_client() as sftp:
            try:
                attrs = await sftp.stat(remote_path)
                return {
                    "exists": True,
                    "path": remote_path,
                    "is_dir": attrs.type == asyncssh.FILEXFER_TYPE_DIRECTORY,
                    "size": attrs.size,
                    "permissions": oct(attrs.permissions) if attrs.permissions else None,
                }
            except (asyncssh.SFTPNoSuchFile, asyncssh.SFTPError):
                return {"exists": False, "path": remote_path}

    async def list_dir(
        self,
        server_name: str,
        remote_path: str = ".",
        limit: int = 0,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List contents of a remote directory with optional pagination.

        Args:
            server_name: Server name.
            remote_path: Remote directory path (default: current dir).
            limit: Max entries to return (0 = all).
            offset: Number of entries to skip.

        Returns:
            Dictionary with entries list, total count, and has_more flag.
        """
        conn = await self.connect(server_name)

        all_entries: list[dict[str, Any]] = []
        async with conn.start_sftp_client() as sftp:
            async for entry in sftp.scandir(remote_path):
                attrs = entry.attrs
                all_entries.append(
                    {
                        "name": entry.filename,
                        "is_dir": attrs.type == asyncssh.FILEXFER_TYPE_DIRECTORY
                        if attrs.type is not None
                        else None,
                        "size": attrs.size,
                        "permissions": oct(attrs.permissions) if attrs.permissions else None,
                    }
                )

        total = len(all_entries)

        if offset:
            all_entries = all_entries[offset:]

        has_more = False
        if limit and limit > 0:
            has_more = len(all_entries) > limit
            all_entries = all_entries[:limit]

        return {
            "entries": all_entries,
            "total": total,
            "has_more": has_more,
        }
