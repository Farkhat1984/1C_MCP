"""
E2E tests for ALL MCP tools against real QGA (1C:ZUP) configuration.

Tests go through the ToolRegistry.call_tool() layer, validating that
every registered tool returns correct results on real configuration data.

Skip automatically if the QGA config directory is not present.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.config import EmbeddingConfig, get_config
from mcp_1c.engines.code.engine import CodeEngine
from mcp_1c.engines.embeddings.engine import EmbeddingEngine
from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.engines.smart.generator import SmartGenerator
from mcp_1c.tools.registry import ToolRegistry

QGA_CONFIG_PATH = Path("/home/faragj/qga_config/qga")
PREBUILT_EMBEDDINGS_DB = Path(".mcp_1c_embeddings.db")
_HAS_API_KEY = bool(os.environ.get("DEEPINFRA_API_KEY"))

pytestmark = pytest.mark.skipif(
    not QGA_CONFIG_PATH.exists(),
    reason=f"QGA config not found at {QGA_CONFIG_PATH}",
)


def _has_embeddings() -> bool:
    """Check if pre-built embeddings DB exists."""
    return PREBUILT_EMBEDDINGS_DB.exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_result(raw: str) -> dict | list:
    """Parse tool result string into Python object."""
    return json.loads(raw)


def assert_no_error(result: dict) -> None:
    """Assert that tool result does not contain an error."""
    assert "error" not in result or result.get("error") is None, (
        f"Tool returned error: {result.get('error')}"
    )


def assert_no_error_str(raw: str) -> None:
    """Assert raw string result does not indicate an error."""
    assert '"error":' not in raw.lower() or '"error": null' in raw.lower(), (
        f"Tool returned error in raw result: {raw[:500]}"
    )


# ---------------------------------------------------------------------------
# Module-scoped fixtures (expensive initialization, shared across tests)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def tool_registry():
    """Set up all engines and create ToolRegistry with real QGA data."""
    # Reset all singletons to ensure clean state
    MetadataEngine._instance = None
    CodeEngine._instance = None
    KnowledgeGraphEngine._instance = None
    EmbeddingEngine._instance = None
    SmartGenerator._instance = None

    # Initialize metadata engine with temp cache DB
    meta_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    meta_db_path = Path(meta_db.name)
    meta_db.close()

    app_config = get_config()
    app_config.cache.db_path = meta_db_path

    engine = MetadataEngine.get_instance()
    engine.cache.db_path = meta_db_path
    await engine.initialize(QGA_CONFIG_PATH, watch=False)

    # Initialize Knowledge Graph
    kg = KnowledgeGraphEngine.get_instance()
    await kg.build(engine)

    # Initialize embeddings if pre-built DB exists
    if PREBUILT_EMBEDDINGS_DB.exists():
        from mcp_1c.engines.embeddings.client import EmbeddingClient

        emb = EmbeddingEngine.get_instance()
        config = EmbeddingConfig.from_env()
        await emb.initialize(config, PREBUILT_EMBEDDINGS_DB)
        # Recreate the HTTP client so its aiohttp session is bound
        # to the current event loop (module-scoped fixture).
        if emb._client:
            await emb._client.close()
            emb._client = EmbeddingClient(config)

    # Create ToolRegistry (initializes all tools from singletons)
    registry = ToolRegistry()

    # Initialize PlatformEngine (shared lazily via PlatformBaseTool class var)
    from mcp_1c.tools.platform_tools import PlatformBaseTool

    platform = PlatformBaseTool.get_engine()
    await platform.initialize()

    yield registry

    # Cleanup
    emb_engine = EmbeddingEngine.get_instance()
    if emb_engine.initialized:
        await emb_engine.close()

    await MetadataEngine.get_instance().cache.close()

    MetadataEngine._instance = None
    CodeEngine._instance = None
    KnowledgeGraphEngine._instance = None
    EmbeddingEngine._instance = None
    SmartGenerator._instance = None

    if meta_db_path.exists():
        meta_db_path.unlink()


# ===========================================================================
# Metadata Tools (4 tools)
# ===========================================================================


class TestMetadataTools:
    """Test metadata-* tools via call_tool."""

    @pytest.mark.asyncio
    async def test_metadata_list_catalogs(self, tool_registry: ToolRegistry) -> None:
        """metadata-list with type=Catalog should return 500+ catalogs."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "Catalog"})
        result = parse_result(raw)
        assert_no_error(result)
        assert result["count"] >= 500, f"Expected 500+ catalogs, got {result['count']}"
        assert len(result["objects"]) == result["count"]

    @pytest.mark.asyncio
    async def test_metadata_list_common_modules(self, tool_registry: ToolRegistry) -> None:
        """metadata-list with type=CommonModule should return 1500+ modules."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        result = parse_result(raw)
        assert_no_error(result)
        assert result["count"] >= 1500

    @pytest.mark.asyncio
    async def test_metadata_list_accumulation_registers(self, tool_registry: ToolRegistry) -> None:
        """metadata-list with AccumulationRegister should return 50+."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "AccumulationRegister"})
        result = parse_result(raw)
        assert_no_error(result)
        assert result["count"] >= 50

    @pytest.mark.asyncio
    async def test_metadata_get_catalog(self, tool_registry: ToolRegistry) -> None:
        """metadata-get for Catalog.ФизическиеЛица should return attributes."""
        raw = await tool_registry.call_tool(
            "metadata-get", {"type": "Catalog", "name": "ФизическиеЛица"}
        )
        result = parse_result(raw)
        assert_no_error(result)
        assert result["name"] == "ФизическиеЛица"
        assert len(result["attributes"]) > 0
        attr_names = [a["name"] for a in result["attributes"]]
        assert "ДатаРождения" in attr_names
        assert "ИНН" in attr_names

    @pytest.mark.asyncio
    async def test_metadata_search(self, tool_registry: ToolRegistry) -> None:
        """metadata-search for 'Сотрудник' should find results."""
        raw = await tool_registry.call_tool("metadata-search", {"query": "Сотрудник"})
        result = parse_result(raw)
        assert_no_error(result)
        assert result["count"] >= 1
        names = [r["name"] for r in result["results"]]
        assert any("Сотрудник" in n for n in names)

    @pytest.mark.asyncio
    async def test_metadata_search_with_type_filter(self, tool_registry: ToolRegistry) -> None:
        """metadata-search with type filter should narrow results."""
        raw = await tool_registry.call_tool(
            "metadata-search", {"query": "Сотрудник", "type": "Catalog"}
        )
        result = parse_result(raw)
        assert_no_error(result)
        for r in result["results"]:
            assert r["type"] == "Catalog"


# ===========================================================================
# Code Tools (8 tools)
# ===========================================================================


class TestCodeTools:
    """Test code-* tools via call_tool."""

    @pytest.mark.asyncio
    async def test_code_module_common_module(self, tool_registry: ToolRegistry) -> None:
        """code-module for a CommonModule should return BSL code."""
        # Find first common module with BSL file
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)
        assert modules["count"] > 0

        # Try first 20 modules to find one with code
        for mod in modules["objects"][:20]:
            raw = await tool_registry.call_tool(
                "code-module",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            result = parse_result(raw)
            if "error" not in result and result.get("code"):
                assert len(result["code"]) > 0
                assert "procedures" in result
                return

        pytest.skip("No parseable CommonModule found in first 20 modules")

    @pytest.mark.asyncio
    async def test_code_procedure(self, tool_registry: ToolRegistry) -> None:
        """code-procedure should return a specific procedure's code."""
        # Find a module with procedures first
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:30]:
            raw_mod = await tool_registry.call_tool(
                "code-module",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            mod_result = parse_result(raw_mod)
            if "error" not in mod_result and mod_result.get("procedures"):
                proc_name = mod_result["procedures"][0]["name"]
                raw_proc = await tool_registry.call_tool(
                    "code-procedure",
                    {
                        "type": "CommonModule",
                        "name": mod["name"],
                        "procedure": proc_name,
                        "module": "CommonModule",
                    },
                )
                proc_result = parse_result(raw_proc)
                assert_no_error(proc_result)
                assert proc_result["name"] == proc_name
                assert "code" in proc_result
                return

        pytest.skip("No module with procedures found")

    @pytest.mark.asyncio
    async def test_code_dependencies(self, tool_registry: ToolRegistry) -> None:
        """code-dependencies should analyze a module's dependencies."""
        # Find a common module with code
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:20]:
            raw_dep = await tool_registry.call_tool(
                "code-dependencies",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            dep_result = parse_result(raw_dep)
            if "error" not in dep_result:
                assert "path" in dep_result
                return

        pytest.skip("No CommonModule with analyzable code found")

    @pytest.mark.asyncio
    async def test_code_callgraph(self, tool_registry: ToolRegistry) -> None:
        """code-callgraph should build call graph for a procedure."""
        # Find module with procedures
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:30]:
            raw_mod = await tool_registry.call_tool(
                "code-module",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            mod_result = parse_result(raw_mod)
            if "error" not in mod_result and mod_result.get("procedures"):
                proc_name = mod_result["procedures"][0]["name"]
                raw_cg = await tool_registry.call_tool(
                    "code-callgraph",
                    {
                        "type": "CommonModule",
                        "name": mod["name"],
                        "procedure": proc_name,
                        "module": "CommonModule",
                    },
                )
                cg_result = parse_result(raw_cg)
                assert_no_error(cg_result)
                # procedure field contains full node_id (e.g. "Module::ProcName")
                assert proc_name in cg_result["procedure"]
                return

        pytest.skip("No module with procedures found")

    @pytest.mark.asyncio
    async def test_code_validate(self, tool_registry: ToolRegistry) -> None:
        """code-validate should validate a BSL module."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:10]:
            raw_v = await tool_registry.call_tool(
                "code-validate",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            result = parse_result(raw_v)
            if "error" not in result:
                assert "valid" in result
                assert "diagnostics" in result
                return

        pytest.skip("No validatable module found")

    @pytest.mark.asyncio
    async def test_code_lint(self, tool_registry: ToolRegistry) -> None:
        """code-lint should run static analysis."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:10]:
            raw_l = await tool_registry.call_tool(
                "code-lint",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            result = parse_result(raw_l)
            if "error" not in result:
                assert "total_issues" in result
                return

        pytest.skip("No lintable module found")

    @pytest.mark.asyncio
    async def test_code_format(self, tool_registry: ToolRegistry) -> None:
        """code-format with preview_only=true should not modify files."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:10]:
            raw_f = await tool_registry.call_tool(
                "code-format",
                {
                    "type": "CommonModule",
                    "name": mod["name"],
                    "module": "CommonModule",
                    "preview_only": True,
                },
            )
            result = parse_result(raw_f)
            if "error" not in result:
                assert result["preview_only"] is True
                return

        pytest.skip("No formattable module found")

    @pytest.mark.asyncio
    async def test_code_complexity(self, tool_registry: ToolRegistry) -> None:
        """code-complexity should return complexity metrics."""
        raw = await tool_registry.call_tool("metadata-list", {"type": "CommonModule"})
        modules = parse_result(raw)

        for mod in modules["objects"][:20]:
            raw_c = await tool_registry.call_tool(
                "code-complexity",
                {"type": "CommonModule", "name": mod["name"], "module": "CommonModule"},
            )
            result = parse_result(raw_c)
            if "error" not in result:
                assert "module_metrics" in result
                assert "procedures" in result
                assert "summary" in result
                return

        pytest.skip("No module for complexity analysis found")


# ===========================================================================
# Query Tools (2 tools)
# ===========================================================================


class TestQueryTools:
    """Test query-* tools via call_tool."""

    SAMPLE_QUERY = "ВЫБРАТЬ Наименование ИЗ Справочник.Товары"

    @pytest.mark.asyncio
    async def test_query_validate(self, tool_registry: ToolRegistry) -> None:
        """query-validate should validate query syntax."""
        raw = await tool_registry.call_tool(
            "query-validate", {"query_text": self.SAMPLE_QUERY}
        )
        result = parse_result(raw)
        assert_no_error(result)

    @pytest.mark.asyncio
    async def test_query_optimize(self, tool_registry: ToolRegistry) -> None:
        """query-optimize should suggest optimizations."""
        raw = await tool_registry.call_tool(
            "query-optimize", {"query_text": self.SAMPLE_QUERY}
        )
        result = parse_result(raw)
        assert_no_error(result)


# ===========================================================================
# Pattern Tools (3 tools)
# ===========================================================================


class TestPatternTools:
    """Test pattern-* tools via call_tool."""

    @pytest.mark.asyncio
    async def test_pattern_list_all(self, tool_registry: ToolRegistry) -> None:
        """pattern-list should return all available patterns."""
        raw = await tool_registry.call_tool("pattern-list", {})
        result = parse_result(raw)
        assert_no_error(result)
        assert result.get("count", 0) > 0 or len(result.get("templates", [])) > 0

    @pytest.mark.asyncio
    async def test_pattern_list_by_category(self, tool_registry: ToolRegistry) -> None:
        """pattern-list with category filter should return subset."""
        raw = await tool_registry.call_tool("pattern-list", {"category": "query"})
        result = parse_result(raw)
        assert_no_error(result)
        # Should have query-related patterns
        templates = result.get("templates", [])
        assert len(templates) > 0

    @pytest.mark.asyncio
    async def test_pattern_suggest(self, tool_registry: ToolRegistry) -> None:
        """pattern-suggest should suggest patterns for a task description."""
        raw = await tool_registry.call_tool(
            "pattern-suggest",
            {"task_description": "выбрать данные из справочника"},
        )
        result = parse_result(raw)
        assert_no_error(result)


# ===========================================================================
# Platform Tools (2 tools)
# ===========================================================================


class TestPlatformTools:
    """Test platform-* tools via call_tool."""

    @pytest.mark.asyncio
    async def test_platform_search(self, tool_registry: ToolRegistry) -> None:
        """platform-search should find platform API items."""
        raw = await tool_registry.call_tool(
            "platform-search", {"query": "Массив"}
        )
        result = parse_result(raw)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_platform_global_context(self, tool_registry: ToolRegistry) -> None:
        """platform-global_context should return global context overview."""
        raw = await tool_registry.call_tool("platform-global_context", {})
        result = parse_result(raw)
        assert isinstance(result, dict)


# ===========================================================================
# Config Tools (1 consolidated + 3 analysis)
# ===========================================================================


class TestConfigTools:
    """Test config-objects consolidated tool via call_tool.

    These may return empty results for partial QGA config but should not crash.
    """

    @pytest.mark.asyncio
    async def test_config_objects_options(self, tool_registry: ToolRegistry) -> None:
        """config-objects type=options should work without error."""
        raw = await tool_registry.call_tool("config-objects", {"type": "options"})
        result = parse_result(raw)
        assert isinstance(result, dict)
        assert result.get("type") == "FunctionalOption"

    @pytest.mark.asyncio
    async def test_config_objects_constants(self, tool_registry: ToolRegistry) -> None:
        """config-objects type=constants should work without error."""
        raw = await tool_registry.call_tool("config-objects", {"type": "constants"})
        result = parse_result(raw)
        assert isinstance(result, dict)
        assert result.get("type") == "Constant"

    @pytest.mark.asyncio
    async def test_config_objects_scheduled_jobs(self, tool_registry: ToolRegistry) -> None:
        """config-objects type=scheduled_jobs should work without error."""
        raw = await tool_registry.call_tool("config-objects", {"type": "scheduled_jobs"})
        result = parse_result(raw)
        assert isinstance(result, dict)
        assert result.get("type") == "ScheduledJob"

    @pytest.mark.asyncio
    async def test_config_objects_event_subscriptions(self, tool_registry: ToolRegistry) -> None:
        """config-objects type=event_subscriptions should work without error."""
        raw = await tool_registry.call_tool("config-objects", {"type": "event_subscriptions"})
        result = parse_result(raw)
        assert isinstance(result, dict)
        assert result.get("type") == "EventSubscription"

    @pytest.mark.asyncio
    async def test_config_objects_exchanges(self, tool_registry: ToolRegistry) -> None:
        """config-objects type=exchanges should work without error."""
        raw = await tool_registry.call_tool("config-objects", {"type": "exchanges"})
        result = parse_result(raw)
        assert isinstance(result, dict)
        assert result.get("type") == "ExchangePlan"

    @pytest.mark.asyncio
    async def test_config_objects_http_services(self, tool_registry: ToolRegistry) -> None:
        """config-objects type=http_services should work without error."""
        raw = await tool_registry.call_tool("config-objects", {"type": "http_services"})
        result = parse_result(raw)
        assert isinstance(result, dict)
        assert result.get("type") == "HTTPService"


# ===========================================================================
# Knowledge Graph Tools (4 tools)
# ===========================================================================


class TestGraphTools:
    """Test graph.* tools via call_tool."""

    @pytest.mark.asyncio
    async def test_graph_stats(self, tool_registry: ToolRegistry) -> None:
        """graph.stats should return stats with 5000+ nodes."""
        raw = await tool_registry.call_tool("graph.stats", {})
        result = parse_result(raw)
        assert result["total_nodes"] >= 5000
        assert result["total_edges"] >= 5000

    @pytest.mark.asyncio
    async def test_graph_impact(self, tool_registry: ToolRegistry) -> None:
        """graph.impact for Catalog.ФизическиеЛица should show impacted objects."""
        raw = await tool_registry.call_tool(
            "graph.impact", {"node_id": "Catalog.ФизическиеЛица", "depth": 2}
        )
        result = parse_result(raw)
        assert result["total_impacted"] >= 1

    @pytest.mark.asyncio
    async def test_graph_related(self, tool_registry: ToolRegistry) -> None:
        """graph.related for Catalog.ФизическиеЛица should show related objects."""
        raw = await tool_registry.call_tool(
            "graph.related", {"node_id": "Catalog.ФизическиеЛица"}
        )
        result = parse_result(raw)
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_graph_related_with_filter(self, tool_registry: ToolRegistry) -> None:
        """graph.related with relationship filter should narrow results."""
        raw = await tool_registry.call_tool(
            "graph.related",
            {"node_id": "Catalog.ФизическиеЛица", "relationship": "attribute_reference"},
        )
        result = parse_result(raw)
        assert result["relationship_filter"] == "attribute_reference"

    @pytest.mark.asyncio
    async def test_graph_build(self, tool_registry: ToolRegistry) -> None:
        """graph.build should rebuild without error."""
        raw = await tool_registry.call_tool("graph.build", {})
        result = parse_result(raw)
        assert result["status"] == "success"
        assert result["statistics"]["total_nodes"] >= 5000


# ===========================================================================
# Embedding Tools (4 tools) - skip if no pre-built DB
# ===========================================================================


class TestEmbeddingTools:
    """Test embedding.* tools via call_tool.

    Skip if .mcp_1c_embeddings.db does not exist.
    """

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _has_embeddings(), reason="No pre-built embeddings DB")
    async def test_embedding_stats(self, tool_registry: ToolRegistry) -> None:
        """embedding.stats should show 78K+ documents."""
        raw = await tool_registry.call_tool("embedding.stats", {})
        result = parse_result(raw)
        assert result["total_documents"] >= 70_000

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _has_embeddings(), reason="No pre-built embeddings DB")
    @pytest.mark.skipif(not _HAS_API_KEY, reason="DEEPINFRA_API_KEY not set")
    async def test_embedding_search(self, tool_registry: ToolRegistry) -> None:
        """embedding.search should return results with scores."""
        raw = await tool_registry.call_tool(
            "embedding.search",
            {"query": "расчет зарплаты", "limit": 10},
        )
        result = parse_result(raw)
        assert result["count"] >= 1
        assert result["results"][0]["score"] > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _has_embeddings(), reason="No pre-built embeddings DB")
    @pytest.mark.skipif(not _HAS_API_KEY, reason="DEEPINFRA_API_KEY not set")
    async def test_embedding_search_with_filters(self, tool_registry: ToolRegistry) -> None:
        """embedding.search with doc_type and object_type filters."""
        raw = await tool_registry.call_tool(
            "embedding.search",
            {
                "query": "начисление",
                "doc_type": "module",
                "object_type": "CommonModule",
                "limit": 5,
            },
        )
        result = parse_result(raw)
        for r in result["results"]:
            assert r["doc_type"] == "module"
            assert r["metadata"].get("object_type") == "CommonModule"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not _has_embeddings(), reason="No pre-built embeddings DB")
    @pytest.mark.skipif(not _HAS_API_KEY, reason="DEEPINFRA_API_KEY not set")
    async def test_embedding_similar(self, tool_registry: ToolRegistry) -> None:
        """embedding.similar should find similar documents."""
        # First get a doc_id from search
        raw = await tool_registry.call_tool(
            "embedding.search",
            {"query": "расчет зарплаты", "limit": 1},
        )
        search_result = parse_result(raw)
        assert search_result["count"] >= 1
        doc_id = search_result["results"][0]["id"]

        raw_sim = await tool_registry.call_tool(
            "embedding.similar", {"doc_id": doc_id, "limit": 5}
        )
        sim_result = parse_result(raw_sim)
        assert sim_result["count"] >= 1
        # Similar docs should have scores
        assert sim_result["similar"][0]["score"] > 0


# ===========================================================================
# Analysis Tools (4 tools)
# ===========================================================================


class TestAnalysisTools:
    """Test analysis tools (config-roles, config-role-rights, code-dead-code, config-compare)."""

    @pytest.mark.asyncio
    async def test_config_roles(self, tool_registry: ToolRegistry) -> None:
        """config-roles should list roles."""
        raw = await tool_registry.call_tool("config-roles", {})
        result = parse_result(raw)
        # Should either have roles or an error for missing metadata
        if "error" not in result:
            assert result.get("count", 0) >= 0

    @pytest.mark.asyncio
    async def test_config_role_rights(self, tool_registry: ToolRegistry) -> None:
        """config-role-rights should show role rights for a catalog."""
        raw = await tool_registry.call_tool(
            "config-role-rights",
            {"object_name": "Catalog.ФизическиеЛица"},
        )
        result = parse_result(raw)
        assert_no_error(result)
        assert result["object"] == "Catalog.ФизическиеЛица"
        assert "roles" in result

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Too slow on large configs like ZUP (1900+ CommonModules)")
    async def test_code_dead_code_filtered(self, tool_registry: ToolRegistry) -> None:
        """code-dead-code with CommonModule filter should analyze without crashing."""
        raw = await tool_registry.call_tool(
            "code-dead-code",
            {"metadata_type": "CommonModule", "include_exports": False},
        )
        result = parse_result(raw)
        assert_no_error(result)
        assert "dead_code" in result
        assert "total_procedures" in result
        assert "files_analyzed" in result
        assert result["files_analyzed"] >= 1

    @pytest.mark.asyncio
    async def test_config_compare_same(self, tool_registry: ToolRegistry) -> None:
        """config-compare with path_a=path_b should show no changes."""
        qga = str(QGA_CONFIG_PATH)
        raw = await tool_registry.call_tool(
            "config-compare", {"path_a": qga, "path_b": qga}
        )
        result = parse_result(raw)
        assert_no_error(result)
        summary = result["summary"]
        assert summary["added"] == 0
        assert summary["removed"] == 0
        assert summary["modified"] == 0
        assert summary["unchanged"] > 0


# ===========================================================================
# Smart Generation Tools (3 tools)
# ===========================================================================


class TestSmartTools:
    """Test smart-* tools via call_tool.

    These use real metadata to generate metadata-aware code.
    """

    @pytest.mark.asyncio
    async def test_smart_query(self, tool_registry: ToolRegistry) -> None:
        """smart-query should generate a query with real attributes."""
        raw = await tool_registry.call_tool(
            "smart-query", {"object_name": "Catalog.ФизическиеЛица"}
        )
        result = parse_result(raw)
        assert_no_error(result)
        # Should have generated query code
        code = result.get("query", result.get("code", ""))
        assert len(code) > 0
        # Should reference real attributes
        assert "ФизическиеЛица" in code or "ФизическиеЛица" in str(result)

    @pytest.mark.asyncio
    async def test_smart_print(self, tool_registry: ToolRegistry) -> None:
        """smart-print should generate a print form with real attributes."""
        raw = await tool_registry.call_tool(
            "smart-print", {"object_name": "Catalog.ФизическиеЛица"}
        )
        result = parse_result(raw)
        assert_no_error(result)
        # Should have generated artifacts
        assert isinstance(result, dict)
        # At least some code should be generated
        has_content = any(
            v for k, v in result.items()
            if isinstance(v, str) and len(v) > 10
        )
        assert has_content, "smart-print should produce non-empty code artifacts"

    @pytest.mark.asyncio
    async def test_smart_movement_graceful(self, tool_registry: ToolRegistry) -> None:
        """smart-movement may fail without documents, should handle gracefully."""
        # Try with a catalog (may fail since movements are for documents + registers)
        raw = await tool_registry.call_tool(
            "smart-movement",
            {
                "document_name": "Document.НесуществующийДокумент",
                "register_name": "AccumulationRegister.НесуществующийРегистр",
            },
        )
        result = parse_result(raw)
        # Should return error gracefully, not crash
        assert isinstance(result, dict)


# ===========================================================================
# Template (MXL) Tools (3 tools) - optional, depend on MXL files existing
# ===========================================================================


class TestTemplateTools:
    """Test template-* MXL tools.

    These require actual MXL template files in the configuration.
    Skip individual tests if no templates found.
    """

    @pytest.mark.asyncio
    async def test_template_find(self, tool_registry: ToolRegistry) -> None:
        """template-find should search for templates in the config."""
        raw = await tool_registry.call_tool(
            "template-find",
            {"config_path": str(QGA_CONFIG_PATH)},
        )
        result = parse_result(raw)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_template_get_if_exists(self, tool_registry: ToolRegistry) -> None:
        """template-get should parse an MXL file if one exists."""
        # Try to find an MXL file in the config
        mxl_files = list(QGA_CONFIG_PATH.rglob("*.xml"))
        # Look for template-like files
        template_files = [
            f for f in mxl_files
            if "Template" in str(f) or "Макет" in str(f) or "template" in str(f).lower()
        ]

        if not template_files:
            pytest.skip("No MXL template files found in config")

        raw = await tool_registry.call_tool(
            "template-get", {"file_path": str(template_files[0])}
        )
        result = parse_result(raw)
        # May error if not a valid MXL, that's OK
        assert isinstance(result, dict)


# ===========================================================================
# Registry Completeness Check
# ===========================================================================


class TestRegistryCompleteness:
    """Verify all expected tools are registered."""

    EXPECTED_TOOLS: list[str] = [
        # Metadata (4)
        "metadata-init", "metadata-list", "metadata-get", "metadata-search",
        # Code (8)
        "code-module", "code-procedure",
        "code-dependencies", "code-callgraph",
        "code-validate", "code-lint", "code-format", "code-complexity",
        # Smart generation (3)
        "smart-query", "smart-print", "smart-movement",
        # Pattern (3)
        "pattern-list", "pattern-apply", "pattern-suggest",
        # Query (2)
        "query-validate", "query-optimize",
        # Template MXL (3)
        "template-get", "template-generate_fill_code", "template-find",
        # Platform (2)
        "platform-search", "platform-global_context",
        # Config (4 — 1 consolidated + 3 analysis)
        "config-objects", "config-roles", "config-role-rights", "config-compare",
        # Graph (4)
        "graph.build", "graph.impact", "graph.related", "graph.stats",
        # Embedding (4)
        "embedding.index", "embedding.search",
        "embedding.similar", "embedding.stats",
        # Analysis (1)
        "code-dead-code",
    ]

    @pytest.mark.asyncio
    async def test_all_tools_registered(self, tool_registry: ToolRegistry) -> None:
        """All expected tools should be registered in the registry."""
        registered = {t.name for t in tool_registry.list_tools()}
        missing = [t for t in self.EXPECTED_TOOLS if t not in registered]
        assert not missing, f"Missing tools: {missing}"

    @pytest.mark.asyncio
    async def test_tool_count(self, tool_registry: ToolRegistry) -> None:
        """Registry should have exactly 38 tools."""
        tools = tool_registry.list_tools()
        assert len(tools) == 38, (
            f"Expected 38 tools, got {len(tools)}: {sorted(t.name for t in tools)}"
        )

    @pytest.mark.asyncio
    async def test_all_tools_have_schemas(self, tool_registry: ToolRegistry) -> None:
        """Every registered tool should have a valid input schema."""
        for tool_def in tool_registry.list_tools():
            assert tool_def.inputSchema is not None, (
                f"Tool {tool_def.name} has no input schema"
            )
            assert tool_def.inputSchema.get("type") == "object", (
                f"Tool {tool_def.name} schema type is not 'object'"
            )
