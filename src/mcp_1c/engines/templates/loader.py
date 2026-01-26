"""
Template loader for loading templates from JSON files.

Loads templates from JSON files in the templates directory.
"""

import json
from pathlib import Path
from typing import Any

from mcp_1c.domain.templates import (
    CodeTemplate,
    Placeholder,
    PlaceholderType,
    TemplateCategory,
    TemplateExample,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class TemplateLoader:
    """
    Loads templates from JSON files.

    Templates are stored in JSON format and loaded on demand.
    Supports caching for performance.
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        """
        Initialize template loader.

        Args:
            templates_dir: Directory containing template JSON files.
                          Defaults to package templates directory.
        """
        if templates_dir is None:
            # Default to package templates directory
            self._templates_dir = Path(__file__).parent / "data"
        else:
            self._templates_dir = templates_dir

        self._cache: dict[str, CodeTemplate] = {}
        self._templates_by_category: dict[TemplateCategory, list[str]] = {}
        self._loaded = False

    def _ensure_templates_dir(self) -> None:
        """Ensure templates directory exists."""
        if not self._templates_dir.exists():
            self._templates_dir.mkdir(parents=True)
            logger.info(f"Created templates directory: {self._templates_dir}")

    def load_all(self) -> dict[str, CodeTemplate]:
        """
        Load all templates from directory.

        Returns:
            Dictionary of template_id -> CodeTemplate
        """
        if self._loaded:
            return self._cache

        self._ensure_templates_dir()
        self._cache.clear()
        self._templates_by_category.clear()

        # Load all JSON files in templates directory
        for json_file in self._templates_dir.glob("*.json"):
            try:
                templates = self._load_file(json_file)
                for template in templates:
                    self._cache[template.id] = template

                    # Index by category
                    if template.category not in self._templates_by_category:
                        self._templates_by_category[template.category] = []
                    self._templates_by_category[template.category].append(template.id)

                logger.debug(f"Loaded {len(templates)} templates from {json_file.name}")
            except Exception as e:
                logger.error(f"Error loading templates from {json_file}: {e}")

        self._loaded = True
        logger.info(f"Loaded {len(self._cache)} templates total")
        return self._cache

    def _load_file(self, file_path: Path) -> list[CodeTemplate]:
        """
        Load templates from a JSON file.

        Args:
            file_path: Path to JSON file

        Returns:
            List of templates from file
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        templates = []
        items = data if isinstance(data, list) else data.get("templates", [data])

        for item in items:
            template = self._parse_template(item)
            if template:
                templates.append(template)

        return templates

    def _parse_template(self, data: dict[str, Any]) -> CodeTemplate | None:
        """
        Parse template from dictionary.

        Args:
            data: Template data dictionary

        Returns:
            CodeTemplate or None if parsing fails
        """
        try:
            # Parse placeholders
            placeholders = []
            for ph_data in data.get("placeholders", []):
                placeholder = Placeholder(
                    name=ph_data["name"],
                    display_name=ph_data.get("display_name", ph_data["name"]),
                    description=ph_data.get("description", ""),
                    placeholder_type=PlaceholderType(
                        ph_data.get("type", "string")
                    ),
                    required=ph_data.get("required", True),
                    default_value=ph_data.get("default_value"),
                    validation_pattern=ph_data.get("validation_pattern"),
                    allowed_values=ph_data.get("allowed_values"),
                    metadata_type=ph_data.get("metadata_type"),
                )
                placeholders.append(placeholder)

            # Parse examples
            examples = []
            for ex_data in data.get("examples", []):
                example = TemplateExample(
                    description=ex_data.get("description", ""),
                    values=ex_data.get("values", {}),
                    result_preview=ex_data.get("result_preview", ""),
                )
                examples.append(example)

            # Create template
            template = CodeTemplate(
                id=data["id"],
                name=data["name"],
                name_ru=data.get("name_ru", ""),
                description=data.get("description", ""),
                description_ru=data.get("description_ru", ""),
                category=TemplateCategory(data["category"]),
                template_code=data["template_code"],
                placeholders=placeholders,
                tags=data.get("tags", []),
                use_cases=data.get("use_cases", []),
                examples=examples,
                requires_metadata=data.get("requires_metadata", False),
                requires_module_context=data.get("requires_module_context", False),
                applicable_module_types=data.get("applicable_module_types", []),
                min_platform_version=data.get("min_platform_version", "8.3.10"),
            )

            return template

        except Exception as e:
            logger.error(f"Error parsing template: {e}, data: {data.get('id', 'unknown')}")
            return None

    def get(self, template_id: str) -> CodeTemplate | None:
        """
        Get template by ID.

        Args:
            template_id: Template identifier

        Returns:
            CodeTemplate or None
        """
        if not self._loaded:
            self.load_all()

        return self._cache.get(template_id)

    def get_by_category(self, category: TemplateCategory) -> list[CodeTemplate]:
        """
        Get all templates in a category.

        Args:
            category: Template category

        Returns:
            List of templates
        """
        if not self._loaded:
            self.load_all()

        template_ids = self._templates_by_category.get(category, [])
        return [self._cache[tid] for tid in template_ids if tid in self._cache]

    def search(
        self,
        query: str,
        category: TemplateCategory | None = None,
        tags: list[str] | None = None,
    ) -> list[CodeTemplate]:
        """
        Search templates by query, category, and tags.

        Args:
            query: Search query (matches name, description, tags)
            category: Optional category filter
            tags: Optional tags filter (any match)

        Returns:
            List of matching templates
        """
        if not self._loaded:
            self.load_all()

        results = []
        query_lower = query.lower()

        for template in self._cache.values():
            # Category filter
            if category and template.category != category:
                continue

            # Tags filter
            if tags and not any(tag in template.tags for tag in tags):
                continue

            # Query match
            if query:
                matches = (
                    query_lower in template.name.lower()
                    or query_lower in template.name_ru.lower()
                    or query_lower in template.description.lower()
                    or query_lower in template.description_ru.lower()
                    or any(query_lower in tag.lower() for tag in template.tags)
                    or any(query_lower in uc.lower() for uc in template.use_cases)
                )
                if not matches:
                    continue

            results.append(template)

        return results

    def list_categories(self) -> dict[TemplateCategory, int]:
        """
        List all categories with template counts.

        Returns:
            Dictionary of category -> count
        """
        if not self._loaded:
            self.load_all()

        return {
            cat: len(ids) for cat, ids in self._templates_by_category.items()
        }

    def reload(self) -> None:
        """Reload all templates from disk."""
        self._loaded = False
        self.load_all()
