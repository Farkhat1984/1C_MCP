"""
File watcher for configuration changes.

Monitors configuration directory and triggers re-indexing on changes.
"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from watchfiles import Change, awatch

from mcp_1c.config import WatcherConfig
from mcp_1c.domain.metadata import MetadataType
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class FileChange:
    """Represents a file change event."""

    def __init__(
        self,
        change_type: Change,
        path: Path,
    ) -> None:
        """Initialize change event."""
        self.change_type = change_type
        self.path = path

    @property
    def is_xml(self) -> bool:
        """Check if changed file is XML."""
        return self.path.suffix.lower() == ".xml"

    @property
    def is_bsl(self) -> bool:
        """Check if changed file is BSL."""
        return self.path.suffix.lower() == ".bsl"

    def get_metadata_info(self) -> tuple[MetadataType | None, str | None]:
        """
        Extract metadata type and name from path.

        Returns:
            Tuple of (MetadataType, object_name) or (None, None)
        """
        parts = self.path.parts

        # Look for known type folders
        type_folders = {
            "Catalogs": MetadataType.CATALOG,
            "Documents": MetadataType.DOCUMENT,
            "Enums": MetadataType.ENUM,
            "InformationRegisters": MetadataType.INFORMATION_REGISTER,
            "AccumulationRegisters": MetadataType.ACCUMULATION_REGISTER,
            "Reports": MetadataType.REPORT,
            "DataProcessors": MetadataType.DATA_PROCESSOR,
            "CommonModules": MetadataType.COMMON_MODULE,
        }

        for i, part in enumerate(parts):
            if part in type_folders and i + 1 < len(parts):
                return type_folders[part], parts[i + 1]

        return None, None


ChangeHandler = Callable[[FileChange], Awaitable[None]]


class ConfigurationWatcher:
    """
    Watches configuration directory for changes.

    Uses watchfiles for efficient cross-platform file watching.
    """

    def __init__(
        self,
        config: WatcherConfig,
        on_change: ChangeHandler | None = None,
    ) -> None:
        """
        Initialize watcher.

        Args:
            config: Watcher configuration
            on_change: Callback for change events
        """
        self.config = config
        self.on_change = on_change
        self._running = False
        self._task: asyncio.Task | None = None
        self.logger = get_logger(__name__)

    async def start(self, watch_path: Path | list[Path]) -> None:
        """
        Start watching one or more directories.

        Args:
            watch_path: Directory (legacy, single Path) or list of
                directories to watch. ``watchfiles.awatch`` natively
                accepts multiple paths in one subscription, so multi-
                root indexing (Phase F3) just hands the list through.
        """
        if not self.config.enabled:
            self.logger.info("File watching disabled")
            return

        if self._running:
            self.logger.warning("Watcher already running")
            return

        paths = (
            list(watch_path)
            if isinstance(watch_path, (list, tuple))
            else [watch_path]
        )
        if not paths:
            self.logger.warning("Watcher start called with empty path list")
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop(paths))
        self.logger.info(f"Started watching: {[str(p) for p in paths]}")

    async def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.logger.info("Watcher stopped")

    async def _watch_loop(self, watch_paths: list[Path]) -> None:
        """
        Main watch loop.

        Args:
            watch_paths: Directories to watch. ``awatch`` accepts a
                varargs of paths and multiplexes them into one event
                stream.
        """
        try:
            async for changes in awatch(
                *watch_paths,
                debounce=self.config.debounce_ms,
                recursive=True,
            ):
                if not self._running:
                    break

                for change_type, path_str in changes:
                    path = Path(path_str)

                    # Skip ignored patterns
                    if self._should_ignore(path):
                        continue

                    change = FileChange(change_type, path)
                    self.logger.debug(
                        f"Change detected: {change_type.name} - {path}"
                    )

                    if self.on_change:
                        try:
                            await self.on_change(change)
                        except Exception as e:
                            self.logger.error(f"Error handling change: {e}")

        except asyncio.CancelledError:
            self.logger.debug("Watch loop cancelled")
        except Exception as e:
            self.logger.error(f"Watch loop error: {e}")

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        for pattern in self.config.ignored_patterns:
            if path.match(pattern):
                return True
        return False


class ChangeAggregator:
    """
    Aggregates multiple changes before processing.

    Collects changes over a time window and batches them
    for more efficient processing.
    """

    def __init__(
        self,
        window_ms: int = 1000,
    ) -> None:
        """
        Initialize aggregator.

        Args:
            window_ms: Aggregation window in milliseconds
        """
        self.window_ms = window_ms
        self._changes: list[FileChange] = []
        self._lock = asyncio.Lock()
        self._timer: asyncio.Task | None = None
        self._handler: ChangeHandler | None = None

    def set_handler(self, handler: ChangeHandler) -> None:
        """Set the batch handler."""
        self._handler = handler

    async def add_change(self, change: FileChange) -> None:
        """Add a change to the aggregation buffer."""
        async with self._lock:
            self._changes.append(change)

            # Start or restart timer
            if self._timer:
                self._timer.cancel()

            self._timer = asyncio.create_task(self._flush_after_delay())

    async def _flush_after_delay(self) -> None:
        """Flush changes after delay."""
        await asyncio.sleep(self.window_ms / 1000)
        await self._flush()

    async def _flush(self) -> None:
        """Process all accumulated changes."""
        async with self._lock:
            if not self._changes or not self._handler:
                return

            # Deduplicate by path (keep latest change type)
            changes_by_path: dict[Path, FileChange] = {}
            for change in self._changes:
                changes_by_path[change.path] = change

            self._changes.clear()

        # Process deduplicated changes
        for change in changes_by_path.values():
            await self._handler(change)
