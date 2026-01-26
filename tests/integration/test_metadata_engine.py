"""
Integration tests for Metadata Engine.

Tests full workflow: initialization, indexing, querying.
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from mcp_1c.engines.metadata.engine import MetadataEngine
from mcp_1c.domain.metadata import MetadataType


class TestMetadataEngineIntegration:
    """Integration tests for MetadataEngine."""

    @pytest_asyncio.fixture
    async def engine(self, mock_config_path: Path) -> MetadataEngine:
        """Create and initialize engine with mock configuration."""
        # Reset singleton for clean test
        MetadataEngine._instance = None

        engine = MetadataEngine.get_instance()

        # Use temp file for test database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        engine.cache.db_path = db_path
        await engine.initialize(mock_config_path, watch=False)

        yield engine

        # Cleanup
        await engine.cache.close()
        if db_path.exists():
            db_path.unlink()

        # Reset singleton
        MetadataEngine._instance = None

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine: MetadataEngine) -> None:
        """Test engine initializes successfully."""
        assert engine.config_path is not None
        assert engine.is_initialized is True

    @pytest.mark.asyncio
    async def test_list_objects_by_type(self, engine: MetadataEngine) -> None:
        """Test listing objects by type."""
        catalogs = await engine.list_objects(MetadataType.CATALOG)

        assert len(catalogs) >= 1
        names = [c.name for c in catalogs]
        assert "Товары" in names

    @pytest.mark.asyncio
    async def test_get_object(self, engine: MetadataEngine) -> None:
        """Test getting a specific object."""
        obj = await engine.get_object(MetadataType.CATALOG, "Товары")

        assert obj is not None
        assert obj.name == "Товары"
        assert obj.metadata_type == MetadataType.CATALOG

    @pytest.mark.asyncio
    async def test_get_object_with_attributes(self, engine: MetadataEngine) -> None:
        """Test that object has attributes."""
        obj = await engine.get_object(MetadataType.CATALOG, "Товары")

        assert obj is not None
        assert len(obj.attributes) > 0

    @pytest.mark.asyncio
    async def test_get_nonexistent_object(self, engine: MetadataEngine) -> None:
        """Test getting non-existent object returns None."""
        obj = await engine.get_object(MetadataType.CATALOG, "НеСуществует")

        assert obj is None

    @pytest.mark.asyncio
    async def test_search_objects(self, engine: MetadataEngine) -> None:
        """Test searching for objects."""
        results = await engine.search("Товар")

        assert len(results) >= 1
        # Should find Товары catalog
        names = [r.name for r in results]
        assert any("Товар" in name for name in names)

    @pytest.mark.asyncio
    async def test_search_by_synonym(self, engine: MetadataEngine) -> None:
        """Test searching by synonym."""
        results = await engine.search("Приход")

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_get_subsystem_tree(self, engine: MetadataEngine) -> None:
        """Test getting subsystem tree."""
        tree = await engine.get_subsystem_tree()

        assert len(tree) >= 1
        names = [s.name for s in tree]
        assert "Торговля" in names

    @pytest.mark.asyncio
    async def test_get_object_attributes(self, engine: MetadataEngine) -> None:
        """Test getting object attributes directly."""
        attributes = await engine.get_attributes(MetadataType.CATALOG, "Товары")

        assert len(attributes) >= 1
        attr_names = [a.name for a in attributes]
        assert "Артикул" in attr_names

    @pytest.mark.asyncio
    async def test_get_object_tabular_sections(self, engine: MetadataEngine) -> None:
        """Test getting object tabular sections."""
        obj = await engine.get_object(MetadataType.CATALOG, "Товары")

        assert obj is not None
        assert len(obj.tabular_sections) >= 1
        ts_names = [ts.name for ts in obj.tabular_sections]
        assert "Штрихкоды" in ts_names

    @pytest.mark.asyncio
    async def test_get_document_with_registers(self, engine: MetadataEngine) -> None:
        """Test getting document with register records."""
        obj = await engine.get_object(MetadataType.DOCUMENT, "ПриходТовара")

        assert obj is not None
        assert len(obj.register_records) >= 1

    @pytest.mark.asyncio
    async def test_get_register_dimensions(self, engine: MetadataEngine) -> None:
        """Test getting register dimensions."""
        obj = await engine.get_object(
            MetadataType.INFORMATION_REGISTER,
            "ЦеныТоваров"
        )

        assert obj is not None
        assert len(obj.dimensions) >= 1
        dim_names = [d.name for d in obj.dimensions]
        assert "Товар" in dim_names

    @pytest.mark.asyncio
    async def test_singleton_pattern(self, mock_config_path: Path) -> None:
        """Test that engine uses singleton pattern."""
        # Reset singleton
        MetadataEngine._instance = None

        engine1 = MetadataEngine.get_instance()
        engine2 = MetadataEngine.get_instance()

        assert engine1 is engine2

        # Cleanup
        MetadataEngine._instance = None


class TestMetadataEngineCaching:
    """Tests for caching behavior."""

    @pytest_asyncio.fixture
    async def engine(self, mock_config_path: Path) -> MetadataEngine:
        """Create and initialize engine."""
        MetadataEngine._instance = None

        engine = MetadataEngine.get_instance()

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        engine.cache.db_path = db_path
        await engine.initialize(mock_config_path, watch=False)

        yield engine

        await engine.cache.close()
        if db_path.exists():
            db_path.unlink()
        MetadataEngine._instance = None

    @pytest.mark.asyncio
    async def test_objects_cached_after_indexing(
        self,
        engine: MetadataEngine,
    ) -> None:
        """Test that objects are cached after indexing."""
        # First get - from cache after indexing
        obj1 = await engine.get_object(MetadataType.CATALOG, "Товары")
        assert obj1 is not None

        # Second get - should still work
        obj2 = await engine.get_object(MetadataType.CATALOG, "Товары")
        assert obj2 is not None
        assert obj2.name == obj1.name

    @pytest.mark.asyncio
    async def test_search_uses_cache(self, engine: MetadataEngine) -> None:
        """Test that search uses cache."""
        # Multiple searches should work
        results1 = await engine.search("Товар")
        results2 = await engine.search("Товар")

        assert len(results1) == len(results2)
