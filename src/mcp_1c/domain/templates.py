"""
Template domain models for code generation.

Represents templates, placeholders, and generation context for 1C code.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TemplateCategory(str, Enum):
    """Template categories."""

    QUERY = "query"
    HANDLER = "handler"
    PRINT_FORM = "print_form"
    MOVEMENT = "movement"
    API = "api"
    FORM_HANDLER = "form_handler"
    SUBSCRIPTION = "subscription"
    SCHEDULED_JOB = "scheduled_job"
    COMMON = "common"


class PlaceholderType(str, Enum):
    """Placeholder value types."""

    STRING = "string"
    IDENTIFIER = "identifier"  # Valid 1C identifier
    METADATA_NAME = "metadata_name"  # Reference to metadata object
    ATTRIBUTE_LIST = "attribute_list"  # List of attributes
    TABLE_NAME = "table_name"  # Query table name
    CONDITION = "condition"  # WHERE condition
    CODE_BLOCK = "code_block"  # Block of 1C code
    TYPE_NAME = "type_name"  # 1C type name
    BOOLEAN = "boolean"
    INTEGER = "integer"
    DATE = "date"


class Placeholder(BaseModel):
    """Template placeholder definition."""

    name: str = Field(..., description="Placeholder name (e.g., 'TableName')")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(default="", description="Placeholder description")
    placeholder_type: PlaceholderType = Field(
        default=PlaceholderType.STRING,
        description="Expected value type",
    )
    required: bool = Field(default=True, description="Is this placeholder required")
    default_value: str | None = Field(
        default=None,
        description="Default value if not provided",
    )
    validation_pattern: str | None = Field(
        default=None,
        description="Regex pattern for validation",
    )
    allowed_values: list[str] | None = Field(
        default=None,
        description="List of allowed values (enum-like)",
    )
    metadata_type: str | None = Field(
        default=None,
        description="For METADATA_NAME type: required metadata type",
    )


class TemplateExample(BaseModel):
    """Example of template usage."""

    description: str = Field(..., description="What this example demonstrates")
    values: dict[str, str] = Field(
        default_factory=dict,
        description="Placeholder values for the example",
    )
    result_preview: str = Field(default="", description="Expected result preview")


class CodeTemplate(BaseModel):
    """Code generation template."""

    id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Template name")
    name_ru: str = Field(default="", description="Russian name")
    description: str = Field(default="", description="Template description")
    description_ru: str = Field(default="", description="Russian description")
    category: TemplateCategory = Field(..., description="Template category")

    # Template content
    template_code: str = Field(..., description="Template code with placeholders")

    # Placeholders
    placeholders: list[Placeholder] = Field(
        default_factory=list,
        description="Placeholder definitions",
    )

    # Metadata
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for search and filtering",
    )
    use_cases: list[str] = Field(
        default_factory=list,
        description="Common use cases",
    )
    examples: list[TemplateExample] = Field(
        default_factory=list,
        description="Usage examples",
    )

    # Context requirements
    requires_metadata: bool = Field(
        default=False,
        description="Whether template needs metadata context",
    )
    requires_module_context: bool = Field(
        default=False,
        description="Whether template needs current module context",
    )
    applicable_module_types: list[str] = Field(
        default_factory=list,
        description="Module types where this template is applicable",
    )

    # Version and compatibility
    min_platform_version: str = Field(
        default="8.3.10",
        description="Minimum 1C platform version",
    )

    def get_placeholder(self, name: str) -> Placeholder | None:
        """Get placeholder by name."""
        for ph in self.placeholders:
            if ph.name == name:
                return ph
        return None

    def get_required_placeholders(self) -> list[Placeholder]:
        """Get all required placeholders."""
        return [ph for ph in self.placeholders if ph.required]

    def get_optional_placeholders(self) -> list[Placeholder]:
        """Get all optional placeholders."""
        return [ph for ph in self.placeholders if not ph.required]


class GenerationContext(BaseModel):
    """Context for template generation."""

    # Configuration path
    config_path: str | None = Field(
        default=None,
        description="Path to 1C configuration",
    )

    # Current module context
    current_module: str | None = Field(
        default=None,
        description="Current module path",
    )
    current_module_type: str | None = Field(
        default=None,
        description="Current module type (ObjectModule, ManagerModule, etc.)",
    )
    current_object_type: str | None = Field(
        default=None,
        description="Current object type (Catalog, Document, etc.)",
    )
    current_object_name: str | None = Field(
        default=None,
        description="Current object name",
    )

    # Available metadata (populated from MetadataEngine)
    available_catalogs: list[str] = Field(
        default_factory=list,
        description="Available catalog names",
    )
    available_documents: list[str] = Field(
        default_factory=list,
        description="Available document names",
    )
    available_registers: list[str] = Field(
        default_factory=list,
        description="Available register names",
    )
    available_enums: list[str] = Field(
        default_factory=list,
        description="Available enum names",
    )
    available_common_modules: list[str] = Field(
        default_factory=list,
        description="Available common module names",
    )

    # Object attributes (for current context)
    object_attributes: dict[str, dict] = Field(
        default_factory=dict,
        description="Object attributes with their types",
    )
    object_tabular_sections: dict[str, list[dict]] = Field(
        default_factory=dict,
        description="Tabular sections with their attributes",
    )


class GenerationResult(BaseModel):
    """Result of code generation."""

    success: bool = Field(..., description="Whether generation succeeded")
    code: str = Field(default="", description="Generated code")
    template_id: str = Field(default="", description="Template used")

    # Warnings and suggestions
    warnings: list[str] = Field(
        default_factory=list,
        description="Generation warnings",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Usage suggestions",
    )

    # Errors (if not successful)
    error: str | None = Field(default=None, description="Error message if failed")
    missing_placeholders: list[str] = Field(
        default_factory=list,
        description="Missing required placeholders",
    )
    invalid_values: dict[str, str] = Field(
        default_factory=dict,
        description="Invalid placeholder values with reasons",
    )


class TemplateSuggestion(BaseModel):
    """Suggested template for a context."""

    template: CodeTemplate = Field(..., description="Suggested template")
    relevance_score: float = Field(
        default=0.0,
        description="Relevance score (0-1)",
    )
    reason: str = Field(default="", description="Why this template is suggested")
    pre_filled_values: dict[str, str] = Field(
        default_factory=dict,
        description="Values that can be pre-filled from context",
    )


# =============================================================================
# Query-specific models
# =============================================================================


class QueryTableReference(BaseModel):
    """Table reference in a query."""

    table_name: str = Field(..., description="Table name (e.g., Catalog.Products)")
    alias: str | None = Field(default=None, description="Table alias")
    is_virtual_table: bool = Field(
        default=False,
        description="Is this a virtual table (SliceLast, Turnovers, etc.)",
    )
    virtual_table_type: str | None = Field(
        default=None,
        description="Virtual table type if applicable",
    )


class QueryField(BaseModel):
    """Field in a query."""

    expression: str = Field(..., description="Field expression")
    alias: str | None = Field(default=None, description="Field alias")
    is_aggregate: bool = Field(default=False, description="Is aggregate function")
    aggregate_function: str | None = Field(
        default=None,
        description="Aggregate function name (SUM, COUNT, etc.)",
    )


class QueryCondition(BaseModel):
    """Condition in a query."""

    left_operand: str = Field(..., description="Left operand")
    operator: str = Field(..., description="Comparison operator")
    right_operand: str = Field(..., description="Right operand")
    is_parameter: bool = Field(
        default=False,
        description="Whether right operand is a parameter",
    )


class ParsedQuery(BaseModel):
    """Parsed 1C query structure."""

    query_text: str = Field(..., description="Original query text")

    # SELECT
    select_fields: list[QueryField] = Field(
        default_factory=list,
        description="Selected fields",
    )
    is_distinct: bool = Field(default=False, description="DISTINCT modifier")
    top_count: int | None = Field(default=None, description="TOP N limit")

    # FROM
    tables: list[QueryTableReference] = Field(
        default_factory=list,
        description="Tables in query",
    )

    # JOIN
    joins: list[dict[str, Any]] = Field(
        default_factory=list,
        description="JOIN clauses",
    )

    # WHERE
    conditions: list[QueryCondition] = Field(
        default_factory=list,
        description="WHERE conditions",
    )

    # GROUP BY
    group_by_fields: list[str] = Field(
        default_factory=list,
        description="GROUP BY fields",
    )

    # HAVING
    having_conditions: list[QueryCondition] = Field(
        default_factory=list,
        description="HAVING conditions",
    )

    # ORDER BY
    order_by_fields: list[dict[str, Any]] = Field(
        default_factory=list,
        description="ORDER BY fields with direction",
    )

    # Query parameters
    parameters: list[str] = Field(
        default_factory=list,
        description="Query parameters (&Parameter)",
    )

    # Temporary tables
    temporary_tables: list[str] = Field(
        default_factory=list,
        description="Temporary tables defined in query",
    )

    # Subqueries count
    has_subqueries: bool = Field(default=False, description="Contains subqueries")


class QueryValidationResult(BaseModel):
    """Result of query validation."""

    is_valid: bool = Field(..., description="Whether query is valid")
    errors: list[str] = Field(
        default_factory=list,
        description="Validation errors",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Validation warnings",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Improvement suggestions",
    )

    # Referenced objects validation
    unknown_tables: list[str] = Field(
        default_factory=list,
        description="Tables not found in metadata",
    )
    unknown_fields: list[str] = Field(
        default_factory=list,
        description="Fields not found in tables",
    )


class QueryOptimizationSuggestion(BaseModel):
    """Query optimization suggestion."""

    category: str = Field(
        ...,
        description="Suggestion category (index, structure, performance)",
    )
    description: str = Field(..., description="What to improve")
    description_ru: str = Field(default="", description="Russian description")
    original_fragment: str = Field(default="", description="Original code fragment")
    suggested_fragment: str = Field(
        default="",
        description="Suggested replacement",
    )
    impact: str = Field(
        default="medium",
        description="Expected impact: low, medium, high",
    )
