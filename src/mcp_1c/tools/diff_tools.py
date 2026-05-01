"""
Diff and test-data tools — Phase 9 premium tools.

These tools depend only on already-indexed metadata. They reuse the
existing MetadataEngine cache so they're cheap to invoke.
"""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.tools.base import BaseTool, ToolError


class ConfigurationDiffTool(BaseTool):
    """Diff two configuration trees by re-parsing their Configuration.xml.

    Produces a per-type added/removed/common list. Detailed object-level
    diff (attributes / forms / modules) is left for a follow-up.
    """

    name: ClassVar[str] = "diff-configurations"
    description: ClassVar[str] = (
        "Сравнить две конфигурации по корневым путям. Возвращает per-type "
        "списки {added, removed, common} объектов."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "left": {"type": "string", "description": "Путь к корню первой конфигурации"},
            "right": {"type": "string", "description": "Путь к корню второй конфигурации"},
        },
        "required": ["left", "right"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        left = Path(arguments.get("left", ""))
        right = Path(arguments.get("right", ""))
        if not left or not right:
            raise ToolError("left and right paths are required", code="MISSING_ARGUMENT")

        parser = XmlParser()
        try:
            left_objs = parser.parse_configuration(left)
            right_objs = parser.parse_configuration(right)
        except FileNotFoundError as exc:
            raise ToolError(str(exc), code="CONFIG_NOT_FOUND")

        all_types = sorted(set(left_objs) | set(right_objs))
        per_type: dict[str, dict[str, list[str]]] = {}
        totals = {"added": 0, "removed": 0, "common": 0}
        for t in all_types:
            l_set = set(left_objs.get(t, []))
            r_set = set(right_objs.get(t, []))
            added = sorted(r_set - l_set)
            removed = sorted(l_set - r_set)
            common = sorted(l_set & r_set)
            per_type[t] = {"added": added, "removed": removed, "common": common}
            totals["added"] += len(added)
            totals["removed"] += len(removed)
            totals["common"] += len(common)

        return {"left": str(left), "right": str(right), "totals": totals, "by_type": per_type}


_TYPE_FAKE_VALUES = {
    "String": ["Test value", "Тестовая строка", "Значение"],
    "Number": [0, 1, 42, 100, 999.99, -1],
    "Boolean": [True, False],
    "Date": [datetime(2024, 1, 1), datetime(2025, 6, 15)],
}


def _fake_value(type_str: str, *, seed: int) -> Any:
    """Return a plausible test value for a 1С attribute type."""
    rng = random.Random(seed)
    base = type_str.split(".", 1)[0]
    if base in {"Catalog", "CatalogRef", "Document", "DocumentRef", "Enum", "EnumRef"}:
        return f"<{type_str}: ref-{rng.randint(1000, 9999)}>"
    if base in {"String", "Строка"}:
        return rng.choice(_TYPE_FAKE_VALUES["String"])
    if base in {"Number", "Число"}:
        return rng.choice(_TYPE_FAKE_VALUES["Number"])
    if base in {"Boolean", "Булево"}:
        return rng.choice(_TYPE_FAKE_VALUES["Boolean"])
    if base in {"Date", "Дата"}:
        return rng.choice(_TYPE_FAKE_VALUES["Date"]).isoformat()
    return f"<{type_str}: ?>"


class TestDataGenerateTool(BaseTool):
    """Generate JSON test data for an indexed metadata object.

    Reads attribute types from the metadata cache and produces N fake rows
    that match those types. Useful for unit-test fixtures and seeding
    development databases.
    """

    name: ClassVar[str] = "test-data-generate"
    description: ClassVar[str] = (
        "Сгенерировать тестовые данные (JSON) для объекта метаданных по типам реквизитов."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Тип объекта (Catalog, Document)"},
            "name": {"type": "string", "description": "Имя объекта"},
            "count": {"type": "integer", "default": 5, "description": "Сколько записей"},
            "seed": {"type": "integer", "default": 0, "description": "Seed для повторяемости"},
        },
        "required": ["type", "name"],
    }

    def __init__(self, metadata_engine: MetadataEngine) -> None:
        super().__init__()
        self._metadata = metadata_engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        type_ = arguments.get("type", "")
        name = arguments.get("name", "")
        count = int(arguments.get("count", 5))
        seed = int(arguments.get("seed", 0))
        if not (type_ and name):
            raise ToolError("type and name are required", code="MISSING_ARGUMENT")
        obj = await self._metadata.get_object(type_, name)
        if obj is None:
            raise ToolError(
                f"Object {type_}.{name} not in metadata cache. Run metadata-init first.",
                code="OBJECT_NOT_INDEXED",
            )
        rows: list[dict[str, Any]] = []
        attrs = list(obj.attributes)
        for i in range(count):
            row: dict[str, Any] = {}
            for attr in attrs:
                row[attr.name] = _fake_value(attr.type, seed=seed + i * 31 + hash(attr.name) % 997)
            rows.append(row)
        return {
            "object": f"{type_}.{name}",
            "count": len(rows),
            "rows": rows,
        }
