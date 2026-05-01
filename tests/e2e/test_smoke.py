"""
End-to-end smoke test — exercises the user-visible MCP path on a real
on-disk fixture (not in-memory mocks).

Catches regressions where the registry/wiring breaks even though unit
tests stay green: a new user runs metadata-init, lists, gets, and
generates code through the real Tool→Engine→Cache→XML pipeline.

Runs in <2s. If this test fails, the product does not work for new
users — fix it before anything else.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.tools.constants import ToolNames
from mcp_1c.tools.registry import ToolRegistry


@pytest_asyncio.fixture
async def initialized_engine(mock_config_path: Path):
    """Boot a metadata engine against the conftest fixture, tear it down after."""
    # Reset singleton between tests so each call gets a clean engine
    MetadataEngine._instance = None
    engine = MetadataEngine.get_instance()
    progress = await engine.initialize(mock_config_path, watch=False)
    assert progress.processed > 0, "fixture should produce indexed objects"
    yield engine
    await engine.shutdown()
    MetadataEngine._instance = None


@pytest.mark.asyncio
async def test_metadata_lifecycle(initialized_engine, mock_config_path: Path) -> None:
    """init → list → get → search must all return real data, not errors."""
    registry = ToolRegistry()

    # metadata-list
    result_list = await registry.call_tool(
        ToolNames.METADATA_LIST, {"type": "Catalog"}
    )
    assert "Товары" in result_list or "Контрагенты" in result_list

    # metadata-get
    result_get = await registry.call_tool(
        ToolNames.METADATA_GET, {"type": "Catalog", "name": "Товары"}
    )
    assert "Товары" in result_get
    # Must include attributes from the fixture
    assert "Артикул" in result_get

    # metadata-search
    result_search = await registry.call_tool(
        ToolNames.METADATA_SEARCH, {"query": "Товар"}
    )
    assert "Товары" in result_search


@pytest.mark.asyncio
async def test_code_lifecycle(initialized_engine, mock_config_path: Path) -> None:
    """code-module must return source (or a structured error) for an indexed object."""
    registry = ToolRegistry()
    result = await registry.call_tool(
        ToolNames.CODE_MODULE,
        {"type": "Catalog", "name": "Товары", "module": "ObjectModule"},
    )
    # The fixture's catalog ObjectModule.bsl contains "ПередЗаписью"
    assert "ПередЗаписью" in result or "ПолучитьЦену" in result


@pytest.mark.asyncio
async def test_generate_query_lifecycle(initialized_engine) -> None:
    """generate-query must produce code without an API key or network."""
    registry = ToolRegistry()
    result = await registry.call_tool(
        ToolNames.GENERATE_QUERY,
        {
            "template_id": "query.select_simple",
            "values": {
                "TableName": "Справочник.Товары",
                "Fields": "Ссылка, Наименование",
            },
        },
    )
    # Result is a JSON-formatted string; check Russian SELECT keyword
    assert "ВЫБРАТЬ" in result or '"success": true' in result


@pytest.mark.asyncio
async def test_registry_serves_expected_tool_count() -> None:
    """38 core + 8 gen + 3 form + 4 skd + 3 ext + 4 bsp + 5 runtime + 2 premium = 67."""
    registry = ToolRegistry()
    tools = registry.list_tools()
    assert len(tools) == 67, (
        f"Expected 67 tools, got {len(tools)}: {sorted(t.name for t in tools)}"
    )
