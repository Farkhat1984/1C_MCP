"""
Runtime tools — talk to a live 1C base via MCPBridge HTTP service.

These tools require the 1C side to have the MCPBridge extension installed
and the env vars MCP_RUNTIME_BASE_URL / MCP_RUNTIME_TOKEN set on the
Python side. See ``docs/runtime-setup.md``.

Without configuration the tools surface a structured error rather than
crash, so they remain visible in `list_tools` even when runtime is off.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.engines.runtime.client import RuntimeClientError
from mcp_1c.engines.runtime.engine import RuntimeEngine
from mcp_1c.tools.base import BaseTool, ToolError


def _wrap_runtime_error(exc: RuntimeClientError) -> ToolError:
    """Convert client errors into the standard ToolError shape."""
    code = "RUNTIME_ERROR"
    if exc.status == 400:
        code = "RUNTIME_NOT_CONFIGURED"
    elif exc.status == 401:
        code = "RUNTIME_UNAUTHORIZED"
    elif exc.status == 403:
        code = "RUNTIME_FORBIDDEN"
    elif exc.status >= 500:
        code = "RUNTIME_SERVER_ERROR"
    return ToolError(exc.message, code=code)


class RuntimeStatusTool(BaseTool):
    name: ClassVar[str] = "runtime-status"
    description: ClassVar[str] = (
        "Проверить связь с 1С через расширение MCPBridge: версия, имя пользователя, "
        "режим (RO/RW)."
    )
    input_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    def __init__(self, engine: RuntimeEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            status = await self._engine.status()
        except RuntimeClientError as exc:
            raise _wrap_runtime_error(exc)
        return {"status": status, "allow_writes": self._engine.allow_writes}


class RuntimeQueryTool(BaseTool):
    name: ClassVar[str] = "runtime-query"
    description: ClassVar[str] = (
        "Выполнить запрос 1С на живой базе через MCPBridge. Поддерживает параметры. "
        "Read-only по умолчанию."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Текст запроса 1С (язык запросов)",
            },
            "parameters": {
                "type": "object",
                "description": "Параметры запроса (имя → значение)",
            },
        },
        "required": ["query"],
    }

    def __init__(self, engine: RuntimeEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        text = arguments.get("query", "")
        if not text:
            raise ToolError("query is required", code="MISSING_ARGUMENT")
        try:
            return await self._engine.query(text, arguments.get("parameters") or {})
        except RuntimeClientError as exc:
            raise _wrap_runtime_error(exc)


class RuntimeEvalTool(BaseTool):
    name: ClassVar[str] = "runtime-eval"
    description: ClassVar[str] = (
        "Выполнить BSL-фрагмент на сервере 1С через MCPBridge (sandbox). "
        "По умолчанию запрещены изменения данных. Включается через MCP_RUNTIME_RW=true."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Текст BSL-фрагмента"},
            "allow_writes": {
                "type": "boolean",
                "default": False,
                "description": "Разрешить запись (требует MCP_RUNTIME_RW=true).",
            },
        },
        "required": ["code"],
    }

    def __init__(self, engine: RuntimeEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        code = arguments.get("code", "")
        if not code:
            raise ToolError("code is required", code="MISSING_ARGUMENT")
        allow_writes = bool(arguments.get("allow_writes", False))
        try:
            return await self._engine.eval_bsl(code, allow_writes=allow_writes)
        except RuntimeClientError as exc:
            raise _wrap_runtime_error(exc)


class RuntimeDataTool(BaseTool):
    name: ClassVar[str] = "runtime-data"
    description: ClassVar[str] = (
        "Получить данные объекта 1С по ссылке (тип/имя/GUID) через MCPBridge."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Тип объекта (Catalog, Document, ...)"},
            "name": {"type": "string", "description": "Имя объекта"},
            "guid": {"type": "string", "description": "GUID-идентификатор"},
        },
        "required": ["type", "name", "guid"],
    }

    def __init__(self, engine: RuntimeEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        type_ = arguments.get("type", "")
        name = arguments.get("name", "")
        guid = arguments.get("guid", "")
        if not (type_ and name and guid):
            raise ToolError("type, name, guid are required", code="MISSING_ARGUMENT")
        try:
            return await self._engine.get_data(type_, name, guid)
        except RuntimeClientError as exc:
            raise _wrap_runtime_error(exc)


class RuntimeMethodTool(BaseTool):
    name: ClassVar[str] = "runtime-method"
    description: ClassVar[str] = (
        "Вызвать экспортную процедуру общего модуля 1С через MCPBridge. "
        "1С-сторона валидирует whitelist разрешённых модулей."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "module": {"type": "string", "description": "Имя общего модуля"},
            "method": {"type": "string", "description": "Имя экспортной процедуры"},
            "arguments": {
                "type": "array",
                "items": {},
                "description": "Список позиционных аргументов",
            },
        },
        "required": ["module", "method"],
    }

    def __init__(self, engine: RuntimeEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        module = arguments.get("module", "")
        method = arguments.get("method", "")
        if not (module and method):
            raise ToolError("module and method are required", code="MISSING_ARGUMENT")
        args = arguments.get("arguments") or []
        try:
            return await self._engine.call_method(module, method, args)
        except RuntimeClientError as exc:
            raise _wrap_runtime_error(exc)
