"""
Extension engine: discover and parse 1С extensions in a configuration tree.

A typical layout puts extensions into ``<config>/Extensions/<Name>/`` —
each subfolder there is a self-contained extension with its own
Configuration.xml. The engine enumerates and caches them.
"""

from __future__ import annotations

from pathlib import Path

from mcp_1c.domain.extension import Extension
from mcp_1c.engines.extensions.parser import ExtensionParser
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.lru_cache import AsyncLRUCache

logger = get_logger(__name__)


class ExtensionEngine:
    """Singleton engine that locates extensions inside the main config tree."""

    _instance: "ExtensionEngine | None" = None

    @classmethod
    def get_instance(cls) -> "ExtensionEngine":
        if cls._instance is None:
            cls._instance = ExtensionEngine()
        return cls._instance

    def __init__(self) -> None:
        self._parser = ExtensionParser()
        self._main_path: Path | None = None
        self._cache: AsyncLRUCache[str, Extension] = AsyncLRUCache(
            maxsize=64, ttl=300.0
        )

    def attach(self, main_config_path: Path) -> None:
        self._main_path = main_config_path

    def _ext_root_candidates(self) -> list[Path]:
        if self._main_path is None:
            return []
        return [
            self._main_path / "Extensions",
            self._main_path.parent / "Extensions",
            self._main_path / "ConfigurationExtensions",
        ]

    async def list_extensions(self) -> list[str]:
        """Return names of extensions discovered next to the main config."""
        names: list[str] = []
        for root in self._ext_root_candidates():
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if child.is_dir() and (child / "Configuration.xml").exists():
                    names.append(child.name)
            if names:
                break
        return names

    async def get(self, extension_name: str) -> Extension:
        cached = await self._cache.get(extension_name)
        if cached is not None:
            return cached
        for root in self._ext_root_candidates():
            ext_path = root / extension_name
            if (ext_path / "Configuration.xml").exists():
                ext = self._parser.parse(ext_path)
                await self._cache.set(extension_name, ext)
                return ext
        raise FileNotFoundError(
            f"Extension {extension_name} not found in: "
            f"{[str(p) for p in self._ext_root_candidates()]}"
        )
