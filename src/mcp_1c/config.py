"""
Configuration module for MCP-1C server.

Uses Pydantic for validation.
"""

import os
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
    max_search_files: int = Field(
        default=100, description="Max files to scan in code search"
    )
    cache_ttl_seconds: int = Field(
        default=300, description="Default TTL for in-memory caches (seconds)"
    )
    max_concurrent_parse: int = Field(
        default=10, description="Max concurrent metadata parse operations"
    )
    parse_workers: int = Field(
        default=4, description="Thread pool size for CPU-bound parsing"
    )
    mxl_cache_size: int = Field(
        default=100, description="Max entries in MXL template cache"
    )

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Create ServerConfig with values from environment variables.

        Environment variables (all optional, fall back to defaults):
            MCP_LOG_LEVEL, MCP_MAX_SEARCH_FILES, MCP_CACHE_TTL,
            MCP_MAX_CONCURRENT_PARSE, MCP_PARSE_WORKERS, MCP_MXL_CACHE_SIZE
        """
        return cls(
            log_level=os.environ.get("MCP_LOG_LEVEL", "INFO"),  # type: ignore[arg-type]
            max_search_files=int(os.environ.get("MCP_MAX_SEARCH_FILES", "100")),
            cache_ttl_seconds=int(os.environ.get("MCP_CACHE_TTL", "300")),
            max_concurrent_parse=int(os.environ.get("MCP_MAX_CONCURRENT_PARSE", "10")),
            parse_workers=int(os.environ.get("MCP_PARSE_WORKERS", "4")),
            mxl_cache_size=int(os.environ.get("MCP_MXL_CACHE_SIZE", "100")),
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


class EmbeddingConfig(BaseModel):
    """Configuration for embeddings engine."""

    api_url: str = Field(
        default="https://api.deepinfra.com/v1/openai/embeddings",
        description="Embeddings API endpoint URL",
    )
    api_key: str = Field(
        default="",
        description="API key for embeddings service (from MCP_EMBEDDING_API_KEY env var)",
    )
    model: str = Field(
        default="Qwen/Qwen3-Embedding-8B",
        description="Embedding model name",
    )
    dimension: int = Field(
        default=4096,
        description="Embedding vector dimension",
    )
    batch_size: int = Field(
        default=32,
        description="Number of texts per single API call",
    )
    pipeline_batch_size: int = Field(
        default=32,
        description="Number of documents to accumulate before embedding",
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries on API failure",
    )
    timeout: float = Field(
        default=120.0,
        description="API request timeout in seconds (larger batches need more time)",
    )
    chunk_size: int = Field(
        default=2000,
        description="Maximum characters per module chunk for embedding",
    )
    chunk_overlap: int = Field(
        default=300,
        description="Character overlap between consecutive chunks",
    )
    max_procedure_chars: int = Field(
        default=4000,
        description="Maximum characters per procedure chunk for embedding",
    )
    max_concurrent: int = Field(
        default=4,
        description="Maximum concurrent API requests",
    )

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Create EmbeddingConfig from environment variables.

        Environment variables (all optional, fall back to defaults):
            MCP_EMBEDDING_API_KEY, MCP_EMBEDDING_API_URL, MCP_EMBEDDING_MODEL
        """
        return cls(
            api_key=os.environ.get("MCP_EMBEDDING_API_KEY", "") or os.environ.get("DEEPINFRA_API_KEY", ""),
            api_url=os.environ.get(
                "MCP_EMBEDDING_API_URL",
                "https://api.deepinfra.com/v1/openai/embeddings",
            ),
            model=os.environ.get("MCP_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B"),
        )


class AppConfig(BaseModel):
    """Main application configuration."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)

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
