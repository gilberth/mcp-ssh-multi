"""MCP SSH Multi - Multi-server SSH access through MCP."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-ssh-multi")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
