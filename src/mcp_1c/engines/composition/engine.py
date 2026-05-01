"""
Composition engine: locate and parse DataCompositionSchema XML for reports.

Convention: a 1С report's main schema lives at
``Reports/<ReportName>/Templates/MainSchema.xml`` (Configurator) or
``src/Reports/<ReportName>/Templates/MainSchema.xml`` (EDT). Some
reports use a non-standard schema name — the engine accepts an explicit
``schema_name`` to disambiguate.
"""

from __future__ import annotations

from pathlib import Path

from mcp_1c.domain.composition import DataCompositionSchema
from mcp_1c.engines.composition.parser import CompositionParser
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.lru_cache import AsyncLRUCache

logger = get_logger(__name__)


class CompositionEngine:
    """Singleton engine that resolves and caches DataCompositionSchema parses."""

    _instance: CompositionEngine | None = None

    @classmethod
    def get_instance(cls) -> CompositionEngine:
        if cls._instance is None:
            cls._instance = CompositionEngine()
        return cls._instance

    def __init__(self) -> None:
        self._parser = CompositionParser()
        self._config_path: Path | None = None
        self._cache: AsyncLRUCache[tuple[str, str, str], DataCompositionSchema] = (
            AsyncLRUCache(maxsize=200, ttl=300.0)
        )

    def _candidate_paths(self, object_name: str, schema_name: str) -> list[Path]:
        if self._config_path is None:
            return []
        root = self._config_path
        return [
            root / "Reports" / object_name / "Templates" / f"{schema_name}.xml",
            root / "src" / "Reports" / object_name / "Templates" / f"{schema_name}.xml",
            root / "Reports" / object_name / "Forms" / f"{schema_name}.xml",  # fallback
        ]

    async def get_schema(
        self,
        object_name: str,
        schema_name: str = "MainSchema",
        object_type: str = "Report",
    ) -> DataCompositionSchema:
        key = (object_type, object_name, schema_name)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached
        for path in self._candidate_paths(object_name, schema_name):
            if path.exists():
                logger.debug(f"Parsing composition schema {object_name}.{schema_name} at {path}")
                schema = self._parser.parse(path, object_type, object_name, schema_name)
                await self._cache.set(key, schema)
                return schema
        raise FileNotFoundError(
            f"DataCompositionSchema not found for {object_type}.{object_name}.{schema_name}"
        )
