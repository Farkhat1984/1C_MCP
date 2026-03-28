"""
SQLite storage for the knowledge graph.

Persists graph nodes and edges alongside the metadata cache database.
"""

from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from mcp_1c.domain.graph import GraphEdge, GraphNode, KnowledgeGraph, RelationshipType
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class GraphStorage:
    """Persistent SQLite storage for knowledge graph nodes and edges.

    Reuses the same database file as MetadataCache to keep data co-located.
    Tables are created lazily on first use.
    """

    def __init__(self) -> None:
        self._connection: aiosqlite.Connection | None = None
        self._db_path: Path | None = None

    async def init_tables(self, db_path: Path) -> None:
        """Open (or reuse) a connection and create graph tables.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._connection = await aiosqlite.connect(str(db_path))
        self._connection.row_factory = aiosqlite.Row

        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")

        await self._create_schema()
        logger.info(f"Graph storage initialized at {db_path}")

    async def _create_schema(self) -> None:
        """Create graph tables and indexes if they do not exist."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    synonym TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}'
                )
            """)

            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    relationship TEXT NOT NULL,
                    label TEXT DEFAULT '',
                    metadata_json TEXT DEFAULT '{}',
                    UNIQUE(source, target, relationship, label)
                )
            """)

            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_graph_edges_source
                ON graph_edges(source)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_graph_edges_target
                ON graph_edges(target)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_graph_edges_relationship
                ON graph_edges(relationship)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_graph_nodes_type
                ON graph_nodes(node_type)
            """)

            await self._connection.commit()

    async def save_graph(self, graph: KnowledgeGraph) -> None:
        """Persist the entire graph (replaces existing data).

        Args:
            graph: KnowledgeGraph to save.
        """
        if not self._connection:
            raise RuntimeError("GraphStorage not initialized. Call init_tables first.")

        await self._connection.execute("BEGIN")
        try:
            await self._connection.execute("DELETE FROM graph_edges")
            await self._connection.execute("DELETE FROM graph_nodes")

            # Batch-insert nodes
            for node in graph.nodes.values():
                await self._connection.execute(
                    """
                    INSERT INTO graph_nodes (id, node_type, name, synonym, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        node.id,
                        node.node_type,
                        node.name,
                        node.synonym,
                        json.dumps(node.metadata, ensure_ascii=False, default=str),
                    ),
                )

            # Batch-insert edges
            for edge in graph.edges:
                await self._connection.execute(
                    """
                    INSERT OR IGNORE INTO graph_edges
                        (source, target, relationship, label, metadata_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        edge.source,
                        edge.target,
                        edge.relationship.value,
                        edge.label,
                        json.dumps(edge.metadata, ensure_ascii=False, default=str),
                    ),
                )

            await self._connection.commit()
            logger.info(
                f"Saved graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges"
            )
        except Exception:
            await self._connection.rollback()
            raise

    async def load_graph(self) -> KnowledgeGraph | None:
        """Load the full graph from storage.

        Returns:
            KnowledgeGraph if data exists, None if tables are empty.
        """
        if not self._connection:
            raise RuntimeError("GraphStorage not initialized. Call init_tables first.")

        graph = KnowledgeGraph()

        async with self._connection.cursor() as cursor:
            # Load nodes
            await cursor.execute("SELECT * FROM graph_nodes")
            rows = await cursor.fetchall()
            if not rows:
                return None

            for row in rows:
                node = GraphNode(
                    id=row["id"],
                    node_type=row["node_type"],
                    name=row["name"],
                    synonym=row["synonym"] or "",
                    metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
                )
                graph.add_node(node)

            # Load edges
            await cursor.execute("SELECT * FROM graph_edges")
            edge_rows = await cursor.fetchall()
            for row in edge_rows:
                try:
                    relationship = RelationshipType(row["relationship"])
                except ValueError:
                    logger.warning(
                        f"Unknown relationship type: {row['relationship']}, skipping"
                    )
                    continue
                edge = GraphEdge(
                    source=row["source"],
                    target=row["target"],
                    relationship=relationship,
                    label=row["label"] or "",
                    metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
                )
                graph.add_edge(edge)

        logger.info(
            f"Loaded graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )
        return graph

    async def clear(self) -> None:
        """Delete all graph data."""
        if not self._connection:
            return
        await self._connection.execute("DELETE FROM graph_edges")
        await self._connection.execute("DELETE FROM graph_nodes")
        await self._connection.commit()
        logger.info("Graph storage cleared")

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
