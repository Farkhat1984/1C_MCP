"""
MXL (SpreadsheetDocument) Parser.

Parses 1C tabular document templates from XML format.
"""

import re
from pathlib import Path
from typing import Any

from lxml import etree

from mcp_1c.domain.mxl import (
    AreaType,
    BorderStyle,
    CellAlignment,
    CellBorders,
    CellStyle,
    CellType,
    CellVerticalAlignment,
    MxlArea,
    MxlCell,
    MxlDocument,
    MxlParseResult,
    ParameterType,
    TemplateParameter,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# Namespaces used in 1C XML exports
NAMESPACES = {
    "v8": "http://v8.1c.ru/8.1/data/core",
    "xs": "http://www.w3.org/2001/XMLSchema",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# Regex patterns for parameter extraction
# [Parameter] - square brackets
PARAM_SQUARE_BRACKET = re.compile(r"\[([^\[\]]+)\]")
# <Parameter> - angle brackets (but not XML tags)
PARAM_ANGLE_BRACKET = re.compile(r"<([A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_.]*)>")
# {Parameter} - curly braces
PARAM_CURLY_BRACKET = re.compile(r"\{([^{}]+)\}")


class MxlParser:
    """Parser for MXL (SpreadsheetDocument) files."""

    def __init__(self) -> None:
        """Initialize MXL parser."""
        self._warnings: list[str] = []

    def parse_file(self, file_path: str | Path) -> MxlParseResult:
        """Parse MXL file from disk.

        Args:
            file_path: Path to MXL/XML file

        Returns:
            Parse result with document or error
        """
        path = Path(file_path)

        if not path.exists():
            return MxlParseResult(
                success=False,
                error=f"File not found: {file_path}",
            )

        try:
            content = path.read_bytes()
            result = self.parse_content(content, str(path))

            # Extract object info from path
            if result.success and result.document:
                self._extract_object_info(result.document, path)

            return result

        except Exception as e:
            logger.error(f"Failed to read MXL file {file_path}: {e}")
            return MxlParseResult(
                success=False,
                error=f"Failed to read file: {e}",
            )

    def parse_content(
        self, content: bytes, source_path: str = ""
    ) -> MxlParseResult:
        """Parse MXL content from bytes.

        Args:
            content: XML content as bytes
            source_path: Source file path for reference

        Returns:
            Parse result with document or error
        """
        self._warnings = []

        try:
            # Parse XML
            root = etree.fromstring(content)

            # Create document
            document = MxlDocument(file_path=source_path)

            # Parse based on root element
            root_tag = etree.QName(root).localname

            if root_tag in ("SpreadsheetDocument", "v8:SpreadsheetDocument"):
                self._parse_spreadsheet_document(root, document)
            elif root_tag == "Template":
                # EDT format - template wrapper
                self._parse_template_wrapper(root, document)
            else:
                # Try to find SpreadsheetDocument inside
                sd = root.find(".//SpreadsheetDocument", NAMESPACES)
                if sd is None:
                    sd = root.find(".//{http://v8.1c.ru/8.1/data/core}SpreadsheetDocument")
                if sd is not None:
                    self._parse_spreadsheet_document(sd, document)
                else:
                    return MxlParseResult(
                        success=False,
                        error=f"Unknown root element: {root_tag}",
                    )

            # Aggregate parameters from areas
            self._aggregate_parameters(document)

            return MxlParseResult(
                success=True,
                document=document,
                warnings=self._warnings,
                areas_found=len(document.areas),
                parameters_found=len(document.parameters),
                cells_parsed=sum(len(a.cells) for a in document.areas),
            )

        except etree.XMLSyntaxError as e:
            logger.error(f"XML syntax error in MXL: {e}")
            return MxlParseResult(
                success=False,
                error=f"XML syntax error: {e}",
            )
        except Exception as e:
            logger.error(f"Failed to parse MXL content: {e}")
            return MxlParseResult(
                success=False,
                error=f"Parse error: {e}",
            )

    def _parse_spreadsheet_document(
        self, element: etree._Element, document: MxlDocument
    ) -> None:
        """Parse SpreadsheetDocument element."""
        # Parse page settings
        self._parse_page_settings(element, document)

        # Parse rows and cells
        rows_data = self._parse_rows(element)
        document.row_count = len(rows_data)

        if rows_data:
            document.column_count = max(
                max((c["column"] for c in row), default=0) for row in rows_data
            )

        # Parse named areas
        areas = self._parse_areas(element)

        # Associate cells with areas
        for area_data in areas:
            area = self._create_area(area_data, rows_data)
            document.areas.append(area)

        # Find cells not in any area (header/footer)
        if rows_data:
            if document.areas:
                first_area_start = min(a.start_row for a in document.areas)
                last_area_end = max(a.end_row for a in document.areas)

                for row_idx, row_cells in enumerate(rows_data, start=1):
                    for cell_data in row_cells:
                        if row_idx < first_area_start:
                            cell = self._create_cell(cell_data)
                            document.header_cells.append(cell)
                        elif row_idx > last_area_end:
                            cell = self._create_cell(cell_data)
                            document.footer_cells.append(cell)
            else:
                # No areas defined - treat all cells as header cells
                for row_idx, row_cells in enumerate(rows_data, start=1):
                    for cell_data in row_cells:
                        cell = self._create_cell(cell_data)
                        document.header_cells.append(cell)

    def _parse_template_wrapper(
        self, element: etree._Element, document: MxlDocument
    ) -> None:
        """Parse EDT-format Template wrapper."""
        # Find SpreadsheetDocument inside Template
        sd = element.find(".//SpreadsheetDocument")
        if sd is None:
            sd = element.find(".//{http://v8.1c.ru/8.1/data/core}SpreadsheetDocument")

        if sd is not None:
            self._parse_spreadsheet_document(sd, document)
        else:
            self._warnings.append("No SpreadsheetDocument found in Template wrapper")

    def _parse_page_settings(
        self, element: etree._Element, document: MxlDocument
    ) -> None:
        """Parse page settings from SpreadsheetDocument."""
        # Page orientation
        orientation = self._get_text(element, "PageOrientation")
        if orientation:
            document.page_orientation = orientation.lower()

        # Page size
        document.page_width = self._get_float(element, "PageWidth")
        document.page_height = self._get_float(element, "PageHeight")

        # Margins
        document.left_margin = self._get_float(element, "LeftMargin")
        document.right_margin = self._get_float(element, "RightMargin")
        document.top_margin = self._get_float(element, "TopMargin")
        document.bottom_margin = self._get_float(element, "BottomMargin")

        # Print settings
        fit_text = self._get_text(element, "FitToPage")
        document.fit_to_page = fit_text and fit_text.lower() == "true"

        print_grid = self._get_text(element, "PrintGrid")
        document.print_grid = print_grid and print_grid.lower() == "true"

    def _parse_rows(self, element: etree._Element) -> list[list[dict[str, Any]]]:
        """Parse all rows and cells."""
        rows_data: list[list[dict[str, Any]]] = []

        # Try different row container names
        rows_container = element.find("Rows")
        if rows_container is None:
            rows_container = element.find("row")
        if rows_container is None:
            # Rows might be direct children
            rows_container = element

        row_elements = rows_container.findall("Row") or rows_container.findall("row")

        for row_idx, row_elem in enumerate(row_elements, start=1):
            row_cells: list[dict[str, Any]] = []
            row_height = self._get_float(row_elem, "Height")

            # Find cells in row
            cell_elements = row_elem.findall("Cell") or row_elem.findall("cell")
            col_idx = 1

            for cell_elem in cell_elements:
                cell_data = self._parse_cell_element(cell_elem, row_idx, col_idx)
                cell_data["height"] = row_height
                row_cells.append(cell_data)

                # Account for merged columns
                merge_cols = cell_data.get("merge_column_count", 1)
                col_idx += merge_cols

            rows_data.append(row_cells)

        return rows_data

    def _parse_cell_element(
        self, element: etree._Element, row: int, column: int
    ) -> dict[str, Any]:
        """Parse single cell element."""
        cell_data: dict[str, Any] = {
            "row": row,
            "column": column,
            "text": "",
            "cell_type": CellType.TEXT,
            "parameters": [],
            "style": {},
            "merge_row_count": 1,
            "merge_column_count": 1,
        }

        # Get text content
        text_elem = element.find("Text")
        if text_elem is None:
            text_elem = element.find("text")
        if text_elem is not None and text_elem.text:
            cell_data["text"] = text_elem.text

        # Check for parameter element
        param_elem = element.find("Parameter")
        if param_elem is None:
            param_elem = element.find("parameter")
        if param_elem is not None and param_elem.text:
            cell_data["text"] = f"[{param_elem.text}]"
            cell_data["cell_type"] = CellType.PARAMETER

        # Extract parameters from text
        if cell_data["text"]:
            params = self._extract_parameters(cell_data["text"], row, column)
            cell_data["parameters"] = params
            if params:
                cell_data["cell_type"] = CellType.PARAMETER

        # Parse merge info
        merge_down = self._get_int(element, "MergeDown") or self._get_int(
            element, "RowSpan"
        )
        if merge_down:
            cell_data["merge_row_count"] = merge_down

        merge_right = self._get_int(element, "MergeRight") or self._get_int(
            element, "ColumnSpan"
        )
        if merge_right:
            cell_data["merge_column_count"] = merge_right

        # Parse width
        cell_data["width"] = self._get_float(element, "Width")

        # Parse style
        cell_data["style"] = self._parse_cell_style(element)

        return cell_data

    def _parse_cell_style(self, element: etree._Element) -> dict[str, Any]:
        """Parse cell style attributes."""
        style: dict[str, Any] = {}

        # Font
        font_elem = element.find("Font")
        if font_elem is None:
            font_elem = element.find("font")
        if font_elem is not None:
            style["font_name"] = self._get_text(font_elem, "Name")
            style["font_size"] = self._get_int(font_elem, "Size")
            style["bold"] = self._get_bool(font_elem, "Bold")
            style["italic"] = self._get_bool(font_elem, "Italic")
            style["underline"] = self._get_bool(font_elem, "Underline")

        # Colors
        style["text_color"] = self._get_text(element, "TextColor")
        style["background_color"] = self._get_text(element, "BackgroundColor")

        # Alignment
        h_align = self._get_text(element, "HorizontalAlignment")
        if h_align:
            style["horizontal_alignment"] = self._map_alignment(h_align)

        v_align = self._get_text(element, "VerticalAlignment")
        if v_align:
            style["vertical_alignment"] = self._map_vertical_alignment(v_align)

        # Borders
        style["borders"] = self._parse_borders(element)

        # Word wrap
        style["word_wrap"] = self._get_bool(element, "WordWrap")

        return style

    def _parse_borders(self, element: etree._Element) -> dict[str, BorderStyle]:
        """Parse cell borders."""
        borders = {
            "left": BorderStyle.NONE,
            "right": BorderStyle.NONE,
            "top": BorderStyle.NONE,
            "bottom": BorderStyle.NONE,
        }

        border_elem = element.find("Border")
        if border_elem is None:
            border_elem = element.find("border")
        if border_elem is not None:
            for side in ["Left", "Right", "Top", "Bottom"]:
                side_elem = border_elem.find(side)
                if side_elem is None:
                    side_elem = border_elem.find(side.lower())
                if side_elem is not None:
                    style_text = self._get_text(side_elem, "Style")
                    if style_text:
                        borders[side.lower()] = self._map_border_style(style_text)

        return borders

    def _parse_areas(self, element: etree._Element) -> list[dict[str, Any]]:
        """Parse named areas."""
        areas: list[dict[str, Any]] = []

        # Try different area container names
        areas_container = element.find("Areas")
        if areas_container is None:
            areas_container = element.find("NamedAreas")
        if areas_container is None:
            return areas

        area_elements = areas_container.findall("Area")
        if not area_elements:
            area_elements = areas_container.findall("NamedArea")

        for area_elem in area_elements:
            area_data: dict[str, Any] = {}

            # Name
            area_data["name"] = (
                self._get_text(area_elem, "Name")
                or area_elem.get("name")
                or area_elem.get("Name")
                or ""
            )

            # Boundaries
            area_data["start_row"] = (
                self._get_int(area_elem, "Top")
                or self._get_int(area_elem, "StartRow")
                or 1
            )
            area_data["end_row"] = (
                self._get_int(area_elem, "Bottom")
                or self._get_int(area_elem, "EndRow")
                or area_data["start_row"]
            )
            area_data["start_column"] = (
                self._get_int(area_elem, "Left")
                or self._get_int(area_elem, "StartColumn")
                or 1
            )
            area_data["end_column"] = self._get_int(
                area_elem, "Right"
            ) or self._get_int(area_elem, "EndColumn")

            # Determine area type from name
            area_data["area_type"] = self._determine_area_type(area_data["name"])

            if area_data["name"]:
                areas.append(area_data)

        return areas

    def _create_area(
        self, area_data: dict[str, Any], rows_data: list[list[dict[str, Any]]]
    ) -> MxlArea:
        """Create MxlArea from parsed data."""
        area = MxlArea(
            name=area_data["name"],
            area_type=area_data.get("area_type", AreaType.CUSTOM),
            start_row=area_data["start_row"],
            end_row=area_data["end_row"],
            start_column=area_data.get("start_column", 1),
            end_column=area_data.get("end_column"),
        )

        # Determine if this is a table area
        name_lower = area_data["name"].lower()
        area.is_table_area = any(
            kw in name_lower
            for kw in ["строка", "row", "данные", "detail", "table", "таблица"]
        )

        # Collect cells in this area
        start_row = area_data["start_row"]
        end_row = area_data["end_row"]
        start_col = area_data.get("start_column", 1)
        end_col = area_data.get("end_column")

        for row_idx, row_cells in enumerate(rows_data, start=1):
            if start_row <= row_idx <= end_row:
                for cell_data in row_cells:
                    col = cell_data["column"]
                    if col >= start_col and (end_col is None or col <= end_col):
                        cell = self._create_cell(cell_data)
                        area.cells.append(cell)

                        # Add parameters to area
                        for param in cell.parameters:
                            param.area_name = area.name
                            area.parameters.append(param)

        return area

    def _create_cell(self, cell_data: dict[str, Any]) -> MxlCell:
        """Create MxlCell from parsed data."""
        # Build style
        style_data = cell_data.get("style", {})
        borders_data = style_data.get("borders", {})

        borders = CellBorders(
            left=borders_data.get("left", BorderStyle.NONE),
            right=borders_data.get("right", BorderStyle.NONE),
            top=borders_data.get("top", BorderStyle.NONE),
            bottom=borders_data.get("bottom", BorderStyle.NONE),
        )

        style = CellStyle(
            font_name=style_data.get("font_name"),
            font_size=style_data.get("font_size"),
            bold=style_data.get("bold", False),
            italic=style_data.get("italic", False),
            underline=style_data.get("underline", False),
            text_color=style_data.get("text_color"),
            background_color=style_data.get("background_color"),
            horizontal_alignment=style_data.get(
                "horizontal_alignment", CellAlignment.LEFT
            ),
            vertical_alignment=style_data.get(
                "vertical_alignment", CellVerticalAlignment.CENTER
            ),
            borders=borders,
            word_wrap=style_data.get("word_wrap", False),
        )

        # Build parameters
        parameters = []
        for param_data in cell_data.get("parameters", []):
            if isinstance(param_data, TemplateParameter):
                parameters.append(param_data)
            elif isinstance(param_data, dict):
                parameters.append(TemplateParameter(**param_data))

        return MxlCell(
            row=cell_data["row"],
            column=cell_data["column"],
            text=cell_data.get("text", ""),
            cell_type=cell_data.get("cell_type", CellType.TEXT),
            parameters=parameters,
            style=style,
            merge_row_count=cell_data.get("merge_row_count", 1),
            merge_column_count=cell_data.get("merge_column_count", 1),
            height=cell_data.get("height"),
            width=cell_data.get("width"),
        )

    def _extract_parameters(
        self, text: str, row: int, column: int
    ) -> list[TemplateParameter]:
        """Extract parameters from cell text."""
        parameters: list[TemplateParameter] = []

        # Square brackets [Parameter]
        for match in PARAM_SQUARE_BRACKET.finditer(text):
            param_name = match.group(1).strip()
            param = self._create_parameter(param_name, text, row, column)
            parameters.append(param)

        # Angle brackets <Parameter> (if not XML tag)
        for match in PARAM_ANGLE_BRACKET.finditer(text):
            param_name = match.group(1).strip()
            # Skip common XML/HTML tags
            if param_name.lower() not in {"b", "i", "u", "br", "p", "span", "div"}:
                param = self._create_parameter(param_name, text, row, column)
                parameters.append(param)

        # Curly braces {Parameter}
        for match in PARAM_CURLY_BRACKET.finditer(text):
            param_name = match.group(1).strip()
            param = self._create_parameter(param_name, text, row, column)
            param.is_expression = True
            parameters.append(param)

        return parameters

    def _create_parameter(
        self, name: str, raw_text: str, row: int, column: int
    ) -> TemplateParameter:
        """Create TemplateParameter from extracted name."""
        # Detect parameter type from name
        param_type = ParameterType.TEXT

        name_lower = name.lower()
        if "." in name:
            # Data path like Object.Contractor.Name
            param_type = ParameterType.DATA_PATH
        elif any(kw in name_lower for kw in ["дата", "date", "период", "period"]):
            param_type = ParameterType.DATE
        elif any(kw in name_lower for kw in ["сумма", "amount", "количество", "qty"]):
            param_type = ParameterType.NUMBER
        elif any(kw in name_lower for kw in ["картинка", "image", "picture", "logo"]):
            param_type = ParameterType.PICTURE

        # Extract data path if present
        data_path = None
        if "." in name:
            data_path = name

        return TemplateParameter(
            name=name,
            display_name=name,
            parameter_type=param_type,
            row=row,
            column=column,
            data_path=data_path,
            raw_text=raw_text,
        )

    def _aggregate_parameters(self, document: MxlDocument) -> None:
        """Aggregate all parameters from areas into document."""
        seen_names: set[str] = set()

        for area in document.areas:
            for param in area.parameters:
                if param.name not in seen_names:
                    document.parameters.append(param)
                    seen_names.add(param.name)

        # Also from header/footer cells
        for cell in document.header_cells + document.footer_cells:
            for param in cell.parameters:
                if param.name not in seen_names:
                    document.parameters.append(param)
                    seen_names.add(param.name)

    def _extract_object_info(self, document: MxlDocument, path: Path) -> None:
        """Extract object info from file path."""
        parts = path.parts

        # Try to find object type and name from path
        # Common patterns:
        # - Documents/DocName/Templates/TemplateName/...
        # - Catalogs/CatName/Templates/TemplateName/...

        for i, part in enumerate(parts):
            if part in ("Documents", "Документы"):
                document.object_type = "Document"
                if i + 1 < len(parts):
                    document.object_name = parts[i + 1]
            elif part in ("Catalogs", "Справочники"):
                document.object_type = "Catalog"
                if i + 1 < len(parts):
                    document.object_name = parts[i + 1]
            elif part in ("DataProcessors", "Обработки"):
                document.object_type = "DataProcessor"
                if i + 1 < len(parts):
                    document.object_name = parts[i + 1]
            elif part in ("Reports", "Отчеты"):
                document.object_type = "Report"
                if i + 1 < len(parts):
                    document.object_name = parts[i + 1]
            elif part in ("Templates", "Макеты"):
                if i + 1 < len(parts):
                    document.template_name = parts[i + 1]

    def _determine_area_type(self, name: str) -> AreaType:
        """Determine area type from name."""
        name_lower = name.lower()

        # Check more specific patterns first (table-related)
        if any(kw in name_lower for kw in ["шапкатаблицы", "tableheader", "колонки"]):
            return AreaType.TABLE_HEADER
        elif any(kw in name_lower for kw in ["итогтаблицы", "tablefooter"]):
            return AreaType.TABLE_FOOTER
        elif any(kw in name_lower for kw in ["группа", "group"]):
            if "шапка" in name_lower or "header" in name_lower:
                return AreaType.GROUP_HEADER
            elif "подвал" in name_lower or "footer" in name_lower:
                return AreaType.GROUP_FOOTER
        # Check general patterns after specific ones
        elif any(kw in name_lower for kw in ["шапка", "header", "заголовок"]):
            return AreaType.HEADER
        elif any(kw in name_lower for kw in ["подвал", "footer", "итог"]):
            return AreaType.FOOTER
        elif any(
            kw in name_lower for kw in ["строка", "row", "detail", "данные", "table"]
        ):
            return AreaType.TABLE_ROW

        return AreaType.CUSTOM

    def _map_alignment(self, value: str) -> CellAlignment:
        """Map alignment string to enum."""
        value_lower = value.lower()
        if value_lower in ("left", "лево"):
            return CellAlignment.LEFT
        elif value_lower in ("center", "центр"):
            return CellAlignment.CENTER
        elif value_lower in ("right", "право"):
            return CellAlignment.RIGHT
        elif value_lower in ("justify", "поширине"):
            return CellAlignment.JUSTIFY
        return CellAlignment.LEFT

    def _map_vertical_alignment(self, value: str) -> CellVerticalAlignment:
        """Map vertical alignment string to enum."""
        value_lower = value.lower()
        if value_lower in ("top", "верх"):
            return CellVerticalAlignment.TOP
        elif value_lower in ("center", "центр"):
            return CellVerticalAlignment.CENTER
        elif value_lower in ("bottom", "низ"):
            return CellVerticalAlignment.BOTTOM
        return CellVerticalAlignment.CENTER

    def _map_border_style(self, value: str) -> BorderStyle:
        """Map border style string to enum."""
        value_lower = value.lower()
        mapping = {
            "none": BorderStyle.NONE,
            "thin": BorderStyle.THIN,
            "medium": BorderStyle.MEDIUM,
            "thick": BorderStyle.THICK,
            "double": BorderStyle.DOUBLE,
            "dashed": BorderStyle.DASHED,
            "dotted": BorderStyle.DOTTED,
        }
        return mapping.get(value_lower, BorderStyle.THIN)

    # Helper methods for XML parsing

    def _get_text(self, element: etree._Element, tag: str) -> str | None:
        """Get text content of child element."""
        child = element.find(tag)
        if child is None:
            child = element.find(tag.lower())
        if child is not None and child.text:
            return child.text.strip()
        return element.get(tag) or element.get(tag.lower())

    def _get_int(self, element: etree._Element, tag: str) -> int | None:
        """Get integer value from child element."""
        text = self._get_text(element, tag)
        if text:
            try:
                return int(text)
            except ValueError:
                pass
        return None

    def _get_float(self, element: etree._Element, tag: str) -> float | None:
        """Get float value from child element."""
        text = self._get_text(element, tag)
        if text:
            try:
                return float(text)
            except ValueError:
                pass
        return None

    def _get_bool(self, element: etree._Element, tag: str) -> bool:
        """Get boolean value from child element."""
        text = self._get_text(element, tag)
        if text:
            return text.lower() in ("true", "1", "да", "yes")
        return False
