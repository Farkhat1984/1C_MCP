"""
Main Metadata Engine.

Facade that combines parser, indexer, cache, and watcher
into a single unified interface.
"""

from pathlib import Path

from mcp_1c.config import WorkspacePaths, get_config
from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem
from mcp_1c.engines.metadata.cache import MetadataCache
from mcp_1c.engines.metadata.indexer import IndexProgress, MetadataIndexer
from mcp_1c.engines.metadata.parser import XmlParser
from mcp_1c.engines.metadata.watcher import (
    ChangeAggregator,
    ConfigurationWatcher,
    FileChange,
)
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
        """Initialize engine components.

        The cache is bound lazily — its path depends on the indexed
        configuration, which is only known when ``initialize()`` is called.
        """
        self.logger = get_logger(__name__)
        self._config_path: Path | None = None
        self._workspace: WorkspacePaths | None = None
        self._overlays: list = []  # Phase F3: bound on initialize()
        self._initialized = False

        # Initialize stateless components; cache is created in initialize()
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
        *,
        overlay_roots: list | None = None,
    ) -> IndexProgress:
        """
        Initialize engine with configuration path and optional overlays.

        Args:
            config_path: Path to 1C configuration root
            full_reindex: Force full reindexing
            watch: Enable file watching
            overlay_roots: Phase F3. List of :class:`OverlayRoot` to
                index alongside the main config. Each overlay tree
                must look like a slice of a configuration (e.g. a
                ``CommonModules/`` subtree); we index whatever XML
                metadata it contains and stamp every object with
                ``source="overlay:<name>"``.

        Returns:
            Indexing progress/statistics — combined across the main
            config and every overlay. Errors from one overlay don't
            abort the others; they accumulate in ``progress.errors``.
        """
        from mcp_1c.config import OverlayRoot

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
        overlays: list[OverlayRoot] = list(overlay_roots or [])

        # Resolve per-workspace storage layout (XDG cache by default).
        # Workspace id includes the overlay set so adding/removing
        # overlays produces a fresh cache directory rather than mixing
        # records into the legacy one.
        self._workspace = WorkspacePaths.for_config(
            config_path, overlays=overlays
        )
        self._workspace.cache_db.parent.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            f"Workspace {self._workspace.workspace_id}: cache={self._workspace.cache_db} "
            f"({len(overlays)} overlay(s))"
        )

        # Re-bind cache to workspace path (cheap if already same)
        if self._cache.db_path != self._workspace.cache_db:
            await self._cache.close()
            self._cache = MetadataCache(self._workspace.cache_db)
            self._indexer = MetadataIndexer(self._parser, self._cache)

        # Connect to cache
        await self._cache.connect()

        # Clear cache if full reindex requested
        if full_reindex:
            self.logger.info("Clearing cache for full reindex")
            await self._cache.clear()

        # Index main config first.
        progress = await self._indexer.index_configuration(
            config_path,
            incremental=not full_reindex,
            source="config",
        )

        # Then each overlay. We sort by descending priority so the
        # higher-priority overlays land first; this only affects
        # progress logs (data lives in its own ``source`` namespace).
        # Overlays whose path lacks a Configuration.xml are skipped
        # with a warning — that's a partial overlay (e.g. a folder of
        # CommonModules) which today's indexer can't enumerate
        # standalone. Phase F3.5 adds standalone-tree support.
        for overlay in sorted(
            overlays, key=lambda o: o.priority, reverse=True
        ):
            overlay_xml = overlay.path / "Configuration.xml"
            if not overlay_xml.exists():
                self.logger.warning(
                    f"Overlay {overlay.name!r} at {overlay.path} has no "
                    "Configuration.xml; skipping (standalone-tree overlays "
                    "are not yet supported — wrap your modules in a minimal "
                    "Configuration.xml or wait for F3.5)."
                )
                continue
            self.logger.info(
                f"Indexing overlay {overlay.name!r} at {overlay.path}"
            )
            try:
                await self._indexer.index_configuration(
                    overlay.path,
                    incremental=not full_reindex,
                    source=overlay.source_label,
                    progress=progress,
                )
            except Exception as exc:
                progress.errors.append(
                    f"Overlay {overlay.name!r}: {exc}"
                )
                self.logger.error(
                    f"Failed to index overlay {overlay.name!r}: {exc}"
                )

        self._initialized = True
        self._overlays = overlays

        # Start watching: main config plus every existing overlay path.
        if watch:
            watch_paths = [config_path] + [
                o.path for o in overlays if o.path.exists()
            ]
            await self._watcher.start(watch_paths)

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

    @property
    def workspace(self) -> WorkspacePaths | None:
        """Resolved storage paths for the current configuration, if any."""
        return self._workspace

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

        After re-indexing the affected metadata object, invalidate
        downstream caches that depend on it: the LSP ``documentSymbol``
        cache (so the next code-tools call hits the server fresh) and
        the embedding store (so semantic search doesn't return stale
        chunks). KG invalidation is delegated to the embedding/KG
        engines themselves once they grow watcher hooks — currently a
        no-op when those engines aren't initialised.

        We swallow errors here on purpose: a failing watcher must never
        bring the server down. The downstream cache will heal on the
        next full re-index, and the error is logged.

        Args:
            change: File change event
        """
        if not self._config_path:
            return

        # Only process relevant files
        if not (change.is_xml or change.is_bsl):
            return

        metadata_type, object_name = change.get_metadata_info()
        if not (metadata_type and object_name):
            return

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
            return

        await self._invalidate_downstream(
            metadata_type, object_name, change.path
        )

    async def _invalidate_downstream(
        self,
        metadata_type: MetadataType,
        object_name: str,
        changed_path: Path,
    ) -> None:
        """Drop cached LSP symbols and embedding chunks for the changed object.

        Lazy-imports the engines so the metadata package doesn't acquire
        a hard runtime dependency on embeddings/code/kg — keeps the
        existing layering intact. Each invalidation is best-effort:
        a logging warning, no exception.
        """
        # 1. LSP documentSymbol cache — keyed on file path. Only the
        # actual changed file needs dropping, so we use change.path.
        try:
            from mcp_1c.engines.code import CodeEngine

            code_engine = CodeEngine.get_instance()
            if changed_path.suffix.lower() == ".bsl":
                await code_engine.invalidate_lsp_cache(changed_path)
        except Exception as exc:
            self.logger.debug(f"LSP cache invalidation skipped: {exc}")

        # 2. Embedding store — chunks are keyed by full object name.
        try:
            from mcp_1c.engines.embeddings.engine import EmbeddingEngine

            embeddings = EmbeddingEngine.get_instance()
            if embeddings.initialized:
                full_name = f"{metadata_type.value}.{object_name}"
                await embeddings.invalidate_object(full_name)
        except Exception as exc:
            self.logger.debug(f"Embedding invalidation skipped: {exc}")

        # 3. KG node — same identity (Type.Name).
        try:
            from mcp_1c.engines.knowledge_graph.engine import (
                KnowledgeGraphEngine,
            )

            kg = KnowledgeGraphEngine.get_instance()
            if getattr(kg, "_built", False):
                full_name = f"{metadata_type.value}.{object_name}"
                if hasattr(kg, "invalidate_node"):
                    await kg.invalidate_node(full_name)
        except Exception as exc:
            self.logger.debug(f"KG invalidation skipped: {exc}")
