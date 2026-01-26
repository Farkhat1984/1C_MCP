"""
Pattern/template tools (pattern.*).

Tools for listing, searching, and applying code patterns/templates.
"""

from typing import Any, ClassVar

from mcp_1c.domain.templates import GenerationContext, TemplateCategory
from mcp_1c.engines.templates import TemplateEngine
from mcp_1c.tools.base import BaseTool


class PatternListTool(BaseTool):
    """List available code patterns/templates."""

    name: ClassVar[str] = "pattern.list"
    description: ClassVar[str] = """
List available code patterns/templates.

Categories:
- query: Query templates (SELECT, JOIN, GROUP BY, etc.)
- handler: Event handler templates (BeforeWrite, OnWrite, etc.)
- print_form: Print form templates
- movement: Register movement templates
- api: API templates (HTTP services, web services)
- form_handler: Form event handlers
- subscription: Event subscription handlers
- scheduled_job: Scheduled job handlers

Returns list of templates with id, name, description, and tags.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "query",
                    "handler",
                    "print_form",
                    "movement",
                    "api",
                    "form_handler",
                    "subscription",
                    "scheduled_job",
                ],
                "description": "Filter by category (optional)",
            },
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """List templates."""
        category_str = arguments.get("category")
        category = TemplateCategory(category_str) if category_str else None

        templates = self._engine.list_templates(category)

        return {
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "name_ru": t.name_ru,
                    "description": t.description,
                    "description_ru": t.description_ru,
                    "category": t.category.value,
                    "tags": t.tags,
                    "use_cases": t.use_cases,
                }
                for t in templates
            ],
            "total": len(templates),
            "categories": {
                cat.value: count
                for cat, count in self._engine.list_categories().items()
            },
        }


class PatternGetTool(BaseTool):
    """Get detailed information about a pattern/template."""

    name: ClassVar[str] = "pattern.get"
    description: ClassVar[str] = """
Get detailed information about a pattern/template.

Returns full template definition including:
- Template code with placeholders
- Placeholder definitions (name, type, required, default)
- Usage examples
- Tags and use cases
- Module type applicability
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Template ID (e.g., 'query.select_simple')",
            },
        },
        "required": ["template_id"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get template details."""
        template_id = arguments["template_id"]

        template = self._engine.get_template(template_id)

        if template is None:
            return {
                "error": f"Template not found: {template_id}",
                "available_categories": list(
                    cat.value for cat in self._engine.list_categories().keys()
                ),
            }

        return {
            "id": template.id,
            "name": template.name,
            "name_ru": template.name_ru,
            "description": template.description,
            "description_ru": template.description_ru,
            "category": template.category.value,
            "template_code": template.template_code,
            "placeholders": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "type": p.placeholder_type.value,
                    "required": p.required,
                    "default_value": p.default_value,
                    "allowed_values": p.allowed_values,
                    "metadata_type": p.metadata_type,
                }
                for p in template.placeholders
            ],
            "examples": [
                {
                    "description": e.description,
                    "values": e.values,
                    "result_preview": e.result_preview,
                }
                for e in template.examples
            ],
            "tags": template.tags,
            "use_cases": template.use_cases,
            "requires_metadata": template.requires_metadata,
            "applicable_module_types": template.applicable_module_types,
            "min_platform_version": template.min_platform_version,
        }


class PatternApplyTool(BaseTool):
    """Apply a pattern/template with values."""

    name: ClassVar[str] = "pattern.apply"
    description: ClassVar[str] = """
Apply a pattern/template with provided values.

This is the main tool for code generation from templates.
Pass template_id and values dictionary.

Returns generated code or error with missing/invalid placeholders.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Template ID to apply",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values",
            },
            "context": {
                "type": "object",
                "description": "Optional generation context (current_module, current_object_type, etc.)",
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Apply template."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        context_dict = arguments.get("context")

        context = None
        if context_dict:
            context = GenerationContext(**context_dict)

        result = self._engine.generate(template_id, values, context)

        return {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "suggestions": result.suggestions,
            "error": result.error,
            "missing_placeholders": result.missing_placeholders,
            "invalid_values": result.invalid_values,
        }


class PatternSuggestTool(BaseTool):
    """Suggest patterns based on context or task description."""

    name: ClassVar[str] = "pattern.suggest"
    description: ClassVar[str] = """
Suggest patterns based on context or task description.

Analyzes the provided context and/or task description and suggests
relevant templates with relevance scores.

Can use:
- current_module_type: Type of current module (ObjectModule, ManagerModule, FormModule)
- current_object_type: Type of current object (Catalog, Document, etc.)
- current_object_name: Name of current object
- task_description: Text description of what you want to do

Returns list of suggestions sorted by relevance.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "Description of what you want to do (e.g., 'создать обработчик проведения')",
            },
            "current_module_type": {
                "type": "string",
                "description": "Current module type (ObjectModule, ManagerModule, FormModule)",
            },
            "current_object_type": {
                "type": "string",
                "description": "Current object type (Catalog, Document, etc.)",
            },
            "current_object_name": {
                "type": "string",
                "description": "Current object name",
            },
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Suggest templates."""
        task_description = arguments.get("task_description", "")

        context = GenerationContext(
            current_module_type=arguments.get("current_module_type"),
            current_object_type=arguments.get("current_object_type"),
            current_object_name=arguments.get("current_object_name"),
        )

        suggestions = self._engine.suggest_templates(context, task_description)

        return {
            "suggestions": [
                {
                    "template_id": s.template.id,
                    "template_name": s.template.name,
                    "template_name_ru": s.template.name_ru,
                    "category": s.template.category.value,
                    "relevance_score": s.relevance_score,
                    "reason": s.reason,
                    "pre_filled_values": s.pre_filled_values,
                    "tags": s.template.tags,
                }
                for s in suggestions
            ],
            "total": len(suggestions),
        }


class PatternSearchTool(BaseTool):
    """Search patterns by query, category, or tags."""

    name: ClassVar[str] = "pattern.search"
    description: ClassVar[str] = """
Search patterns by query, category, or tags.

Search is performed across:
- Template names (Russian and English)
- Descriptions
- Tags
- Use cases

Returns matching templates with relevance info.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (e.g., 'запрос остатки' or 'select join')",
            },
            "category": {
                "type": "string",
                "enum": [
                    "query",
                    "handler",
                    "print_form",
                    "movement",
                    "api",
                    "form_handler",
                    "subscription",
                    "scheduled_job",
                ],
                "description": "Filter by category (optional)",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by tags (optional, any match)",
            },
        },
        "required": ["query"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Search templates."""
        query = arguments["query"]
        category_str = arguments.get("category")
        tags = arguments.get("tags")

        category = TemplateCategory(category_str) if category_str else None

        templates = self._engine.search_templates(query, category, tags)

        return {
            "results": [
                {
                    "id": t.id,
                    "name": t.name,
                    "name_ru": t.name_ru,
                    "description": t.description,
                    "description_ru": t.description_ru,
                    "category": t.category.value,
                    "tags": t.tags,
                    "use_cases": t.use_cases,
                }
                for t in templates
            ],
            "total": len(templates),
            "query": query,
        }
