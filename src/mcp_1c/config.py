"""
Configuration module for MCP-1C server.

Uses Pydantic for validation.
"""

import hashlib
import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _default_cache_root() -> Path:
    """Pick a per-user cache root suitable for the current OS.

    Honors XDG_CACHE_HOME on Linux/Mac, %LOCALAPPDATA% on Windows.
    Override via MCP_CACHE_DIR.
    """
    override = os.environ.get("MCP_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "mcp-1c"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "mcp-1c"


def _workspace_id(config_path: Path, overlays: list = None) -> str:
    """Stable per-config identifier — first 16 hex chars of sha256(canonical inputs).

    Hash inputs:
    1. Absolute resolved path of the main config root.
    2. Sorted ``(name, abs_path)`` pairs for each overlay (sorted by name
       so the order in which overlays were declared doesn't affect the id).

    Why include overlays: the cache stores a *combined* metadata index;
    running with overlay set A and then with set B against the same
    main config must produce a different cache directory, otherwise
    objects from A leak into the B-only graph.
    """
    parts = [str(config_path.resolve())]
    for overlay in sorted(overlays or [], key=lambda o: o.name):
        parts.append(f"{overlay.name}={Path(overlay.path).resolve()}")
    canonical = "\n".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class OverlayRoot(BaseModel):
    """A developer-supplied overlay tree that contributes own modules.

    Сценарий из 1С-практики: команда держит библиотеку common modules
    в отдельной папке вне типовой; при индексации эти модули должны
    попадать в общий граф знаний наравне с типовой. Каждый ``OverlayRoot``
    несёт ярлык (``name``), путь и приоритет — приоритет используется
    лишь как stable ordering при индексации (выше приоритет — индексируется
    раньше); конфликтов имён нет, потому что узлы помечаются ``source``-
    меткой и live в собственном неймспейсе.

    Phase F3 не разрешает overlay-у заменять объекты типовой. Это работа
    расширений (.cfe), которые уже моделируются как ``ExtensionObject``
    с edge'ами ``EXTENSION_REPLACES``.
    """

    name: str = Field(
        ..., description="Stable identifier, used as 'overlay:<name>' label"
    )
    path: Path = Field(..., description="Filesystem root of the overlay tree")
    priority: int = Field(
        default=100,
        description="Indexing order; higher numbers indexed earlier",
    )

    @property
    def source_label(self) -> str:
        """Format used as ``MetadataObject.source`` for objects from this root."""
        return f"overlay:{self.name}"


class WorkspacePaths(BaseModel):
    """Filesystem layout for one indexed 1C configuration."""

    workspace_id: str
    root: Path
    cache_db: Path
    embeddings_db: Path
    overlays: list[OverlayRoot] = Field(
        default_factory=list,
        description=(
            "Developer-supplied overlay roots indexed alongside the main "
            "config. Empty by default — single-root mode is the historical "
            "behaviour and stays the default."
        ),
    )

    @classmethod
    def for_config(
        cls,
        config_path: Path,
        *,
        overlays: list[OverlayRoot] | None = None,
    ) -> "WorkspacePaths":
        """Pick paths for ``config_path``.

        Backward compat: if legacy DBs exist directly in ``config_path``
        (`<config>/.mcp_1c_cache.db` or `.mcp_1c_embeddings.db`), reuse
        them instead of starting fresh in the cache root.

        Args:
            config_path: Main config root.
            overlays: Optional developer-supplied trees indexed in addition.
                Their hash contributes to ``workspace_id`` so changing the
                overlay set produces a fresh cache directory — that prevents
                stale cross-pollination when a team rotates which overlays
                they carry.
        """
        legacy_cache = config_path / ".mcp_1c_cache.db"
        legacy_emb = config_path / ".mcp_1c_embeddings.db"

        wid = _workspace_id(config_path, overlays or [])
        root = _default_cache_root() / wid
        cache_db = legacy_cache if legacy_cache.exists() else root / "cache.db"
        emb_db = legacy_emb if legacy_emb.exists() else root / "embeddings.db"
        return cls(
            workspace_id=wid,
            root=root,
            cache_db=cache_db,
            embeddings_db=emb_db,
            overlays=list(overlays or []),
        )


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

    backend: Literal["api", "local"] = Field(
        default="api",
        description=(
            "Embedding backend: 'api' for OpenAI-compatible HTTP service "
            "(DeepInfra/Qwen3-Embedding-8B by default), 'local' for "
            "sentence-transformers running in-process. Set via MCP_EMBEDDING_BACKEND."
        ),
    )
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
            MCP_EMBEDDING_BACKEND  — "api" (default) or "local"
            MCP_EMBEDDING_API_KEY, MCP_EMBEDDING_API_URL, MCP_EMBEDDING_MODEL
            MCP_EMBEDDING_DIMENSION

        Auto-fallback: if backend is unset and no API key is available,
        choose ``local`` so the user gets working embeddings without signup.
        """
        api_key = os.environ.get("MCP_EMBEDDING_API_KEY", "") or os.environ.get(
            "DEEPINFRA_API_KEY", ""
        )
        backend_env = os.environ.get("MCP_EMBEDDING_BACKEND")
        if backend_env in ("api", "local"):
            backend: Literal["api", "local"] = backend_env  # type: ignore[assignment]
        else:
            backend = "api" if api_key else "local"

        if backend == "local":
            default_model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            default_dim = 384
        else:
            default_model = "Qwen/Qwen3-Embedding-8B"
            default_dim = 4096

        return cls(
            backend=backend,
            api_key=api_key,
            api_url=os.environ.get(
                "MCP_EMBEDDING_API_URL",
                "https://api.deepinfra.com/v1/openai/embeddings",
            ),
            model=os.environ.get("MCP_EMBEDDING_MODEL", default_model),
            dimension=int(
                os.environ.get("MCP_EMBEDDING_DIMENSION", str(default_dim))
            ),
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
    overlay_roots: list[OverlayRoot] = Field(
        default_factory=list,
        description=(
            "Developer-supplied overlays indexed alongside the main config "
            "(Phase F3). See OverlayRoot for semantics."
        ),
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


def set_overlay_roots(overlays: list[OverlayRoot]) -> None:
    """Replace the configured overlay set on the global config.

    Validates that overlay paths exist and that names are unique —
    we want a hard fail at configure-time, not a confusing partial
    index later. Lists are stored as-is; ordering is preserved for
    round-trip equality but doesn't affect indexing semantics.
    """
    seen: set[str] = set()
    for overlay in overlays:
        if overlay.name in seen:
            raise ValueError(
                f"Duplicate overlay name {overlay.name!r}; names must be unique"
            )
        seen.add(overlay.name)
        if not overlay.path.exists() or not overlay.path.is_dir():
            raise ValueError(
                f"Overlay path does not exist or is not a directory: "
                f"{overlay.path}"
            )
    config = get_config()
    config.overlay_roots = list(overlays)
