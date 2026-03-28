"""
Embedding tools for MCP-1C.

Provides tools for semantic search over 1C configuration code and metadata
using vector embeddings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from mcp_1c.config import EmbeddingConfig, get_config
from mcp_1c.engines.code import CodeEngine
from mcp_1c.engines.embeddings import EmbeddingEngine
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError


class EmbeddingIndexTool(BaseTool):
    """Index 1C configuration for semantic search."""

    name: ClassVar[str] = "embedding.index"
    description: ClassVar[str] = (
        "Индексация конфигурации 1С для семантического поиска. "
        "Создает векторные эмбеддинги для модулей, процедур и описаний метаданных. "
        "Необходимо вызвать перед использованием embedding.search."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "scope": {
                "type": "string",
                "description": (
                    "Что индексировать: 'all' (всё), 'modules' (модули), "
                    "'procedures' (процедуры), 'metadata' (описания метаданных). "
                    "По умолчанию: 'all'"
                ),
                "default": "all",
                "enum": ["all", "modules", "procedures", "metadata"],
            },
        },
    }

    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        metadata_engine: MetadataEngine,
        code_engine: CodeEngine,
    ) -> None:
        super().__init__()
        self._embedding_engine = embedding_engine
        self._metadata_engine = metadata_engine
        self._code_engine = code_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run indexing."""
        scope = arguments.get("scope", "all")

        # Ensure engine is initialized
        if not self._embedding_engine.initialized:
            config = get_config()
            embedding_config = EmbeddingConfig.from_env()
            if not embedding_config.api_key:
                raise ToolError(
                    "Не задан API-ключ для эмбеддингов. "
                    "Установите переменную окружения MCP_EMBEDDING_API_KEY.",
                    code="MISSING_API_KEY",
                )
            db_path = Path(config.cache.db_path).parent / ".mcp_1c_embeddings.db"
            await self._embedding_engine.initialize(embedding_config, db_path)

        results: dict[str, dict[str, int]] = {}
        progress_log: list[dict[str, Any]] = []

        async def _progress_cb(info: dict[str, Any]) -> None:
            progress_log.append(info)

        if scope in ("all", "modules"):
            results["modules"] = await self._embedding_engine.index_modules(
                self._metadata_engine, self._code_engine, progress_cb=_progress_cb
            )

        if scope in ("all", "procedures"):
            results["procedures"] = await self._embedding_engine.index_procedures(
                self._metadata_engine, self._code_engine, progress_cb=_progress_cb
            )

        if scope in ("all", "metadata"):
            results["metadata"] = await self._embedding_engine.index_metadata_descriptions(
                self._metadata_engine, progress_cb=_progress_cb
            )

        total_indexed = sum(r.get("indexed", 0) for r in results.values())
        total_errors = sum(r.get("errors", 0) for r in results.values())

        return {
            "status": "ok",
            "scope": scope,
            "total_indexed": total_indexed,
            "total_errors": total_errors,
            "details": results,
            "progress_log": progress_log,
        }


class EmbeddingSearchTool(BaseTool):
    """Semantic search over 1C configuration."""

    name: ClassVar[str] = "embedding.search"
    description: ClassVar[str] = (
        "Семантический поиск по конфигурации 1С. "
        "Находит модули, процедуры и объекты метаданных по смыслу запроса. "
        "Перед использованием необходимо выполнить embedding.index."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Поисковый запрос на естественном языке "
                    "(например, 'расчет себестоимости', 'обработка проведения документа')"
                ),
            },
            "doc_type": {
                "type": "string",
                "description": (
                    "Фильтр по типу документа: 'module', 'procedure', "
                    "'metadata_description'. Если не указан, ищет везде."
                ),
                "enum": ["module", "procedure", "metadata_description"],
            },
            "object_type": {
                "type": "string",
                "description": (
                    "Фильтр по типу объекта метаданных "
                    "(например, 'Catalog', 'Document', 'InformationRegister'). "
                    "Если не указан, ищет по всем типам."
                ),
            },
            "module_type": {
                "type": "string",
                "description": (
                    "Фильтр по типу модуля "
                    "(например, 'ObjectModule', 'ManagerModule', 'FormModule'). "
                    "Если не указан, ищет по всем модулям."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатов (по умолчанию: 20)",
                "default": 20,
            },
        },
        "required": ["query"],
    }

    def __init__(self, embedding_engine: EmbeddingEngine) -> None:
        super().__init__()
        self._embedding_engine = embedding_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Run semantic search."""
        query = arguments["query"]
        doc_type = arguments.get("doc_type")
        object_type = arguments.get("object_type")
        module_type = arguments.get("module_type")
        limit = arguments.get("limit", 20)

        if not self._embedding_engine.initialized:
            raise ToolError(
                "Индекс эмбеддингов не инициализирован. "
                "Сначала вызовите embedding.index.",
                code="NOT_INITIALIZED",
            )

        results = await self._embedding_engine.search(
            query=query,
            doc_type=doc_type,
            object_type=object_type,
            module_type=module_type,
            limit=limit,
        )

        return {
            "query": query,
            "doc_type": doc_type,
            "count": len(results),
            "results": [
                {
                    "id": r.document.id,
                    "score": r.score,
                    "doc_type": r.document.doc_type,
                    "content_preview": r.document.content[:300],
                    "metadata": r.document.metadata,
                }
                for r in results
            ],
        }


class EmbeddingSimilarTool(BaseTool):
    """Find similar code/objects to a given one."""

    name: ClassVar[str] = "embedding.similar"
    description: ClassVar[str] = (
        "Поиск похожего кода или объектов метаданных. "
        "По ID существующего документа находит наиболее похожие. "
        "ID можно получить из результатов embedding.search."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "string",
                "description": (
                    "ID документа для поиска похожих "
                    "(например, 'Catalog.Номенклатура.ObjectModule')"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатов (по умолчанию: 10)",
                "default": 10,
            },
        },
        "required": ["doc_id"],
    }

    def __init__(self, embedding_engine: EmbeddingEngine) -> None:
        super().__init__()
        self._embedding_engine = embedding_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Find similar documents."""
        doc_id = arguments["doc_id"]
        limit = arguments.get("limit", 10)

        if not self._embedding_engine.initialized:
            raise ToolError(
                "Индекс эмбеддингов не инициализирован. "
                "Сначала вызовите embedding.index.",
                code="NOT_INITIALIZED",
            )

        try:
            results = await self._embedding_engine.find_similar(
                doc_id=doc_id, limit=limit
            )
        except ValueError as exc:
            raise ToolError(str(exc), code="NOT_FOUND") from exc

        return {
            "doc_id": doc_id,
            "count": len(results),
            "similar": [
                {
                    "id": r.document.id,
                    "score": r.score,
                    "doc_type": r.document.doc_type,
                    "content_preview": r.document.content[:300],
                    "metadata": r.document.metadata,
                }
                for r in results
            ],
        }


class EmbeddingStatsTool(BaseTool):
    """Get embedding index statistics."""

    name: ClassVar[str] = "embedding.stats"
    description: ClassVar[str] = (
        "Статистика индекса эмбеддингов: количество проиндексированных документов "
        "по типам, размер индекса, размерность векторов."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, embedding_engine: EmbeddingEngine) -> None:
        super().__init__()
        self._embedding_engine = embedding_engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get stats."""
        if not self._embedding_engine.initialized:
            raise ToolError(
                "Индекс эмбеддингов не инициализирован. "
                "Сначала вызовите embedding.index.",
                code="NOT_INITIALIZED",
            )

        stats = await self._embedding_engine.get_stats()
        return {
            "total_documents": stats.total_documents,
            "by_type": stats.by_type,
            "dimension": stats.dimension,
            "index_size_bytes": stats.index_size_bytes,
            "index_size_mb": round(stats.index_size_bytes / (1024 * 1024), 2),
        }
