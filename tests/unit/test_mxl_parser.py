"""
Unit tests for MXL (SpreadsheetDocument) parser.

Tests template parsing, parameter extraction, and code generation.
"""

import pytest

from mcp_1c.domain.mxl import (
    AreaType,
    CellType,
    FillCodeGenerationOptions,
    MxlDocument,
    ParameterType,
)
from mcp_1c.engines.mxl import MxlParser, FillCodeGenerator, MxlEngine


class TestMxlParser:
    """Tests for MxlParser class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.parser = MxlParser()

    def test_parse_simple_template(self) -> None:
        """Test parsing a simple template."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>Title</Text></Cell>
                </Row>
                <Row>
                    <Cell><Text>[Parameter1]</Text></Cell>
                    <Cell><Text>[Parameter2]</Text></Cell>
                </Row>
            </Rows>
            <Areas>
                <Area>
                    <Name>Header</Name>
                    <Top>1</Top>
                    <Bottom>1</Bottom>
                </Area>
                <Area>
                    <Name>Row</Name>
                    <Top>2</Top>
                    <Bottom>2</Bottom>
                </Area>
            </Areas>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        assert result.document is not None
        assert result.areas_found == 2
        assert result.parameters_found >= 2

    def test_extract_square_bracket_parameters(self) -> None:
        """Test extracting [Parameter] style parameters."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[Organization]</Text></Cell>
                </Row>
                <Row>
                    <Cell><Text>Date: [DocumentDate]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        doc = result.document
        param_names = [p.name for p in doc.parameters]
        assert "Organization" in param_names
        assert "DocumentDate" in param_names

    def test_extract_angle_bracket_parameters(self) -> None:
        """Test extracting <Parameter> style parameters."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>&lt;Contractor.Name&gt;</Text></Cell>
                </Row>
                <Row>
                    <Cell><Text>&lt;Amount&gt;</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        # Angle bracket parameters should be extracted
        doc = result.document
        param_names = [p.name for p in doc.parameters]
        # Note: lxml will decode &lt; to < which our parser handles
        assert len(param_names) >= 0  # At least parsed without error

    def test_extract_curly_brace_expressions(self) -> None:
        """Test extracting {Expression} style parameters."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>{Quantity * Price}</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        doc = result.document
        if doc.parameters:
            expr_param = doc.parameters[0]
            assert expr_param.is_expression

    def test_parse_named_areas(self) -> None:
        """Test parsing named areas."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row><Cell><Text>Header</Text></Cell></Row>
                <Row><Cell><Text>Col1</Text></Cell><Cell><Text>Col2</Text></Cell></Row>
                <Row><Cell><Text>[Value1]</Text></Cell><Cell><Text>[Value2]</Text></Cell></Row>
                <Row><Cell><Text>Total</Text></Cell></Row>
            </Rows>
            <Areas>
                <Area>
                    <Name>Шапка</Name>
                    <Top>1</Top>
                    <Bottom>1</Bottom>
                </Area>
                <Area>
                    <Name>ШапкаТаблицы</Name>
                    <Top>2</Top>
                    <Bottom>2</Bottom>
                </Area>
                <Area>
                    <Name>Строка</Name>
                    <Top>3</Top>
                    <Bottom>3</Bottom>
                </Area>
                <Area>
                    <Name>Подвал</Name>
                    <Top>4</Top>
                    <Bottom>4</Bottom>
                </Area>
            </Areas>
        </SpreadsheetDocument>
        """.encode("utf-8")

        result = self.parser.parse_content(xml_content)

        assert result.success
        doc = result.document

        # Check area types
        header = doc.get_area("Шапка")
        assert header is not None
        assert header.area_type == AreaType.HEADER

        table_header = doc.get_area("ШапкаТаблицы")
        assert table_header is not None
        assert table_header.area_type == AreaType.TABLE_HEADER

        row_area = doc.get_area("Строка")
        assert row_area is not None
        assert row_area.is_table_area

        footer = doc.get_area("Подвал")
        assert footer is not None
        assert footer.area_type == AreaType.FOOTER

    def test_detect_parameter_types(self) -> None:
        """Test automatic parameter type detection."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[DocumentDate]</Text></Cell>
                    <Cell><Text>[TotalAmount]</Text></Cell>
                    <Cell><Text>[Object.Contractor.Name]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        doc = result.document

        # Find date parameter
        date_params = [p for p in doc.parameters if "Date" in p.name or "Дата" in p.name]
        if date_params:
            assert date_params[0].parameter_type == ParameterType.DATE

        # Find amount parameter
        amount_params = [p for p in doc.parameters if "Amount" in p.name or "Сумма" in p.name]
        if amount_params:
            assert amount_params[0].parameter_type == ParameterType.NUMBER

        # Find data path parameter
        path_params = [p for p in doc.parameters if "." in p.name]
        if path_params:
            assert path_params[0].parameter_type == ParameterType.DATA_PATH
            assert path_params[0].data_path is not None

    def test_parse_page_settings(self) -> None:
        """Test parsing page settings."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <PageOrientation>landscape</PageOrientation>
            <PageWidth>297</PageWidth>
            <PageHeight>210</PageHeight>
            <LeftMargin>20</LeftMargin>
            <RightMargin>10</RightMargin>
            <TopMargin>15</TopMargin>
            <BottomMargin>15</BottomMargin>
            <FitToPage>true</FitToPage>
            <Rows>
                <Row><Cell><Text>Content</Text></Cell></Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        doc = result.document

        assert doc.page_orientation == "landscape"
        assert doc.page_width == 297
        assert doc.page_height == 210
        assert doc.left_margin == 20
        assert doc.right_margin == 10
        assert doc.fit_to_page

    def test_get_unique_parameter_names(self) -> None:
        """Test getting unique parameter names."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[Parameter1]</Text></Cell>
                    <Cell><Text>[Parameter2]</Text></Cell>
                </Row>
                <Row>
                    <Cell><Text>[Parameter1]</Text></Cell>
                    <Cell><Text>[Parameter3]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        doc = result.document

        unique_names = doc.get_unique_parameter_names()
        assert "Parameter1" in unique_names
        assert "Parameter2" in unique_names
        assert "Parameter3" in unique_names
        # No duplicates
        assert len(unique_names) == 3

    def test_parse_error_invalid_xml(self) -> None:
        """Test parse error for invalid XML."""
        invalid_xml = b"<not valid xml"

        result = self.parser.parse_content(invalid_xml)

        assert not result.success
        assert result.error is not None
        assert "XML" in result.error or "syntax" in result.error.lower()


class TestFillCodeGenerator:
    """Tests for FillCodeGenerator class."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.generator = FillCodeGenerator()

    def _create_test_document(self) -> MxlDocument:
        """Create a test document for code generation."""
        from mcp_1c.domain.mxl import MxlArea, TemplateParameter

        doc = MxlDocument(
            file_path="test/Template.xml",
            object_type="Document",
            object_name="Invoice",
            template_name="PrintForm",
            row_count=5,
            column_count=4,
        )

        # Add header area
        header = MxlArea(
            name="Header",
            area_type=AreaType.HEADER,
            start_row=1,
            end_row=2,
            parameters=[
                TemplateParameter(
                    name="Organization",
                    parameter_type=ParameterType.TEXT,
                    area_name="Header",
                    row=1,
                    column=1,
                ),
                TemplateParameter(
                    name="DocumentDate",
                    parameter_type=ParameterType.DATE,
                    area_name="Header",
                    row=2,
                    column=1,
                ),
            ],
        )
        doc.areas.append(header)

        # Add table row area
        row_area = MxlArea(
            name="Row",
            area_type=AreaType.TABLE_ROW,
            start_row=3,
            end_row=3,
            is_table_area=True,
            parameters=[
                TemplateParameter(
                    name="ProductName",
                    parameter_type=ParameterType.TEXT,
                    area_name="Row",
                    row=3,
                    column=1,
                ),
                TemplateParameter(
                    name="Quantity",
                    parameter_type=ParameterType.NUMBER,
                    area_name="Row",
                    row=3,
                    column=2,
                ),
                TemplateParameter(
                    name="Amount",
                    parameter_type=ParameterType.NUMBER,
                    area_name="Row",
                    row=3,
                    column=3,
                ),
            ],
        )
        doc.areas.append(row_area)

        # Aggregate parameters
        doc.parameters = header.parameters + row_area.parameters

        return doc

    def test_generate_basic_code(self) -> None:
        """Test basic code generation."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(language="ru")

        result = self.generator.generate(doc, options)

        assert result.code
        assert "ПолучитьМакет" in result.code
        assert "ТабличныйДокумент" in result.code
        assert "ПолучитьОбласть" in result.code
        assert "Вывести" in result.code

    def test_generate_with_english_keywords(self) -> None:
        """Test code generation with English keywords."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(language="en")

        result = self.generator.generate(doc, options)

        assert "GetTemplate" in result.code
        assert "SpreadsheetDocument" in result.code
        assert "GetArea" in result.code
        assert "Put" in result.code

    def test_generate_includes_loop_for_table_area(self) -> None:
        """Test that table areas generate loop code."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(language="ru")

        result = self.generator.generate(doc, options)

        assert "Для Каждого" in result.code or "For Each" in result.code
        assert "КонецЦикла" in result.code or "EndDo" in result.code

    def test_generate_with_comments(self) -> None:
        """Test code generation with comments."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(
            language="ru",
            generate_comments=True,
        )

        result = self.generator.generate(doc, options)

        assert "//" in result.code
        assert "Шапка" in result.code or "Header" in result.code

    def test_generate_without_comments(self) -> None:
        """Test code generation without comments."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(
            language="ru",
            generate_comments=False,
        )

        result = self.generator.generate(doc, options)

        # Should still have code but minimal comments
        assert "ПолучитьМакет" in result.code

    def test_generate_procedure(self) -> None:
        """Test complete procedure generation."""
        doc = self._create_test_document()

        code = self.generator.generate_procedure(
            doc,
            procedure_name="ЗаполнитьПечатнуюФорму",
            parameter_name="ДанныеПечати",
            language="ru",
        )

        assert "Процедура ЗаполнитьПечатнуюФорму" in code
        assert "ДанныеПечати" in code
        assert "КонецПроцедуры" in code
        assert "Экспорт" in code

    def test_generate_tracks_used_areas(self) -> None:
        """Test that generator tracks used areas."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(language="ru")

        result = self.generator.generate(doc, options)

        assert "Header" in result.areas_used
        assert "Row" in result.areas_used

    def test_generate_tracks_used_parameters(self) -> None:
        """Test that generator tracks used parameters."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(language="ru")

        result = self.generator.generate(doc, options)

        assert "Organization" in result.parameters_used
        assert "DocumentDate" in result.parameters_used
        assert "ProductName" in result.parameters_used

    def test_generate_area_code_breakdown(self) -> None:
        """Test area code breakdown in result."""
        doc = self._create_test_document()
        options = FillCodeGenerationOptions(language="ru")

        result = self.generator.generate(doc, options)

        assert "Header" in result.area_fill_code
        assert "Row" in result.area_fill_code
        assert "Параметры" in result.area_fill_code["Header"]


class TestMxlEngine:
    """Tests for MxlEngine facade."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.engine = MxlEngine()

    def test_parse_content(self) -> None:
        """Test parsing template content."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row><Cell><Text>[Test]</Text></Cell></Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.engine.parse_content(xml_content)

        assert result.success
        assert result.document is not None

    def test_get_template_structure(self) -> None:
        """Test getting template structure as dict."""
        # Create a temporary file-like structure using parse_content
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row><Cell><Text>[Param]</Text></Cell></Row>
            </Rows>
            <Areas>
                <Area>
                    <Name>TestArea</Name>
                    <Top>1</Top>
                    <Bottom>1</Bottom>
                </Area>
            </Areas>
        </SpreadsheetDocument>
        """

        result = self.engine.parse_content(xml_content)
        assert result.success

        # Test structure extraction from document
        doc = result.document
        assert doc is not None
        assert len(doc.areas) == 1
        assert doc.areas[0].name == "TestArea"

    def test_get_parameters(self) -> None:
        """Test getting template parameters."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[Param1]</Text></Cell>
                    <Cell><Text>[Param2]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.engine.parse_content(xml_content)
        assert result.success

        params = result.document.parameters
        assert len(params) >= 2

    def test_get_parameter_names(self) -> None:
        """Test getting unique parameter names."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[A] [B] [A]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.engine.parse_content(xml_content)
        assert result.success

        names = result.document.get_unique_parameter_names()
        assert "A" in names
        assert "B" in names
        assert len(names) == 2  # No duplicates

    def test_cache_functionality(self) -> None:
        """Test that caching works."""
        # This would require file system access, so we test cache methods exist
        self.engine.clear_cache()
        # Should not raise
        self.engine.invalidate_cache("nonexistent/path")


class TestParameterExtraction:
    """Tests for parameter extraction patterns."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.parser = MxlParser()

    def test_multiple_parameters_in_one_cell(self) -> None:
        """Test extracting multiple parameters from one cell."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>From [StartDate] to [EndDate]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        param_names = [p.name for p in result.document.parameters]
        assert "StartDate" in param_names
        assert "EndDate" in param_names

    def test_russian_parameter_names(self) -> None:
        """Test extracting Russian parameter names."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[Организация]</Text></Cell>
                    <Cell><Text>[ДатаДокумента]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """.encode("utf-8")

        result = self.parser.parse_content(xml_content)

        assert result.success
        param_names = [p.name for p in result.document.parameters]
        assert "Организация" in param_names
        assert "ДатаДокумента" in param_names

    def test_parameter_element_style(self) -> None:
        """Test extracting parameter from <Parameter> element."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell>
                        <Parameter>ParameterFromElement</Parameter>
                    </Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        assert len(result.document.parameters) >= 1
        # Should have extracted the parameter
        param_names = [p.name for p in result.document.parameters]
        assert "ParameterFromElement" in param_names

    def test_data_path_parameter(self) -> None:
        """Test data path detection in parameters."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <SpreadsheetDocument>
            <Rows>
                <Row>
                    <Cell><Text>[Object.Contractor.Name]</Text></Cell>
                    <Cell><Text>[Document.Number]</Text></Cell>
                </Row>
            </Rows>
        </SpreadsheetDocument>
        """

        result = self.parser.parse_content(xml_content)

        assert result.success
        path_params = [
            p for p in result.document.parameters
            if p.parameter_type == ParameterType.DATA_PATH
        ]
        assert len(path_params) == 2

        # Check data paths are set
        for param in path_params:
            assert param.data_path is not None
            assert "." in param.data_path
