"""Multi-root indexing — main config + developer overlays.

Verifies the F3 indexing contract end-to-end against the synthetic
mock_config_path fixture plus a minimal overlay tree built in the
test. Real validation against УТ/ZUP fixtures is outside the unit
suite (gated `pytest -m lsp`).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.config import OverlayRoot
from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.metadata import MetadataEngine

_OVERLAY_CONFIG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core">
    <Configuration>
        <Properties>
            <Name>TeamUtils</Name>
            <Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Утилиты команды</v8:content></v8:item></Synonym>
        </Properties>
        <ChildObjects>
            <CommonModule>НашиОбщие</CommonModule>
        </ChildObjects>
    </Configuration>
</MetaDataObject>"""


_OVERLAY_COMMON_MODULE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" xmlns:v8="http://v8.1c.ru/8.1/data/core">
    <CommonModule>
        <Properties>
            <Name>НашиОбщие</Name>
            <Synonym><v8:item><v8:lang>ru</v8:lang><v8:content>Наши общие</v8:content></v8:item></Synonym>
            <Server>true</Server>
        </Properties>
    </CommonModule>
</MetaDataObject>"""


_OVERLAY_COMMON_MODULE_BSL = """Процедура НормализоватьИНН() Экспорт
КонецПроцедуры
"""


def _make_overlay_tree(root: Path, *, name: str = "TeamUtils") -> Path:
    """Build a minimal valid 1С configuration root for an overlay.

    Just enough to satisfy XmlParser.parse_configuration: a
    Configuration.xml with one CommonModule plus the module folder.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "Configuration.xml").write_text(_OVERLAY_CONFIG_XML, encoding="utf-8")
    cm_dir = root / "CommonModules" / "НашиОбщие"
    cm_dir.mkdir(parents=True)
    (cm_dir / "НашиОбщие.xml").write_text(
        _OVERLAY_COMMON_MODULE_XML, encoding="utf-8"
    )
    ext_dir = cm_dir / "Ext"
    ext_dir.mkdir()
    (ext_dir / "Module.bsl").write_text(
        _OVERLAY_COMMON_MODULE_BSL, encoding="utf-8"
    )
    return root


@pytest_asyncio.fixture
async def fresh_engine() -> MetadataEngine:
    """Engine instance independent from the singleton; cleans up after."""
    import contextlib

    MetadataEngine._instance = None
    engine = MetadataEngine()
    yield engine
    with contextlib.suppress(Exception):
        await engine.shutdown()
    MetadataEngine._instance = None


@pytest.mark.asyncio
async def test_overlay_objects_get_overlay_source_label(
    fresh_engine: MetadataEngine, mock_config_path: Path, tmp_path: Path
) -> None:
    """Each object indexed from an overlay carries ``source='overlay:<name>'``."""
    overlay = OverlayRoot(
        name="utils",
        path=_make_overlay_tree(tmp_path / "team-utils"),
    )
    progress = await fresh_engine.initialize(
        mock_config_path,
        full_reindex=True,
        watch=False,
        overlay_roots=[overlay],
    )
    assert progress.errors == []

    overlay_module = await fresh_engine.get_object(
        MetadataType.COMMON_MODULE, "НашиОбщие"
    )
    assert overlay_module is not None
    assert overlay_module.source == "overlay:utils"


@pytest.mark.asyncio
async def test_main_config_objects_keep_config_source_label(
    fresh_engine: MetadataEngine, mock_config_path: Path, tmp_path: Path
) -> None:
    """Sanity counterproof: main-config objects do NOT get overlay labels
    even when the engine indexed an overlay alongside them."""
    overlay = OverlayRoot(
        name="utils",
        path=_make_overlay_tree(tmp_path / "team-utils"),
    )
    await fresh_engine.initialize(
        mock_config_path,
        full_reindex=True,
        watch=False,
        overlay_roots=[overlay],
    )
    main_catalog = await fresh_engine.get_object(MetadataType.CATALOG, "Товары")
    assert main_catalog is not None
    assert main_catalog.source == "config"


@pytest.mark.asyncio
async def test_overlay_without_configuration_xml_is_skipped_with_warning(
    fresh_engine: MetadataEngine, mock_config_path: Path, tmp_path: Path
) -> None:
    """Folder-of-modules overlay without Configuration.xml — engine logs
    and skips, doesn't crash. F3.5 will support the standalone form."""
    standalone = tmp_path / "standalone-libs"
    standalone.mkdir()
    overlay = OverlayRoot(name="libs", path=standalone)

    progress = await fresh_engine.initialize(
        mock_config_path,
        full_reindex=True,
        watch=False,
        overlay_roots=[overlay],
    )
    # No errors, just a logged skip — overlay simply has no objects.
    assert progress.errors == []
    # Main-config objects are still indexed.
    catalog = await fresh_engine.get_object(MetadataType.CATALOG, "Товары")
    assert catalog is not None


@pytest.mark.asyncio
async def test_overlay_metadata_init_tool_threads_overlays_through(
    fresh_engine: MetadataEngine, mock_config_path: Path, tmp_path: Path
) -> None:
    """End-to-end: MetadataInitTool accepts overlays from arguments."""
    from mcp_1c.tools.metadata_tools import MetadataInitTool

    overlay_path = _make_overlay_tree(tmp_path / "lib")
    tool = MetadataInitTool(fresh_engine)

    result = await tool.execute(
        {
            "path": str(mock_config_path),
            "full_reindex": True,
            "overlay_roots": [
                {"name": "lib", "path": str(overlay_path), "priority": 50}
            ],
        }
    )

    assert result["status"] == "success"
    assert len(result["overlays"]) == 1
    assert result["overlays"][0]["name"] == "lib"
    assert result["overlays"][0]["priority"] == 50
    # The overlay's own CommonModule was indexed.
    overlay_obj = await fresh_engine.get_object(
        MetadataType.COMMON_MODULE, "НашиОбщие"
    )
    assert overlay_obj is not None
    assert overlay_obj.source == "overlay:lib"


@pytest.mark.asyncio
async def test_init_tool_rejects_malformed_overlay_entry(
    fresh_engine: MetadataEngine, mock_config_path: Path
) -> None:
    """An overlay entry missing ``name``/``path`` must produce a
    structured ToolError, not a stack trace."""
    from mcp_1c.tools.base import ToolError
    from mcp_1c.tools.metadata_tools import MetadataInitTool

    tool = MetadataInitTool(fresh_engine)
    with pytest.raises(ToolError, match="Invalid overlay"):
        await tool.execute(
            {
                "path": str(mock_config_path),
                "overlay_roots": [{"name": "no-path"}],
            }
        )


@pytest.mark.asyncio
async def test_no_overlays_keeps_legacy_behaviour(
    fresh_engine: MetadataEngine, mock_config_path: Path
) -> None:
    """Initialize without overlays still works — single-root mode is the
    default, no breaking change for existing callers."""
    progress = await fresh_engine.initialize(
        mock_config_path, full_reindex=True, watch=False
    )
    assert progress.errors == []
    main_catalog = await fresh_engine.get_object(MetadataType.CATALOG, "Товары")
    assert main_catalog is not None
    assert main_catalog.source == "config"
