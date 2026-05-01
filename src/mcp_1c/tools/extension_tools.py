"""
Extension tools — surface 1С configuration extensions to MCP clients.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.engines.extensions.engine import ExtensionEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError


class _ExtensionToolBase(BaseTool):
    def __init__(
        self, engine: ExtensionEngine, metadata_engine: MetadataEngine
    ) -> None:
        super().__init__()
        self._engine = engine
        self._metadata = metadata_engine

    def _bind(self) -> None:
        config = self._metadata.config_path
        if config is not None:
            self._engine.attach(config)


class ExtensionListTool(_ExtensionToolBase):
    name: ClassVar[str] = "extension-list"
    description: ClassVar[str] = (
        "Список расширений конфигурации, обнаруженных рядом с основной (папка Extensions/)."
    )
    input_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._bind()
        names = await self._engine.list_extensions()
        return {"extensions": names, "count": len(names)}


class ExtensionObjectsTool(_ExtensionToolBase):
    name: ClassVar[str] = "extension-objects"
    description: ClassVar[str] = (
        "Объекты расширения с разделением на собственные/заимствованные/заменённые."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Имя расширения"}
        },
        "required": ["name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._bind()
        name = arguments.get("name", "")
        if not name:
            raise ToolError("name is required", code="MISSING_ARGUMENT")
        try:
            ext = await self._engine.get(name)
        except FileNotFoundError as exc:
            raise ToolError(str(exc), code="EXTENSION_NOT_FOUND")
        return {
            "extension": ext.name,
            "purpose": ext.purpose.value if hasattr(ext.purpose, "value") else str(ext.purpose),
            "target": ext.target_configuration,
            "namespace": ext.namespace,
            "objects": [
                {
                    "metadata_type": o.metadata_type,
                    "name": o.name,
                    "mode": o.mode.value if hasattr(o.mode, "value") else str(o.mode),
                    "parent": o.parent,
                }
                for o in ext.objects
            ],
            "counts": {
                "own": len(ext.own_objects),
                "adopted": len(ext.adopted_objects),
                "replaced": len(ext.replaced_objects),
            },
        }


class ExtensionImpactTool(_ExtensionToolBase):
    """Estimate which extensions touch a given main-config object."""

    name: ClassVar[str] = "extension-impact"
    description: ClassVar[str] = (
        "Какие расширения затрагивают объект основной конфигурации (заимствуют или заменяют его)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Тип объекта (Catalog, Document, ...)"},
            "name": {"type": "string", "description": "Имя объекта"},
        },
        "required": ["type", "name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._bind()
        target_type = arguments.get("type", "")
        target_name = arguments.get("name", "")
        if not (target_type and target_name):
            raise ToolError("type and name are required", code="MISSING_ARGUMENT")

        names = await self._engine.list_extensions()
        affecting: list[dict[str, str]] = []
        for ext_name in names:
            try:
                ext = await self._engine.get(ext_name)
            except FileNotFoundError:
                continue
            for obj in ext.objects:
                if obj.metadata_type == target_type and obj.name == target_name:
                    affecting.append(
                        {
                            "extension": ext.name,
                            "mode": obj.mode.value if hasattr(obj.mode, "value") else str(obj.mode),
                            "purpose": ext.purpose.value if hasattr(ext.purpose, "value") else str(ext.purpose),
                        }
                    )
        return {
            "target": f"{target_type}.{target_name}",
            "extensions": affecting,
            "count": len(affecting),
        }
