"""
Composition engine: locate and parse DataCompositionSchema XML for reports.

Configurator export keeps the actual DCS payload in the unpacked
template folder ``Reports/<R>/Templates/<TplName>/Ext/Template.xml`` —
the flat ``<TplName>.xml`` next to it is just a metadata stub. EDT puts
both under ``src/``. Russian-language configurations name the main
template ``ОсновнаяСхемаКомпоновкиДанных`` rather than ``MainSchema``,
so when the caller doesn't specify a name we auto-detect the first
template whose stub declares ``<TemplateType>DataCompositionSchema``.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from mcp_1c.domain.composition import DataCompositionSchema
from mcp_1c.engines.composition.parser import CompositionParser
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.lru_cache import AsyncLRUCache

logger = get_logger(__name__)


_DCS_AUTO_HINTS: tuple[str | None, ...] = ("MainSchema", "", None)


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

    def _templates_roots(self, object_name: str) -> list[Path]:
        if self._config_path is None:
            return []
        root = self._config_path
        # Configurator export (real 8.3 layout) keeps the schema in a
        # subfolder: Templates/<SchemaName>/Ext/Template.xml. The bare
        # Templates/<SchemaName>.xml is the metadata wrapper, not the
        # schema itself, so it must be tried *after* the Ext path.
        return [
            root / "Reports" / object_name / "Templates",
            root / "src" / "Reports" / object_name / "Templates",
        ]

    def _candidate_paths(self, object_name: str, schema_name: str) -> list[Path]:
        if self._config_path is None:
            return []
        candidates: list[Path] = []
        for templates_root in self._templates_roots(object_name):
            candidates.extend([
                # Configurator/EDT unpacked: real DCS payload
                templates_root / schema_name / "Ext" / "Template.xml",
                templates_root / schema_name / f"{schema_name}.mdo",
                # Flat XML (rare — usually only the metadata stub lives here)
                templates_root / f"{schema_name}.xml",
            ])
        # Last-ditch fallback for unusual layouts
        candidates.append(
            self._config_path / "Reports" / object_name / "Forms" / f"{schema_name}.xml"
        )
        return candidates

    def _detect_main_schema_name(self, object_name: str) -> str | None:
        """Find the first template whose stub declares DataCompositionSchema.

        Looks at ``Templates/<name>.xml`` stubs (Configurator) and the
        unpacked sub-folders themselves. Returns ``None`` when nothing
        matches — caller should surface a clear error.
        """
        for templates_root in self._templates_roots(object_name):
            if not templates_root.exists():
                continue
            for stub in sorted(templates_root.glob("*.xml")):
                try:
                    if self._stub_is_dcs(stub):
                        return stub.stem
                except (ET.ParseError, OSError):
                    continue
            # Pure EDT layouts may not have stubs — assume any folder with
            # an Ext/Template.xml is a DCS. Pick the first.
            for child in sorted(templates_root.iterdir()):
                if child.is_dir() and (child / "Ext" / "Template.xml").exists():
                    return child.name
        return None

    @staticmethod
    def _stub_is_dcs(stub_path: Path) -> bool:
        text = stub_path.read_text(encoding="utf-8", errors="ignore")
        return "DataCompositionSchema" in text

    async def get_schema(
        self,
        object_name: str,
        schema_name: str | None = "MainSchema",
        object_type: str = "Report",
    ) -> DataCompositionSchema:
        if schema_name in _DCS_AUTO_HINTS:
            detected = self._detect_main_schema_name(object_name)
            if detected:
                logger.debug(f"Auto-detected DCS template for {object_name}: {detected}")
                schema_name = detected
            else:
                schema_name = "MainSchema"

        assert schema_name is not None
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
