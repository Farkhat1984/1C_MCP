"""
Composition tools — query 1C report DataCompositionSchema (СКД).
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.domain.composition import DataCompositionSchema
from mcp_1c.engines.composition.engine import CompositionEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError


class _CompositionToolBase(BaseTool):
    def __init__(
        self, engine: CompositionEngine, metadata_engine: MetadataEngine
    ) -> None:
        super().__init__()
        self._engine = engine
        self._metadata = metadata_engine

    async def _resolve(self, args: dict[str, Any]) -> DataCompositionSchema:
        name = args.get("name") or args.get("report") or ""
        schema_name = args.get("schema") or "MainSchema"
        if not name:
            raise ToolError("Report name is required (`name`)", code="MISSING_ARGUMENT")
        config_path = self._metadata.config_path
        if config_path is not None:
            self._engine._config_path = config_path  # type: ignore[attr-defined]
        try:
            return await self._engine.get_schema(name, schema_name)
        except FileNotFoundError as exc:
            raise ToolError(str(exc), code="SCHEMA_NOT_FOUND")


class CompositionGetTool(_CompositionToolBase):
    name: ClassVar[str] = "composition-get"
    description: ClassVar[str] = (
        "Получить структуру схемы компоновки данных (СКД) отчёта 1С: наборы данных, "
        "поля, параметры, ресурсы, варианты настроек."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Имя отчёта"},
            "schema": {
                "type": "string",
                "description": "Имя схемы (по умолчанию MainSchema)",
                "default": "MainSchema",
            },
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        return {
            "object_type": s.object_type,
            "object_name": s.object_name,
            "schema_name": s.schema_name,
            "title": s.title,
            "data_sets": [
                {
                    "name": ds.name,
                    "kind": ds.kind.value if hasattr(ds.kind, "value") else str(ds.kind),
                    "field_count": len(ds.fields),
                    "has_query": bool(ds.query_text),
                }
                for ds in s.data_sets
            ],
            "parameter_count": len(s.parameters),
            "resource_count": len(s.resources),
            "setting_variants": [v.name for v in s.settings],
        }


class CompositionFieldsTool(_CompositionToolBase):
    name: ClassVar[str] = "composition-fields"
    description: ClassVar[str] = (
        "Список полей всех наборов данных схемы компоновки отчёта 1С."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "schema": {"type": "string", "default": "MainSchema"},
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        out: list[dict[str, str]] = []
        for ds in s.data_sets:
            for f in ds.fields:
                out.append(
                    {
                        "data_set": ds.name,
                        "name": f.name,
                        "title": f.title,
                        "type": f.type,
                        "role": f.role,
                    }
                )
        for f in s.fields:  # calculated/total fields at schema level
            out.append(
                {
                    "data_set": "(schema)",
                    "name": f.name,
                    "title": f.title,
                    "type": f.type,
                    "role": "Calculated",
                }
            )
        return {"fields": out, "count": len(out)}


class CompositionDatasetsTool(_CompositionToolBase):
    name: ClassVar[str] = "composition-datasets"
    description: ClassVar[str] = "Наборы данных схемы компоновки (с текстами запросов)."
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "schema": {"type": "string", "default": "MainSchema"},
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        return {
            "data_sets": [
                {
                    "name": ds.name,
                    "kind": ds.kind.value if hasattr(ds.kind, "value") else str(ds.kind),
                    "query_text": ds.query_text,
                    "fields": [
                        {"name": f.name, "type": f.type, "title": f.title}
                        for f in ds.fields
                    ],
                }
                for ds in s.data_sets
            ]
        }


class CompositionSettingsTool(_CompositionToolBase):
    name: ClassVar[str] = "composition-settings"
    description: ClassVar[str] = "Варианты настроек (presets) схемы компоновки отчёта."
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "schema": {"type": "string", "default": "MainSchema"},
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        return {
            "variants": [
                {
                    "name": v.name,
                    "title": v.title,
                    "selection": v.selection,
                    "order": v.order,
                    "filters": v.filters,
                    "structure": v.structure,
                }
                for v in s.settings
            ]
        }
