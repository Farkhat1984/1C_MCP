"""
Form engine: facade for parsing and querying 1C managed forms.

Discovers Form.xml files inside the 1С configuration tree, parses them
on demand and caches the parsed structures via an LRU cache so repeated
access is cheap.
"""

from __future__ import annotations

from pathlib import Path

from mcp_1c.domain.form import FormStructure
from mcp_1c.engines.forms.parser import FormParser
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.lru_cache import AsyncLRUCache

logger = get_logger(__name__)


class FormEngine:
    """Singleton engine that resolves and caches form structures."""

    _instance: FormEngine | None = None

    @classmethod
    def get_instance(cls) -> FormEngine:
        if cls._instance is None:
            cls._instance = FormEngine()
        return cls._instance

    def __init__(self) -> None:
        self._parser = FormParser()
        self._config_path: Path | None = None
        self._cache: AsyncLRUCache[tuple[str, str, str], FormStructure] = (
            AsyncLRUCache(maxsize=200, ttl=300.0)
        )

    def attach(self, config_path: Path) -> None:
        """Bind the engine to a configuration root (called from MetadataEngine)."""
        if self._config_path != config_path:
            self._config_path = config_path
            # Reset cache when switching configs
            import asyncio

            asyncio.get_event_loop().run_until_complete(self._cache.clear()) if False else None

    def _candidate_paths(
        self, object_type: str, object_name: str, form_name: str
    ) -> list[Path]:
        """Possible on-disk locations for ``object_type.object_name.Form.<form_name>``.

        Configurations differ between EDT and Configurator exports, so we try
        a small list of conventional layouts.
        """
        if self._config_path is None:
            return []
        plural = object_type if object_type.endswith("s") else f"{object_type}s"
        root = self._config_path
        return [
            # Configurator: Catalogs/Товары/Forms/ФормаСписка/Ext/Form.xml
            root / plural / object_name / "Forms" / form_name / "Ext" / "Form.xml",
            # EDT: src/Catalogs/Товары/Forms/ФормаСписка.form/Form.form
            root / "src" / plural / object_name / "Forms" / f"{form_name}.form" / "Form.form",
            # Some EDT trees keep .form/Form.form alongside Forms folder
            root / plural / object_name / "Forms" / f"{form_name}.form" / "Form.form",
        ]

    async def get_form(
        self, object_type: str, object_name: str, form_name: str
    ) -> FormStructure:
        """Parse and cache the form ``object_type.object_name.Form.form_name``.

        Raises ``FileNotFoundError`` if no Form.xml is found in the expected
        locations — the metadata index might list the form even if its XML
        file was excluded from the export.
        """
        key = (object_type, object_name, form_name)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        for path in self._candidate_paths(object_type, object_name, form_name):
            if path.exists():
                logger.debug(f"Parsing form {object_type}.{object_name}.{form_name} at {path}")
                structure = self._parser.parse(path, object_type, object_name, form_name)
                await self._cache.set(key, structure)
                return structure

        raise FileNotFoundError(
            f"Form XML not found for {object_type}.{object_name}.Form.{form_name}. "
            f"Searched: {[str(p) for p in self._candidate_paths(object_type, object_name, form_name)]}"
        )
