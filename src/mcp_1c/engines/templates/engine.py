"""
Template Engine facade.

Provides unified interface for template operations, code generation, and query analysis.
"""

from pathlib import Path
from typing import Any

from mcp_1c.domain.templates import (
    CodeTemplate,
    GenerationContext,
    GenerationResult,
    ParsedQuery,
    QueryOptimizationSuggestion,
    QueryValidationResult,
    TemplateCategory,
    TemplateSuggestion,
)
from mcp_1c.engines.templates.generator import CodeGenerator
from mcp_1c.engines.templates.loader import TemplateLoader
from mcp_1c.engines.templates.query_parser import QueryParser
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class TemplateEngine:
    """
    Facade for template operations.

    Provides:
    - Template listing and search
    - Code generation from templates
    - Query parsing and analysis
    - Context-aware suggestions
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        """
        Initialize template engine.

        Args:
            templates_dir: Optional custom templates directory
        """
        self._loader = TemplateLoader(templates_dir)
        self._generator = CodeGenerator()
        self._query_parser = QueryParser()

        # Ensure templates are loaded
        self._loader.load_all()

        logger.info("TemplateEngine initialized")

    # =========================================================================
    # Template operations
    # =========================================================================

    def list_templates(
        self,
        category: TemplateCategory | None = None,
    ) -> list[CodeTemplate]:
        """
        List available templates.

        Args:
            category: Optional category filter

        Returns:
            List of templates
        """
        if category:
            return self._loader.get_by_category(category)
        return list(self._loader.load_all().values())

    def get_template(self, template_id: str) -> CodeTemplate | None:
        """
        Get template by ID.

        Args:
            template_id: Template identifier

        Returns:
            Template or None
        """
        return self._loader.get(template_id)

    def search_templates(
        self,
        query: str,
        category: TemplateCategory | None = None,
        tags: list[str] | None = None,
    ) -> list[CodeTemplate]:
        """
        Search templates.

        Args:
            query: Search query
            category: Optional category filter
            tags: Optional tags filter

        Returns:
            Matching templates
        """
        return self._loader.search(query, category, tags)

    def list_categories(self) -> dict[TemplateCategory, int]:
        """
        List categories with counts.

        Returns:
            Category -> count dictionary
        """
        return self._loader.list_categories()

    # =========================================================================
    # Code generation
    # =========================================================================

    def generate(
        self,
        template_id: str,
        values: dict[str, Any],
        context: GenerationContext | None = None,
    ) -> GenerationResult:
        """
        Generate code from template.

        Args:
            template_id: Template to use
            values: Placeholder values
            context: Optional generation context

        Returns:
            Generation result
        """
        template = self._loader.get(template_id)
        if template is None:
            return GenerationResult(
                success=False,
                error=f"Template not found: {template_id}",
            )

        return self._generator.generate(template, values, context)

    def preview(
        self,
        template_id: str,
        values: dict[str, Any],
    ) -> str:
        """
        Preview generated code without full validation.

        Args:
            template_id: Template to use
            values: Placeholder values

        Returns:
            Preview code or error message
        """
        template = self._loader.get(template_id)
        if template is None:
            return f"Error: Template not found: {template_id}"

        return self._generator.preview(template, values)

    def suggest_templates(
        self,
        context: GenerationContext,
        task_description: str = "",
    ) -> list[TemplateSuggestion]:
        """
        Suggest relevant templates based on context.

        Args:
            context: Current generation context
            task_description: Optional task description

        Returns:
            List of template suggestions with relevance scores
        """
        suggestions = []
        all_templates = self._loader.load_all()

        for template in all_templates.values():
            score = 0.0
            reason = ""
            pre_filled = {}

            # Module type matching
            if (
                template.applicable_module_types
                and context.current_module_type
                and context.current_module_type in template.applicable_module_types
            ):
                score += 0.3
                reason = f"Подходит для {context.current_module_type}"

            # Task description matching
            if task_description:
                task_lower = task_description.lower()
                for tag in template.tags:
                    if tag.lower() in task_lower:
                        score += 0.2
                        reason = f"Соответствует задаче: {tag}"
                        break

                for use_case in template.use_cases:
                    if any(word in task_lower for word in use_case.lower().split()):
                        score += 0.2
                        break

            # Context pre-filling
            if context.current_object_name:
                pre_filled["ObjectName"] = context.current_object_name
                score += 0.1

            if score > 0:
                suggestions.append(
                    TemplateSuggestion(
                        template=template,
                        relevance_score=min(score, 1.0),
                        reason=reason,
                        pre_filled_values=pre_filled,
                    )
                )

        # Sort by relevance
        suggestions.sort(key=lambda s: s.relevance_score, reverse=True)

        return suggestions[:10]  # Return top 10

    # =========================================================================
    # Query operations
    # =========================================================================

    def parse_query(self, query_text: str) -> ParsedQuery:
        """
        Parse 1C query.

        Args:
            query_text: Query text

        Returns:
            Parsed query structure
        """
        return self._query_parser.parse(query_text)

    def validate_query(
        self,
        query_text: str,
        available_tables: list[str] | None = None,
    ) -> QueryValidationResult:
        """
        Validate 1C query.

        Args:
            query_text: Query text
            available_tables: Optional list of valid tables

        Returns:
            Validation result
        """
        parsed = self._query_parser.parse(query_text)
        return self._query_parser.validate(parsed, available_tables)

    def optimize_query(
        self,
        query_text: str,
    ) -> list[QueryOptimizationSuggestion]:
        """
        Get optimization suggestions for query.

        Args:
            query_text: Query text

        Returns:
            List of optimization suggestions
        """
        parsed = self._query_parser.parse(query_text)
        return self._query_parser.suggest_optimizations(parsed)

    def explain_query(self, query_text: str) -> str:
        """
        Get human-readable query explanation.

        Args:
            query_text: Query text

        Returns:
            Explanation text
        """
        parsed = self._query_parser.parse(query_text)
        return self._query_parser.explain(parsed)

    def get_query_tables(self, query_text: str) -> list[str]:
        """
        Get list of tables used in query.

        Args:
            query_text: Query text

        Returns:
            List of table names
        """
        parsed = self._query_parser.parse(query_text)
        return [t.table_name for t in parsed.tables]

    # =========================================================================
    # Utility methods
    # =========================================================================

    def reload_templates(self) -> None:
        """Reload templates from disk."""
        self._loader.reload()
        logger.info("Templates reloaded")

    def get_template_stats(self) -> dict[str, Any]:
        """
        Get template statistics.

        Returns:
            Statistics dictionary
        """
        templates = self._loader.load_all()
        categories = self._loader.list_categories()

        all_tags = set()
        for t in templates.values():
            all_tags.update(t.tags)

        return {
            "total_templates": len(templates),
            "categories": {cat.value: count for cat, count in categories.items()},
            "unique_tags": len(all_tags),
            "tags": sorted(all_tags),
        }
