"""
SQLite cache for metadata index.

Provides persistent storage for indexed metadata objects.
Optimized with:
- WAL mode for better concurrent access
- Batch operations for bulk inserts
- In-memory LRU cache for frequent queries
- Prepared statements
"""

from datetime import datetime
from pathlib import Path
from typing import Any
import json

import aiosqlite

from mcp_1c.domain.metadata import MetadataObject, MetadataType, Subsystem
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.lru_cache import AsyncLRUCache
from mcp_1c.utils.profiler import get_profiler

logger = get_logger(__name__)
profiler = get_profiler()


class MetadataCache:
    """
    SQLite-based cache for metadata objects.

    Provides:
    - Persistent storage of indexed objects
    - Efficient querying by type, name, subsystem
    - Hash-based change detection for incremental updates
    - In-memory LRU cache for frequent queries
    - WAL mode for better performance
    """

    def __init__(self, db_path: Path) -> None:
        """
        Initialize cache.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None
        self.logger = get_logger(__name__)

        # In-memory LRU caches for frequent queries
        self._object_cache: AsyncLRUCache[tuple[str, str], MetadataObject] = (
            AsyncLRUCache(maxsize=500, ttl=300.0)  # 5 min TTL
        )
        self._search_cache: AsyncLRUCache[str, list[MetadataObject]] = (
            AsyncLRUCache(maxsize=100, ttl=60.0)  # 1 min TTL
        )
        self._list_cache: AsyncLRUCache[str, list[MetadataObject]] = (
            AsyncLRUCache(maxsize=50, ttl=120.0)  # 2 min TTL
        )

        # Batch operation state
        self._batch_mode = False
        self._batch_objects: list[MetadataObject] = []
        self._batch_size = 100

    async def connect(self) -> None:
        """Open database connection and create schema."""
        self.logger.debug(f"Connecting to cache: {self.db_path}")
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        # SQLite optimizations
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA cache_size=-64000")  # 64MB cache
        await self._connection.execute("PRAGMA temp_store=MEMORY")
        await self._connection.execute("PRAGMA mmap_size=268435456")  # 256MB mmap

        await self._create_schema()

    async def close(self) -> None:
        """Close database connection."""
        # Flush any pending batch operations
        if self._batch_mode and self._batch_objects:
            await self._flush_batch()

        if self._connection:
            await self._connection.close()
            self._connection = None

    async def start_batch(self) -> None:
        """Start batch mode for bulk inserts."""
        self._batch_mode = True
        self._batch_objects = []

    async def end_batch(self) -> None:
        """End batch mode and flush remaining objects."""
        if self._batch_objects:
            await self._flush_batch()
        self._batch_mode = False

    async def _flush_batch(self) -> None:
        """Flush batch objects to database atomically.

        Wraps batch inserts in an explicit transaction so that either all
        objects are committed or none are (atomic batch operation).
        """
        if not self._batch_objects:
            return

        await self._connection.execute("BEGIN")
        try:
            async with self._connection.cursor() as cursor:
                for obj in self._batch_objects:
                    data_json = obj.model_dump_json(
                        exclude={"config_path", "object_path", "indexed_at"}
                    )
                    await cursor.execute("""
                        INSERT OR REPLACE INTO metadata_objects
                        (uuid, name, synonym, comment, metadata_type,
                         config_path, object_path, file_hash, indexed_at, data_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        obj.uuid,
                        obj.name,
                        obj.synonym,
                        obj.comment,
                        obj.metadata_type.value,
                        str(obj.config_path),
                        str(obj.object_path),
                        obj.file_hash,
                        datetime.now().isoformat(),
                        data_json,
                    ))
            await self._connection.commit()
        except Exception:
            await self._connection.rollback()
            raise

        # Invalidate caches only after successful commit
        await self._invalidate_caches()
        self._batch_objects = []

    async def _invalidate_caches(self) -> None:
        """Invalidate all in-memory caches."""
        await self._object_cache.clear()
        await self._search_cache.clear()
        await self._list_cache.clear()

    async def _create_schema(self) -> None:
        """Create database schema if not exists."""
        async with self._connection.cursor() as cursor:
            # Metadata objects table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS metadata_objects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid TEXT,
                    name TEXT NOT NULL,
                    synonym TEXT,
                    comment TEXT,
                    metadata_type TEXT NOT NULL,
                    config_path TEXT NOT NULL,
                    object_path TEXT NOT NULL,
                    file_hash TEXT,
                    indexed_at TEXT,
                    data_json TEXT,
                    UNIQUE(metadata_type, name)
                )
            """)

            # Subsystems table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS subsystems (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    synonym TEXT,
                    parent TEXT,
                    children_json TEXT,
                    content_json TEXT,
                    UNIQUE(name, parent)
                )
            """)

            # Object-subsystem relation
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS object_subsystems (
                    object_id INTEGER,
                    subsystem_name TEXT,
                    FOREIGN KEY (object_id) REFERENCES metadata_objects(id),
                    UNIQUE(object_id, subsystem_name)
                )
            """)

            # Indexes
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_objects_type
                ON metadata_objects(metadata_type)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_objects_name
                ON metadata_objects(name)
            """)
            await cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_objects_hash
                ON metadata_objects(file_hash)
            """)

            await self._connection.commit()

    async def save_object(self, obj: MetadataObject) -> int:
        """
        Save or update metadata object.

        Args:
            obj: MetadataObject to save

        Returns:
            Database ID of saved object
        """
        # Use batch mode if enabled
        if self._batch_mode:
            self._batch_objects.append(obj)
            if len(self._batch_objects) >= self._batch_size:
                await self._flush_batch()
            return 0

        # Serialize complex fields to JSON
        data_json = obj.model_dump_json(
            exclude={"config_path", "object_path", "indexed_at"}
        )

        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT OR REPLACE INTO metadata_objects
                (uuid, name, synonym, comment, metadata_type,
                 config_path, object_path, file_hash, indexed_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obj.uuid,
                obj.name,
                obj.synonym,
                obj.comment,
                obj.metadata_type.value,
                str(obj.config_path),
                str(obj.object_path),
                obj.file_hash,
                datetime.now().isoformat(),
                data_json,
            ))
            await self._connection.commit()

            # Update object cache
            cache_key = (obj.metadata_type.value, obj.name)
            await self._object_cache.set(cache_key, obj)

            return cursor.lastrowid or 0

    async def get_object(
        self,
        metadata_type: MetadataType,
        name: str,
    ) -> MetadataObject | None:
        """
        Get object by type and name.

        Args:
            metadata_type: Object type
            name: Object name

        Returns:
            MetadataObject or None
        """
        # Check in-memory cache first
        cache_key = (metadata_type.value, name)
        cached = await self._object_cache.get(cache_key)
        if cached is not None:
            return cached

        async with profiler.measure("cache.get_object"):
            async with self._connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT * FROM metadata_objects
                    WHERE metadata_type = ? AND name = ?
                """, (metadata_type.value, name))
                row = await cursor.fetchone()

                if not row:
                    return None

                obj = self._row_to_object(row)

                # Store in cache
                await self._object_cache.set(cache_key, obj)
                return obj

    async def get_objects_by_type(
        self,
        metadata_type: MetadataType,
    ) -> list[MetadataObject]:
        """
        Get all objects of a type.

        Args:
            metadata_type: Object type

        Returns:
            List of MetadataObjects
        """
        # Check cache
        cache_key = metadata_type.value
        cached = await self._list_cache.get(cache_key)
        if cached is not None:
            return cached

        async with profiler.measure("cache.get_objects_by_type"):
            async with self._connection.cursor() as cursor:
                await cursor.execute("""
                    SELECT * FROM metadata_objects
                    WHERE metadata_type = ?
                    ORDER BY name
                """, (metadata_type.value,))
                rows = await cursor.fetchall()

                result = [self._row_to_object(row) for row in rows]

                # Store in cache
                await self._list_cache.set(cache_key, result)
                return result

    async def search_objects(
        self,
        query: str,
        metadata_type: MetadataType | None = None,
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
        # Check cache
        cache_key = f"{query}:{metadata_type.value if metadata_type else ''}:{limit}"
        cached = await self._search_cache.get(cache_key)
        if cached is not None:
            return cached

        async with profiler.measure("cache.search_objects"):
            search_pattern = f"%{query}%"

            async with self._connection.cursor() as cursor:
                if metadata_type:
                    await cursor.execute("""
                        SELECT * FROM metadata_objects
                        WHERE metadata_type = ?
                        AND (name LIKE ? OR synonym LIKE ? COLLATE NOCASE)
                        ORDER BY
                            CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                            name
                        LIMIT ?
                    """, (metadata_type.value, search_pattern, search_pattern,
                          f"{query}%", limit))
                else:
                    await cursor.execute("""
                        SELECT * FROM metadata_objects
                        WHERE name LIKE ? OR synonym LIKE ? COLLATE NOCASE
                        ORDER BY
                            CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                            name
                        LIMIT ?
                    """, (search_pattern, search_pattern, f"{query}%", limit))

                rows = await cursor.fetchall()
                result = [self._row_to_object(row) for row in rows]

                # Store in cache
                await self._search_cache.set(cache_key, result)
                return result

    async def get_all_object_names(
        self,
        metadata_type: MetadataType | None = None,
    ) -> list[tuple[str, str]]:
        """
        Get list of (type, name) tuples for all objects.

        Args:
            metadata_type: Optional type filter

        Returns:
            List of (type, name) tuples
        """
        async with self._connection.cursor() as cursor:
            if metadata_type:
                await cursor.execute("""
                    SELECT metadata_type, name FROM metadata_objects
                    WHERE metadata_type = ?
                    ORDER BY name
                """, (metadata_type.value,))
            else:
                await cursor.execute("""
                    SELECT metadata_type, name FROM metadata_objects
                    ORDER BY metadata_type, name
                """)

            rows = await cursor.fetchall()
            return [(row["metadata_type"], row["name"]) for row in rows]

    async def get_hash(
        self,
        metadata_type: MetadataType,
        name: str,
    ) -> str | None:
        """
        Get stored file hash for object.

        Args:
            metadata_type: Object type
            name: Object name

        Returns:
            File hash or None
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT file_hash FROM metadata_objects
                WHERE metadata_type = ? AND name = ?
            """, (metadata_type.value, name))
            row = await cursor.fetchone()
            return row["file_hash"] if row else None

    async def save_subsystem(self, subsystem: Subsystem) -> None:
        """
        Save or update subsystem.

        Args:
            subsystem: Subsystem to save
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT OR REPLACE INTO subsystems
                (name, synonym, parent, children_json, content_json)
                VALUES (?, ?, ?, ?, ?)
            """, (
                subsystem.name,
                subsystem.synonym,
                subsystem.parent,
                json.dumps(subsystem.children),
                json.dumps(subsystem.content),
            ))
            await self._connection.commit()

    async def get_subsystems(
        self,
        parent: str | None = None,
    ) -> list[Subsystem]:
        """
        Get subsystems by parent.

        Args:
            parent: Parent subsystem name or None for root

        Returns:
            List of subsystems
        """
        async with self._connection.cursor() as cursor:
            if parent is None:
                await cursor.execute("""
                    SELECT * FROM subsystems
                    WHERE parent IS NULL
                    ORDER BY name
                """)
            else:
                await cursor.execute("""
                    SELECT * FROM subsystems
                    WHERE parent = ?
                    ORDER BY name
                """, (parent,))

            rows = await cursor.fetchall()
            return [self._row_to_subsystem(row) for row in rows]

    async def get_stats(self) -> dict[str, int]:
        """
        Get cache statistics.

        Returns:
            Dictionary with counts by type
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                SELECT metadata_type, COUNT(*) as count
                FROM metadata_objects
                GROUP BY metadata_type
            """)
            rows = await cursor.fetchall()
            return {row["metadata_type"]: row["count"] for row in rows}

    async def clear(self) -> None:
        """Clear all cached data."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("DELETE FROM object_subsystems")
            await cursor.execute("DELETE FROM subsystems")
            await cursor.execute("DELETE FROM metadata_objects")
            await self._connection.commit()

        # Clear in-memory caches
        await self._invalidate_caches()

    def cache_stats(self) -> dict[str, dict]:
        """
        Get in-memory cache statistics.

        Returns:
            Dictionary with cache stats
        """
        return {
            "object_cache": self._object_cache.stats(),
            "search_cache": self._search_cache.stats(),
            "list_cache": self._list_cache.stats(),
        }

    def _row_to_object(self, row: aiosqlite.Row) -> MetadataObject:
        """Convert database row to MetadataObject."""
        data = json.loads(row["data_json"])

        # Reconstruct MetadataObject
        data["config_path"] = Path(row["config_path"])
        data["object_path"] = Path(row["object_path"])
        data["metadata_type"] = MetadataType(row["metadata_type"])

        if row["indexed_at"]:
            data["indexed_at"] = datetime.fromisoformat(row["indexed_at"])

        return MetadataObject.model_validate(data)

    def _row_to_subsystem(self, row: aiosqlite.Row) -> Subsystem:
        """Convert database row to Subsystem."""
        return Subsystem(
            name=row["name"],
            synonym=row["synonym"] or "",
            parent=row["parent"],
            children=json.loads(row["children_json"]) if row["children_json"] else [],
            content=json.loads(row["content_json"]) if row["content_json"] else [],
        )
