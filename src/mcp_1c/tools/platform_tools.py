"""
Platform tools for accessing 1C:Enterprise platform API documentation.

Tools:
- platform-method - Get method description
- platform-type - Get type description
- platform-event - Get event description
- platform-search - Search platform API
- platform-global_context - Get global context overview
"""

import logging
from typing import Any

from ..engines.platform import PlatformEngine
from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class PlatformBaseTool(BaseTool):
    """Base class for platform tools with lazy-loaded engine."""

    _engine: PlatformEngine | None = None

    @classmethod
    def get_engine(cls) -> PlatformEngine:
        """Get or create the shared PlatformEngine instance (lazy)."""
        if cls._engine is None:
            cls._engine = PlatformEngine()
        return cls._engine

    @property
    def engine(self) -> PlatformEngine:
        """Access the lazily-loaded PlatformEngine."""
        return self.get_engine()


class PlatformMethodTool(PlatformBaseTool):
    """Get platform method description."""

    name = "platform-method"
    description = "Get description of a platform method from global context or type"

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Method name (Russian or English)",
                },
                "type_name": {
                    "type": "string",
                    "description": "Type name if searching for type method (optional)",
                },
                "lang": {
                    "type": "string",
                    "enum": ["ru", "en"],
                    "default": "ru",
                    "description": "Output language",
                },
            },
            "required": ["name"],
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = arguments.get("name", "")
        type_name = arguments.get("type_name")
        lang = arguments.get("lang", "ru")

        if type_name:
            method = self.engine.get_type_method(type_name, name)
            if not method:
                return ToolResult(
                    success=False,
                    error=f"Method '{name}' not found in type '{type_name}'",
                )
        else:
            method = self.engine.get_method(name)
            if not method:
                return ToolResult(
                    success=False,
                    error=f"Method '{name}' not found in global context",
                )

        result = {
            "name": method.name,
            "name_en": method.name_en,
            "description": method.description if lang == "ru" else method.description_en or method.description,
            "signature": method.get_signature(lang),
            "category": method.category,
            "parameters": [
                {
                    "name": p.name if lang == "ru" else p.name_en or p.name,
                    "types": p.types,
                    "required": p.required,
                    "description": p.description,
                    "direction": p.direction.value,
                }
                for p in method.parameters
            ],
            "return_types": method.return_types,
            "return_description": method.return_description,
            "since_version": method.since_version,
            "examples": method.examples,
            "related_methods": method.related_methods,
            "notes": method.notes,
        }

        if method.available_contexts:
            result["available_contexts"] = [c.value for c in method.available_contexts]

        return ToolResult(success=True, data=result)


class PlatformTypeTool(PlatformBaseTool):
    """Get platform type description."""

    name = "platform-type"
    description = "Get description of a platform data type with its methods and properties"

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Type name (Russian or English)",
                },
                "include_methods": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include method list",
                },
                "include_properties": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include property list",
                },
            },
            "required": ["name"],
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = arguments.get("name", "")
        include_methods = arguments.get("include_methods", True)
        include_properties = arguments.get("include_properties", True)

        platform_type = self.engine.get_type(name)
        if not platform_type:
            return ToolResult(
                success=False,
                error=f"Type '{name}' not found",
            )

        result: dict[str, Any] = {
            "name": platform_type.name,
            "name_en": platform_type.name_en,
            "description": platform_type.description,
            "category": platform_type.category,
            "since_version": platform_type.since_version,
        }

        if platform_type.constructors:
            result["constructors"] = [
                {
                    "signature": c.get_signature("ru"),
                    "parameters": [
                        {"name": p.name, "types": p.types, "required": p.required}
                        for p in c.parameters
                    ],
                }
                for c in platform_type.constructors
            ]

        if include_methods and platform_type.methods:
            result["methods"] = [
                {
                    "name": m.name,
                    "name_en": m.name_en,
                    "description": m.description,
                    "signature": m.get_signature("ru"),
                    "return_types": m.return_types,
                }
                for m in platform_type.methods
            ]

        if include_properties and platform_type.properties:
            result["properties"] = [
                {
                    "name": p.name,
                    "name_en": p.name_en,
                    "description": p.description,
                    "types": p.types,
                    "readable": p.readable,
                    "writable": p.writable,
                }
                for p in platform_type.properties
            ]

        if platform_type.examples:
            result["examples"] = platform_type.examples

        return ToolResult(success=True, data=result)


class PlatformEventTool(PlatformBaseTool):
    """Get platform event description."""

    name = "platform-event"
    description = "Get description of an object event with handler signature"

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Event name (Russian or English)",
                },
                "object_type": {
                    "type": "string",
                    "description": "Filter by object type (e.g., 'Документ', 'Справочник')",
                },
            },
            "required": ["name"],
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = arguments.get("name", "")
        object_type = arguments.get("object_type")

        event = self.engine.get_event(name)
        if not event:
            # Try searching
            events = self.engine.search_events(name)
            if object_type:
                events = [e for e in events if object_type in e.object_types]
            if events:
                event = events[0]
            else:
                return ToolResult(
                    success=False,
                    error=f"Event '{name}' not found",
                )

        result = {
            "name": event.name,
            "name_en": event.name_en,
            "description": event.description,
            "category": event.category,
            "object_types": event.object_types,
            "handler_signature": event.get_handler_signature("ru"),
            "parameters": [
                {
                    "name": p.name,
                    "types": p.types,
                    "direction": p.direction.value,
                    "description": p.description,
                }
                for p in event.parameters
            ],
            "execution_context": event.execution_context.value,
            "can_cancel": event.can_cancel,
            "since_version": event.since_version,
        }

        if event.cancel_parameter:
            result["cancel_parameter"] = event.cancel_parameter

        if event.examples:
            result["examples"] = event.examples

        if event.notes:
            result["notes"] = event.notes

        if event.related_events:
            result["related_events"] = event.related_events

        return ToolResult(success=True, data=result)


class PlatformSearchTool(PlatformBaseTool):
    """Search platform API."""

    name = "platform-search"
    description = "Search for methods, types, and events in platform API"

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "category": {
                    "type": "string",
                    "enum": ["all", "methods", "types", "events"],
                    "default": "all",
                    "description": "Search category",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum results per category",
                },
            },
            "required": ["query"],
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        category = arguments.get("category", "all")
        limit = arguments.get("limit", 20)

        results: dict[str, Any] = {}

        if category in ("all", "methods"):
            methods = self.engine.search_methods(query)[:limit]
            results["methods"] = [
                {
                    "name": m.name,
                    "name_en": m.name_en,
                    "description": m.description[:100] + "..." if len(m.description) > 100 else m.description,
                    "category": m.category,
                }
                for m in methods
            ]

        if category in ("all", "types"):
            types = self.engine.search_types(query)[:limit]
            results["types"] = [
                {
                    "name": t.name,
                    "name_en": t.name_en,
                    "description": t.description[:100] + "..." if len(t.description) > 100 else t.description,
                    "category": t.category,
                }
                for t in types
            ]

        if category in ("all", "events"):
            events = self.engine.search_events(query)[:limit]
            results["events"] = [
                {
                    "name": e.name,
                    "name_en": e.name_en,
                    "description": e.description[:100] + "..." if len(e.description) > 100 else e.description,
                    "object_types": e.object_types,
                }
                for e in events
            ]

        total = sum(len(v) for v in results.values())
        return ToolResult(
            success=True,
            data={
                "query": query,
                "total_results": total,
                "results": results,
            },
        )


class PlatformGlobalContextTool(PlatformBaseTool):
    """Get global context overview."""

    name = "platform-global_context"
    description = "Get overview of platform global context sections and methods"

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "Specific section name (optional)",
                },
                "include_methods": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include method list in each section",
                },
            },
        }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        section_name = arguments.get("section")
        include_methods = arguments.get("include_methods", False)

        sections = self.engine.get_global_context_sections()

        if section_name:
            section_name_lower = section_name.lower()
            sections = [
                s for s in sections
                if section_name_lower in s.name.lower() or section_name_lower in s.name_en.lower()
            ]
            if not sections:
                return ToolResult(
                    success=False,
                    error=f"Section '{section_name}' not found",
                )

        result = {
            "platform_version": "8.3.24",
            "sections": [],
        }

        for section in sections:
            section_data: dict[str, Any] = {
                "name": section.name,
                "name_en": section.name_en,
                "method_count": len(section.methods),
            }

            if include_methods:
                section_data["methods"] = [
                    {
                        "name": m.name,
                        "name_en": m.name_en,
                        "signature": m.get_signature("ru"),
                    }
                    for m in section.methods
                ]

            result["sections"].append(section_data)

        result["total_methods"] = sum(len(s.methods) for s in sections)

        return ToolResult(success=True, data=result)


def register_platform_tools(registry: Any) -> None:
    """Register all platform tools (engine is lazily loaded on first use)."""
    tools = [
        PlatformMethodTool(),
        PlatformTypeTool(),
        PlatformEventTool(),
        PlatformSearchTool(),
        PlatformGlobalContextTool(),
    ]
    for tool in tools:
        registry.register(tool)
