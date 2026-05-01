"""bsl-language-server JVM subprocess lifecycle.

Locates the BSL-LS jar (env override → home cache → PATH), spawns it
in LSP stdio mode, monitors liveness, and serves up a fully wired
:class:`BslLspClient` ready for requests.

Responsibilities:
- Resolve the JAR path and the Java executable.
- Spawn the subprocess with stdin/stdout pipes (stderr → logger).
- Hand a client back to callers and **keep it alive**: a periodic
  healthcheck pings the server; if it stops responding (or the
  subprocess died), the manager kills what's left and starts a fresh
  process on the next request.

Out of scope: workspace tracking, per-request retries, response caching.
Those belong to ``client.py`` and ``cache.py``. Keeping this module
narrow makes per-workspace lifecycle trivial — one manager per
workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from mcp_1c.engines.code.lsp.client import BslLspClient, LspError
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

RestartListener = Callable[[], Awaitable[None]]

# Environment overrides — kept here as constants so the variable names
# are documented in one place and can't drift between modules.
ENV_BSL_LS_JAR = "MCP_BSL_LS_JAR"
ENV_BSL_LS_PATH = "MCP_BSL_LS_PATH"  # native binary (e.g. graalvm build)
ENV_JAVA = "MCP_JAVA_PATH"
ENV_DISABLE = "MCP_BSL_LS_DISABLED"

_DEFAULT_JAVA_OPTS = (
    "-Xms256m",
    "-Xmx2g",
    "-Dfile.encoding=UTF-8",
    "-Dstdout.encoding=UTF-8",
)


class BslLspUnavailable(RuntimeError):
    """Raised when no usable BSL-LS binary can be located.

    Callers must catch this and either fall back to the legacy regex
    parser or surface the error to the user — the LSP layer cannot
    paper over a missing dependency.
    """


class BslLspServerManager:
    """Manages one bsl-language-server process and its LSP client.

    Typical lifecycle::

        manager = BslLspServerManager(root_uri="file:///configs/uta")
        client = await manager.start()
        symbols = await client.document_symbol(...)
        await manager.stop()

    The manager is single-instance per workspace. After ``stop()`` the
    instance can be re-started — useful for picking up a new BSL-LS
    version without dropping the workspace.
    """

    def __init__(
        self,
        *,
        root_uri: str | None = None,
        jar_path: str | Path | None = None,
        binary_path: str | Path | None = None,
        java_path: str | None = None,
        java_opts: tuple[str, ...] = _DEFAULT_JAVA_OPTS,
        request_timeout: float = 30.0,
        healthcheck_interval: float = 30.0,
        max_restarts_per_minute: int = 3,
    ) -> None:
        self._root_uri = root_uri
        self._jar_path = Path(jar_path) if jar_path else None
        self._binary_path = Path(binary_path) if binary_path else None
        self._java_path = java_path
        self._java_opts = java_opts
        self._request_timeout = request_timeout
        self._healthcheck_interval = healthcheck_interval
        # Crash storms protection: if the JAR is broken or the JVM is
        # OOM-killed repeatedly, restart loops at full speed will burn
        # CPU and spam logs. We cap the restart rate; over-budget the
        # manager goes "circuit-broken" and refuses to start until
        # a manual ``stop()`` resets the window.
        self._max_restarts_per_minute = max_restarts_per_minute
        self._restart_timestamps: list[float] = []

        self._process: asyncio.subprocess.Process | None = None
        self._client: BslLspClient | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._healthcheck_task: asyncio.Task[None] | None = None
        # Listeners get notified after a successful restart so they can
        # invalidate caches keyed on the old client (e.g. ``did_open``
        # state — every restart loses the open-document set, callers
        # must redo their state).
        self._restart_listeners: list[RestartListener] = []
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def client(self) -> BslLspClient:
        if self._client is None:
            raise LspError("BSL-LS not started; call start() first")
        return self._client

    def on_restart(self, listener: RestartListener) -> None:
        """Register an async callback fired after every successful restart.

        Used by the workspace layer to drop ``did_open`` state, refresh
        caches keyed by client identity, etc. Listeners must not raise —
        if they do, the exception is logged and the next listener still
        runs. This mirrors the notification-handler contract on the
        :class:`BslLspClient`.
        """
        self._restart_listeners.append(listener)

    async def start(self) -> BslLspClient:
        """Resolve, spawn, and initialise BSL-LS. Idempotent.

        Concurrent ``start()`` calls dedup via the lock so two callers
        don't spawn two JVMs. Raises :class:`BslLspUnavailable` when the
        binary cannot be located or :class:`LspError` when initialisation
        fails. Re-raises ``BslLspUnavailable`` on circuit-broken state
        too, so callers see a clean failure mode instead of waiting
        forever.
        """
        if os.environ.get(ENV_DISABLE, "").lower() in ("1", "true", "yes"):
            raise BslLspUnavailable(
                f"BSL-LS disabled via {ENV_DISABLE} environment variable"
            )

        async with self._lock:
            if self.running and self._client is not None:
                return self._client
            if self._is_restart_storm():
                raise BslLspUnavailable(
                    f"Restart storm: {self._max_restarts_per_minute} crashes "
                    "in the last minute. Investigate logs and call stop() "
                    "to reset the circuit."
                )
            return await self._start_locked()

    async def _start_locked(self) -> BslLspClient:
        """The actual spawn-and-handshake, called under the manager lock."""
        cmd = self._build_command()
        logger.info(f"Starting bsl-language-server: {' '.join(cmd)}")
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # bsl-language-server walks the workspace from cwd if no
            # rootUri is sent; pin cwd to a neutral place.
            cwd=str(Path.home()),
        )

        if self._process.stdin is None or self._process.stdout is None:
            raise LspError("Failed to wire stdio for bsl-language-server")

        # Forward stderr to the logger; BSL-LS writes startup banner and
        # warnings there, and silent loss of those bytes is the #1 cause
        # of "why doesn't it work?" debug sessions.
        if self._process.stderr is not None:
            self._stderr_task = asyncio.create_task(
                self._drain_stderr(self._process.stderr),
                name="bsl-lsp-stderr",
            )

        client = BslLspClient(
            self._process.stdout,
            self._process.stdin,
            request_timeout=self._request_timeout,
        )
        try:
            await client.initialize(root_uri=self._root_uri)
        except Exception:
            await self._terminate_process()
            raise
        self._client = client

        # Healthcheck loop fires only when the interval is positive;
        # tests pass 0 to skip and exercise restarts deterministically.
        if self._healthcheck_interval > 0:
            self._healthcheck_task = asyncio.create_task(
                self._healthcheck_loop(), name="bsl-lsp-healthcheck"
            )
        return client

    async def stop(self) -> None:
        """Shut the server down and tear down the subprocess.

        Calls LSP ``shutdown`` + ``exit``, then SIGTERMs the process if
        it didn't go cleanly within a small grace window. Resets the
        restart-storm circuit breaker so a subsequent ``start()`` is
        unblocked even if the breaker had tripped.
        """
        async with self._lock:
            await self._stop_locked()
        # Resetting the restart timestamps lives outside the lock so
        # ``stop()`` is genuinely idempotent: calling it twice gives
        # the second call a fresh-state object to work with.
        self._restart_timestamps.clear()

    async def _stop_locked(self) -> None:
        if self._healthcheck_task is not None and not self._healthcheck_task.done():
            self._healthcheck_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._healthcheck_task
        self._healthcheck_task = None

        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.shutdown()
            self._client = None
        await self._terminate_process()

    async def _restart(self, *, reason: str) -> None:
        """Tear down the old process and spawn a new one.

        Called by the healthcheck loop when the server stops responding,
        or by external callers via :meth:`force_restart`. Records the
        restart timestamp for storm detection. Notifies registered
        listeners after a successful restart so caches/state can be
        rebuilt.
        """
        async with self._lock:
            logger.warning(f"Restarting bsl-language-server: {reason}")
            await self._stop_locked()
            self._restart_timestamps.append(time.monotonic())
            if self._is_restart_storm():
                logger.error(
                    f"Restart storm detected ({len(self._restart_timestamps)} "
                    "in 60s); refusing to start again until stop() is called"
                )
                return
            try:
                await self._start_locked()
            except Exception as exc:
                logger.error(f"Restart failed: {exc}")
                return

        # Notify listeners outside the lock — they may take their own
        # locks or call back into the manager.
        for listener in self._restart_listeners:
            try:
                await listener()
            except Exception as exc:
                logger.warning(f"Restart listener raised: {exc}")

    async def force_restart(self, *, reason: str = "manual") -> None:
        """External handle for callers that want to recycle the JVM.

        Useful when picking up a new BSL-LS jar at runtime, or after a
        config-tree-relayout that the server isn't watching.
        """
        await self._restart(reason=reason)

    def _is_restart_storm(self) -> bool:
        """True if more than ``max_restarts_per_minute`` happened recently.

        Sliding window of 60 seconds; the manager refuses to restart
        again until ``stop()`` resets the timestamps.
        """
        now = time.monotonic()
        cutoff = now - 60.0
        self._restart_timestamps = [
            t for t in self._restart_timestamps if t > cutoff
        ]
        return len(self._restart_timestamps) >= self._max_restarts_per_minute

    async def _healthcheck_loop(self) -> None:
        """Periodically ping the server; restart on hang or crash.

        Each iteration:
        1. If the process exited, force restart.
        2. Send a cheap ``workspace/symbol`` ping with a tight timeout;
           any LspError or TimeoutError → restart.

        Exceptions inside the loop are caught — a healthcheck failure
        must never crash the asyncio task because *that* would silently
        disable the very protection the caller paid for.
        """
        try:
            while True:
                await asyncio.sleep(self._healthcheck_interval)
                if self._client is None:
                    return
                if self._process is None or self._process.returncode is not None:
                    await self._restart(reason="subprocess exited")
                    continue
                try:
                    await asyncio.wait_for(
                        self._client.workspace_symbol(""),
                        timeout=min(5.0, self._healthcheck_interval / 2),
                    )
                except (LspError, TimeoutError) as exc:
                    await self._restart(reason=f"ping failed: {exc}")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(f"Healthcheck unexpected error: {exc}")
        except asyncio.CancelledError:
            return

    async def _terminate_process(self) -> None:
        proc = self._process
        if proc is None:
            return
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                logger.warning("bsl-language-server did not exit; killing")
                proc.kill()
                await proc.wait()
        self._process = None
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stderr_task
            self._stderr_task = None

    @staticmethod
    async def _drain_stderr(stream: asyncio.StreamReader) -> None:
        while True:
            line = await stream.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                logger.info(f"[bsl-ls] {text}")

    def _build_command(self) -> list[str]:
        # Native binary takes precedence — startup is ~10× faster than
        # a JVM cold start.
        binary = self._resolve_binary()
        if binary is not None:
            return [str(binary)]

        jar = self._resolve_jar()
        if jar is None:
            raise BslLspUnavailable(
                "bsl-language-server not found. Set "
                f"{ENV_BSL_LS_JAR} to the path of bsl-language-server.jar "
                f"or {ENV_BSL_LS_PATH} to a native build."
            )
        java = self._java_path or os.environ.get(ENV_JAVA) or "java"
        if shutil.which(java) is None and not Path(java).exists():
            raise BslLspUnavailable(
                f"Java executable not found ({java!r}). Install JDK 17+ "
                f"or set {ENV_JAVA} to the absolute path of `java`."
            )
        return [java, *self._java_opts, "-jar", str(jar)]

    def _resolve_binary(self) -> Path | None:
        candidate = self._binary_path or _path_from_env(ENV_BSL_LS_PATH)
        if candidate is not None and candidate.exists():
            return candidate
        on_path = shutil.which("bsl-language-server")
        return Path(on_path) if on_path else None

    def _resolve_jar(self) -> Path | None:
        candidate = self._jar_path or _path_from_env(ENV_BSL_LS_JAR)
        if candidate is not None and candidate.exists():
            return candidate
        # Conventional cache location used by the future installer.
        cache_jar = (
            Path.home() / ".cache" / "mcp-1c" / "bsl-language-server.jar"
        )
        if cache_jar.exists():
            return cache_jar
        return None


def _path_from_env(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else None


__all__ = ["BslLspServerManager", "BslLspUnavailable"]
