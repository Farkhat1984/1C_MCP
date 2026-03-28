"""Security tests for input validation and injection prevention."""

from pathlib import Path

import pytest
from lxml import etree

from mcp_1c.tools.base import ToolError, parse_metadata_type


# ---------------------------------------------------------------------------
# XXE Protection
# ---------------------------------------------------------------------------


class TestXXEProtection:
    """Verify XML parsers are hardened against XXE (XML External Entity) attacks."""

    def test_metadata_parser_blocks_entity_resolution(self) -> None:
        """Metadata parser must not resolve external entities."""
        from mcp_1c.engines.metadata.parser import _SECURE_PARSER

        xxe_xml = b"""<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/hostname">
]>
<Root>&xxe;</Root>"""
        # Secure parser should either raise or return unexpanded entity
        try:
            tree = etree.fromstring(xxe_xml, _SECURE_PARSER)
            # If parsed, text must NOT contain resolved content
            text = tree.text or ""
            assert text == "", f"Entity was resolved to: {text!r}"
        except etree.XMLSyntaxError:
            pass  # Raising is the preferred secure behavior

    def test_mxl_parser_blocks_entity_resolution(self) -> None:
        """MXL parser must not resolve external entities."""
        from mcp_1c.engines.mxl.parser import _SECURE_PARSER

        xxe_xml = b"""<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/hostname">
]>
<Root>&xxe;</Root>"""
        try:
            tree = etree.fromstring(xxe_xml, _SECURE_PARSER)
            text = tree.text or ""
            assert text == "", f"Entity was resolved to: {text!r}"
        except etree.XMLSyntaxError:
            pass

    def test_xxe_file_payload_blocked(self, tmp_path: Path) -> None:
        """XXE file:// entity in metadata XML must not leak file contents."""
        from mcp_1c.engines.metadata.parser import XmlParser

        xxe_xml = '''<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
    <Configuration>
        <Name>&xxe;</Name>
        <ChildObjects/>
    </Configuration>
</MetaDataObject>'''
        config_root = tmp_path / "XXETest"
        config_root.mkdir()
        xml_file = config_root / "Configuration.xml"
        xml_file.write_text(xxe_xml, encoding="utf-8")

        parser = XmlParser()
        # Either raises or parses without resolving the entity
        try:
            result = parser.parse_configuration(config_root)
        except etree.XMLSyntaxError:
            return  # Raising is acceptable

        # If it parsed, /etc/passwd contents must not appear in any value
        for type_name, names in result.items():
            for name in names:
                assert "root:" not in name, "XXE entity was resolved!"

    def test_xxe_mxl_payload_blocked(self) -> None:
        """XXE in MXL content must not leak file contents."""
        from mcp_1c.engines.mxl.parser import MxlParser

        xxe_content = b"""<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<SpreadsheetDocument>
    <Rows>
        <Row><Cell><Text>&xxe;</Text></Cell></Row>
    </Rows>
</SpreadsheetDocument>"""

        parser = MxlParser()
        result = parser.parse_content(xxe_content, source_path="xxe.mxl")

        if result.success and result.document:
            for cell in result.document.header_cells:
                assert "root:" not in cell.text, "XXE entity was resolved in MXL!"
        # Failure is also acceptable (parser rejects the DTD)


# ---------------------------------------------------------------------------
# Path Traversal
# ---------------------------------------------------------------------------


class TestPathTraversal:
    """Test that path traversal characters are rejected where appropriate."""

    def test_metadata_type_with_path_chars(self) -> None:
        """parse_metadata_type rejects strings with path traversal."""
        with pytest.raises(ToolError):
            parse_metadata_type("../../../etc/passwd")

    def test_metadata_type_with_null_bytes(self) -> None:
        """Null bytes in metadata type string are rejected."""
        with pytest.raises(ToolError):
            parse_metadata_type("Catalog\x00.evil")

    def test_metadata_type_with_slashes(self) -> None:
        with pytest.raises(ToolError):
            parse_metadata_type("Catalog/../../secret")

    def test_metadata_type_with_backslashes(self) -> None:
        with pytest.raises(ToolError):
            parse_metadata_type("Catalog\\..\\secret")


# ---------------------------------------------------------------------------
# Input Validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Test that tool input validation rejects dangerous payloads."""

    def test_metadata_type_sql_injection(self) -> None:
        """SQL injection attempts in metadata type are rejected."""
        with pytest.raises(ToolError):
            parse_metadata_type("Catalog'; DROP TABLE metadata; --")

    def test_metadata_type_script_injection(self) -> None:
        """Script tags in metadata type are rejected."""
        with pytest.raises(ToolError):
            parse_metadata_type("<script>alert(1)</script>")

    def test_very_long_input(self) -> None:
        """Extremely long strings are rejected (not a valid type)."""
        with pytest.raises(ToolError):
            parse_metadata_type("A" * 10_000)
