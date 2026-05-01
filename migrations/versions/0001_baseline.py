"""Baseline schema for the MCP-1C Postgres backend.

Mirrors the three SQLite stores (metadata cache, vector store, graph
store) into a multi-tenant PG layout where every row is keyed by
``workspace_id``. That gives us per-tenant isolation today and a
straight path to row-level security later.

The vector dimension is parameterised — read from
``MCP_PG_EMBEDDING_DIM`` at migration time so a deployment using a
different embedding model (e.g. 1024-dim BGE) can run the same
migration. Default 4096 matches DeepInfra ``Qwen/Qwen3-Embedding-8B``.

Revision ID: 0001
Revises:
Create Date: 2026-05-01
"""

from __future__ import annotations

import os

from alembic import op

# Alembic identifiers.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


_DEFAULT_DIM: int = 4096


def _embedding_dim() -> int:
    """Resolve the vector dimension from env, with a safe default.

    Validation here is paranoid on purpose: a bad value silently
    creating ``vector(0)`` columns would corrupt the schema.
    """

    raw = os.environ.get("MCP_PG_EMBEDDING_DIM")
    if raw is None or raw == "":
        return _DEFAULT_DIM
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"MCP_PG_EMBEDDING_DIM must be an integer, got {raw!r}"
        ) from exc
    if value <= 0 or value > 16000:
        # 16000 is pgvector's hard ceiling for HNSW-indexed columns.
        raise RuntimeError(
            f"MCP_PG_EMBEDDING_DIM out of range (1..16000): {value}"
        )
    return value


def upgrade() -> None:
    dim = _embedding_dim()

    # pgvector must be enabled before any ``vector(N)`` column is
    # created. Operators need ``CREATE EXTENSION`` privilege; if that's
    # missing, an admin should create the extension once and re-run.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ----- metadata_objects -------------------------------------------------
    op.execute(
        """
        CREATE TABLE metadata_objects (
            workspace_id TEXT NOT NULL,
            full_name    TEXT NOT NULL,
            type         TEXT NOT NULL,
            source       TEXT,
            data_jsonb   JSONB NOT NULL,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (workspace_id, full_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_metadata_objects_type "
        "ON metadata_objects (workspace_id, type)"
    )

    # ----- vectors ---------------------------------------------------------
    # Dimension is locked at create time. Changing models means a fresh
    # table — that's by design: a mixed-dim table is a footgun.
    op.execute(
        f"""
        CREATE TABLE vectors (
            workspace_id     TEXT NOT NULL,
            chunk_id         TEXT NOT NULL,
            object_full_name TEXT,
            content          TEXT NOT NULL,
            embedding        vector({dim}) NOT NULL,
            metadata_jsonb   JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            PRIMARY KEY (workspace_id, chunk_id)
        )
        """
    )
    # HNSW index on the cosine operator class — matches what the
    # embedding engine assumes (cosine similarity over normalised
    # vectors). m/ef_construction tuned for "fast index build, decent
    # recall"; production deployments may want to bump ef_construction.
    op.execute(
        "CREATE INDEX idx_vectors_embedding_hnsw "
        "ON vectors USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX idx_vectors_object "
        "ON vectors (workspace_id, object_full_name)"
    )

    # ----- graph_nodes -----------------------------------------------------
    op.execute(
        """
        CREATE TABLE graph_nodes (
            workspace_id TEXT NOT NULL,
            node_id      TEXT NOT NULL,
            kind         TEXT NOT NULL,
            attrs_jsonb  JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (workspace_id, node_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_graph_nodes_kind "
        "ON graph_nodes (workspace_id, kind)"
    )

    # ----- graph_edges -----------------------------------------------------
    op.execute(
        """
        CREATE TABLE graph_edges (
            workspace_id TEXT NOT NULL,
            src          TEXT NOT NULL,
            dst          TEXT NOT NULL,
            kind         TEXT NOT NULL,
            attrs_jsonb  JSONB NOT NULL DEFAULT '{}'::jsonb,
            PRIMARY KEY (workspace_id, src, dst, kind)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_graph_edges_dst "
        "ON graph_edges (workspace_id, dst, kind)"
    )
    op.execute(
        "CREATE INDEX idx_graph_edges_kind "
        "ON graph_edges (workspace_id, kind)"
    )


def downgrade() -> None:
    # Reverse declaration order so foreign-key-like edges drop before
    # nodes. We don't drop the ``vector`` extension — other databases
    # on the same cluster may depend on it.
    op.execute("DROP TABLE IF EXISTS graph_edges")
    op.execute("DROP TABLE IF EXISTS graph_nodes")
    op.execute("DROP TABLE IF EXISTS vectors")
    op.execute("DROP TABLE IF EXISTS metadata_objects")
