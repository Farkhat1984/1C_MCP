"""
Query analysis tools (query.*).

Tools for parsing, validating, and optimizing 1C queries.
"""

from typing import Any, ClassVar

from mcp_1c.engines.templates import TemplateEngine
from mcp_1c.tools.base import BaseTool


class QueryParseTool(BaseTool):
    """Parse 1C query into structured representation."""

    name: ClassVar[str] = "query.parse"
    description: ClassVar[str] = """
Parse a 1C query into structured representation.

Returns parsed structure with:
- select_fields: Selected fields with aliases and aggregates
- tables: Tables with aliases and virtual table info
- conditions: WHERE conditions
- group_by_fields: GROUP BY fields
- order_by_fields: ORDER BY fields
- parameters: Query parameters (&Parameter)
- temporary_tables: Temp tables (ПОМЕСТИТЬ)
- has_subqueries: Whether query has subqueries

Supports both Russian and English query syntax.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "1C query text to parse",
            },
        },
        "required": ["query_text"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Parse query."""
        query_text = arguments["query_text"]

        parsed = self._engine.parse_query(query_text)

        return {
            "select_fields": [
                {
                    "expression": f.expression,
                    "alias": f.alias,
                    "is_aggregate": f.is_aggregate,
                    "aggregate_function": f.aggregate_function,
                }
                for f in parsed.select_fields
            ],
            "is_distinct": parsed.is_distinct,
            "top_count": parsed.top_count,
            "tables": [
                {
                    "table_name": t.table_name,
                    "alias": t.alias,
                    "is_virtual_table": t.is_virtual_table,
                    "virtual_table_type": t.virtual_table_type,
                }
                for t in parsed.tables
            ],
            "conditions": [
                {
                    "left_operand": c.left_operand,
                    "operator": c.operator,
                    "right_operand": c.right_operand,
                    "is_parameter": c.is_parameter,
                }
                for c in parsed.conditions
            ],
            "group_by_fields": parsed.group_by_fields,
            "order_by_fields": parsed.order_by_fields,
            "parameters": parsed.parameters,
            "temporary_tables": parsed.temporary_tables,
            "has_subqueries": parsed.has_subqueries,
        }


class QueryValidateTool(BaseTool):
    """Validate 1C query."""

    name: ClassVar[str] = "query.validate"
    description: ClassVar[str] = """
Validate a 1C query.

Checks for:
- Correct query structure
- GROUP BY consistency (fields in SELECT must be in GROUP BY or aggregated)
- Tables existence (if available_tables provided)
- Common query issues

Returns validation result with errors, warnings, and suggestions.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "1C query text to validate",
            },
            "available_tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of valid table names for validation",
            },
        },
        "required": ["query_text"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate query."""
        query_text = arguments["query_text"]
        available_tables = arguments.get("available_tables")

        result = self._engine.validate_query(query_text, available_tables)

        return {
            "is_valid": result.is_valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "suggestions": result.suggestions,
            "unknown_tables": result.unknown_tables,
            "unknown_fields": result.unknown_fields,
        }


class QueryOptimizeTool(BaseTool):
    """Get optimization suggestions for 1C query."""

    name: ClassVar[str] = "query.optimize"
    description: ClassVar[str] = """
Get optimization suggestions for a 1C query.

Analyzes query and suggests:
- Performance improvements (indexes, structure)
- Replacing SELECT * with explicit fields
- Virtual table parameter usage
- Temporary tables instead of subqueries
- Redundant DISTINCT removal

Returns list of suggestions with impact level.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "1C query text to optimize",
            },
        },
        "required": ["query_text"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get optimization suggestions."""
        query_text = arguments["query_text"]

        suggestions = self._engine.optimize_query(query_text)

        return {
            "suggestions": [
                {
                    "category": s.category,
                    "description": s.description,
                    "description_ru": s.description_ru,
                    "original_fragment": s.original_fragment,
                    "suggested_fragment": s.suggested_fragment,
                    "impact": s.impact,
                }
                for s in suggestions
            ],
            "total_suggestions": len(suggestions),
        }


class QueryExplainTool(BaseTool):
    """Explain 1C query in human-readable format."""

    name: ClassVar[str] = "query.explain"
    description: ClassVar[str] = """
Explain a 1C query in human-readable format (Russian).

Provides detailed explanation of:
- Data sources (tables)
- Selected fields
- Conditions (WHERE)
- Grouping (GROUP BY)
- Sorting (ORDER BY)
- Parameters
- Query modifiers (DISTINCT, TOP)

Useful for understanding complex queries.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "1C query text to explain",
            },
        },
        "required": ["query_text"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> str:
        """Explain query."""
        query_text = arguments["query_text"]

        explanation = self._engine.explain_query(query_text)

        return explanation


class QueryTablesTool(BaseTool):
    """Get list of tables used in 1C query."""

    name: ClassVar[str] = "query.tables"
    description: ClassVar[str] = """
Get list of tables used in a 1C query.

Returns list of table names (e.g., Справочник.Номенклатура, РегистрСведений.ЦеныНоменклатуры).

Useful for dependency analysis and validation.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "1C query text",
            },
        },
        "required": ["query_text"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = TemplateEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get tables from query."""
        query_text = arguments["query_text"]

        tables = self._engine.get_query_tables(query_text)

        return {
            "tables": tables,
            "count": len(tables),
        }
