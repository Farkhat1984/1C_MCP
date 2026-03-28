"""
Template (MXL) tools (template.*).

Tools for working with 1C tabular document templates (MXL/SpreadsheetDocument).
"""

from typing import Any, ClassVar

from mcp_1c.domain.mxl import FillCodeGenerationOptions
from mcp_1c.engines.mxl import MxlEngine
from mcp_1c.tools.base import BaseTool


class TemplateGetTool(BaseTool):
    """Get structure and information about a template (MXL)."""

    name: ClassVar[str] = "template-get"
    description: ClassVar[str] = """
Get structure and information about a 1C template (MXL/SpreadsheetDocument).

Parses the template file and returns:
- Document dimensions (rows, columns)
- Named areas with their boundaries and types
- Parameters found in the template (in [brackets] or <angle brackets>)
- Page settings

Use this to understand template structure before generating fill code.

Args:
    file_path: Path to MXL or XML template file
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to template file (MXL or XML)",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = MxlEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get template structure."""
        file_path = arguments["file_path"]

        result = self._engine.get_template_structure(file_path)

        return result


class TemplateParametersTool(BaseTool):
    """Get parameters from a template (MXL)."""

    name: ClassVar[str] = "template-parameters"
    description: ClassVar[str] = """
Get all parameters from a 1C template (MXL/SpreadsheetDocument).

Parameters are placeholders in the template that get filled with data:
- [Parameter] - square bracket parameters
- <Parameter> - angle bracket parameters (data paths)
- {Parameter} - expression parameters

Returns list of parameters with:
- Name and display name
- Type (text, number, date, picture, data_path, expression)
- Location (area name, row, column)
- Data path if detected

Args:
    file_path: Path to template file
    area_name: Optional - filter parameters by area name
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to template file (MXL or XML)",
            },
            "area_name": {
                "type": "string",
                "description": "Filter by area name (optional)",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = MxlEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get template parameters."""
        file_path = arguments["file_path"]
        area_name = arguments.get("area_name")

        parameters = self._engine.get_parameters(file_path, area_name)

        if not parameters:
            # Check if file was parsed successfully
            result = self._engine.parse_template(file_path)
            if not result.success:
                return {
                    "success": False,
                    "error": result.error or "Failed to parse template",
                    "parameters": [],
                }

        return {
            "success": True,
            "parameters": [
                {
                    "name": p.name,
                    "display_name": p.display_name,
                    "type": p.parameter_type.value,
                    "area": p.area_name,
                    "row": p.row,
                    "column": p.column,
                    "data_path": p.data_path,
                    "format": p.format_string,
                    "is_expression": p.is_expression,
                    "raw_text": p.raw_text,
                }
                for p in parameters
            ],
            "unique_names": list({p.name for p in parameters}),
            "total": len(parameters),
            "area_filter": area_name,
        }


class TemplateAreasTool(BaseTool):
    """Get named areas from a template (MXL)."""

    name: ClassVar[str] = "template-areas"
    description: ClassVar[str] = """
Get named areas from a 1C template (MXL/SpreadsheetDocument).

Named areas are regions of the template that can be output separately:
- Header (Шапка) - document header
- Footer (Подвал) - document footer
- TableHeader (ШапкаТаблицы) - table column headers
- TableRow (Строка) - table data row (repeated for each data item)
- TableFooter (ИтогТаблицы) - table totals

Returns list of areas with:
- Name and type
- Row boundaries (start_row, end_row)
- Whether it's a table area (requires loop output)
- Parameters in the area

Args:
    file_path: Path to template file
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to template file (MXL or XML)",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = MxlEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Get template areas."""
        file_path = arguments["file_path"]

        areas = self._engine.get_areas(file_path)

        if not areas:
            result = self._engine.parse_template(file_path)
            if not result.success:
                return {
                    "success": False,
                    "error": result.error or "Failed to parse template",
                    "areas": [],
                }

        return {
            "success": True,
            "areas": areas,
            "total": len(areas),
            "table_areas": [a["name"] for a in areas if a.get("is_table")],
        }


class TemplateGenerateFillCodeTool(BaseTool):
    """Generate BSL code for filling a template."""

    name: ClassVar[str] = "template-generate_fill_code"
    description: ClassVar[str] = """
Generate BSL code for filling a 1C template (MXL/SpreadsheetDocument).

Analyzes the template structure and generates complete code for:
- Getting the template
- Creating spreadsheet document
- Filling each area with parameters
- Outputting to screen or print

Options:
- language: "ru" (Russian) or "en" (English) keywords
- variable_name: Name for spreadsheet document variable
- template_variable: Name for template variable
- data_variable: Name for data variable
- use_areas: Use GetArea() for named areas
- use_parameters_collection: Use Parameters collection vs indexer
- generate_comments: Add explanatory comments

Args:
    file_path: Path to template file
    language: Code language ("ru" or "en", default "ru")
    generate_comments: Add comments to code (default true)
    as_procedure: Generate as complete procedure (default false)
    procedure_name: Name for procedure (if as_procedure is true)
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to template file (MXL or XML)",
            },
            "language": {
                "type": "string",
                "enum": ["ru", "en"],
                "description": "Code language (default: ru)",
            },
            "generate_comments": {
                "type": "boolean",
                "description": "Add comments to generated code (default: true)",
            },
            "as_procedure": {
                "type": "boolean",
                "description": "Generate as complete procedure (default: false)",
            },
            "procedure_name": {
                "type": "string",
                "description": "Procedure name if as_procedure is true",
            },
            "data_variable": {
                "type": "string",
                "description": "Variable name for data (default: Data/Данные)",
            },
        },
        "required": ["file_path"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = MxlEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate fill code."""
        file_path = arguments["file_path"]
        language = arguments.get("language", "ru")
        generate_comments = arguments.get("generate_comments", True)
        as_procedure = arguments.get("as_procedure", False)
        procedure_name = arguments.get("procedure_name", "ЗаполнитьМакет")
        data_variable = arguments.get("data_variable")

        # Parse template first
        parse_result = self._engine.parse_template(file_path)
        if not parse_result.success or not parse_result.document:
            return {
                "success": False,
                "error": parse_result.error or "Failed to parse template",
                "code": "",
            }

        if as_procedure:
            # Generate complete procedure
            param_name = data_variable or ("Данные" if language == "ru" else "Data")
            code = self._engine.generate_procedure(
                file_path,
                procedure_name=procedure_name,
                parameter_name=param_name,
                language=language,
            )

            return {
                "success": True,
                "code": code,
                "type": "procedure",
                "procedure_name": procedure_name,
                "areas_used": [a.name for a in parse_result.document.areas],
                "parameters_used": parse_result.document.get_unique_parameter_names(),
            }
        else:
            # Generate with options
            options = FillCodeGenerationOptions(
                language=language,
                generate_comments=generate_comments,
                data_variable=data_variable or ("Данные" if language == "ru" else "Data"),
            )

            result = self._engine.generate_fill_code(file_path, options)

            return {
                "success": True,
                "code": result.code,
                "type": "inline",
                "breakdown": {
                    "initialization": result.initialization_code,
                    "areas": result.area_fill_code,
                    "output": result.output_code,
                },
                "areas_used": result.areas_used,
                "parameters_used": result.parameters_used,
                "suggestions": result.suggestions,
            }


class TemplateFindTool(BaseTool):
    """Find all templates in a 1C configuration."""

    name: ClassVar[str] = "template-find"
    description: ClassVar[str] = """
Find all MXL templates in a 1C configuration.

Searches for template files (MXL, XML) in the configuration directory
and returns list of found templates with their locations.

Searches in:
- Documents/*/Templates/
- Catalogs/*/Templates/
- DataProcessors/*/Templates/
- Reports/*/Templates/
- CommonTemplates/

Args:
    config_path: Path to configuration root directory
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "config_path": {
                "type": "string",
                "description": "Path to 1C configuration root directory",
            },
        },
        "required": ["config_path"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = MxlEngine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Find templates in configuration."""
        config_path = arguments["config_path"]

        templates = self._engine.find_templates_in_config(config_path)

        # Group by object type
        by_type: dict[str, list[dict[str, Any]]] = {}
        for tmpl in templates:
            obj_type = tmpl.get("object_type", "Other")
            if obj_type not in by_type:
                by_type[obj_type] = []
            by_type[obj_type].append(tmpl)

        return {
            "templates": templates,
            "total": len(templates),
            "by_type": {
                obj_type: {
                    "count": len(items),
                    "items": [
                        {"name": t.get("name"), "object": t.get("object_name")}
                        for t in items
                    ],
                }
                for obj_type, items in by_type.items()
            },
        }
