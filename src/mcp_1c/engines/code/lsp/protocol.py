"""LSP wire-protocol primitives.

JSON-RPC 2.0 framed with ``Content-Length`` headers, as required by LSP.
Reading is structured around two awaitable streams: incoming bytes from
the BSL-LS process, outgoing bytes to it. This module owns nothing
above the message layer — request/response correlation lives in
``client.py``.

Frame format::

    Content-Length: 87\\r\\n
    \\r\\n
    { "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": ... }

References:
- https://microsoft.github.io/language-server-protocol/specification
"""

from __future__ import annotations

import json
from asyncio import StreamReader, StreamWriter
from typing import Any

JSONRPC_VERSION = "2.0"
_HEADER_TERMINATOR = b"\r\n"


def encode_message(payload: dict[str, Any]) -> bytes:
    """Encode a JSON-RPC message into the LSP wire format.

    Always serialises with ``ensure_ascii=False`` so cyrillic identifiers
    in 1С code travel as UTF-8 directly — bsl-language-server handles
    them natively, and ASCII-escaping would inflate every payload by ~6×.
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


async def write_message(writer: StreamWriter, payload: dict[str, Any]) -> None:
    """Write one JSON-RPC message and drain the buffer."""
    writer.write(encode_message(payload))
    await writer.drain()


async def read_message(reader: StreamReader) -> dict[str, Any] | None:
    """Read one JSON-RPC message from the stream.

    Returns ``None`` on EOF (server closed stdout) so callers can
    distinguish a graceful shutdown from a parse error. Raises
    :class:`LspProtocolError` on a malformed header or body — that
    is unrecoverable; caller should restart the process.
    """
    content_length: int | None = None

    # Read headers until blank line. Each header line ends in \r\n.
    while True:
        line = await reader.readline()
        if not line:
            return None  # EOF
        if line == _HEADER_TERMINATOR:
            break
        # Headers are ASCII per spec; tolerate trailing whitespace.
        try:
            decoded = line.decode("ascii").strip()
        except UnicodeDecodeError as exc:
            raise LspProtocolError(f"Non-ASCII header: {line!r}") from exc

        if not decoded:
            continue
        if ":" not in decoded:
            raise LspProtocolError(f"Malformed LSP header: {decoded!r}")
        name, _, value = decoded.partition(":")
        if name.strip().lower() == "content-length":
            try:
                content_length = int(value.strip())
            except ValueError as exc:
                raise LspProtocolError(
                    f"Invalid Content-Length: {value!r}"
                ) from exc

    if content_length is None:
        raise LspProtocolError("Missing Content-Length header")
    if content_length < 0 or content_length > _MAX_MESSAGE_BYTES:
        raise LspProtocolError(f"Content-Length out of range: {content_length}")

    body = await reader.readexactly(content_length)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise LspProtocolError(f"Malformed JSON body: {exc}") from exc


# Cap message size at 64 MiB. BSL-LS responses for full-config workspace
# symbols can be large but realistically stay under a few MiB; anything
# bigger likely indicates corruption or a malicious server.
_MAX_MESSAGE_BYTES = 64 * 1024 * 1024


class LspProtocolError(RuntimeError):
    """Raised when the LSP wire format is violated.

    Recovery is the caller's responsibility — typically by killing and
    restarting the BSL-LS subprocess. The exception carries a human-
    readable message suitable for logging.
    """


__all__ = [
    "JSONRPC_VERSION",
    "encode_message",
    "read_message",
    "write_message",
    "LspProtocolError",
]
