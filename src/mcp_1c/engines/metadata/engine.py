"""
Main Metadata Engine.

Facade that combines parser, indexer, cache, and watcher
into a single unified interface.
"""

from pathlib import Path
from typing import Callable, Awaitable

from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.metadata.indexer import MetadataIndexer, IndexProgress
from mcp_1c.engines.metadata.cache import MetadataCache
from mcp_1c.engines.metadata.watcher import (
    ConfigurationWatcher,
    FileChange,
    ChangeAggregator,
)
from mcp_1c.config import get_config, CacheConfig, WatcherConfig
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class MetadataEngine:
    """
    Main engine for metadata operations.

    Provides a unified interface for:
    - Initializing and indexing configurations
    - Querying metadata objects
    - Watching for changes
    """

    _instance: "MetadataEngine | None" = None

    def __init__(self) -> None:
        """Initialize engine components."""
        self.logger = get_logger(__name__)
        self._config_path: Path | None = None
        self._initialized = False

        # Initialize components
        config = get_config()
        self._parser = XmlParser()
        self._cache = MetadataCache(config.cache.db_path)
        self._indexer = MetadataIndexer(self._parser, self._cache)
        self._watcher = ConfigurationWatcher(
            config.watcher,
            on_change=self._handle_change,
        )
        self._change_aggregator = ChangeAggregator()

    @classmethod
    def get_instance(cls) -> "MetadataEngine":
        """
        Get singleton instance.

        Returns:
            MetadataEngine instance
        """
        if cls._instance is None:
            cls._instance = MetadataEngine()
        return cls._instance

    @property
    def is_initialized(self) -> bool:
        """Check if engine is initialized."""
        return self._initialized

    @property
    def config_path(self) -> Path | None:
        """Get current configuration path."""
        return self._config_path

    async def initialize(
        self,
        config_path: Path,
        full_reindex: bool = False,
        watch: bool = True,
    ) -> IndexProgress:
        """
        Initialize engine with configuration path.

        Args:
            config_path: Path to 1C configuration root
            full_reindex: Force full reindexing
            watch: Enable file watching

        Returns:
            Indexing progress/statistics
        """
        self.logger.info(f"Initializing metadata engine: {config_path}")

        # Validate path
        if not config_path.exists():
            raise ValueError(f"Configuration path does not exist: {config_path}")

        config_xml = config_path / "Configuration.xml"
        if not config_xml.exists():
            raise ValueError(
                f"Invalid configuration: Configuration.xml not found at {config_path}"
            )

        self._config_path = config_path

        # Connect to cache
        await self._cache.connect()

        # Clear cache if full reindex requested
        if full_reindex:
            self.logger.info("Clearing cache for full reindex")
            await self._cache.clear()

        # Index configuration
        progress = await self._indexer.index_configuration(
            config_path,
            incremental=not full_reindex,
        )

        self._initialized = True

        # Start watching
        if watch:
            await self._watcher.start(config_path)

        return progress

    async def shutdown(self) -> None:
        """Shutdown engine and release resources."""
        self.logger.info("Shutting down metadata engine")
        await self._watcher.stop()
        await self._cache.close()
        self._initialized = False

    async def get_object(
        self,
        metadata_type: MetadataType | str,
        name: str,
    ) -> MetadataObject | None:
        """
        Get metadata object by type and name.

        Args:
            metadata_type: Object type (enum or string)
            name: Object name

        Returns:
            MetadataObject or None
        """
        self._ensure_initialized()

        if isinstance(metadata_type, str):
            metadata_type = MetadataType(metadata_type)

        return await self._cache.get_object(metadata_type, name)

    async def list_objects(
        self,
        metadata_type: MetadataType | str,
    ) -> list[MetadataObject]:
        """
        List all objects of a type.

        Args:
            metadata_type: Object type

        Returns:
            List of MetadataObjects
        """
        self._ensure_initialized()

        if isinstance(metadata_type, str):
            metadata_type = MetadataType(metadata_type)

        return await self._cache.get_objects_by_type(metadata_type)

    async def search(
        self,
        query: str,
        metadata_type: MetadataType | str | None = None,
        limit: int = 50,
    ) -> list[MetadataObject]:
        """
        Search objects by name or synonym.

        Args:
            query: Search query
            metadata_type: Optional type filter
            limit: Maximum results

        Returns:
            List of matching objects
        """
        self._ensure_initialized()

        if isinstance(metadata_type, str):
            metadata_type = MetadataType(metadata_type)

        return await self._cache.search_objects(query, metadata_type, limit)

    async def get_subsystem_tree(
        self,
        parent: str | None = None,
    ) -> list[Subsystem]:
        """
        Get subsystem tree.

        Args:
            parent: Parent subsystem name or None for root

        Returns:
            List of subsystems
        """
        self._ensure_initialized()
        return await self._cache.get_subsystems(parent)

    async def get_stats(self) -> dict[str, int]:
        """
        Get statistics about indexed objects.

        Returns:
            Dictionary with counts by type
        """
        self._ensure_initialized()
        return await self._cache.get_stats()

    async def get_attributes(
        self,
        metadata_type: MetadataType | str,
        name: str,
    ) -> list:
        """
        Get attributes of a metadata object.

        Args:
            metadata_type: Object type
            name: Object name

        Returns:
            List of Attribute objects
        """
        obj = await self.get_object(metadata_type, name)
        if obj is None:
            return []
        return obj.attributes

    @property
    def cache(self) -> MetadataCache:
        """Get cache instance."""
        return self._cache

    async def refresh_object(
        self,
        metadata_type: MetadataType | str,
        name: str,
    ) -> MetadataObject:
        """
        Force refresh of a single object.

        Args:
            metadata_type: Object type
            name: Object name

        Returns:
            Refreshed MetadataObject
        """
        self._ensure_initialized()

        if isinstance(metadata_type, str):
            metadata_type = MetadataType(metadata_type)

        if self._config_path is None:
            raise RuntimeError("Configuration path not set")

        return await self._indexer.index_single_object(
            self._config_path,
            metadata_type,
            name,
        )

    def _ensure_initialized(self) -> None:
        """Ensure engine is initialized."""
        if not self._initialized:
            raise RuntimeError(
                "Metadata engine not initialized. "
                "Call metadata.init first."
            )

    async def _handle_change(self, change: FileChange) -> None:
        """
        Handle file change event.

        Args:
            change: File change event
        """
        if not self._config_path:
            return

        # Only process relevant files
        if not (change.is_xml or change.is_bsl):
            return

        metadata_type, object_name = change.get_metadata_info()
        if metadata_type and object_name:
            self.logger.info(
                f"Detected change in {metadata_type.value}.{object_name}"
            )
            try:
                await self._indexer.index_single_object(
                    self._config_path,
                    metadata_type,
                    object_name,
                )
            except Exception as e:
                self.logger.error(f"Error re-indexing object: {e}")
