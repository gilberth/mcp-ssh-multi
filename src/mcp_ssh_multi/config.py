"""
Configuration management for SSH MCP Server.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

project_root = Path(__file__).parent.parent.parent

# Support for different environment files via SSH_MCP_ENV_FILE
env_file = os.getenv("SSH_MCP_ENV_FILE", ".env")
env_path = project_root / env_file

# Load the specified environment file
if env_path.exists():
    load_dotenv(env_path)
else:
    default_env_path = project_root / ".env"
    if default_env_path.exists():
        load_dotenv(default_env_path)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # SSH servers configuration file path
    ssh_servers_file: str = Field(
        "ssh_servers.yaml", alias="SSH_SERVERS_FILE"
    )

    # Server configuration
    timeout: int = Field(30, alias="SSH_TIMEOUT")
    max_retries: int = Field(3, alias="SSH_MAX_RETRIES")

    # Development/Debug configuration
    debug: bool = Field(False, alias="DEBUG")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # MCP Server configuration
    mcp_server_name: str = Field("ssh-mcp", alias="MCP_SERVER_NAME")
    mcp_server_version: str = Field("0.1.0", alias="MCP_SERVER_VERSION")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("ssh_servers_file")
    @classmethod
    def validate_servers_file(cls, v: str) -> str:
        """Resolve servers file path."""
        path = Path(v)
        if not path.is_absolute():
            # Resolve relative to project root
            path = project_root / v
        return str(path)

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow"
    )


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()  # type: ignore[call-arg]


# Global settings instance
_settings: Settings | None = None


def get_global_settings() -> Settings:
    """Get global settings instance (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings
