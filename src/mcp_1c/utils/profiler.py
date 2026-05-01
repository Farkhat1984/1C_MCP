"""
Performance profiling utilities.

Provides decorators and context managers for measuring execution time.
"""

import functools
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ProfileStats:
    """Statistics for a profiled operation."""

    name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0

    @property
    def avg_time(self) -> float:
        """Average execution time."""
        if self.call_count == 0:
            return 0.0
        return self.total_time / self.call_count

    def record(self, elapsed: float) -> None:
        """Record a timing measurement."""
        self.call_count += 1
        self.total_time += elapsed
        self.min_time = min(self.min_time, elapsed)
        self.max_time = max(self.max_time, elapsed)


@dataclass
class Profiler:
    """
    Performance profiler for tracking operation timings.

    Usage:
        profiler = Profiler()

        @profiler.profile
        async def my_operation():
            ...

        # Or with context manager:
        async with profiler.measure("operation_name"):
            ...

        # Get stats:
        profiler.report()
    """

    enabled: bool = True
    stats: dict[str, ProfileStats] = field(default_factory=dict)

    def _get_stats(self, name: str) -> ProfileStats:
        """Get or create stats for an operation."""
        if name not in self.stats:
            self.stats[name] = ProfileStats(name=name)
        return self.stats[name]

    def profile(self, func: F) -> F:
        """
        Decorator for profiling async functions.

        Args:
            func: Async function to profile

        Returns:
            Wrapped function
        """
        name = func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self.enabled:
                return await func(*args, **kwargs)

            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                self._get_stats(name).record(elapsed)

        return wrapper  # type: ignore

    def profile_sync(self, func: F) -> F:
        """
        Decorator for profiling sync functions.

        Args:
            func: Sync function to profile

        Returns:
            Wrapped function
        """
        name = func.__qualname__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not self.enabled:
                return func(*args, **kwargs)

            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                self._get_stats(name).record(elapsed)

        return wrapper  # type: ignore

    @asynccontextmanager
    async def measure(self, name: str):
        """
        Context manager for measuring async operations.

        Args:
            name: Operation name

        Yields:
            None
        """
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self._get_stats(name).record(elapsed)

    @contextmanager
    def measure_sync(self, name: str):
        """
        Context manager for measuring sync operations.

        Args:
            name: Operation name

        Yields:
            None
        """
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self._get_stats(name).record(elapsed)

    def report(self, threshold_ms: float = 0.0) -> str:
        """
        Generate performance report.

        Args:
            threshold_ms: Only include operations above this threshold

        Returns:
            Formatted report string
        """
        if not self.stats:
            return "No profiling data collected."

        lines = ["=" * 70]
        lines.append("Performance Report")
        lines.append("=" * 70)
        lines.append(
            f"{'Operation':<40} {'Calls':>8} {'Total':>10} {'Avg':>10} {'Max':>10}"
        )
        lines.append("-" * 70)

        # Sort by total time descending
        sorted_stats = sorted(
            self.stats.values(),
            key=lambda s: s.total_time,
            reverse=True,
        )

        for stat in sorted_stats:
            if stat.total_time * 1000 < threshold_ms:
                continue

            name = stat.name[:40]
            lines.append(
                f"{name:<40} {stat.call_count:>8} "
                f"{stat.total_time*1000:>9.1f}ms "
                f"{stat.avg_time*1000:>9.2f}ms "
                f"{stat.max_time*1000:>9.2f}ms"
            )

        lines.append("=" * 70)

        report = "\n".join(lines)
        logger.info(f"\n{report}")
        return report

    def reset(self) -> None:
        """Reset all profiling statistics."""
        self.stats.clear()

    def get_stats(self, name: str) -> ProfileStats | None:
        """Get stats for a specific operation."""
        return self.stats.get(name)


# Global profiler instance
_profiler = Profiler()


def get_profiler() -> Profiler:
    """Get global profiler instance."""
    return _profiler


def profile(func: F) -> F:
    """Decorator using global profiler."""
    return _profiler.profile(func)


def profile_sync(func: F) -> F:
    """Decorator using global profiler for sync functions."""
    return _profiler.profile_sync(func)
