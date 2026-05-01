"""Unit tests for the extension parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.domain.extension import AdoptionMode, ExtensionPurpose
from mcp_1c.engines.extensions.parser import ExtensionParser

EXTENSION_CONFIG = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Configuration>
    <Name>МоеРасширение</Name>
    <Properties>
      <Purpose>Customization</Purpose>
      <NamePrefix>МР_</NamePrefix>
      <BaseConfigurationName>УправлениеТорговлей</BaseConfigurationName>
      <ExtensionConfigurationSafeMode>false</ExtensionConfigurationSafeMode>
      <UpdateCompatibilityMode>Version8_3_18</UpdateCompatibilityMode>
    </Properties>
    <ChildObjects>
      <Catalog Adopted="true">Номенклатура</Catalog>
      <Catalog>МР_ДополнительныйСправочник</Catalog>
      <Document Replaced="true">РеализацияТоваров</Document>
      <CommonModule>МР_ОбщегоНазначения</CommonModule>
    </ChildObjects>
  </Configuration>
</MetaDataObject>
"""


@pytest.fixture
def extension_path(tmp_path: Path) -> Path:
    cfg_xml = tmp_path / "Configuration.xml"
    cfg_xml.write_text(EXTENSION_CONFIG, encoding="utf-8")
    return tmp_path


def test_parses_metadata(extension_path: Path) -> None:
    parser = ExtensionParser()
    ext = parser.parse(extension_path)
    assert ext.name == "МоеРасширение"
    assert ext.purpose == ExtensionPurpose.CUSTOMIZATION
    assert ext.namespace == "МР_"
    assert ext.target_configuration == "УправлениеТорговлей"
    assert ext.update_compatibility_mode == "Version8_3_18"
    assert ext.safe_mode is False


def test_classifies_objects(extension_path: Path) -> None:
    parser = ExtensionParser()
    ext = parser.parse(extension_path)

    by_name = {o.name: o for o in ext.objects}
    assert by_name["Номенклатура"].mode == AdoptionMode.ADOPTED
    assert by_name["МР_ДополнительныйСправочник"].mode == AdoptionMode.OWN
    assert by_name["РеализацияТоваров"].mode == AdoptionMode.REPLACED
    assert by_name["МР_ОбщегоНазначения"].mode == AdoptionMode.OWN


def test_aggregates(extension_path: Path) -> None:
    parser = ExtensionParser()
    ext = parser.parse(extension_path)
    assert len(ext.adopted_objects) == 1
    assert len(ext.replaced_objects) == 1
    assert len(ext.own_objects) == 2


def test_missing_configuration_xml(tmp_path: Path) -> None:
    parser = ExtensionParser()
    with pytest.raises(FileNotFoundError):
        parser.parse(tmp_path)
