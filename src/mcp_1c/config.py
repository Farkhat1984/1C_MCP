"""
Configuration module for MCP-1C server.

Uses Pydantic for validation.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """MCP Server configuration."""

    name: str = Field(default="mcp-1c", description="Server name")
    version: str = Field(default="0.1.0", description="Server version")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )


class CacheConfig(BaseModel):
    """SQLite cache configuration."""

    db_path: Path = Field(
        default=Path(".mcp_1c_cache.db"),
        description="Path to SQLite database file",
    )
    max_cache_age_hours: int = Field(
        default=24,
        description="Maximum age of cached entries in hours",
    )


class WatcherConfig(BaseModel):
    """File watcher configuration."""

    enabled: bool = Field(default=True, description="Enable file watching")
    debounce_ms: int = Field(
        default=500,
        description="Debounce time in milliseconds",
    )
    ignored_patterns: list[str] = Field(
        default_factory=lambda: ["*.bak", "*.tmp", "__pycache__"],
        description="Glob patterns to ignore",
    )


class AppConfig(BaseModel):
    """Main application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)

    # Configuration root path (set at runtime)
    config_root: Path | None = Field(
        default=None,
        description="Root path of 1C configuration",
    )


# Global configuration instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def set_config_root(path: Path) -> None:
    """Set the configuration root path."""
    config = get_config()
    config.config_root = path
