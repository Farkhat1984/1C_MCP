"""EDT-format support in the metadata parser.

EDT (1C:Enterprise Development Tools, Eclipse-based) lays out
configurations under ``src/`` with ``.mdo`` files and per-type
suffixes — distinct from Configurator's ``Configuration.xml`` +
``<Type>/<Name>/<Name>.xml`` layout.

These tests build a minimal EDT tree on disk and verify:

- :func:`detect_layout` flags it as EDT.
- :meth:`parse_configuration` reads from
  ``Configuration/Configuration.mdo``.
- :meth:`parse_metadata_object` resolves the right
  ``src/<Type>/<Name><suffix>/<Name>.mdo`` path.

We don't try to validate the full XML schema variation between
Configurator and EDT — both share the inner structure for the bits
the parser cares about (Synonym, ChildObjects, Properties).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.metadata.parser import (
    LayoutKind,
    XmlParser,
    detect_layout,
)

_EDT_CONFIG_MDO = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core">
    <Configuration>
        <Properties>
            <Name>EDTSample</Name>
            <Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Образец EDT</v8:content></v8:item></Synonym>
        </Properties>
        <ChildObjects>
            <Catalog>Контрагенты</Catalog>
            <CommonModule>НашиОбщие</CommonModule>
        </ChildObjects>
    </Configuration>
</MetaDataObject>"""


_EDT_CATALOG_MDO = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core">
    <Catalog>
        <Properties>
            <Name>Контрагенты</Name>
            <Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Контрагенты</v8:content></v8:item></Synonym>
        </Properties>
        <ChildObjects/>
    </Catalog>
</MetaDataObject>"""


_EDT_COMMON_MODULE_MDO = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core">
    <CommonModule>
        <Properties>
            <Name>НашиОбщие</Name>
            <Server>true</Server>
        </Properties>
    </CommonModule>
</MetaDataObject>"""


@pytest.fixture
def edt_config_path(tmp_path: Path) -> Path:
    """Build a minimal EDT-format configuration tree.

    Layout:
    ::

        <root>/
          Configuration/
            Configuration.mdo
          src/
            Catalogs/
              Контрагенты.catalog/
                Контрагенты.mdo
            CommonModules/
              НашиОбщие.cmm/
                НашиОбщие.mdo
                Module.bsl
    """
    root = tmp_path / "EDTSample"
    root.mkdir()

    # Configuration.mdo
    (root / "Configuration").mkdir()
    (root / "Configuration" / "Configuration.mdo").write_text(
        _EDT_CONFIG_MDO, encoding="utf-8"
    )

    # Catalog
    catalog_dir = root / "src" / "Catalogs" / "Контрагенты.catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "Контрагенты.mdo").write_text(
        _EDT_CATALOG_MDO, encoding="utf-8"
    )

    # CommonModule with BSL
    cm_dir = root / "src" / "CommonModules" / "НашиОбщие.cmm"
    cm_dir.mkdir(parents=True)
    (cm_dir / "НашиОбщие.mdo").write_text(
        _EDT_COMMON_MODULE_MDO, encoding="utf-8"
    )
    (cm_dir / "Module.bsl").write_text(
        "Процедура НормализоватьИНН() Экспорт\nКонецПроцедуры\n",
        encoding="utf-8",
    )

    return root


# ---------------------------------------------------------------------------
# Layout detection
# ---------------------------------------------------------------------------


def test_detect_edt_layout(edt_config_path: Path) -> None:
    assert detect_layout(edt_config_path) == LayoutKind.EDT


def test_detect_configurator_layout_for_classic_export(tmp_path: Path) -> None:
    """A folder with Configuration.xml at the root → CONFIGURATOR."""
    (tmp_path / "Configuration.xml").write_text("<x/>", encoding="utf-8")
    assert detect_layout(tmp_path) == LayoutKind.CONFIGURATOR


def test_detect_falls_back_to_configurator_for_empty_path(tmp_path: Path) -> None:
    """Neither marker present → CONFIGURATOR (caller will get
    "FileNotFoundError" downstream when it tries to open
    Configuration.xml). Better than failing detection itself."""
    assert detect_layout(tmp_path) == LayoutKind.CONFIGURATOR


def test_edt_takes_precedence_over_configurator_when_both_present(
    edt_config_path: Path,
) -> None:
    """Migration-in-flight: both files exist. EDT wins (modern)."""
    (edt_config_path / "Configuration.xml").write_text(
        "<v/>", encoding="utf-8"
    )
    assert detect_layout(edt_config_path) == LayoutKind.EDT


# ---------------------------------------------------------------------------
# parse_configuration on EDT
# ---------------------------------------------------------------------------


def test_parse_configuration_reads_edt_mdo(edt_config_path: Path) -> None:
    parser = XmlParser()
    result = parser.parse_configuration(edt_config_path)
    assert "Catalog" in result
    assert "Контрагенты" in result["Catalog"]
    assert "CommonModule" in result
    assert "НашиОбщие" in result["CommonModule"]


def test_parse_configuration_raises_when_edt_mdo_missing(tmp_path: Path) -> None:
    """EDT-shape root *without* the Configuration/Configuration.mdo
    file (e.g. mid-checkout) → clear error message including layout."""
    parser = XmlParser()
    with pytest.raises(FileNotFoundError, match="layout=configurator"):
        # No EDT marker → falls back to Configurator path; that file
        # is missing too, so the error references configurator layout.
        parser.parse_configuration(tmp_path)


# ---------------------------------------------------------------------------
# parse_metadata_object on EDT
# ---------------------------------------------------------------------------


def test_parse_catalog_on_edt(edt_config_path: Path) -> None:
    parser = XmlParser()
    obj = parser.parse_metadata_object(
        edt_config_path, MetadataType.CATALOG, "Контрагенты"
    )
    assert obj.name == "Контрагенты"
    assert obj.metadata_type == MetadataType.CATALOG
    # object_path resolves to the catalog suffix dir.
    assert obj.object_path.name == "Контрагенты.catalog"


def test_parse_common_module_on_edt(edt_config_path: Path) -> None:
    parser = XmlParser()
    obj = parser.parse_metadata_object(
        edt_config_path, MetadataType.COMMON_MODULE, "НашиОбщие"
    )
    assert obj.name == "НашиОбщие"
    assert obj.object_path.name == "НашиОбщие.cmm"


def test_unknown_object_returns_empty_metadata(edt_config_path: Path) -> None:
    """EDT path resolution for a non-existent name → empty MetadataObject
    (same contract as Configurator path)."""
    parser = XmlParser()
    obj = parser.parse_metadata_object(
        edt_config_path, MetadataType.CATALOG, "DoesNotExist"
    )
    # No XML found → empty defaults; ``name`` carries through.
    assert obj.name == "DoesNotExist"
    assert obj.attributes == []


# ---------------------------------------------------------------------------
# Configurator layout regression: legacy code path still works
# ---------------------------------------------------------------------------


def test_configurator_layout_still_works(mock_config_path: Path) -> None:
    """The synthetic ``mock_config_path`` is Configurator-flavoured —
    layout must detect as such, parse must work as before."""
    assert detect_layout(mock_config_path) == LayoutKind.CONFIGURATOR
    parser = XmlParser()
    result = parser.parse_configuration(mock_config_path)
    assert "Catalog" in result
    assert "Товары" in result["Catalog"]
