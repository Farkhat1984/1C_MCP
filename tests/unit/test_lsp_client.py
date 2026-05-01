"""Mock-based tests for the LSP client.

We don't spin up bsl-language-server here — the JVM cold-start would
make the suite slow and the JAR might not even be installed in CI.
Instead we run the client against an in-memory pair of streams driven
by a tiny scripted "server" coroutine. That exercises every edge of the
state machine: framing, request/response correlation, notifications,
errors, EOF, timeouts.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from mcp_1c.engines.code.lsp.client import BslLspClient, LspError
from mcp_1c.engines.code.lsp.protocol import (
    LspProtocolError,
    encode_message,
    read_message,
)


def _make_pipe() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Create a connected (reader, writer) pair backed by an in-memory buffer."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    transport = _LoopbackTransport(reader)
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer


class _LoopbackTransport(asyncio.WriteTransport):
    """Minimal write transport that feeds whatever you write back into
    a paired StreamReader. Lets us script a "server" that responds to
    the client's bytes without sockets or subprocesses."""

    def __init__(self, paired_reader: asyncio.StreamReader) -> None:
        self._reader = paired_reader
        self._closed = False

    def write(self, data: bytes) -> None:  # type: ignore[override]
        if self._closed:
            return
        self._reader.feed_data(data)

    def close(self) -> None:  # type: ignore[override]
        if not self._closed:
            self._closed = True
            self._reader.feed_eof()

    def is_closing(self) -> bool:  # type: ignore[override]
        return self._closed

    def get_write_buffer_size(self) -> int:  # type: ignore[override]
        return 0


# ---------------------------------------------------------------------------
# Wire-format primitives
# ---------------------------------------------------------------------------


def test_encode_message_uses_lsp_framing() -> None:
    raw = encode_message({"jsonrpc": "2.0", "method": "x"})
    assert raw.startswith(b"Content-Length: ")
    header, _, body = raw.partition(b"\r\n\r\n")
    declared = int(header.split(b":")[1].strip())
    assert declared == len(body)
    assert json.loads(body) == {"jsonrpc": "2.0", "method": "x"}


def test_encode_message_preserves_unicode() -> None:
    raw = encode_message({"params": {"name": "Контрагенты"}})
    body = raw.split(b"\r\n\r\n", 1)[1]
    # Body must not be ASCII-escaped — UTF-8 bytes for Cyrillic stay raw.
    assert "Контрагенты".encode() in body


@pytest.mark.asyncio
async def test_read_message_parses_well_formed_frame() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(encode_message({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}))
    reader.feed_eof()

    msg = await read_message(reader)
    assert msg == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


@pytest.mark.asyncio
async def test_read_message_returns_none_on_eof() -> None:
    reader = asyncio.StreamReader()
    reader.feed_eof()
    assert await read_message(reader) is None


@pytest.mark.asyncio
async def test_read_message_rejects_missing_content_length() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b"X-Bogus: 1\r\n\r\n{}")
    reader.feed_eof()
    with pytest.raises(LspProtocolError):
        await read_message(reader)


@pytest.mark.asyncio
async def test_read_message_rejects_malformed_json() -> None:
    reader = asyncio.StreamReader()
    body = b"{broken"
    reader.feed_data(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    reader.feed_eof()
    with pytest.raises(LspProtocolError):
        await read_message(reader)


# ---------------------------------------------------------------------------
# Request / response correlation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_resolves_with_matching_id() -> None:
    """A response with the right id must wake the awaiting request."""
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )

    client = BslLspClient(reader_into_client, client_writer, request_timeout=2.0)
    await client.start()

    async def fake_server() -> None:
        msg = await read_message(reader_into_server)
        assert msg is not None
        assert msg["method"] == "documentSymbol/test"
        reader_into_client.feed_data(
            encode_message({"jsonrpc": "2.0", "id": msg["id"], "result": [{"name": "X"}]})
        )

    server_task = asyncio.create_task(fake_server())
    result = await client.request("documentSymbol/test", {"q": 1})
    await server_task
    assert result == [{"name": "X"}]
    await client.close()


@pytest.mark.asyncio
async def test_request_raises_on_error_response() -> None:
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )

    client = BslLspClient(reader_into_client, client_writer, request_timeout=2.0)
    await client.start()

    async def fake_server() -> None:
        msg = await read_message(reader_into_server)
        assert msg is not None
        reader_into_client.feed_data(
            encode_message(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32601, "message": "Method not found"},
                }
            )
        )

    server_task = asyncio.create_task(fake_server())
    with pytest.raises(LspError) as exc_info:
        await client.request("does/not/exist", None)
    await server_task
    assert exc_info.value.code == -32601
    assert "Method not found" in exc_info.value.message
    await client.close()


@pytest.mark.asyncio
async def test_concurrent_requests_correlated_by_id() -> None:
    """Two in-flight requests must each receive their own response."""
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )
    client = BslLspClient(reader_into_client, client_writer, request_timeout=2.0)
    await client.start()

    async def server_replier() -> None:
        # Read both incoming requests, reply in reverse order.
        first = await read_message(reader_into_server)
        second = await read_message(reader_into_server)
        assert first is not None and second is not None
        # Reply to second first.
        reader_into_client.feed_data(
            encode_message(
                {"jsonrpc": "2.0", "id": second["id"], "result": "second"}
            )
        )
        reader_into_client.feed_data(
            encode_message(
                {"jsonrpc": "2.0", "id": first["id"], "result": "first"}
            )
        )

    server_task = asyncio.create_task(server_replier())
    a, b = await asyncio.gather(
        client.request("a", None), client.request("b", None)
    )
    await server_task
    assert a == "first"
    assert b == "second"
    await client.close()


@pytest.mark.asyncio
async def test_request_times_out_when_server_silent() -> None:
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )
    client = BslLspClient(reader_into_client, client_writer, request_timeout=0.1)
    await client.start()
    with pytest.raises(LspError, match="timed out"):
        await client.request("hangs/forever", None)
    await client.close()


@pytest.mark.asyncio
async def test_close_fails_pending_requests() -> None:
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )
    client = BslLspClient(reader_into_client, client_writer, request_timeout=5.0)
    await client.start()

    async def request_then_close() -> None:
        # Give the request a tick to register, then close.
        await asyncio.sleep(0.01)
        await client.close()

    closer_task = asyncio.create_task(request_then_close())
    with pytest.raises(LspError, match="closed"):
        await client.request("never/responds", None)
    await closer_task


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notification_dispatches_to_handler() -> None:
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )
    client = BslLspClient(reader_into_client, client_writer, request_timeout=2.0)
    received: list[dict[str, Any]] = []

    async def handler(params: dict[str, Any]) -> None:
        received.append(params)

    client.on_notification("textDocument/publishDiagnostics", handler)
    await client.start()

    reader_into_client.feed_data(
        encode_message(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": "file:///a.bsl", "diagnostics": []},
            }
        )
    )
    # Yield so the read loop processes the message.
    await asyncio.sleep(0.05)
    assert received == [{"uri": "file:///a.bsl", "diagnostics": []}]
    await client.close()


@pytest.mark.asyncio
async def test_notification_handler_exception_does_not_break_loop() -> None:
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )
    client = BslLspClient(reader_into_client, client_writer, request_timeout=2.0)

    async def bad(_: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    seen: list[dict[str, Any]] = []

    async def good(params: dict[str, Any]) -> None:
        seen.append(params)

    client.on_notification("evt", bad)
    client.on_notification("evt", good)
    await client.start()

    reader_into_client.feed_data(
        encode_message(
            {"jsonrpc": "2.0", "method": "evt", "params": {"i": 1}}
        )
    )
    await asyncio.sleep(0.02)
    # Even though the first handler raised, the second still ran.
    assert seen == [{"i": 1}]
    await client.close()


# ---------------------------------------------------------------------------
# Initialize handshake
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_sends_initialize_then_initialized() -> None:
    reader_into_client = asyncio.StreamReader()
    reader_into_server = asyncio.StreamReader()
    client_writer = asyncio.StreamWriter(
        _LoopbackTransport(reader_into_server),
        asyncio.StreamReaderProtocol(reader_into_client),
        reader_into_client,
        asyncio.get_event_loop(),
    )
    client = BslLspClient(reader_into_client, client_writer, request_timeout=2.0)

    async def fake_server() -> None:
        init = await read_message(reader_into_server)
        assert init is not None
        assert init["method"] == "initialize"
        reader_into_client.feed_data(
            encode_message(
                {"jsonrpc": "2.0", "id": init["id"], "result": {"capabilities": {}}}
            )
        )
        # Next message must be the "initialized" notification (no id).
        notif = await read_message(reader_into_server)
        assert notif is not None
        assert notif["method"] == "initialized"
        assert "id" not in notif

    server_task = asyncio.create_task(fake_server())
    caps = await client.initialize(root_uri="file:///configs/uta")
    await server_task
    assert caps == {"capabilities": {}}
    assert client.is_initialized
    await client.close()
