"""
MXL (SpreadsheetDocument) domain models.

Models for parsing and representing 1C tabular document templates.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CellType(str, Enum):
    """Cell content type."""

    TEXT = "text"
    PARAMETER = "parameter"  # [Parameter] or <Parameter>
    TEMPLATE = "template"  # Template expression
    FORMULA = "formula"
    PICTURE = "picture"
    EMPTY = "empty"


class AreaType(str, Enum):
    """Named area type."""

    HEADER = "header"
    FOOTER = "footer"
    TABLE_HEADER = "table_header"
    TABLE_ROW = "table_row"
    TABLE_FOOTER = "table_footer"
    DETAIL = "detail"
    GROUP_HEADER = "group_header"
    GROUP_FOOTER = "group_footer"
    CUSTOM = "custom"


class CellAlignment(str, Enum):
    """Cell text alignment."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class CellVerticalAlignment(str, Enum):
    """Cell vertical alignment."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class BorderStyle(str, Enum):
    """Cell border style."""

    NONE = "none"
    THIN = "thin"
    MEDIUM = "medium"
    THICK = "thick"
    DOUBLE = "double"
    DASHED = "dashed"
    DOTTED = "dotted"


class ParameterType(str, Enum):
    """Template parameter type."""

    TEXT = "text"  # Simple text substitution
    NUMBER = "number"  # Numeric value
    DATE = "date"  # Date value
    BOOLEAN = "boolean"  # Boolean value
    PICTURE = "picture"  # Picture/image
    EXPRESSION = "expression"  # Calculated expression
    DATA_PATH = "data_path"  # Path to data (e.g., Object.Name)


class CellBorders(BaseModel):
    """Cell border configuration."""

    left: BorderStyle = Field(default=BorderStyle.NONE)
    right: BorderStyle = Field(default=BorderStyle.NONE)
    top: BorderStyle = Field(default=BorderStyle.NONE)
    bottom: BorderStyle = Field(default=BorderStyle.NONE)


class CellStyle(BaseModel):
    """Cell style definition."""

    font_name: str | None = Field(default=None, description="Font name")
    font_size: int | None = Field(default=None, description="Font size in points")
    bold: bool = Field(default=False, description="Bold text")
    italic: bool = Field(default=False, description="Italic text")
    underline: bool = Field(default=False, description="Underlined text")
    strikethrough: bool = Field(default=False, description="Strikethrough text")

    text_color: str | None = Field(default=None, description="Text color (hex)")
    background_color: str | None = Field(
        default=None, description="Background color (hex)"
    )

    horizontal_alignment: CellAlignment = Field(default=CellAlignment.LEFT)
    vertical_alignment: CellVerticalAlignment = Field(
        default=CellVerticalAlignment.CENTER
    )

    borders: CellBorders = Field(default_factory=CellBorders)

    word_wrap: bool = Field(default=False, description="Enable word wrap")


class TemplateParameter(BaseModel):
    """Parameter found in template."""

    name: str = Field(..., description="Parameter name")
    display_name: str = Field(default="", description="Display name if different")

    parameter_type: ParameterType = Field(
        default=ParameterType.TEXT, description="Parameter value type"
    )

    # Location info
    area_name: str | None = Field(
        default=None, description="Area where parameter is located"
    )
    row: int = Field(default=0, description="Row number (1-based)")
    column: int = Field(default=0, description="Column number (1-based)")

    # Format info
    format_string: str | None = Field(
        default=None, description="Format string for the parameter"
    )

    # Data binding
    data_path: str | None = Field(
        default=None, description="Data path (e.g., Object.Contractor.Name)"
    )

    # Extraction info
    raw_text: str = Field(default="", description="Raw text containing the parameter")
    is_expression: bool = Field(
        default=False, description="Whether parameter is an expression"
    )


class MxlCell(BaseModel):
    """Single cell in spreadsheet document."""

    row: int = Field(..., description="Row number (1-based)")
    column: int = Field(..., description="Column number (1-based)")

    # Content
    text: str = Field(default="", description="Cell text content")
    cell_type: CellType = Field(default=CellType.TEXT, description="Cell content type")

    # Parameters in this cell
    parameters: list[TemplateParameter] = Field(
        default_factory=list, description="Parameters found in cell"
    )

    # Style
    style: CellStyle = Field(default_factory=CellStyle, description="Cell style")

    # Merge info
    merge_row_count: int = Field(default=1, description="Number of merged rows")
    merge_column_count: int = Field(default=1, description="Number of merged columns")

    # Size
    height: float | None = Field(default=None, description="Row height")
    width: float | None = Field(default=None, description="Column width")


class MxlArea(BaseModel):
    """Named area in spreadsheet document."""

    name: str = Field(..., description="Area name")
    area_type: AreaType = Field(default=AreaType.CUSTOM, description="Area type")

    # Boundaries (1-based)
    start_row: int = Field(..., description="Start row")
    end_row: int = Field(..., description="End row")
    start_column: int = Field(default=1, description="Start column")
    end_column: int | None = Field(
        default=None, description="End column (None = all columns)"
    )

    # Cells in this area
    cells: list[MxlCell] = Field(default_factory=list, description="Cells in area")

    # Parameters in this area
    parameters: list[TemplateParameter] = Field(
        default_factory=list, description="All parameters in this area"
    )

    # Metadata
    is_table_area: bool = Field(
        default=False, description="Whether this is a table row area"
    )
    parent_area: str | None = Field(default=None, description="Parent area name")


class MxlDocument(BaseModel):
    """Parsed MXL (SpreadsheetDocument) template."""

    # Source info
    file_path: str = Field(default="", description="Source file path")
    object_type: str = Field(
        default="", description="Owner object type (Document, Catalog, etc.)"
    )
    object_name: str = Field(default="", description="Owner object name")
    template_name: str = Field(default="", description="Template name")

    # Document structure
    row_count: int = Field(default=0, description="Total row count")
    column_count: int = Field(default=0, description="Total column count")

    # Named areas
    areas: list[MxlArea] = Field(
        default_factory=list, description="Named areas in document"
    )

    # All parameters (aggregated from all areas)
    parameters: list[TemplateParameter] = Field(
        default_factory=list, description="All parameters in document"
    )

    # Cells outside named areas
    header_cells: list[MxlCell] = Field(
        default_factory=list, description="Cells in header (before first area)"
    )
    footer_cells: list[MxlCell] = Field(
        default_factory=list, description="Cells in footer (after last area)"
    )

    # Page settings
    page_orientation: str = Field(
        default="portrait", description="Page orientation (portrait/landscape)"
    )
    page_width: float | None = Field(default=None, description="Page width in mm")
    page_height: float | None = Field(default=None, description="Page height in mm")
    left_margin: float | None = Field(default=None, description="Left margin in mm")
    right_margin: float | None = Field(default=None, description="Right margin in mm")
    top_margin: float | None = Field(default=None, description="Top margin in mm")
    bottom_margin: float | None = Field(default=None, description="Bottom margin in mm")

    # Print settings
    fit_to_page: bool = Field(default=False, description="Fit to page width")
    print_headers: bool = Field(default=False, description="Print column headers")
    print_grid: bool = Field(default=False, description="Print grid lines")

    def get_area(self, name: str) -> MxlArea | None:
        """Get area by name (case-insensitive)."""
        name_lower = name.lower()
        for area in self.areas:
            if area.name.lower() == name_lower:
                return area
        return None

    def get_parameters_by_area(self, area_name: str) -> list[TemplateParameter]:
        """Get parameters for a specific area."""
        return [p for p in self.parameters if p.area_name == area_name]

    def get_unique_parameter_names(self) -> list[str]:
        """Get list of unique parameter names."""
        return list({p.name for p in self.parameters})

    def get_table_areas(self) -> list[MxlArea]:
        """Get all table row areas."""
        return [a for a in self.areas if a.is_table_area]


class MxlParseResult(BaseModel):
    """Result of MXL parsing."""

    success: bool = Field(..., description="Whether parsing succeeded")
    document: MxlDocument | None = Field(
        default=None, description="Parsed document if successful"
    )

    # Errors and warnings
    error: str | None = Field(default=None, description="Error message if failed")
    warnings: list[str] = Field(default_factory=list, description="Parse warnings")

    # Statistics
    areas_found: int = Field(default=0, description="Number of areas found")
    parameters_found: int = Field(default=0, description="Number of parameters found")
    cells_parsed: int = Field(default=0, description="Number of cells parsed")


class FillCodeGenerationOptions(BaseModel):
    """Options for generating template fill code."""

    variable_name: str = Field(
        default="SpreadsheetDocument", description="Variable name for spreadsheet"
    )
    template_variable: str = Field(
        default="Template", description="Variable name for template"
    )
    data_variable: str = Field(default="Data", description="Variable name for data")

    # Code style
    use_areas: bool = Field(
        default=True, description="Use GetArea() for named areas"
    )
    use_parameters_collection: bool = Field(
        default=True, description="Use Parameters collection"
    )
    generate_comments: bool = Field(default=True, description="Add comments to code")
    language: str = Field(default="ru", description="Code language (ru/en)")

    # Data binding
    include_sample_values: bool = Field(
        default=False, description="Include sample values in generated code"
    )
    use_data_composition: bool = Field(
        default=False, description="Generate code for data composition"
    )


class GeneratedFillCode(BaseModel):
    """Generated code for filling a template."""

    code: str = Field(..., description="Generated BSL code")

    # Breakdown
    initialization_code: str = Field(
        default="", description="Template initialization code"
    )
    area_fill_code: dict[str, str] = Field(
        default_factory=dict, description="Code for each area"
    )
    output_code: str = Field(default="", description="Final output code")

    # Metadata
    parameters_used: list[str] = Field(
        default_factory=list, description="Parameters used in code"
    )
    areas_used: list[str] = Field(
        default_factory=list, description="Areas used in code"
    )

    # Suggestions
    suggestions: list[str] = Field(
        default_factory=list, description="Code improvement suggestions"
    )
