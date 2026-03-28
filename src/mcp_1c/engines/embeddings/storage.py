"""
SQLite-based vector storage with cosine similarity search.

Stores embedding vectors as packed float BLOBs for space efficiency.
Cosine similarity is computed in pure Python (no numpy dependency).
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

import aiosqlite

from mcp_1c.domain.embedding import EmbeddingDocument, EmbeddingStats, SearchResult
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# SQL statements
_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    embedding BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_INDEX_TYPE = """
CREATE INDEX IF NOT EXISTS idx_embeddings_doc_type ON embeddings(doc_type)
"""

_UPSERT_DOC = """
INSERT INTO embeddings (id, content, doc_type, metadata, embedding, object_type, module_type)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    content = excluded.content,
    doc_type = excluded.doc_type,
    metadata = excluded.metadata,
    embedding = excluded.embedding,
    object_type = excluded.object_type,
    module_type = excluded.module_type,
    created_at = CURRENT_TIMESTAMP
"""

_SELECT_COLS = "id, content, doc_type, metadata, embedding"

_SELECT_ALL = f"SELECT {_SELECT_COLS} FROM embeddings"

_SELECT_BY_TYPE = f"SELECT {_SELECT_COLS} FROM embeddings WHERE doc_type = ?"

_SELECT_BY_ID = (
    "SELECT id, content, doc_type, metadata, embedding FROM embeddings WHERE id = ?"
)

_DELETE_BY_PREFIX = "DELETE FROM embeddings WHERE id LIKE ?"

_COUNT_ALL = "SELECT COUNT(*) FROM embeddings"

_COUNT_BY_TYPE = "SELECT doc_type, COUNT(*) as cnt FROM embeddings GROUP BY doc_type"

_DB_SIZE = "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Args:
        a: First vector.
        b: Second vector (must be same dimension as a).

    Returns:
        Cosine similarity in range [-1.0, 1.0].
        Returns 0.0 if either vector has zero norm.
    """
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _pack_vector(vector: list[float]) -> bytes:
    """Pack a float vector into a compact binary blob.

    Args:
        vector: List of float values.

    Returns:
        Packed binary data (4 bytes per float).
    """
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_vector(data: bytes) -> list[float]:
    """Unpack a binary blob back into a float vector.

    Args:
        data: Packed binary data.

    Returns:
        List of float values.
    """
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


class VectorStorage:
    """SQLite-based vector storage with cosine similarity search.

    Stores documents with their embedding vectors in SQLite.
    Vectors are packed as BLOBs for storage efficiency.
    Cosine similarity search is performed by loading all
    candidate vectors into memory (suitable for < 100K documents).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """Get or create the database connection."""
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self._db_path))
            self._conn.row_factory = aiosqlite.Row
        return self._conn

    async def init_tables(self) -> None:
        """Create tables and indexes if they don't exist.

        Also runs schema migrations for new columns (object_type, module_type).
        """
        conn = await self._get_conn()
        await conn.execute(_CREATE_TABLE)
        await conn.execute(_CREATE_INDEX_TYPE)

        # Schema migration: add object_type and module_type columns
        cursor = await conn.execute("PRAGMA table_info(embeddings)")
        existing_columns = {row[1] for row in await cursor.fetchall()}

        if "object_type" not in existing_columns:
            await conn.execute(
                "ALTER TABLE embeddings ADD COLUMN object_type TEXT DEFAULT ''"
            )
            logger.info("Migrated: added object_type column to embeddings")
        if "module_type" not in existing_columns:
            await conn.execute(
                "ALTER TABLE embeddings ADD COLUMN module_type TEXT DEFAULT ''"
            )
            logger.info("Migrated: added module_type column to embeddings")

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_embeddings_object_type "
            "ON embeddings(object_type)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_embeddings_module_type "
            "ON embeddings(module_type)"
        )

        await conn.commit()
        logger.info(f"Vector storage initialized at {self._db_path}")

    async def save_documents(self, documents: list[EmbeddingDocument]) -> int:
        """Save or update documents with their embeddings.

        Args:
            documents: List of documents to save.

        Returns:
            Number of documents saved.
        """
        if not documents:
            return 0

        conn = await self._get_conn()
        import json

        rows = [
            (
                doc.id,
                doc.content,
                doc.doc_type,
                json.dumps(doc.metadata, ensure_ascii=False),
                _pack_vector(doc.embedding),
                doc.metadata.get("object_type", ""),
                doc.metadata.get("module_type", ""),
            )
            for doc in documents
            if doc.embedding  # skip documents without embeddings
        ]

        await conn.executemany(_UPSERT_DOC, rows)
        await conn.commit()
        logger.debug(f"Saved {len(rows)} documents to vector storage")
        return len(rows)

    async def search(
        self,
        query_vector: list[float],
        doc_type: str | None = None,
        object_type: str | None = None,
        module_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Search for similar documents using cosine similarity.

        Args:
            query_vector: The query embedding vector.
            doc_type: Optional filter by document type.
            object_type: Optional filter by 1C object type (e.g., 'Catalog').
            module_type: Optional filter by module type (e.g., 'ObjectModule').
            limit: Maximum number of results.

        Returns:
            List of SearchResult sorted by similarity (highest first).
        """
        conn = await self._get_conn()
        import json

        # Build dynamic WHERE clause
        conditions: list[str] = []
        params: list[str] = []

        if doc_type:
            conditions.append("doc_type = ?")
            params.append(doc_type)
        if object_type:
            conditions.append("object_type = ?")
            params.append(object_type)
        if module_type:
            conditions.append("module_type = ?")
            params.append(module_type)

        if conditions:
            where = " WHERE " + " AND ".join(conditions)
            query_sql = f"SELECT {_SELECT_COLS} FROM embeddings{where}"
            cursor = await conn.execute(query_sql, params)
        else:
            cursor = await conn.execute(_SELECT_ALL)

        rows = await cursor.fetchall()

        # Compute similarities
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            stored_vector = _unpack_vector(row["embedding"])
            score = _cosine_similarity(query_vector, stored_vector)
            scored.append((score, dict(row)))

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        results: list[SearchResult] = []
        for score, row_data in top:
            doc = EmbeddingDocument(
                id=row_data["id"],
                content=row_data["content"],
                doc_type=row_data["doc_type"],
                metadata=json.loads(row_data["metadata"]),
                embedding=[],  # Don't include vectors in search results
            )
            results.append(SearchResult(document=doc, score=round(score, 6)))

        return results

    async def get_document(self, doc_id: str) -> EmbeddingDocument | None:
        """Get a document by its ID.

        Args:
            doc_id: The document identifier.

        Returns:
            The document if found, None otherwise.
        """
        conn = await self._get_conn()
        import json

        cursor = await conn.execute(_SELECT_BY_ID, (doc_id,))
        row = await cursor.fetchone()

        if row is None:
            return None

        return EmbeddingDocument(
            id=row["id"],
            content=row["content"],
            doc_type=row["doc_type"],
            metadata=json.loads(row["metadata"]),
            embedding=_unpack_vector(row["embedding"]),
        )

    async def get_existing_ids(self, id_prefixes: list[str] | None = None) -> set[str]:
        """Get set of document IDs that already have embeddings.

        Args:
            id_prefixes: Optional list of ID prefixes to filter
                        (e.g., ['Catalog.Товары.']).
                        If None, returns ALL existing IDs.

        Returns:
            Set of existing document IDs.
        """
        conn = await self._get_conn()

        if id_prefixes:
            # Build OR-ed LIKE conditions for each prefix
            conditions = " OR ".join("id LIKE ?" for _ in id_prefixes)
            params = [f"{p}%" for p in id_prefixes]
            cursor = await conn.execute(
                f"SELECT id FROM embeddings WHERE {conditions}", params
            )
        else:
            cursor = await conn.execute("SELECT id FROM embeddings")

        rows = await cursor.fetchall()
        return {row[0] for row in rows}

    async def delete_by_prefix(self, prefix: str) -> int:
        """Delete all documents whose ID starts with the given prefix.

        Args:
            prefix: ID prefix to match (e.g., 'Catalog.Nomenclature').

        Returns:
            Number of deleted documents.
        """
        conn = await self._get_conn()
        cursor = await conn.execute(_DELETE_BY_PREFIX, (f"{prefix}%",))
        await conn.commit()
        deleted = cursor.rowcount
        logger.debug(f"Deleted {deleted} documents with prefix '{prefix}'")
        return deleted

    async def get_stats(self) -> EmbeddingStats:
        """Get statistics about the vector storage.

        Returns:
            Storage statistics including counts and size.
        """
        conn = await self._get_conn()

        # Total count
        cursor = await conn.execute(_COUNT_ALL)
        row = await cursor.fetchone()
        total = row[0] if row else 0

        # Count by type
        cursor = await conn.execute(_COUNT_BY_TYPE)
        by_type: dict[str, int] = {}
        async for row in cursor:
            by_type[row["doc_type"]] = row["cnt"]

        # Database size
        cursor = await conn.execute(_DB_SIZE)
        size_row = await cursor.fetchone()
        size_bytes = size_row[0] if size_row else 0

        # Determine dimension from first document
        dimension = 0
        if total > 0:
            cursor = await conn.execute(
                "SELECT embedding FROM embeddings LIMIT 1"
            )
            first = await cursor.fetchone()
            if first:
                dimension = len(first["embedding"]) // 4  # 4 bytes per float

        return EmbeddingStats(
            total_documents=total,
            by_type=by_type,
            dimension=dimension,
            index_size_bytes=size_bytes,
        )

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
