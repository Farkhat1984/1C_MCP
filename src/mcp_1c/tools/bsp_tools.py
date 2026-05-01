"""
BSP tools — query the BSP knowledge base, fetch hook templates, BSP code review.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.engines.bsp.engine import BspEngine
from mcp_1c.tools.base import BaseTool, ToolError


class BspFindTool(BaseTool):
    name: ClassVar[str] = "bsp-find"
    description: ClassVar[str] = (
        "Найти в базе знаний БСП модуль / экспортную процедуру / хук / паттерн "
        "по подстроке (например, 'печать', 'обновление', 'доступ')."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Поисковая фраза"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    }

    def __init__(self, engine: BspEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query", "")
        if not query:
            raise ToolError("query is required", code="MISSING_ARGUMENT")
        limit = int(arguments.get("limit", 10))
        results = self._engine.find(query, limit=limit)
        return {"query": query, "results": results, "count": len(results)}


class BspHookTool(BaseTool):
    name: ClassVar[str] = "bsp-hook"
    description: ClassVar[str] = (
        "Получить шаблон реализации БСП-хука (переопределяемой процедуры). "
        "Принимает имя хука."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Имя хука БСП"}
        },
        "required": ["name"],
    }

    def __init__(self, engine: BspEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        name = arguments.get("name", "")
        if not name:
            raise ToolError("name is required", code="MISSING_ARGUMENT")
        hook = self._engine.get_hook(name)
        if hook is None:
            raise ToolError(
                f"Hook '{name}' not found. Use bsp-find to discover hook names.",
                code="HOOK_NOT_FOUND",
            )
        return {
            "name": hook.name,
            "module": hook.module,
            "purpose": hook.purpose,
            "template": hook.template,
        }


class BspModulesTool(BaseTool):
    name: ClassVar[str] = "bsp-modules"
    description: ClassVar[str] = (
        "Список модулей БСП с фильтрацией по тегу (server/client/users/print/...)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "tag": {"type": "string", "description": "Фильтр по тегу"},
        },
    }

    def __init__(self, engine: BspEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        tag = arguments.get("tag") or None
        modules = self._engine.list_modules(tag)
        return {
            "tag": tag,
            "modules": [
                {
                    "name": m.name,
                    "kind": m.kind,
                    "purpose": m.purpose,
                    "tags": m.tags,
                    "procedures": [p.name for p in m.procedures if p.exported],
                }
                for m in modules
            ],
            "count": len(modules),
        }


class BspReviewTool(BaseTool):
    name: ClassVar[str] = "bsp-review"
    description: ClassVar[str] = (
        "Базовая статическая проверка кода 1С на соответствие практикам БСП. "
        "Возвращает список замечаний (rule/severity/line/message)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Текст кода BSL"}
        },
        "required": ["code"],
    }

    def __init__(self, engine: BspEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        code = arguments.get("code", "")
        if not code:
            raise ToolError("code is required", code="MISSING_ARGUMENT")
        findings = self._engine.review_code(code)
        return {"finding_count": len(findings), "findings": findings}
