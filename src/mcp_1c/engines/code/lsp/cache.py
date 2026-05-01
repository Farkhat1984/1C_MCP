"""Cache for ``textDocument/documentSymbol`` responses.

Document symbols are read-heavy (every KG build, every code-tools call)
and the LSP round-trip dominates the latency budget. Keying by
``(path, mtime, sha256)`` means we never serve stale data — the file
must change *and* contents must differ before we re-parse.

The cache is async-safe and bounded; sits on top of
:class:`mcp_1c.utils.lru_cache.AsyncLRUCache`. Designed to be shared
across engines (KG builder + code tools) inside a single workspace.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mcp_1c.utils.lru_cache import AsyncLRUCache


class DocumentSymbolCache:
    """Hash-keyed cache for documentSymbol responses.

    Key is ``(absolute_path, mtime_ns, sha256_hex_first_16)``. Hashing
    the first 16 hex chars of SHA-256 is enough to defeat mtime-only
    races while keeping the key compact. Cache size defaults to 1024
    entries (~1 MiB of metadata for an UTA-sized workspace).
    """

    def __init__(self, *, maxsize: int = 1024, ttl: float = 600.0) -> None:
        self._cache: AsyncLRUCache[tuple[str, int, str], list[dict[str, Any]]] = (
            AsyncLRUCache(maxsize=maxsize, ttl=ttl)
        )

    async def get(self, path: Path) -> list[dict[str, Any]] | None:
        key = self._key_for(path)
        if key is None:
            return None
        return await self._cache.get(key)

    async def set(
        self, path: Path, symbols: list[dict[str, Any]]
    ) -> None:
        key = self._key_for(path)
        if key is None:
            return
        await self._cache.set(key, symbols)

    async def invalidate(self, path: Path) -> None:
        """Drop every entry for this path regardless of mtime/sha.

        Called by the metadata watcher when a file is rewritten — at
        that point the old (mtime, sha) tuple is moot. Walks the cache's
        keyspace under its own lock; safe because invalidation is rare
        (one event per file change) and the keyspace is small (≤
        ``maxsize``).
        """
        absolute = str(path.resolve())
        # ``AsyncLRUCache`` doesn't expose key iteration in its public
        # API, but the OrderedDict and its lock are stable internals
        # we co-own at this layer.
        async with self._cache._lock:  # type: ignore[attr-defined]
            stale = [
                k for k in self._cache._cache  # type: ignore[attr-defined]
                if k[0] == absolute
            ]
            for k in stale:
                self._cache._cache.pop(k, None)  # type: ignore[attr-defined]

    async def clear(self) -> None:
        await self._cache.clear()

    def stats(self) -> dict[str, Any]:
        return self._cache.stats()

    @staticmethod
    def _key_for(path: Path) -> tuple[str, int, str] | None:
        """Produce a cache key, or ``None`` if the file has gone away.

        We deliberately read the file twice (stat + bytes) instead of
        only stat: an editor that writes-then-touches will set the same
        mtime as before, so mtime alone is not a safe identity.
        """
        try:
            stat = path.stat()
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError, PermissionError):
            return None
        digest = hashlib.sha256(data).hexdigest()[:16]
        return (str(path.resolve()), stat.st_mtime_ns, digest)


__all__ = ["DocumentSymbolCache"]
