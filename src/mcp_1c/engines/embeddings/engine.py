"""
Embeddings Engine for semantic search over 1C configurations.

Singleton engine that orchestrates indexing of BSL modules, procedures,
and metadata descriptions into vector embeddings, and provides
semantic search capabilities.
"""

from __future__ import annotations

import gc
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_1c.config import EmbeddingConfig
from mcp_1c.domain.embedding import EmbeddingDocument, EmbeddingStats, SearchResult
from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.embeddings.chunking import (
    chunk_module_text,
    chunk_procedure_text,
    make_chunk_id,
    prepare_metadata_text,
)
from mcp_1c.engines.embeddings.local_client import make_embedding_client
from mcp_1c.engines.embeddings.storage import VectorStorage
from mcp_1c.utils.logger import get_logger

if TYPE_CHECKING:
    from mcp_1c.engines.code.engine import CodeEngine
    from mcp_1c.engines.metadata.engine import MetadataEngine

logger = get_logger(__name__)

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]] | None


class EmbeddingEngine:
    """Singleton engine for semantic search over 1C codebase.

    Manages the lifecycle of embedding client and vector storage,
    provides indexing and search operations.
    """

    _instance: EmbeddingEngine | None = None

    @classmethod
    def get_instance(cls) -> EmbeddingEngine:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = EmbeddingEngine()
        return cls._instance

    def __init__(self) -> None:
        self._client: Any = None  # EmbeddingClient | LocalEmbeddingClient
        self._storage: VectorStorage | None = None
        self._config: EmbeddingConfig | None = None
        self._initialized = False

    @property
    def initialized(self) -> bool:
        """Whether the engine has been initialized."""
        return self._initialized

    async def initialize(self, config: EmbeddingConfig, db_path: Path) -> None:
        """Initialize the engine with configuration and storage path.

        Args:
            config: Embedding configuration.
            db_path: Path to SQLite database for vector storage.
        """
        if self._initialized:
            logger.debug("Embedding engine already initialized, skipping")
            return

        self._config = config
        self._client = make_embedding_client(config)
        self._storage = VectorStorage(db_path, dimension=config.dimension)
        await self._storage.init_tables()
        self._initialized = True
        logger.info(
            f"Embeddings ready: backend={config.backend} model={config.model} dim={config.dimension}"
        )
        logger.info(
            f"Embedding engine initialized "
            f"(model={config.model}, max_concurrent={config.max_concurrent}, db={db_path})"
        )

    def _ensure_initialized(self) -> None:
        """Raise if engine is not initialized."""
        if not self._initialized or self._client is None or self._storage is None:
            raise RuntimeError(
                "EmbeddingEngine not initialized. "
                "Call initialize() first or use the embedding.index tool."
            )

    async def _embed_and_save_batch(
        self,
        documents: list[EmbeddingDocument],
        texts: list[str],
        skip_vec: bool = False,
    ) -> int:
        """Embed a batch of texts and save documents to storage."""
        assert self._client is not None
        assert self._storage is not None

        embeddings = await self._client.embed_batched(texts)
        for doc, emb in zip(documents, embeddings, strict=True):
            doc.embedding = emb
        return await self._storage.save_documents(documents, skip_vec=skip_vec)

    async def _count_modules(
        self,
        metadata_engine: MetadataEngine,
        indexable_types: list[MetadataType],
    ) -> int:
        """Count total existing modules across all indexable types.

        Args:
            metadata_engine: Initialized MetadataEngine instance.
            indexable_types: Metadata types to scan.

        Returns:
            Total number of modules with existing files.
        """
        total = 0
        for md_type in indexable_types:
            try:
                objects = await metadata_engine.list_objects(md_type)
            except Exception:
                continue
            for obj in objects:
                for module in obj.modules:
                    if module.exists and module.path.exists():
                        total += 1
            del objects
            gc.collect()
        return total

    async def index_modules(
        self,
        metadata_engine: MetadataEngine,
        code_engine: CodeEngine,
        progress_cb: ProgressCallback = None,
        force_reindex: bool = False,
    ) -> dict[str, int]:
        """Index all BSL modules from the configuration.

        Supports resume: already-indexed modules are skipped unless
        force_reindex is True.

        Args:
            metadata_engine: Initialized MetadataEngine instance.
            code_engine: Initialized CodeEngine instance.
            progress_cb: Optional async callback for progress updates.
            force_reindex: If True, re-embed everything ignoring existing data.

        Returns:
            Stats dict with counts: indexed, skipped, errors, total, processed.
        """
        self._ensure_initialized()
        assert self._client is not None
        assert self._storage is not None
        assert self._config is not None

        stats = {"indexed": 0, "skipped": 0, "errors": 0, "processed": 0, "total": 0}

        indexable_types = [
            MetadataType.CATALOG,
            MetadataType.DOCUMENT,
            MetadataType.REPORT,
            MetadataType.DATA_PROCESSOR,
            MetadataType.INFORMATION_REGISTER,
            MetadataType.ACCUMULATION_REGISTER,
            MetadataType.ACCOUNTING_REGISTER,
            MetadataType.CALCULATION_REGISTER,
            MetadataType.CHART_OF_CHARACTERISTIC_TYPES,
            MetadataType.CHART_OF_ACCOUNTS,
            MetadataType.CHART_OF_CALCULATION_TYPES,
            MetadataType.EXCHANGE_PLAN,
            MetadataType.BUSINESS_PROCESS,
            MetadataType.TASK,
            MetadataType.COMMON_MODULE,
        ]

        # Count total modules for progress reporting
        stats["total"] = await self._count_modules(metadata_engine, indexable_types)

        # Load existing base prefixes for resume support (O(1) lookup)
        existing_prefixes: set[str] = set()
        if not force_reindex:
            existing_ids = await self._storage.get_existing_ids()
            for eid in existing_ids:
                # Strip .chunk_N suffix to get base prefix
                base = eid.rsplit(".chunk_", 1)[0] if ".chunk_" in eid else eid
                existing_prefixes.add(base)
            if existing_prefixes:
                logger.info(
                    f"Resume mode: {len(existing_prefixes)} existing module prefixes, "
                    f"will skip already-indexed modules"
                )

        for md_type in indexable_types:
            try:
                objects = await metadata_engine.list_objects(md_type)
            except Exception as exc:
                logger.warning(f"Failed to list {md_type.value}: {exc}")
                continue

            for obj in objects:
                for module in obj.modules:
                    if not module.exists or not module.path.exists():
                        stats["skipped"] += 1
                        stats["processed"] += 1
                        continue

                    try:
                        obj_full = f"{obj.metadata_type.value}.{obj.name}"
                        base_id = f"{obj_full}.{module.module_type.value}"

                        # Resume: O(1) prefix lookup
                        if not force_reindex and base_id in existing_prefixes:
                            stats["skipped"] += 1
                            stats["processed"] += 1
                            if progress_cb is not None:
                                await progress_cb({
                                    "stage": "modules",
                                    "processed": stats["processed"],
                                    "total": stats["total"],
                                    "indexed": stats["indexed"],
                                    "skipped": stats["skipped"],
                                })
                            continue

                        bsl_module = await code_engine.get_module_by_path(module.path)
                        content = bsl_module.content
                        del bsl_module

                        if force_reindex:
                            await self._storage.delete_by_prefix(base_id)

                        chunks = chunk_module_text(
                            obj_full_name=obj_full,
                            synonym=obj.synonym,
                            comment=obj.comment,
                            module_type=module.module_type.value,
                            content=content,
                            chunk_size=self._config.chunk_size,
                            overlap=self._config.chunk_overlap,
                        )
                        del content

                        module_docs: list[EmbeddingDocument] = []
                        module_texts: list[str] = []
                        for text, extra in chunks:
                            chunk_idx = int(extra["chunk_index"])
                            chunk_total = int(extra["chunk_total"])
                            doc_id = make_chunk_id(base_id, chunk_idx, chunk_total)

                            doc = EmbeddingDocument(
                                id=doc_id,
                                content=text,
                                doc_type="module",
                                metadata={
                                    "object_type": obj.metadata_type.value,
                                    "object_name": obj.name,
                                    "module_type": module.module_type.value,
                                    "synonym": obj.synonym,
                                    "chunk_index": extra["chunk_index"],
                                    "chunk_total": extra["chunk_total"],
                                },
                            )
                            module_docs.append(doc)
                            module_texts.append(text)

                        # Flush per module to bound memory
                        if module_texts:
                            saved = await self._embed_and_save_batch(
                                module_docs, module_texts, skip_vec=True
                            )
                            stats["indexed"] += saved
                            del module_docs, module_texts

                        stats["processed"] += 1
                        gc.collect()

                        if progress_cb is not None:
                            await progress_cb({
                                "stage": "modules",
                                "processed": stats["processed"],
                                "total": stats["total"],
                                "indexed": stats["indexed"],
                                "skipped": stats["skipped"],
                            })

                    except Exception as exc:
                        logger.warning(f"Error preparing module {module.path}: {exc}")
                        stats["errors"] += 1
                        stats["processed"] += 1


        logger.info(f"Module indexing complete: {stats}")
        return stats

    async def index_procedures(
        self,
        metadata_engine: MetadataEngine,
        code_engine: CodeEngine,
        progress_cb: ProgressCallback = None,
        force_reindex: bool = False,
    ) -> dict[str, int]:
        """Index individual procedures for fine-grained search.

        Supports resume: already-indexed procedures are skipped unless
        force_reindex is True.

        Args:
            metadata_engine: Initialized MetadataEngine instance.
            code_engine: Initialized CodeEngine instance.
            progress_cb: Optional async callback for progress updates.
            force_reindex: If True, re-embed everything ignoring existing data.

        Returns:
            Stats dict with counts: indexed, skipped, errors, total, processed.
        """
        self._ensure_initialized()
        assert self._client is not None
        assert self._storage is not None
        assert self._config is not None

        stats = {"indexed": 0, "skipped": 0, "errors": 0, "processed": 0, "total": 0}

        indexable_types = [
            MetadataType.CATALOG,
            MetadataType.DOCUMENT,
            MetadataType.REPORT,
            MetadataType.DATA_PROCESSOR,
            MetadataType.COMMON_MODULE,
            MetadataType.INFORMATION_REGISTER,
            MetadataType.ACCUMULATION_REGISTER,
        ]

        # Use module count as approximate total (avoids parsing all BSL upfront)
        stats["total"] = await self._count_modules(metadata_engine, indexable_types)

        # Build module-level skip set for fast resume (no BSL parsing needed)
        existing_prefixes: set[str] = set()
        indexed_modules: set[str] = set()
        if not force_reindex:
            for eid in await self._storage.get_existing_ids():
                base = eid.rsplit(".chunk_", 1)[0] if ".chunk_" in eid else eid
                existing_prefixes.add(base)
                # "Type.Name.ModuleType.ProcName" → "Type.Name.ModuleType."
                parts = base.split(".")
                if len(parts) >= 4:
                    indexed_modules.add(".".join(parts[:3]) + ".")

        for md_type in indexable_types:
            try:
                objects = await metadata_engine.list_objects(md_type)
            except Exception as exc:
                logger.warning(f"Failed to list {md_type.value}: {exc}")
                continue

            for obj in objects:
                for module in obj.modules:
                    if not module.exists or not module.path.exists():
                        continue

                    obj_full = f"{obj.metadata_type.value}.{obj.name}"
                    module_prefix = f"{obj_full}.{module.module_type.value}."

                    # Resume: skip entire module if procedures from it exist (O(1))
                    if not force_reindex and module_prefix in indexed_modules:
                        stats["skipped"] += 1
                        stats["processed"] += 1
                        if progress_cb is not None:
                            await progress_cb({
                                "stage": "procedures",
                                "processed": stats["processed"],
                                "total": stats["total"],
                                "indexed": stats["indexed"],
                                "skipped": stats["skipped"],
                            })
                        continue

                    logger.info(f"[proc] parse: {module.path}")
                    try:
                        import asyncio as _asyncio
                        bsl_module = await _asyncio.wait_for(
                            code_engine.get_module_by_path(module.path),
                            timeout=90.0,
                        )
                        # Extract only what we need, then release the BSL module
                        procedures = list(bsl_module.procedures)
                        del bsl_module
                        logger.info(f"[proc] parsed: {module.path} procs={len(procedures)}")
                    except Exception as exc:
                        logger.warning(f"Error parsing {module.path}: {exc}")
                        stats["errors"] += 1
                        stats["processed"] += 1
                        if progress_cb is not None:
                            await progress_cb({
                                "stage": "procedures",
                                "processed": stats["processed"],
                                "total": stats["total"],
                                "indexed": stats["indexed"],
                                "skipped": stats["skipped"],
                            })
                        continue

                    mod_docs: list[EmbeddingDocument] = []
                    mod_texts: list[str] = []

                    for proc in procedures:
                        try:
                            base_id = f"{obj_full}.{module.module_type.value}.{proc.name}"

                            # Resume: O(1) prefix lookup
                            if not force_reindex and base_id in existing_prefixes:
                                continue

                            if force_reindex:
                                await self._storage.delete_by_prefix(base_id)

                            chunks = chunk_procedure_text(
                                obj_full_name=obj_full,
                                proc_name=proc.name,
                                is_function=proc.is_function,
                                is_export=proc.is_export,
                                directive=proc.directive.value if proc.directive else "",
                                proc_comment=proc.comment,
                                body=proc.body,
                                signature=proc.signature,
                                max_chunk_chars=self._config.max_procedure_chars,
                                overlap_chars=self._config.chunk_overlap,
                            )

                            for text, extra in chunks:
                                chunk_idx = int(extra["chunk_index"])
                                chunk_total = int(extra["chunk_total"])
                                doc_id = make_chunk_id(base_id, chunk_idx, chunk_total)

                                doc = EmbeddingDocument(
                                    id=doc_id,
                                    content=text,
                                    doc_type="procedure",
                                    metadata={
                                        "object_type": obj.metadata_type.value,
                                        "object_name": obj.name,
                                        "module_type": module.module_type.value,
                                        "procedure_name": proc.name,
                                        "is_function": str(proc.is_function),
                                        "is_export": str(proc.is_export),
                                        "chunk_index": extra["chunk_index"],
                                        "chunk_total": extra["chunk_total"],
                                    },
                                )
                                mod_docs.append(doc)
                                mod_texts.append(text)

                        except Exception as exc:
                            logger.warning(
                                f"Error preparing procedure {proc.name}: {exc}"
                            )
                            stats["errors"] += 1

                    # Free parsed procedures immediately
                    del procedures

                    # Flush after each module to bound memory
                    if mod_texts:
                        logger.info(f"[proc] embed {len(mod_texts)} texts for {module_prefix}")
                        saved = await self._embed_and_save_batch(
                            mod_docs, mod_texts, skip_vec=True
                        )
                        logger.info(f"[proc] saved {saved} docs for {module_prefix}")
                        stats["indexed"] += saved
                    del mod_docs, mod_texts
                    gc.collect()

                    # Progress per module
                    stats["processed"] += 1
                    if progress_cb is not None:
                        await progress_cb({
                            "stage": "procedures",
                            "processed": stats["processed"],
                            "total": stats["total"],
                            "indexed": stats["indexed"],
                            "skipped": stats["skipped"],
                        })

            # Release memory after each metadata type
            del objects
            gc.collect()

        logger.info(f"Procedure indexing complete: {stats}")
        return stats

    async def _count_metadata_objects(
        self,
        metadata_engine: MetadataEngine,
        indexable_types: list[MetadataType],
    ) -> int:
        """Count total metadata objects across all indexable types.

        Args:
            metadata_engine: Initialized MetadataEngine instance.
            indexable_types: Metadata types to scan.

        Returns:
            Total number of metadata objects.
        """
        total = 0
        for md_type in indexable_types:
            try:
                objects = await metadata_engine.list_objects(md_type)
                total += len(objects)
            except Exception:
                continue
        return total

    async def index_metadata_descriptions(
        self,
        metadata_engine: MetadataEngine,
        progress_cb: ProgressCallback = None,
        force_reindex: bool = False,
    ) -> dict[str, int]:
        """Index metadata object descriptions for semantic search.

        Supports resume: already-indexed descriptions are skipped unless
        force_reindex is True.

        Args:
            metadata_engine: Initialized MetadataEngine instance.
            progress_cb: Optional async callback for progress updates.
            force_reindex: If True, re-embed everything ignoring existing data.

        Returns:
            Stats dict with counts: indexed, skipped, errors, total, processed.
        """
        self._ensure_initialized()
        assert self._client is not None
        assert self._storage is not None
        assert self._config is not None

        stats = {"indexed": 0, "skipped": 0, "errors": 0, "processed": 0, "total": 0}

        indexable_types = [
            MetadataType.CATALOG,
            MetadataType.DOCUMENT,
            MetadataType.ENUM,
            MetadataType.REPORT,
            MetadataType.DATA_PROCESSOR,
            MetadataType.INFORMATION_REGISTER,
            MetadataType.ACCUMULATION_REGISTER,
            MetadataType.ACCOUNTING_REGISTER,
            MetadataType.CHART_OF_CHARACTERISTIC_TYPES,
            MetadataType.CHART_OF_ACCOUNTS,
            MetadataType.EXCHANGE_PLAN,
            MetadataType.BUSINESS_PROCESS,
            MetadataType.TASK,
            MetadataType.CONSTANT,
        ]

        # Count total objects for progress reporting
        stats["total"] = await self._count_metadata_objects(
            metadata_engine, indexable_types
        )

        # Load existing base prefixes for O(1) resume lookup
        existing_prefixes: set[str] = set()
        if not force_reindex:
            for eid in await self._storage.get_existing_ids():
                base = eid.rsplit(".chunk_", 1)[0] if ".chunk_" in eid else eid
                existing_prefixes.add(base)

        batch_docs: list[EmbeddingDocument] = []
        batch_texts: list[str] = []
        batch_size = self._config.pipeline_batch_size

        for md_type in indexable_types:
            try:
                objects = await metadata_engine.list_objects(md_type)
            except Exception as exc:
                logger.warning(f"Failed to list {md_type.value}: {exc}")
                continue

            for obj in objects:
                try:
                    obj_full = f"{obj.metadata_type.value}.{obj.name}"
                    doc_id = f"{obj_full}.description"

                    # Resume: check if this description already exists
                    if not force_reindex and doc_id in existing_prefixes:
                        stats["skipped"] += 1
                        stats["processed"] += 1
                        if progress_cb is not None:
                            await progress_cb({
                                "stage": "metadata",
                                "processed": stats["processed"],
                                "total": stats["total"],
                                "indexed": stats["indexed"],
                                "skipped": stats["skipped"],
                            })
                        continue

                    attr_names = [a.name for a in obj.attributes]
                    ts_names = [ts.name for ts in obj.tabular_sections]

                    text = prepare_metadata_text(
                        obj_full_name=obj_full,
                        synonym=obj.synonym,
                        comment=obj.comment,
                        attributes=attr_names,
                        tabular_sections=ts_names,
                    )

                    doc = EmbeddingDocument(
                        id=doc_id,
                        content=text,
                        doc_type="metadata_description",
                        metadata={
                            "object_type": obj.metadata_type.value,
                            "object_name": obj.name,
                            "synonym": obj.synonym,
                            "attribute_count": str(len(attr_names)),
                        },
                    )
                    batch_docs.append(doc)
                    batch_texts.append(text)
                    stats["processed"] += 1

                    # Flush batch when full
                    if len(batch_texts) >= batch_size:
                        saved = await self._embed_and_save_batch(batch_docs, batch_texts, skip_vec=True)
                        stats["indexed"] += saved
                        batch_docs = []
                        batch_texts = []

                        if progress_cb is not None:
                            await progress_cb({
                                "stage": "metadata",
                                "processed": stats["processed"],
                                "total": stats["total"],
                                "indexed": stats["indexed"],
                                "skipped": stats["skipped"],
                            })

                except Exception as exc:
                    logger.warning(f"Error preparing metadata {obj.name}: {exc}")
                    stats["errors"] += 1
                    stats["processed"] += 1

        # Flush remaining
        if batch_texts:
            saved = await self._embed_and_save_batch(batch_docs, batch_texts, skip_vec=True)
            stats["indexed"] += saved

            if progress_cb is not None:
                await progress_cb({
                    "stage": "metadata",
                    "processed": stats["processed"],
                    "total": stats["total"],
                    "indexed": stats["indexed"],
                    "skipped": stats["skipped"],
                })

        logger.info(f"Metadata description indexing complete: {stats}")
        return stats

    async def search(
        self,
        query: str,
        doc_type: str | None = None,
        object_type: str | None = None,
        module_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Semantic search: embed query and find similar documents.

        Args:
            query: Natural language search query.
            doc_type: Optional filter by document type
                      ('module', 'procedure', 'metadata_description').
            object_type: Optional filter by 1C object type (e.g., 'Catalog').
            module_type: Optional filter by module type (e.g., 'ObjectModule').
            limit: Maximum number of results.

        Returns:
            List of SearchResult sorted by similarity.
        """
        self._ensure_initialized()
        assert self._client is not None
        assert self._storage is not None

        query_vector = await self._client.embed_single(query)
        return await self._storage.search(
            query_vector,
            doc_type=doc_type,
            object_type=object_type,
            module_type=module_type,
            limit=limit,
        )

    async def find_similar(
        self,
        doc_id: str,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Find documents similar to an existing one.

        Args:
            doc_id: ID of the reference document.
            limit: Maximum number of similar documents.

        Returns:
            List of SearchResult (excluding the reference document itself).

        Raises:
            ValueError: If document not found.
        """
        self._ensure_initialized()
        assert self._storage is not None

        doc = await self._storage.get_document(doc_id)
        if doc is None:
            raise ValueError(f"Document not found: {doc_id}")

        # Search using the document's own embedding
        results = await self._storage.search(doc.embedding, limit=limit + 1)

        # Exclude the reference document itself
        return [r for r in results if r.document.id != doc_id][:limit]

    async def get_stats(self) -> EmbeddingStats:
        """Get embedding index statistics.

        Returns:
            EmbeddingStats with counts and storage info.
        """
        self._ensure_initialized()
        assert self._storage is not None
        return await self._storage.get_stats()

    async def invalidate_object(self, object_full_name: str) -> int:
        """Drop all embedding chunks for a metadata object.

        Called by the metadata watcher when an object is rewritten:
        ``Catalog.Контрагенты`` will match every chunk id starting with
        that prefix (modules, procedures, descriptions). Returns the
        number of chunks deleted so callers can log/measure.

        Idempotent. Does nothing if the engine isn't initialised — the
        watcher hands off blindly and we don't want startup-order races
        to crash invalidation.
        """
        if not self._initialized or self._storage is None:
            return 0
        prefix = object_full_name if object_full_name.endswith(".") else f"{object_full_name}."
        try:
            return await self._storage.delete_by_prefix(prefix)
        except Exception as exc:
            logger.warning(f"Failed to invalidate embeddings for {object_full_name}: {exc}")
            return 0

    async def rebuild_vec(self) -> int:
        """Rebuild vec_embeddings from the embeddings table.

        Call after a bulk indexing run to sync the KNN index.
        Returns the number of rows inserted.
        """
        self._ensure_initialized()
        assert self._storage is not None
        return await self._storage.rebuild_vec_from_embeddings()

    async def close(self) -> None:
        """Close all resources."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._storage:
            await self._storage.close()
            self._storage = None
        self._initialized = False
        logger.info("Embedding engine closed")
