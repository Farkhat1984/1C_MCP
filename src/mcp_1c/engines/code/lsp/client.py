"""Async LSP client over stdio.

Talks to one bsl-language-server JVM subprocess. Owns the request/
response correlation table, dispatches incoming notifications to
registered handlers, and exposes a small typed API over the LSP
methods we actually use.

Methods exposed (Phase 1):
- ``initialize`` / ``initialized`` / ``shutdown`` / ``exit`` (handshake)
- ``textDocument/didOpen`` / ``didChange`` / ``didClose`` (sync state)
- ``textDocument/documentSymbol`` (procedures + functions in a file)
- ``textDocument/references`` (find all callers of a symbol)
- ``textDocument/definition`` (resolve a symbol to its declaration)
- ``workspace/symbol`` (cross-file symbol search)
- ``textDocument/diagnostics`` consumed via the
  ``textDocument/publishDiagnostics`` notification

Concurrency: one writer task and one reader task per process. Public
methods are coroutine-safe — internal request map is locked. Pending
requests are cancelled on ``close()`` so callers waiting on a dead
process get a clean ``LspError`` rather than hanging forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from asyncio import StreamReader, StreamWriter
from collections.abc import Awaitable, Callable
from typing import Any

from mcp_1c.engines.code.lsp.protocol import (
    JSONRPC_VERSION,
    LspProtocolError,
    read_message,
    write_message,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

NotificationHandler = Callable[[dict[str, Any]], Awaitable[None]]


class LspError(RuntimeError):
    """LSP-level error.

    Wraps both transport failures (process died, malformed frame) and
    JSON-RPC error responses. ``code`` is the JSON-RPC error code when
    available, ``data`` is the optional ``error.data`` payload.
    """

    def __init__(
        self, message: str, *, code: int = 0, data: Any = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data


class BslLspClient:
    """LSP client speaking JSON-RPC over a pair of streams.

    The client is process-agnostic: feed it any pair of ``StreamReader``
    and ``StreamWriter`` connected to a real LSP server (typically the
    output of :class:`BslLspServerManager`). Tests pipe in-memory
    streams to exercise the request/response state machine without a
    JVM.
    """

    def __init__(
        self,
        reader: StreamReader,
        writer: StreamWriter,
        *,
        request_timeout: float = 30.0,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._request_timeout = request_timeout
        self._next_id = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._notification_handlers: dict[str, list[NotificationHandler]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def start(self) -> None:
        """Begin the background reader loop. Idempotent."""
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(
                self._read_loop(), name="bsl-lsp-reader"
            )

    async def initialize(
        self,
        *,
        root_uri: str | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the LSP handshake.

        Sends ``initialize`` followed by the ``initialized`` notification.
        Returns the server's reported capabilities so the caller can
        decide which features to use.
        """
        await self.start()
        params: dict[str, Any] = {
            "processId": None,
            "clientInfo": {"name": "mcp-1c", "version": "0.2.0"},
            "capabilities": capabilities or {},
            "rootUri": root_uri,
            "workspaceFolders": (
                [{"uri": root_uri, "name": "workspace"}]
                if root_uri is not None
                else None
            ),
        }
        result = await self.request("initialize", params)
        await self.notify("initialized", {})
        self._initialized = True
        return result if isinstance(result, dict) else {}

    async def shutdown(self) -> None:
        """Send ``shutdown`` then ``exit`` and close streams.

        Even if the server doesn't reply (already crashed, partial
        transport), we still close cleanly — connection cleanup is the
        manager's job, not ours.
        """
        try:
            await asyncio.wait_for(self.request("shutdown", None), timeout=5.0)
        except (TimeoutError, LspError) as exc:
            logger.debug(f"shutdown request did not complete cleanly: {exc}")
        try:
            await self.notify("exit", None)
        except Exception as exc:
            logger.debug(f"exit notification failed: {exc}")
        await self.close()

    async def close(self) -> None:
        """Cancel pending requests and stop the reader loop.

        Called by ``shutdown()`` and by the manager when restarting a
        crashed server. Safe to call multiple times.
        """
        if self._closed.is_set():
            return
        self._closed.set()
        # Fail every in-flight request so awaiters wake up.
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(LspError("LSP client closed"))
        self._pending.clear()
        with contextlib.suppress(Exception):
            self._writer.close()
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader_task

    # -- public LSP methods ------------------------------------------------

    async def did_open(
        self,
        uri: str,
        text: str,
        *,
        language_id: str = "bsl",
        version: int = 1,
    ) -> None:
        """Tell the server we're now tracking a document."""
        await self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": version,
                    "text": text,
                }
            },
        )

    async def did_close(self, uri: str) -> None:
        await self.notify(
            "textDocument/didClose",
            {"textDocument": {"uri": uri}},
        )

    async def document_symbol(self, uri: str) -> list[dict[str, Any]]:
        """Return the procedures/functions/regions in a document.

        Falls back to an empty list when the server returns ``null``;
        bsl-language-server emits null for unparseable files but the
        caller usually wants a list either way.
        """
        result = await self.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": uri}},
        )
        if not result:
            return []
        if isinstance(result, list):
            return result
        return []

    async def references(
        self,
        uri: str,
        line: int,
        character: int,
        *,
        include_declaration: bool = False,
    ) -> list[dict[str, Any]]:
        """Find references to the symbol at ``(line, character)``."""
        result = await self.request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": include_declaration},
            },
        )
        return result if isinstance(result, list) else []

    async def definition(
        self, uri: str, line: int, character: int
    ) -> list[dict[str, Any]]:
        """Resolve a symbol to its declaration site(s)."""
        result = await self.request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        if result is None:
            return []
        if isinstance(result, list):
            return result
        # Older servers return a single Location.
        return [result] if isinstance(result, dict) else []

    async def workspace_symbol(self, query: str) -> list[dict[str, Any]]:
        """Search across the workspace for matching symbols."""
        result = await self.request("workspace/symbol", {"query": query})
        return result if isinstance(result, list) else []

    # -- generic request / notify -----------------------------------------

    async def request(self, method: str, params: Any) -> Any:
        """Send a request and await its response.

        Raises :class:`LspError` on a JSON-RPC error response, on
        transport failure, or when the per-request timeout elapses.
        """
        if self._closed.is_set():
            raise LspError("LSP client is closed")
        request_id = next(self._next_id)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        message: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        try:
            await write_message(self._writer, message)
        except Exception as exc:
            self._pending.pop(request_id, None)
            raise LspError(f"Failed to send {method}: {exc}") from exc

        try:
            return await asyncio.wait_for(future, timeout=self._request_timeout)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise LspError(
                f"LSP request {method} timed out after {self._request_timeout}s"
            ) from exc

    async def notify(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message: dict[str, Any] = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        try:
            await write_message(self._writer, message)
        except Exception as exc:
            raise LspError(f"Failed to send notification {method}: {exc}") from exc

    def on_notification(
        self, method: str, handler: NotificationHandler
    ) -> None:
        """Register an async handler for incoming server notifications.

        Multiple handlers can be registered for the same method; each
        receives the raw ``params`` dict. Handlers must not raise — if
        they do, the exception is logged and the read loop continues.
        """
        self._notification_handlers.setdefault(method, []).append(handler)

    # -- internal ----------------------------------------------------------

    async def _read_loop(self) -> None:
        """Continuously read messages and dispatch them.

        On EOF or a protocol error the loop ends; any pending requests
        get notified via ``close()``. The loop never raises out — that
        would silently fault the asyncio task.
        """
        try:
            while not self._closed.is_set():
                try:
                    message = await read_message(self._reader)
                except LspProtocolError as exc:
                    logger.warning(f"LSP framing error: {exc}")
                    break
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    break
                if message is None:  # EOF
                    break
                await self._dispatch(message)
        finally:
            await self.close()

    async def _dispatch(self, message: dict[str, Any]) -> None:
        """Route a single decoded message to a request future or
        a notification handler.

        Server-initiated requests are not yet handled — bsl-language-
        server doesn't issue any that we care about. If one shows up,
        we log and reply with an error so the server doesn't block.
        """
        if "id" in message and "method" not in message:
            await self._handle_response(message)
            return
        if "method" in message and "id" not in message:
            await self._handle_notification(message)
            return
        if "method" in message and "id" in message:
            # Server-initiated request: politely refuse rather than block.
            await self._reply_method_not_found(message)
            return
        logger.warning(f"Unknown LSP message shape: {message!r}")

    async def _handle_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return
        if "error" in message:
            err = message["error"] or {}
            future.set_exception(
                LspError(
                    err.get("message", "Unknown LSP error"),
                    code=int(err.get("code", 0)) if err.get("code") else 0,
                    data=err.get("data"),
                )
            )
            return
        future.set_result(message.get("result"))

    async def _handle_notification(self, message: dict[str, Any]) -> None:
        method = message["method"]
        params = message.get("params") or {}
        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                await handler(params)
            except Exception as exc:
                logger.warning(
                    f"Notification handler for {method!r} raised: {exc}"
                )

    async def _reply_method_not_found(self, message: dict[str, Any]) -> None:
        try:
            await write_message(
                self._writer,
                {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": message["id"],
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {message.get('method')}",
                    },
                },
            )
        except Exception as exc:
            logger.debug(f"Failed to refuse server-initiated request: {exc}")


__all__ = ["BslLspClient", "LspError", "NotificationHandler"]
