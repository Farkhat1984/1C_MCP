"""
Unit tests for Metadata Indexer.

Tests indexing operations and cache population.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_1c.engines.metadata.indexer import MetadataIndexer, IndexProgress
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.metadata.cache import MetadataCache
from mcp_1c.domain.metadata import MetadataType, MetadataObject


class TestIndexProgress:
    """Test suite for IndexProgress."""

    def test_initial_state(self) -> None:
        """Test initial progress state."""
        progress = IndexProgress()

        assert progress.total == 0
        assert progress.processed == 0
        assert progress.updated == 0
        assert progress.skipped == 0
        assert progress.errors == []

    def test_percentage_zero_total(self) -> None:
        """Test percentage calculation with zero total."""
        progress = IndexProgress()
        assert progress.percentage == 0.0

    def test_percentage_calculation(self) -> None:
        """Test percentage calculation."""
        progress = IndexProgress()
        progress.total = 100
        progress.processed = 50

        assert progress.percentage == 50.0

    def test_percentage_full(self) -> None:
        """Test percentage at 100%."""
        progress = IndexProgress()
        progress.total = 10
        progress.processed = 10

        assert progress.percentage == 100.0


class TestMetadataIndexer:
    """Test suite for MetadataIndexer."""

    @pytest.fixture
    def parser(self) -> XmlParser:
        """Create parser instance."""
        return XmlParser()

    @pytest.fixture
    def mock_cache(self) -> AsyncMock:
        """Create mock cache."""
        cache = AsyncMock(spec=MetadataCache)
        cache.save_object = AsyncMock()
        cache.save_subsystem = AsyncMock()
        cache.get_hash = AsyncMock(return_value=None)
        return cache

    @pytest.fixture
    def indexer(self, parser: XmlParser, mock_cache: AsyncMock) -> MetadataIndexer:
        """Create indexer with mocked cache."""
        return MetadataIndexer(parser, mock_cache)

    @pytest.mark.asyncio
    async def test_index_configuration_returns_progress(
        self,
        indexer: MetadataIndexer,
        mock_config_path: Path,
    ) -> None:
        """Test that indexing returns progress object."""
        progress = await indexer.index_configuration(mock_config_path)

        assert isinstance(progress, IndexProgress)
        assert progress.total > 0
        assert progress.processed == progress.total

    @pytest.mark.asyncio
    async def test_index_configuration_counts_objects(
        self,
        indexer: MetadataIndexer,
        mock_config_path: Path,
    ) -> None:
        """Test that indexing counts all objects."""
        progress = await indexer.index_configuration(mock_config_path)

        # Config has: 2 catalogs, 2 documents, 1 common module, 1 subsystem,
        # 1 register, 1 constant, 1 functional option, 1 scheduled job,
        # 1 event subscription, 1 exchange plan, 1 HTTP service = 12+
        assert progress.total >= 12

    @pytest.mark.asyncio
    async def test_index_configuration_saves_to_cache(
        self,
        indexer: MetadataIndexer,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test that objects are saved to cache."""
        await indexer.index_configuration(mock_config_path)

        # Cache save_object should be called for each object
        assert mock_cache.save_object.call_count > 0

    @pytest.mark.asyncio
    async def test_index_configuration_indexes_subsystems(
        self,
        indexer: MetadataIndexer,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test that subsystems are indexed."""
        await indexer.index_configuration(mock_config_path)

        # Cache save_subsystem should be called
        assert mock_cache.save_subsystem.call_count > 0

    @pytest.mark.asyncio
    async def test_index_configuration_missing_config(
        self,
        indexer: MetadataIndexer,
        temp_dir: Path,
    ) -> None:
        """Test error handling when Configuration.xml is missing."""
        progress = await indexer.index_configuration(temp_dir)

        assert len(progress.errors) > 0
        assert progress.total == 0

    @pytest.mark.asyncio
    async def test_index_single_object(
        self,
        indexer: MetadataIndexer,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test indexing a single object."""
        obj = await indexer.index_single_object(
            mock_config_path,
            MetadataType.CATALOG,
            "Товары",
        )

        assert isinstance(obj, MetadataObject)
        assert obj.name == "Товары"
        mock_cache.save_object.assert_called()

    @pytest.mark.asyncio
    async def test_index_incremental_mode(
        self,
        indexer: MetadataIndexer,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test incremental indexing mode."""
        progress = await indexer.index_configuration(
            mock_config_path,
            incremental=True,
        )

        assert progress.processed > 0
        # In incremental mode, get_hash should be called
        # Note: Current implementation always updates

    @pytest.mark.asyncio
    async def test_index_full_mode(
        self,
        indexer: MetadataIndexer,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test full indexing mode."""
        progress = await indexer.index_configuration(
            mock_config_path,
            incremental=False,
        )

        assert progress.processed > 0
        assert progress.updated > 0

    @pytest.mark.asyncio
    async def test_index_handles_parse_errors(
        self,
        parser: XmlParser,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test error handling during parsing."""
        # Create indexer with mock parser that raises exception
        mock_parser = MagicMock(spec=XmlParser)
        mock_parser.parse_configuration.return_value = {
            MetadataType.CATALOG.value: ["BadObject"]
        }
        mock_parser.parse_metadata_object.side_effect = Exception("Parse error")

        indexer = MetadataIndexer(mock_parser, mock_cache)
        progress = await indexer.index_configuration(mock_config_path)

        assert len(progress.errors) > 0
        assert "Parse error" in progress.errors[0]

    @pytest.mark.asyncio
    async def test_index_progress_tracking(
        self,
        indexer: MetadataIndexer,
        mock_config_path: Path,
    ) -> None:
        """Test that progress is tracked correctly."""
        progress = await indexer.index_configuration(mock_config_path)

        # All objects should be processed
        assert progress.processed == progress.total

        # Updated + Skipped should equal processed (excluding errors)
        assert progress.updated + progress.skipped == progress.processed - len(progress.errors)


class TestIndexerIntegration:
    """Integration tests for indexer with real parser and mock cache."""

    @pytest.fixture
    def mock_cache(self) -> AsyncMock:
        """Create mock cache."""
        cache = AsyncMock(spec=MetadataCache)
        cache.save_object = AsyncMock()
        cache.save_subsystem = AsyncMock()
        cache.get_hash = AsyncMock(return_value=None)
        return cache

    @pytest.mark.asyncio
    async def test_full_indexing_workflow(
        self,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test complete indexing workflow."""
        parser = XmlParser()
        indexer = MetadataIndexer(parser, mock_cache)

        progress = await indexer.index_configuration(mock_config_path)

        # Verify all objects were indexed
        assert progress.total >= 12
        assert progress.processed == progress.total
        assert len(progress.errors) == 0
        assert progress.percentage == 100.0

        # Verify cache was populated with all real objects from mock config
        # At minimum: 2 catalogs + 2 documents + 1 common module + 1 register +
        # 1 constant + 1 functional option + 1 scheduled job + 1 event sub +
        # 1 exchange plan + 1 HTTP service = 11 objects
        assert mock_cache.save_object.call_count >= 11
        assert mock_cache.save_subsystem.call_count >= 1

    @pytest.mark.asyncio
    async def test_indexer_parses_all_metadata_types(
        self,
        mock_cache: AsyncMock,
        mock_config_path: Path,
    ) -> None:
        """Test that all metadata types are indexed."""
        parser = XmlParser()
        indexer = MetadataIndexer(parser, mock_cache)

        await indexer.index_configuration(mock_config_path)

        # Collect all saved objects
        saved_objects = [
            call.args[0] for call in mock_cache.save_object.call_args_list
        ]

        # Check that different metadata types are present
        types_indexed = set(obj.metadata_type for obj in saved_objects)

        assert MetadataType.CATALOG in types_indexed
        assert MetadataType.DOCUMENT in types_indexed
        assert MetadataType.COMMON_MODULE in types_indexed
        assert MetadataType.INFORMATION_REGISTER in types_indexed
