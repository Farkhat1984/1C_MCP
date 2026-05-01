"""Tests for error handling paths across engines and tools."""

from pathlib import Path
from typing import Any

import pytest

from mcp_1c.domain.code import DependencyGraph
from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.mxl.parser import MxlParser
from mcp_1c.tools.base import BaseTool, ToolError, parse_metadata_type

# ---------------------------------------------------------------------------
# parse_metadata_type
# ---------------------------------------------------------------------------


class TestParseMetadataType:
    """Test parse_metadata_type error handling."""

    def test_valid_english_type(self) -> None:
        result = parse_metadata_type("Catalog")
        assert result == MetadataType.CATALOG

    def test_valid_russian_type(self) -> None:
        result = parse_metadata_type("Справочник")
        assert result == MetadataType.CATALOG

    def test_valid_russian_plural(self) -> None:
        result = parse_metadata_type("Документы")
        assert result == MetadataType.DOCUMENT

    def test_unknown_type_raises_tool_error(self) -> None:
        with pytest.raises(ToolError, match="Unknown metadata type"):
            parse_metadata_type("НесуществующийТип")

    def test_empty_string_raises_tool_error(self) -> None:
        with pytest.raises(ToolError):
            parse_metadata_type("")

    @pytest.mark.parametrize(
        "bad_input",
        [
            "catalog",  # wrong case (enum values are capitalized)
            "  ",
            "123",
            "Catalog;DROP TABLE",
        ],
    )
    def test_invalid_strings_raise_tool_error(self, bad_input: str) -> None:
        with pytest.raises(ToolError):
            parse_metadata_type(bad_input)


# ---------------------------------------------------------------------------
# BaseTool.run() required-parameter validation
# ---------------------------------------------------------------------------


class _StubTool(BaseTool):
    """Minimal concrete tool for testing BaseTool.run()."""

    name = "test.stub"
    description = "Stub for tests"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string"},
        },
        "required": ["name", "type"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
        return {"ok": True}


class TestBaseToolRequiredParams:
    """Test required parameter validation in BaseTool.run()."""

    @pytest.fixture
    def tool(self) -> _StubTool:
        return _StubTool()

    @pytest.mark.asyncio
    async def test_missing_required_param(self, tool: _StubTool) -> None:
        result = await tool.run({})
        assert "error" in result
        assert "name" in result  # mentions the missing field

    @pytest.mark.asyncio
    async def test_none_required_param(self, tool: _StubTool) -> None:
        result = await tool.run({"name": None, "type": "x"})
        assert "error" in result
        assert "name" in result

    @pytest.mark.asyncio
    async def test_partial_required_params(self, tool: _StubTool) -> None:
        result = await tool.run({"name": "test"})
        assert "error" in result
        assert "type" in result

    @pytest.mark.asyncio
    async def test_valid_params_pass(self, tool: _StubTool) -> None:
        result = await tool.run({"name": "test", "type": "x"})
        assert "ok" in result
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_tool_error_in_execute_returns_error_json(self) -> None:
        """ToolError raised inside execute() is caught and serialized."""

        class _FailTool(BaseTool):
            name = "test.fail"
            description = "Always fails"
            input_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

            async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
                raise ToolError("something broke", code="BROKEN")

        tool = _FailTool()
        result = await tool.run({})
        assert "something broke" in result
        assert "BROKEN" in result


# ---------------------------------------------------------------------------
# XmlParser error paths
# ---------------------------------------------------------------------------


class TestXmlParserErrors:
    """Test XmlParser with corrupted / invalid input."""

    @pytest.fixture
    def parser(self) -> XmlParser:
        return XmlParser()

    def test_corrupted_xml(self, parser: XmlParser, tmp_path: Path) -> None:
        """Corrupted XML should raise lxml.etree.XMLSyntaxError."""
        from lxml import etree

        config_root = tmp_path / "Broken"
        config_root.mkdir()
        xml_file = config_root / "Configuration.xml"
        xml_file.write_text("<broken>>><not xml", encoding="utf-8")

        with pytest.raises(etree.XMLSyntaxError):
            parser.parse_configuration(config_root)

    def test_empty_xml_file(self, parser: XmlParser, tmp_path: Path) -> None:
        """Empty XML file should raise an error."""
        from lxml import etree

        config_root = tmp_path / "Empty"
        config_root.mkdir()
        xml_file = config_root / "Configuration.xml"
        xml_file.write_text("", encoding="utf-8")

        with pytest.raises(etree.XMLSyntaxError):
            parser.parse_configuration(config_root)

    def test_valid_xml_but_no_metadata(self, parser: XmlParser, tmp_path: Path) -> None:
        """Valid XML without expected metadata structure returns empty dict."""
        config_root = tmp_path / "NoMeta"
        config_root.mkdir()
        xml_file = config_root / "Configuration.xml"
        xml_file.write_text(
            '<?xml version="1.0"?><Root><Unrelated/></Root>',
            encoding="utf-8",
        )

        result = parser.parse_configuration(config_root)
        assert result == {}

    def test_missing_configuration_xml(self, parser: XmlParser, tmp_path: Path) -> None:
        """Missing Configuration.xml raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parser.parse_configuration(tmp_path)

    def test_parse_nonexistent_object_returns_minimal(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Parsing a non-existent object returns stub with empty attributes."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "НеСуществует",
        )
        assert obj.name == "НеСуществует"
        assert obj.metadata_type == MetadataType.CATALOG
        assert len(obj.attributes) == 0


# ---------------------------------------------------------------------------
# MxlParser error paths
# ---------------------------------------------------------------------------


class TestMxlParserErrors:
    """Test MxlParser with invalid / empty content."""

    @pytest.fixture
    def parser(self) -> MxlParser:
        return MxlParser()

    def test_invalid_xml_content(self, parser: MxlParser) -> None:
        result = parser.parse_content(b"<not valid xml>>>", source_path="test.mxl")
        assert result.success is False
        assert result.error is not None
        assert "XML syntax error" in result.error

    def test_empty_content(self, parser: MxlParser) -> None:
        result = parser.parse_content(b"", source_path="test.mxl")
        assert result.success is False
        assert result.error is not None

    def test_unknown_root_element(self, parser: MxlParser) -> None:
        content = b'<?xml version="1.0"?><UnknownRoot><Child/></UnknownRoot>'
        result = parser.parse_content(content, source_path="test.mxl")
        assert result.success is False
        assert "Unknown root element" in (result.error or "")

    def test_file_not_found(self, parser: MxlParser) -> None:
        result = parser.parse_file("/nonexistent/path/template.mxl")
        assert result.success is False
        assert "not found" in (result.error or "").lower()

    def test_valid_but_empty_spreadsheet(self, parser: MxlParser) -> None:
        """A valid SpreadsheetDocument with no rows/areas parses successfully."""
        content = b'<?xml version="1.0"?><SpreadsheetDocument></SpreadsheetDocument>'
        result = parser.parse_content(content, source_path="empty.mxl")
        assert result.success is True
        assert result.document is not None
        assert result.areas_found == 0
        assert result.cells_parsed == 0


# ---------------------------------------------------------------------------
# DependencyGraph cycle detection
# ---------------------------------------------------------------------------


class TestDependencyGraphCycles:
    """Test DependencyGraph behavior with circular dependencies."""

    def test_cycle_does_not_infinite_loop(self) -> None:
        """A -> B -> C -> A cycle must not cause infinite recursion."""
        graph = DependencyGraph()
        graph.add_node("A", "procedure")
        graph.add_node("B", "procedure")
        graph.add_node("C", "procedure")

        graph.add_edge("A", "B", "calls")
        graph.add_edge("B", "C", "calls")
        graph.add_edge("C", "A", "calls")

        # get_dependencies with sufficient depth should terminate
        deps = graph.get_dependencies("A", depth=10)
        assert deps["node"] == "A"
        # The cycle should be detected and traversal stopped
        # (visited set prevents re-entry)

    def test_self_cycle(self) -> None:
        """A procedure calling itself should not infinite-loop."""
        graph = DependencyGraph()
        graph.add_node("A", "procedure")
        graph.add_edge("A", "A", "calls")

        deps = graph.get_dependencies("A", depth=5)
        assert deps["node"] == "A"

    def test_callees_callers_with_cycle(self) -> None:
        """get_callees / get_callers are simple edge lookups, unaffected by cycles."""
        graph = DependencyGraph()
        graph.add_edge("A", "B", "calls")
        graph.add_edge("B", "A", "calls")

        assert "B" in graph.get_callees("A")
        assert "A" in graph.get_callees("B")
        assert "B" in graph.get_callers("A")
        assert "A" in graph.get_callers("B")

    def test_deep_dag_does_not_overflow(self) -> None:
        """A linear chain of 500 nodes with depth=500 must not overflow.

        This guards against future regressions where someone removes the
        ``_visited`` set assuming acyclic inputs are safe — Python's
        default recursion limit is 1000 and stack frames here are small,
        but the structure must remain iterative-friendly.
        """
        graph = DependencyGraph()
        for i in range(500):
            graph.add_node(f"N{i}", "procedure")
        for i in range(499):
            graph.add_edge(f"N{i}", f"N{i+1}", "calls")

        deps = graph.get_dependencies("N0", depth=500)
        assert deps["node"] == "N0"

    def test_dense_graph_with_overlapping_paths(self) -> None:
        """Diamond: A->B, A->C, B->D, C->D — D must not be re-walked."""
        graph = DependencyGraph()
        for n in ("A", "B", "C", "D"):
            graph.add_node(n, "procedure")
        graph.add_edge("A", "B", "calls")
        graph.add_edge("A", "C", "calls")
        graph.add_edge("B", "D", "calls")
        graph.add_edge("C", "D", "calls")

        deps = graph.get_dependencies("A", depth=10)
        assert deps["node"] == "A"


# ---------------------------------------------------------------------------
# Empty inputs to engines
# ---------------------------------------------------------------------------


class TestEmptyInputs:
    """Test engines gracefully handle empty / missing inputs."""

    def test_xml_parser_empty_config_folder(self, tmp_path: Path) -> None:
        """Config folder with no Configuration.xml raises FileNotFoundError."""
        parser = XmlParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_configuration(tmp_path)

    def test_mxl_parser_empty_areas(self) -> None:
        """Template with rows but no named areas still parses cells."""
        parser = MxlParser()
        content = b"""<?xml version="1.0"?>
        <SpreadsheetDocument>
            <Rows>
                <Row><Cell><Text>hello</Text></Cell></Row>
            </Rows>
        </SpreadsheetDocument>"""
        result = parser.parse_content(content, source_path="no_areas.mxl")
        assert result.success is True
        assert result.areas_found == 0
        # Cells should still be captured as header cells
        assert result.document is not None
        assert len(result.document.header_cells) >= 1

    def test_dependency_graph_empty(self) -> None:
        """Empty graph returns empty callees/callers."""
        graph = DependencyGraph()
        assert graph.get_callees("nonexistent") == []
        assert graph.get_callers("nonexistent") == []

    def test_dependency_graph_get_dependencies_unknown_node(self) -> None:
        """get_dependencies for unknown node returns stub dict."""
        graph = DependencyGraph()
        deps = graph.get_dependencies("missing", depth=3)
        assert deps["node"] == "missing"
        assert deps["callees"] == []
