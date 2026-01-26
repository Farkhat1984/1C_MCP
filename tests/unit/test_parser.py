"""
Unit tests for XML Parser.

Tests Configuration.xml parsing and metadata object parsing.
"""

from pathlib import Path

import pytest

from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.domain.metadata import MetadataType


class TestXmlParser:
    """Test suite for XmlParser."""

    @pytest.fixture
    def parser(self) -> XmlParser:
        """Create parser instance."""
        return XmlParser()

    def test_parse_configuration_returns_objects(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test that parse_configuration returns dict with objects."""
        result = parser.parse_configuration(mock_config_path)

        assert isinstance(result, dict)
        assert len(result) > 0

    def test_parse_configuration_finds_catalogs(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test that catalogs are found in configuration."""
        result = parser.parse_configuration(mock_config_path)

        assert MetadataType.CATALOG.value in result
        catalogs = result[MetadataType.CATALOG.value]
        assert "Товары" in catalogs
        assert "Контрагенты" in catalogs

    def test_parse_configuration_finds_documents(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test that documents are found in configuration."""
        result = parser.parse_configuration(mock_config_path)

        assert MetadataType.DOCUMENT.value in result
        documents = result[MetadataType.DOCUMENT.value]
        assert "ПриходТовара" in documents
        assert "РасходТовара" in documents

    def test_parse_configuration_finds_common_modules(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test that common modules are found."""
        result = parser.parse_configuration(mock_config_path)

        assert MetadataType.COMMON_MODULE.value in result
        modules = result[MetadataType.COMMON_MODULE.value]
        assert "ОбщегоНазначения" in modules

    def test_parse_configuration_finds_registers(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test that registers are found."""
        result = parser.parse_configuration(mock_config_path)

        assert MetadataType.INFORMATION_REGISTER.value in result
        registers = result[MetadataType.INFORMATION_REGISTER.value]
        assert "ЦеныТоваров" in registers

    def test_parse_configuration_file_not_found(
        self,
        parser: XmlParser,
        temp_dir: Path,
    ) -> None:
        """Test error handling when Configuration.xml is missing."""
        with pytest.raises(FileNotFoundError):
            parser.parse_configuration(temp_dir)

    def test_parse_catalog_object(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing a catalog metadata object."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert obj.name == "Товары"
        assert obj.metadata_type == MetadataType.CATALOG
        assert obj.synonym == "Товары"
        assert obj.comment == "Справочник товаров"

    def test_parse_catalog_attributes(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing catalog attributes."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert len(obj.attributes) == 2

        # Find Артикул attribute
        article = next((a for a in obj.attributes if a.name == "Артикул"), None)
        assert article is not None
        assert article.synonym == "Артикул"
        assert article.type == "String"
        assert article.indexed is True

        # Find ЕдиницаИзмерения attribute
        unit = next((a for a in obj.attributes if a.name == "ЕдиницаИзмерения"), None)
        assert unit is not None
        assert unit.type == "CatalogRef.ЕдиницыИзмерения"

    def test_parse_catalog_tabular_sections(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing catalog tabular sections."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert len(obj.tabular_sections) == 1

        ts = obj.tabular_sections[0]
        assert ts.name == "Штрихкоды"
        assert ts.synonym == "Штрихкоды"
        assert len(ts.attributes) == 1
        assert ts.attributes[0].name == "Штрихкод"

    def test_parse_catalog_forms(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing catalog forms list."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert len(obj.forms) == 2
        form_names = [f.name for f in obj.forms]
        assert "ФормаЭлемента" in form_names
        assert "ФормаСписка" in form_names

    def test_parse_catalog_templates(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing catalog templates list."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert len(obj.templates) == 1
        assert obj.templates[0].name == "ЭтикеткаТовара"

    def test_parse_document_object(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing a document metadata object."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.DOCUMENT,
            "ПриходТовара",
        )

        assert obj.name == "ПриходТовара"
        assert obj.metadata_type == MetadataType.DOCUMENT
        assert obj.synonym == "Приход товара"
        assert obj.posting is True

    def test_parse_document_register_records(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing document register records."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.DOCUMENT,
            "ПриходТовара",
        )

        assert len(obj.register_records) == 1
        assert "РегистрНакопления.ОстаткиТоваров" in obj.register_records

    def test_parse_document_tabular_section_attributes(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing document tabular section with attributes."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.DOCUMENT,
            "ПриходТовара",
        )

        assert len(obj.tabular_sections) == 1
        ts = obj.tabular_sections[0]
        assert ts.name == "Товары"
        assert len(ts.attributes) == 2

        attr_names = [a.name for a in ts.attributes]
        assert "Товар" in attr_names
        assert "Количество" in attr_names

    def test_parse_information_register(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing information register metadata."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.INFORMATION_REGISTER,
            "ЦеныТоваров",
        )

        assert obj.name == "ЦеныТоваров"
        assert obj.metadata_type == MetadataType.INFORMATION_REGISTER
        assert obj.synonym == "Цены товаров"

    def test_parse_register_dimensions(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing register dimensions."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.INFORMATION_REGISTER,
            "ЦеныТоваров",
        )

        assert len(obj.dimensions) == 2
        dim_names = [d.name for d in obj.dimensions]
        assert "Товар" in dim_names
        assert "ТипЦены" in dim_names

    def test_parse_register_resources(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing register resources."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.INFORMATION_REGISTER,
            "ЦеныТоваров",
        )

        assert len(obj.resources) == 1
        assert obj.resources[0].name == "Цена"
        assert obj.resources[0].type == "Number"

    def test_parse_subsystem(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing subsystem metadata."""
        subsystem = parser.parse_subsystem(mock_config_path, "Торговля")

        assert subsystem.name == "Торговля"
        assert subsystem.synonym == "Торговля"
        assert subsystem.include_in_command_interface is True

    def test_parse_subsystem_content(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing subsystem content."""
        subsystem = parser.parse_subsystem(mock_config_path, "Торговля")

        assert len(subsystem.content) == 2
        assert "Catalog.Товары" in subsystem.content
        assert "Document.ПриходТовара" in subsystem.content

    def test_parse_missing_object_returns_empty(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test parsing non-existent object returns object with minimal data."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "НесуществующийСправочник",
        )

        assert obj.name == "НесуществующийСправочник"
        assert obj.metadata_type == MetadataType.CATALOG
        assert len(obj.attributes) == 0

    def test_find_modules(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test finding module files for an object."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert len(obj.modules) >= 1
        # Should find ObjectModule.bsl
        module_paths = [str(m.path) for m in obj.modules]
        assert any("ObjectModule.bsl" in p for p in module_paths)

    def test_calculate_file_hash(
        self,
        parser: XmlParser,
        mock_config_path: Path,
    ) -> None:
        """Test that file hash is calculated."""
        obj = parser.parse_metadata_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert obj.file_hash is not None
        assert len(obj.file_hash) == 32  # MD5 hex length

    def test_get_type_folder_mapping(
        self,
        parser: XmlParser,
    ) -> None:
        """Test type to folder mapping."""
        assert parser._get_type_folder(MetadataType.CATALOG) == "Catalogs"
        assert parser._get_type_folder(MetadataType.DOCUMENT) == "Documents"
        assert parser._get_type_folder(MetadataType.COMMON_MODULE) == "CommonModules"
        assert parser._get_type_folder(MetadataType.INFORMATION_REGISTER) == "InformationRegisters"
