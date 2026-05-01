"""
SQLite-based vector storage with cosine KNN via sqlite-vec.

Two tables side by side in a single .db file:
  embeddings    — metadata + raw vector blob (compatibility, backfill source)
  vec_embeddings — sqlite-vec vec0 virtual table providing fast cosine KNN

Search path uses vec_embeddings (KNN in C with partition-key prefilter on
doc_type). Writes go to both tables in one transaction. On init, the vec0
table is backfilled from `embeddings` if it lags behind.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import aiosqlite
import sqlite_vec

from mcp_1c.domain.embedding import EmbeddingDocument, EmbeddingStats, SearchResult
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# Default vector dimension — overridable per VectorStorage instance via the
# `dimension` parameter so we can support both 4096-dim cloud models
# (DeepInfra Qwen3-Embedding-8B) and smaller local models (e.g. 384-dim
# multilingual MiniLM).
VECTOR_DIM = 4096

# ---- metadata table (unchanged shape) -------------------------------------

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

_CREATE_INDEX_TYPE = (
    "CREATE INDEX IF NOT EXISTS idx_embeddings_doc_type ON embeddings(doc_type)"
)

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

_SELECT_BY_ID = (
    "SELECT id, content, doc_type, metadata, embedding FROM embeddings WHERE id = ?"
)

_DELETE_BY_PREFIX = "DELETE FROM embeddings WHERE id LIKE ?"

_COUNT_ALL = "SELECT COUNT(*) FROM embeddings"
_COUNT_BY_TYPE = (
    "SELECT doc_type, COUNT(*) AS cnt FROM embeddings GROUP BY doc_type"
)
_DB_SIZE = (
    "SELECT page_count * page_size AS size "
    "FROM pragma_page_count(), pragma_page_size()"
)

# ---- vec0 virtual table ----------------------------------------------------

def _vec_table_sql(dim: int) -> str:
    """Render the vec0 virtual-table DDL for a given vector dimension."""
    return f"""
    CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings USING vec0(
        doc_type TEXT PARTITION KEY,
        id TEXT PRIMARY KEY,
        embedding float[{dim}] distance_metric=cosine,
        +object_type TEXT,
        +module_type TEXT
    )
    """

_VEC_INSERT = (
    "INSERT INTO vec_embeddings"
    "(doc_type, id, embedding, object_type, module_type) VALUES (?, ?, ?, ?, ?)"
)
_VEC_DELETE_BY_ID = "DELETE FROM vec_embeddings WHERE id = ?"

_VEC_COUNT = "SELECT COUNT(*) FROM vec_embeddings"


def _pack_vector(vector: list[float]) -> bytes:
    """Pack a float vector as little-endian float32 (4 bytes/float)."""
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack_vector(data: bytes) -> list[float]:
    """Unpack a float32 BLOB back into a list of floats."""
    n = len(data) // 4
    return list(struct.unpack(f"{n}f", data))


def _load_vec_extension(raw_conn: Any) -> None:
    """Load sqlite-vec into a raw sqlite3 connection (sync)."""
    raw_conn.enable_load_extension(True)
    sqlite_vec.load(raw_conn)
    raw_conn.enable_load_extension(False)


class VectorStorage:
    """SQLite vector storage with sqlite-vec KNN search."""

    def __init__(self, db_path: Path, dimension: int = VECTOR_DIM) -> None:
        self._db_path = db_path
        self._dimension = dimension
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(str(self._db_path))
            self._conn.row_factory = aiosqlite.Row
            # sqlite-vec extension lives on the underlying sync sqlite3 conn.
            await self._conn._execute(_load_vec_extension, self._conn._conn)  # type: ignore[attr-defined]
        return self._conn

    async def init_tables(self) -> None:
        """Create tables, run schema migrations, ensure vec0 is in sync."""
        conn = await self._get_conn()
        await conn.execute(_CREATE_TABLE)
        await conn.execute(_CREATE_INDEX_TYPE)

        # Schema migration: add object_type/module_type if missing
        cursor = await conn.execute("PRAGMA table_info(embeddings)")
        existing = {row[1] for row in await cursor.fetchall()}
        if "object_type" not in existing:
            await conn.execute(
                "ALTER TABLE embeddings ADD COLUMN object_type TEXT DEFAULT ''"
            )
            logger.info("Migrated: added object_type column")
        if "module_type" not in existing:
            await conn.execute(
                "ALTER TABLE embeddings ADD COLUMN module_type TEXT DEFAULT ''"
            )
            logger.info("Migrated: added module_type column")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_embeddings_object_type "
            "ON embeddings(object_type)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_embeddings_module_type "
            "ON embeddings(module_type)"
        )

        # vec0 KNN table — dimension comes from the active embedding model
        await conn.execute(_vec_table_sql(self._dimension))
        await conn.commit()

        await self._backfill_vec_if_needed(conn)
        logger.info(f"Vector storage initialized at {self._db_path}")

    async def _backfill_vec_if_needed(self, conn: aiosqlite.Connection) -> None:
        """If vec_embeddings is behind embeddings, copy missing rows."""
        cur = await conn.execute(_COUNT_ALL)
        total = (await cur.fetchone())[0]  # type: ignore[index]
        cur = await conn.execute(_VEC_COUNT)
        vec_total = (await cur.fetchone())[0]  # type: ignore[index]

        if vec_total >= total:
            logger.info(
                f"vec_embeddings up to date ({vec_total}/{total})"
            )
            return

        logger.warning(
            f"vec_embeddings backfill required: {vec_total}/{total} rows, "
            "this may take several minutes"
        )
        batch_size = 500
        copied = 0
        # Stream rows whose id is NOT yet in vec_embeddings.
        # LEFT JOIN strategy keeps memory bounded and is resumable.
        select_sql = (
            "SELECT e.id, e.doc_type, e.embedding, "
            "  COALESCE(e.object_type,'') AS object_type, "
            "  COALESCE(e.module_type,'') AS module_type "
            "FROM embeddings e "
            "LEFT JOIN vec_embeddings v ON v.id = e.id "
            "WHERE v.id IS NULL"
        )
        cursor = await conn.execute(select_sql)
        batch: list[tuple[Any, ...]] = []
        while True:
            rows = await cursor.fetchmany(batch_size)
            if not rows:
                break
            for r in rows:
                batch.append(
                    (r["doc_type"], r["id"], r["embedding"],
                     r["object_type"], r["module_type"])
                )
            await conn.executemany(_VEC_INSERT, batch)
            await conn.commit()
            copied += len(batch)
            batch.clear()
            logger.info(f"vec backfill progress: {copied}/{total - vec_total}")
        logger.info(f"vec_embeddings backfill complete: {copied} rows copied")

    async def save_documents(self, documents: list[EmbeddingDocument]) -> int:
        """Save or update documents in both metadata and vec0 tables."""
        if not documents:
            return 0

        conn = await self._get_conn()

        meta_rows: list[tuple[Any, ...]] = []
        vec_rows: list[tuple[Any, ...]] = []
        for doc in documents:
            if not doc.embedding:
                continue
            obj_type = doc.metadata.get("object_type", "")
            mod_type = doc.metadata.get("module_type", "")
            blob = _pack_vector(doc.embedding)
            meta_rows.append((
                doc.id,
                doc.content,
                doc.doc_type,
                json.dumps(doc.metadata, ensure_ascii=False),
                blob,
                obj_type,
                mod_type,
            ))
            vec_rows.append((doc.doc_type, doc.id, blob, obj_type, mod_type))

        if not meta_rows:
            return 0

        # vec0 has no UPSERT — emulate via DELETE + INSERT in one transaction.
        del_rows = [(row[1],) for row in vec_rows]  # row[1] is id

        await conn.executemany(_UPSERT_DOC, meta_rows)
        await conn.executemany(_VEC_DELETE_BY_ID, del_rows)
        await conn.executemany(_VEC_INSERT, vec_rows)
        await conn.commit()
        logger.debug(f"Saved {len(meta_rows)} documents to vector storage")
        return len(meta_rows)

    async def search(
        self,
        query_vector: list[float],
        doc_type: str | None = None,
        object_type: str | None = None,
        module_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """KNN cosine search with partition-key prefilter on doc_type."""
        conn = await self._get_conn()
        q_blob = _pack_vector(query_vector)

        # vec0 supports WHERE on PARTITION KEY but not on auxiliary columns
        # during KNN. So when object_type/module_type filters are present,
        # over-fetch and post-filter in Python.
        post_filter_active = bool(object_type or module_type)
        k = limit * 10 if post_filter_active else limit

        params: list[Any] = [q_blob, k]
        sql = (
            "SELECT id, distance, doc_type, object_type, module_type "
            "FROM vec_embeddings "
            "WHERE embedding MATCH ? AND k = ?"
        )
        if doc_type:
            sql += " AND doc_type = ?"
            params.append(doc_type)
        sql += " ORDER BY distance"

        cursor = await conn.execute(sql, params)
        knn_rows = await cursor.fetchall()

        if post_filter_active:
            knn_rows = [
                r for r in knn_rows
                if (not object_type or r["object_type"] == object_type)
                and (not module_type or r["module_type"] == module_type)
            ][:limit]
        else:
            knn_rows = list(knn_rows)[:limit]

        if not knn_rows:
            return []

        # Pull content + metadata in one query
        ids = [r["id"] for r in knn_rows]
        placeholders = ",".join("?" * len(ids))
        meta_cur = await conn.execute(
            f"SELECT id, content, doc_type, metadata "
            f"FROM embeddings WHERE id IN ({placeholders})",
            ids,
        )
        meta_by_id = {row["id"]: row for row in await meta_cur.fetchall()}

        results: list[SearchResult] = []
        for r in knn_rows:
            meta = meta_by_id.get(r["id"])
            if meta is None:
                continue
            score = 1.0 - float(r["distance"])  # cosine_distance -> similarity
            results.append(SearchResult(
                document=EmbeddingDocument(
                    id=meta["id"],
                    content=meta["content"],
                    doc_type=meta["doc_type"],
                    metadata=json.loads(meta["metadata"]),
                    embedding=[],
                ),
                score=round(score, 6),
            ))
        return results

    async def get_document(self, doc_id: str) -> EmbeddingDocument | None:
        conn = await self._get_conn()
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
        conn = await self._get_conn()
        if id_prefixes:
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
        conn = await self._get_conn()
        like = f"{prefix}%"
        # vec0 doesn't support `WHERE id LIKE ?` — collect ids first, then
        # delete one-by-one (executemany batches them efficiently).
        cur = await conn.execute("SELECT id FROM embeddings WHERE id LIKE ?", (like,))
        ids = [(row[0],) for row in await cur.fetchall()]
        if not ids:
            return 0
        await conn.executemany(_VEC_DELETE_BY_ID, ids)
        cursor = await conn.execute(_DELETE_BY_PREFIX, (like,))
        await conn.commit()
        deleted = cursor.rowcount
        logger.debug(f"Deleted {deleted} documents with prefix '{prefix}'")
        return deleted

    async def get_stats(self) -> EmbeddingStats:
        conn = await self._get_conn()

        cursor = await conn.execute(_COUNT_ALL)
        row = await cursor.fetchone()
        total = row[0] if row else 0

        cursor = await conn.execute(_COUNT_BY_TYPE)
        by_type: dict[str, int] = {}
        async for row in cursor:
            by_type[row["doc_type"]] = row["cnt"]

        cursor = await conn.execute(_DB_SIZE)
        size_row = await cursor.fetchone()
        size_bytes = size_row[0] if size_row else 0

        dimension = 0
        if total > 0:
            cursor = await conn.execute("SELECT embedding FROM embeddings LIMIT 1")
            first = await cursor.fetchone()
            if first:
                dimension = len(first["embedding"]) // 4

        return EmbeddingStats(
            total_documents=total,
            by_type=by_type,
            dimension=dimension,
            index_size_bytes=size_bytes,
        )

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
