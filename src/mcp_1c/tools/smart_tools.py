"""
Smart generation tools (smart.*).

Metadata-aware tools that generate syntactically correct 1C code
by reading real object definitions from the configuration.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.engines.smart import SmartGenerator
from mcp_1c.tools.base import BaseTool, ToolError


class SmartQueryTool(BaseTool):
    """Генерация запроса 1С по метаданным объекта."""

    name: ClassVar[str] = "smart-query"
    description: ClassVar[str] = (
        "Генерирует запрос на языке запросов 1С из реальных метаданных объекта конфигурации. "
        "Автоматически определяет типы реквизитов и разыменовывает ссылки через точку. "
        "Поддерживает включение табличных частей через LEFT JOIN.\n\n"
        "Примеры object_name: 'Document.ПриходТовара', 'Документ.ПриходТовара', "
        "'Catalog.Товары', 'Справочник.Товары'."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Полное имя объекта: Type.Name (Document.ПриходТовара или Документ.ПриходТовара)",
            },
            "include_tabular": {
                "type": "string",
                "description": "Имя табличной части для включения в запрос (необязательно)",
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Список конкретных полей для включения (необязательно, по умолчанию — все)",
            },
        },
        "required": ["object_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        generator = SmartGenerator.get_instance()
        try:
            return await generator.generate_query(
                arguments["object_name"],
                include_tabular=arguments.get("include_tabular"),
                fields=arguments.get("fields"),
            )
        except ValueError as e:
            raise ToolError(str(e), code="INVALID_INPUT") from e


class SmartPrintTool(BaseTool):
    """Генерация печатной формы по метаданным объекта."""

    name: ClassVar[str] = "smart-print"
    description: ClassVar[str] = (
        "Генерирует полную печатную форму по стандарту БСП: процедуру печати, "
        "код модуля менеджера, макет MXL и текст запроса. Все имена полей берутся "
        "из реальных метаданных объекта.\n\n"
        "Возвращает 4 артефакта: print_procedure, manager_module, mxl_template, query."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Полное имя объекта: Type.Name (Document.ПриходТовара)",
            },
            "form_name": {
                "type": "string",
                "description": "Имя печатной формы (по умолчанию — имя объекта)",
            },
            "include_tabular": {
                "type": "boolean",
                "description": "Включить первую табличную часть (по умолчанию true)",
                "default": True,
            },
        },
        "required": ["object_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        generator = SmartGenerator.get_instance()
        try:
            return await generator.generate_print_form(
                arguments["object_name"],
                include_tabular=arguments.get("include_tabular", True),
                form_name=arguments.get("form_name"),
            )
        except ValueError as e:
            raise ToolError(str(e), code="INVALID_INPUT") from e


class SmartMovementTool(BaseTool):
    """Генерация кода движений регистра по метаданным документа."""

    name: ClassVar[str] = "smart-movement"
    description: ClassVar[str] = (
        "Генерирует код формирования движений регистра из документа. "
        "Автоматически сопоставляет реквизиты документа с измерениями и ресурсами "
        "регистра по совпадению типов. Выбирает табличную часть с наибольшим числом совпадений.\n\n"
        "При необходимости генерирует код контроля остатков."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "document_name": {
                "type": "string",
                "description": "Полное имя документа: Document.ПриходТовара",
            },
            "register_name": {
                "type": "string",
                "description": "Полное имя регистра: AccumulationRegister.ОстаткиТоваров",
            },
            "movement_type": {
                "type": "string",
                "enum": ["Приход", "Расход"],
                "description": "Вид движения (автоопределение если не указан)",
            },
        },
        "required": ["document_name", "register_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        generator = SmartGenerator.get_instance()
        try:
            return await generator.generate_movement(
                arguments["document_name"],
                arguments["register_name"],
                movement_type=arguments.get("movement_type"),
            )
        except ValueError as e:
            raise ToolError(str(e), code="INVALID_INPUT") from e
