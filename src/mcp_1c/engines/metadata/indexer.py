"""
Metadata Indexer.

Scans configuration directory and builds metadata index.
Supports incremental updates based on file hashes.
Optimized with parallel processing for large configurations.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncIterator

from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.metadata.cache import MetadataCache
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.profiler import get_profiler

logger = get_logger(__name__)
profiler = get_profiler()


class IndexProgress:
    """Progress tracking for indexing operation."""

    def __init__(self) -> None:
        """Initialize progress tracker."""
        self.total: int = 0
        self.processed: int = 0
        self.updated: int = 0
        self.skipped: int = 0
        self.errors: list[str] = []

    @property
    def percentage(self) -> float:
        """Get completion percentage."""
        if self.total == 0:
            return 0.0
        return (self.processed / self.total) * 100


class MetadataIndexer:
    """
    Indexer for 1C configuration metadata.

    Scans configuration directory, parses XML files,
    and populates the cache with metadata objects.

    Optimized with:
    - Parallel parsing using ThreadPoolExecutor
    - Batch database operations
    - Semaphore-limited concurrency
    """

    # Number of concurrent parsing operations
    MAX_CONCURRENT_PARSE = 10

    # Number of threads for CPU-bound parsing
    PARSE_WORKERS = 4

    def __init__(
        self,
        parser: XmlParser,
        cache: MetadataCache,
    ) -> None:
        """
        Initialize indexer.

        Args:
            parser: XML parser instance
            cache: Metadata cache instance
        """
        self.parser = parser
        self.cache = cache
        self.logger = get_logger(__name__)
        self._semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_PARSE)
        self._executor = ThreadPoolExecutor(max_workers=self.PARSE_WORKERS)

    async def index_configuration(
        self,
        config_path: Path,
        incremental: bool = True,
        parallel: bool = True,
    ) -> IndexProgress:
        """
        Index entire configuration.

        Args:
            config_path: Path to configuration root
            incremental: Only update changed files
            parallel: Use parallel processing

        Returns:
            IndexProgress with statistics
        """
        progress = IndexProgress()

        self.logger.info(f"Starting indexing: {config_path}")
        self.logger.info(f"Mode: {'incremental' if incremental else 'full'}")
        self.logger.info(f"Parallel: {parallel}")

        async with profiler.measure("indexer.parse_configuration"):
            # Parse configuration to get object list
            try:
                objects_by_type = self.parser.parse_configuration(config_path)
            except FileNotFoundError as e:
                self.logger.error(str(e))
                progress.errors.append(str(e))
                return progress

        # Count total objects
        for obj_list in objects_by_type.values():
            progress.total += len(obj_list)

        self.logger.info(f"Found {progress.total} objects to index")

        # Start batch mode for bulk inserts
        await self.cache.start_batch()

        try:
            if parallel and progress.total > 20:
                # Use parallel indexing for large configurations
                await self._index_parallel(
                    config_path,
                    objects_by_type,
                    incremental,
                    progress,
                )
            else:
                # Sequential indexing for small configurations
                await self._index_sequential(
                    config_path,
                    objects_by_type,
                    incremental,
                    progress,
                )
        finally:
            # End batch mode - flush remaining objects
            await self.cache.end_batch()

        # Index subsystems
        await self._index_subsystems(config_path)

        self.logger.info(
            f"Indexing complete: {progress.updated} updated, "
            f"{progress.skipped} skipped, {len(progress.errors)} errors"
        )

        # Generate profiling report
        profiler.report()

        return progress

    async def _index_sequential(
        self,
        config_path: Path,
        objects_by_type: dict[str, list[str]],
        incremental: bool,
        progress: IndexProgress,
    ) -> None:
        """Sequential indexing for small configurations."""
        for type_name, object_names in objects_by_type.items():
            metadata_type = MetadataType(type_name)

            for obj_name in object_names:
                try:
                    updated = await self._index_object(
                        config_path,
                        metadata_type,
                        obj_name,
                        incremental,
                    )
                    if updated:
                        progress.updated += 1
                    else:
                        progress.skipped += 1
                except Exception as e:
                    error_msg = f"Error indexing {type_name}.{obj_name}: {e}"
                    self.logger.error(error_msg)
                    progress.errors.append(error_msg)
                finally:
                    progress.processed += 1

                # Log progress every 100 objects
                if progress.processed % 100 == 0:
                    self.logger.info(
                        f"Progress: {progress.processed}/{progress.total} "
                        f"({progress.percentage:.1f}%)"
                    )

    async def _index_parallel(
        self,
        config_path: Path,
        objects_by_type: dict[str, list[str]],
        incremental: bool,
        progress: IndexProgress,
    ) -> None:
        """Parallel indexing for large configurations."""
        # Collect all indexing tasks
        tasks = []

        for type_name, object_names in objects_by_type.items():
            metadata_type = MetadataType(type_name)

            for obj_name in object_names:
                task = self._index_object_with_semaphore(
                    config_path,
                    metadata_type,
                    obj_name,
                    incremental,
                )
                tasks.append((type_name, obj_name, task))

        # Process in batches to avoid memory issues
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            batch_coros = [t[2] for t in batch]

            results = await asyncio.gather(*batch_coros, return_exceptions=True)

            for (type_name, obj_name, _), result in zip(batch, results):
                progress.processed += 1

                if isinstance(result, Exception):
                    error_msg = f"Error indexing {type_name}.{obj_name}: {result}"
                    self.logger.error(error_msg)
                    progress.errors.append(error_msg)
                elif result:
                    progress.updated += 1
                else:
                    progress.skipped += 1

            # Log progress
            if progress.processed % 100 == 0 or progress.processed == progress.total:
                self.logger.info(
                    f"Progress: {progress.processed}/{progress.total} "
                    f"({progress.percentage:.1f}%)"
                )

    async def _index_object_with_semaphore(
        self,
        config_path: Path,
        metadata_type: MetadataType,
        object_name: str,
        incremental: bool,
    ) -> bool:
        """Index object with semaphore for concurrency control."""
        async with self._semaphore:
            return await self._index_object(
                config_path,
                metadata_type,
                object_name,
                incremental,
            )

    async def _index_object(
        self,
        config_path: Path,
        metadata_type: MetadataType,
        object_name: str,
        incremental: bool,
    ) -> bool:
        """
        Index a single object.

        Args:
            config_path: Configuration root path
            metadata_type: Object type
            object_name: Object name
            incremental: Check hash before updating

        Returns:
            True if object was updated
        """
        # Check if update needed
        if incremental:
            existing_hash = await self.cache.get_hash(metadata_type, object_name)
            # Calculate current hash
            current_hash = await self._calculate_hash(
                config_path, metadata_type, object_name
            )
            if existing_hash and existing_hash == current_hash:
                return False  # Skip unchanged objects

        async with profiler.measure("indexer.parse_object"):
            # Parse object (CPU-bound, run in executor)
            loop = asyncio.get_event_loop()
            obj = await loop.run_in_executor(
                self._executor,
                self.parser.parse_metadata_object,
                config_path,
                metadata_type,
                object_name,
            )

        async with profiler.measure("indexer.save_object"):
            await self.cache.save_object(obj)

        return True

    async def _calculate_hash(
        self,
        config_path: Path,
        metadata_type: MetadataType,
        object_name: str,
    ) -> str | None:
        """
        Calculate file hash for change detection.

        Args:
            config_path: Configuration root path
            metadata_type: Object type
            object_name: Object name

        Returns:
            File hash or None if file not found
        """
        import hashlib

        # Determine object directory
        type_dirs = {
            MetadataType.CATALOG: "Catalogs",
            MetadataType.DOCUMENT: "Documents",
            MetadataType.REPORT: "Reports",
            MetadataType.DATA_PROCESSOR: "DataProcessors",
            MetadataType.INFORMATION_REGISTER: "InformationRegisters",
            MetadataType.ACCUMULATION_REGISTER: "AccumulationRegisters",
            MetadataType.ENUM: "Enums",
        }

        type_dir = type_dirs.get(metadata_type)
        if not type_dir:
            return None

        object_path = config_path / type_dir / object_name
        if not object_path.exists():
            return None

        # Calculate hash of main XML file
        xml_path = object_path / f"{object_name}.xml"
        if not xml_path.exists():
            # Try alternate naming
            for xml_file in object_path.glob("*.xml"):
                xml_path = xml_file
                break
            else:
                return None

        try:
            hasher = hashlib.md5()
            with open(xml_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except OSError:
            return None

    async def _index_subsystems(
        self,
        config_path: Path,
        parent: str | None = None,
    ) -> None:
        """
        Recursively index subsystems.

        Args:
            config_path: Configuration root path
            parent: Parent subsystem name
        """
        if parent:
            subsystems_path = config_path / "Subsystems" / parent / "Subsystems"
        else:
            subsystems_path = config_path / "Subsystems"

        if not subsystems_path.exists():
            return

        for subsystem_dir in subsystems_path.iterdir():
            if not subsystem_dir.is_dir():
                continue

            subsystem_name = subsystem_dir.name

            try:
                subsystem = self.parser.parse_subsystem(
                    config_path,
                    subsystem_name,
                    parent,
                )
                await self.cache.save_subsystem(subsystem)

                # Recursively index children
                if subsystem.children:
                    full_name = f"{parent}.{subsystem_name}" if parent else subsystem_name
                    await self._index_subsystems(config_path, full_name)

            except Exception as e:
                self.logger.error(f"Error indexing subsystem {subsystem_name}: {e}")

    async def index_single_object(
        self,
        config_path: Path,
        metadata_type: MetadataType,
        object_name: str,
    ) -> MetadataObject:
        """
        Index or re-index a single object.

        Args:
            config_path: Configuration root path
            metadata_type: Object type
            object_name: Object name

        Returns:
            Indexed MetadataObject
        """
        obj = self.parser.parse_metadata_object(
            config_path,
            metadata_type,
            object_name,
        )
        await self.cache.save_object(obj)
        return obj

    async def remove_object(
        self,
        metadata_type: MetadataType,
        object_name: str,
    ) -> None:
        """
        Remove object from index.

        Args:
            metadata_type: Object type
            object_name: Object name
        """
        # TODO: Implement deletion in cache
        pass
