"""
MXL Engine Facade.

High-level interface for working with MXL templates.
"""

from pathlib import Path
from typing import Any

from mcp_1c.domain.mxl import (
    FillCodeGenerationOptions,
    GeneratedFillCode,
    MxlDocument,
    MxlParseResult,
    TemplateParameter,
)
from collections import OrderedDict

from mcp_1c.engines.mxl.generator import FillCodeGenerator
from mcp_1c.engines.mxl.parser import MxlParser
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

_MXL_CACHE_MAX_SIZE = 100


class _LRUDict(OrderedDict):
    """Bounded LRU dictionary for sync cache usage."""

    def __init__(self, max_size: int = _MXL_CACHE_MAX_SIZE) -> None:
        super().__init__()
        self._max_size = max_size

    def __getitem__(self, key: str) -> MxlDocument:
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key: str, value: MxlDocument) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self._max_size:
            self.popitem(last=False)


class MxlEngine:
    """High-level engine for MXL template operations."""

    def __init__(self) -> None:
        """Initialize MXL engine."""
        self._parser = MxlParser()
        self._generator = FillCodeGenerator()
        self._cache: _LRUDict = _LRUDict(max_size=_MXL_CACHE_MAX_SIZE)

    def parse_template(
        self, file_path: str | Path, use_cache: bool = True
    ) -> MxlParseResult:
        """Parse MXL template file.

        Args:
            file_path: Path to MXL/XML file
            use_cache: Whether to use cached result

        Returns:
            Parse result with document or error
        """
        path_str = str(file_path)

        # Check cache
        if use_cache and path_str in self._cache:
            return MxlParseResult(
                success=True,
                document=self._cache[path_str],
            )

        # Parse file
        result = self._parser.parse_file(file_path)

        # Cache successful result
        if result.success and result.document and use_cache:
            self._cache[path_str] = result.document

        return result

    def parse_content(self, content: bytes, source_path: str = "") -> MxlParseResult:
        """Parse MXL content from bytes.

        Args:
            content: XML content as bytes
            source_path: Source file path for reference

        Returns:
            Parse result with document or error
        """
        return self._parser.parse_content(content, source_path)

    def get_template_structure(self, file_path: str | Path) -> dict[str, Any]:
        """Get template structure as dictionary.

        Args:
            file_path: Path to MXL/XML file

        Returns:
            Dictionary with template structure
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return {
                "success": False,
                "error": result.error or "Failed to parse template",
            }

        doc = result.document

        return {
            "success": True,
            "file_path": doc.file_path,
            "object_type": doc.object_type,
            "object_name": doc.object_name,
            "template_name": doc.template_name,
            "dimensions": {
                "rows": doc.row_count,
                "columns": doc.column_count,
            },
            "areas": [
                {
                    "name": area.name,
                    "type": area.area_type.value,
                    "rows": f"{area.start_row}-{area.end_row}",
                    "is_table": area.is_table_area,
                    "parameters": [p.name for p in area.parameters],
                    "cell_count": len(area.cells),
                }
                for area in doc.areas
            ],
            "parameters": [
                {
                    "name": p.name,
                    "type": p.parameter_type.value,
                    "area": p.area_name,
                    "location": f"R{p.row}C{p.column}",
                    "data_path": p.data_path,
                }
                for p in doc.parameters
            ],
            "page_settings": {
                "orientation": doc.page_orientation,
                "width": doc.page_width,
                "height": doc.page_height,
                "margins": {
                    "left": doc.left_margin,
                    "right": doc.right_margin,
                    "top": doc.top_margin,
                    "bottom": doc.bottom_margin,
                },
            },
        }

    def get_parameters(
        self, file_path: str | Path, area_name: str | None = None
    ) -> list[TemplateParameter]:
        """Get template parameters.

        Args:
            file_path: Path to MXL/XML file
            area_name: Optional area name to filter by

        Returns:
            List of template parameters
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return []

        doc = result.document

        if area_name:
            return doc.get_parameters_by_area(area_name)
        else:
            return doc.parameters

    def get_parameter_names(self, file_path: str | Path) -> list[str]:
        """Get list of unique parameter names.

        Args:
            file_path: Path to MXL/XML file

        Returns:
            List of parameter names
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return []

        return result.document.get_unique_parameter_names()

    def get_areas(self, file_path: str | Path) -> list[dict[str, Any]]:
        """Get list of named areas in template.

        Args:
            file_path: Path to MXL/XML file

        Returns:
            List of area info dictionaries
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return []

        return [
            {
                "name": area.name,
                "type": area.area_type.value,
                "start_row": area.start_row,
                "end_row": area.end_row,
                "is_table": area.is_table_area,
                "parameters": [p.name for p in area.parameters],
            }
            for area in result.document.areas
        ]

    def generate_fill_code(
        self,
        file_path: str | Path,
        options: FillCodeGenerationOptions | None = None,
    ) -> GeneratedFillCode:
        """Generate code for filling template.

        Args:
            file_path: Path to MXL/XML file
            options: Generation options

        Returns:
            Generated code with breakdown
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return GeneratedFillCode(
                code=f"// Error: {result.error or 'Failed to parse template'}",
            )

        return self._generator.generate(result.document, options)

    def generate_simple_code(
        self,
        file_path: str | Path,
        language: str = "ru",
    ) -> str:
        """Generate simple fill code for template.

        Args:
            file_path: Path to MXL/XML file
            language: Code language (ru/en)

        Returns:
            Generated BSL code
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return f"// Error: {result.error or 'Failed to parse template'}"

        return self._generator.generate_simple_fill(result.document, language=language)

    def generate_procedure(
        self,
        file_path: str | Path,
        procedure_name: str = "ЗаполнитьМакет",
        parameter_name: str = "Данные",
        language: str = "ru",
    ) -> str:
        """Generate complete procedure for filling template.

        Args:
            file_path: Path to MXL/XML file
            procedure_name: Name for the procedure
            parameter_name: Name for the data parameter
            language: Code language (ru/en)

        Returns:
            Complete procedure code
        """
        result = self.parse_template(file_path)

        if not result.success or not result.document:
            return f"// Error: {result.error or 'Failed to parse template'}"

        return self._generator.generate_procedure(
            result.document,
            procedure_name=procedure_name,
            parameter_name=parameter_name,
            language=language,
        )

    def find_templates_in_config(
        self, config_path: str | Path
    ) -> list[dict[str, Any]]:
        """Find all MXL templates in configuration.

        Args:
            config_path: Path to configuration root

        Returns:
            List of template info dictionaries
        """
        config_dir = Path(config_path)
        templates: list[dict[str, Any]] = []

        if not config_dir.exists():
            return templates

        # Search for template files
        # Common patterns in 1C exports
        patterns = [
            "**/*.mxl",
            "**/Templates/**/Template.xml",
            "**/Макеты/**/Template.xml",
            "**/Templates/**/*.xml",
            "**/Макеты/**/*.xml",
        ]

        found_files: set[Path] = set()
        for pattern in patterns:
            for file_path in config_dir.glob(pattern):
                if file_path not in found_files:
                    found_files.add(file_path)
                    templates.append(self._get_template_info(file_path))

        return templates

    def _get_template_info(self, file_path: Path) -> dict[str, Any]:
        """Get basic info about template file."""
        info: dict[str, Any] = {
            "path": str(file_path),
            "name": file_path.stem,
        }

        # Try to extract object info from path
        parts = file_path.parts
        for i, part in enumerate(parts):
            if part in ("Documents", "Документы") and i + 1 < len(parts):
                info["object_type"] = "Document"
                info["object_name"] = parts[i + 1]
            elif part in ("Catalogs", "Справочники") and i + 1 < len(parts):
                info["object_type"] = "Catalog"
                info["object_name"] = parts[i + 1]
            elif part in ("DataProcessors", "Обработки") and i + 1 < len(parts):
                info["object_type"] = "DataProcessor"
                info["object_name"] = parts[i + 1]
            elif part in ("Reports", "Отчеты") and i + 1 < len(parts):
                info["object_type"] = "Report"
                info["object_name"] = parts[i + 1]

        return info

    def clear_cache(self) -> None:
        """Clear template cache."""
        self._cache.clear()

    def invalidate_cache(self, file_path: str | Path) -> None:
        """Invalidate cache for specific file.

        Args:
            file_path: Path to invalidate
        """
        path_str = str(file_path)
        if path_str in self._cache:
            del self._cache[path_str]
