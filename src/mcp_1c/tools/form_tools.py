"""
Form tools — expose 1C managed-form structure to MCP clients.

Each tool wraps a single ``FormEngine`` operation. The engine resolves
``object_type.object_name.Form.<form_name>`` to a parsed FormStructure
(see ``domain/form.py``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.domain.form import FormElement, FormStructure
from mcp_1c.engines.forms.engine import FormEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError


def _flatten_handlers(structure: FormStructure) -> list[dict[str, str]]:
    """Walk the element tree and return [{event,procedure,element}] in flat form."""
    out: list[dict[str, str]] = []
    for h in structure.handlers:
        out.append({"event": h.event, "procedure": h.procedure, "element": ""})

    def _walk(node: FormElement) -> None:
        for h in node.handlers:
            out.append(
                {"event": h.event, "procedure": h.procedure, "element": node.name}
            )
        for child in node.children:
            _walk(child)

    _walk(structure.elements)
    return out


def _flatten_elements(node: FormElement, depth: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    out.append(
        {
            "name": node.name,
            "kind": node.kind.value if hasattr(node.kind, "value") else str(node.kind),
            "title": node.title,
            "data_path": node.data_path,
            "depth": depth,
            "handler_count": len(node.handlers),
        }
    )
    for child in node.children:
        out.extend(_flatten_elements(child, depth + 1))
    return out


class _FormToolBase(BaseTool):
    """Shared init: every form tool needs a MetadataEngine and a FormEngine."""

    def __init__(
        self,
        form_engine: FormEngine,
        metadata_engine: MetadataEngine,
    ) -> None:
        super().__init__()
        self._forms = form_engine
        self._metadata = metadata_engine

    async def _resolve(
        self, args: dict[str, Any]
    ) -> FormStructure:
        object_type = args.get("type") or args.get("object_type") or ""
        object_name = args.get("name") or args.get("object_name") or ""
        form_name = args.get("form") or args.get("form_name") or ""
        if not (object_type and object_name and form_name):
            raise ToolError(
                "type, name, form are required",
                code="MISSING_ARGUMENT",
            )
        # Bind the form engine to the active configuration on first use
        workspace_path = (
            self._metadata.config_path
            if hasattr(self._metadata, "config_path")
            else None
        )
        if workspace_path is not None:
            self._forms._config_path = workspace_path  # type: ignore[attr-defined]
        try:
            return await self._forms.get_form(object_type, object_name, form_name)
        except FileNotFoundError as exc:
            raise ToolError(str(exc), code="FORM_NOT_FOUND")


class FormGetTool(_FormToolBase):
    """Return the full structure of a form: elements tree, attributes, commands."""

    name: ClassVar[str] = "form-get"
    description: ClassVar[str] = (
        "Получить структуру управляемой формы 1С: дерево элементов, "
        "реквизиты, команды, обработчики. "
        "Принимает type/name/form (например, type=Catalog name=Товары form=ФормаСписка)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "description": "Owner metadata type"},
            "name": {"type": "string", "description": "Owner metadata name"},
            "form": {"type": "string", "description": "Form name"},
        },
        "required": ["type", "name", "form"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        return {
            "object_type": s.object_type,
            "object_name": s.object_name,
            "form_name": s.form_name,
            "title": s.title,
            "purpose": s.purpose,
            "attributes": [
                {"name": a.name, "type": a.type, "title": a.title, "main": a.main}
                for a in s.attributes
            ],
            "commands": [
                {"name": c.name, "title": c.title, "action": c.action, "use": c.use}
                for c in s.commands
            ],
            "elements": _flatten_elements(s.elements),
            "command_interface": {
                "navigation_panel": s.command_interface.navigation_panel,
                "command_bar": s.command_interface.command_bar,
            },
        }


class FormHandlersTool(_FormToolBase):
    """List all event handlers wired up in a form."""

    name: ClassVar[str] = "form-handlers"
    description: ClassVar[str] = (
        "Список обработчиков событий формы (на форме и на её элементах). "
        "Возвращает [{event, procedure, element}]."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "name": {"type": "string"},
            "form": {"type": "string"},
        },
        "required": ["type", "name", "form"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        return {
            "object_type": s.object_type,
            "object_name": s.object_name,
            "form_name": s.form_name,
            "handlers": _flatten_handlers(s),
        }


class FormAttributesTool(_FormToolBase):
    """Return the form's reactive attributes (data items)."""

    name: ClassVar[str] = "form-attributes"
    description: ClassVar[str] = "Реквизиты управляемой формы (с типами и заголовками)."
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "name": {"type": "string"},
            "form": {"type": "string"},
        },
        "required": ["type", "name", "form"],
    }

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        s = await self._resolve(arguments)
        return {
            "object_type": s.object_type,
            "object_name": s.object_name,
            "form_name": s.form_name,
            "attributes": [
                {
                    "name": a.name,
                    "type": a.type,
                    "title": a.title,
                    "main": a.main,
                    "save_data": a.save_data,
                    "columns": [
                        {"name": c.name, "type": c.type} for c in a.columns
                    ],
                }
                for a in s.attributes
            ],
        }
