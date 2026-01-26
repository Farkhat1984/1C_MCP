"""
LRU Cache implementation for async operations.

Provides an async-compatible LRU cache with TTL support.
"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Generic, Hashable, TypeVar

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    """Entry in the LRU cache."""

    value: V
    created_at: float
    access_count: int = 0


class AsyncLRUCache(Generic[K, V]):
    """
    Async-compatible LRU cache with TTL support.

    Features:
    - Maximum size limit with LRU eviction
    - Optional TTL for entries
    - Thread-safe for async operations
    - Statistics tracking
    """

    def __init__(
        self,
        maxsize: int = 1000,
        ttl: float | None = None,
    ) -> None:
        """
        Initialize cache.

        Args:
            maxsize: Maximum number of entries
            ttl: Time-to-live in seconds (None = infinite)
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get(self, key: K) -> V | None:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        async with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check TTL
            if self.ttl is not None:
                age = time.time() - entry.created_at
                if age > self.ttl:
                    del self._cache[key]
                    self._misses += 1
                    return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.access_count += 1
            self._hits += 1
            return entry.value

    async def set(self, key: K, value: V) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            # Remove if exists
            if key in self._cache:
                del self._cache[key]

            # Evict if at capacity
            while len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)

            # Add new entry
            self._cache[key] = CacheEntry(
                value=value,
                created_at=time.time(),
            )

    async def delete(self, key: K) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if key was present
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    async def invalidate_pattern(
        self,
        predicate: Callable[[K], bool],
    ) -> int:
        """
        Invalidate entries matching predicate.

        Args:
            predicate: Function returning True for keys to invalidate

        Returns:
            Number of entries invalidated
        """
        async with self._lock:
            keys_to_remove = [k for k in self._cache if predicate(k)]
            for key in keys_to_remove:
                del self._cache[key]
            return len(keys_to_remove)

    @property
    def size(self) -> int:
        """Current number of entries."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self._hits + self._misses
        if total == 0:
            return 0.0
        return self._hits / total

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self._cache),
            "maxsize": self.maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "ttl": self.ttl,
        }


class CacheManager:
    """
    Manager for multiple named caches.

    Provides centralized cache management and statistics.
    """

    def __init__(self) -> None:
        """Initialize cache manager."""
        self._caches: dict[str, AsyncLRUCache] = {}

    def get_cache(
        self,
        name: str,
        maxsize: int = 1000,
        ttl: float | None = None,
    ) -> AsyncLRUCache:
        """
        Get or create a named cache.

        Args:
            name: Cache name
            maxsize: Maximum entries
            ttl: Time-to-live

        Returns:
            AsyncLRUCache instance
        """
        if name not in self._caches:
            self._caches[name] = AsyncLRUCache(maxsize=maxsize, ttl=ttl)
        return self._caches[name]

    async def clear_all(self) -> None:
        """Clear all caches."""
        for cache in self._caches.values():
            await cache.clear()

    def stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all caches."""
        return {name: cache.stats() for name, cache in self._caches.items()}

    def report(self) -> str:
        """Generate statistics report."""
        lines = ["=" * 60]
        lines.append("Cache Statistics")
        lines.append("=" * 60)
        lines.append(
            f"{'Cache':<20} {'Size':>8} {'Hits':>10} {'Misses':>10} {'Hit%':>8}"
        )
        lines.append("-" * 60)

        for name, cache in self._caches.items():
            s = cache.stats()
            lines.append(
                f"{name:<20} {s['size']:>8} "
                f"{s['hits']:>10} {s['misses']:>10} "
                f"{s['hit_rate']*100:>7.1f}%"
            )

        lines.append("=" * 60)
        return "\n".join(lines)


# Global cache manager instance
_cache_manager = CacheManager()


def get_cache_manager() -> CacheManager:
    """Get global cache manager."""
    return _cache_manager


def get_cache(
    name: str,
    maxsize: int = 1000,
    ttl: float | None = None,
) -> AsyncLRUCache:
    """Get or create a named cache using global manager."""
    return _cache_manager.get_cache(name, maxsize, ttl)
