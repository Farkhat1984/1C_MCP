"""LSP integration with bsl-language-server.

Persistent JSON-RPC client over stdio. One BSL-LS subprocess per
workspace, reused across tool calls — replaces the per-invocation
``--analyze`` CLI flow in :mod:`mcp_1c.engines.code.bsl_ls`.

Public surface:

- :class:`BslLspClient` — async LSP client (initialize / didOpen / shutdown,
  documentSymbol, references, definition, diagnostics).
- :class:`BslLspServerManager` — JVM subprocess lifecycle (auto-start,
  health check, restart on crash).
- :class:`DocumentSymbolCache` — hash-keyed cache for documentSymbol
  responses, shared across engines.

Failure mode: if bsl-language-server is not configured or fails to
start, callers must fall back to the legacy regex parser. The client
exposes :attr:`BslLspClient.is_available` for that branch.
"""

from mcp_1c.engines.code.lsp.adapter import lsp_symbols_to_procedures
from mcp_1c.engines.code.lsp.cache import DocumentSymbolCache
from mcp_1c.engines.code.lsp.client import BslLspClient, LspError
from mcp_1c.engines.code.lsp.server_manager import (
    BslLspServerManager,
    BslLspUnavailable,
)

__all__ = [
    "BslLspClient",
    "BslLspServerManager",
    "BslLspUnavailable",
    "DocumentSymbolCache",
    "LspError",
    "lsp_symbols_to_procedures",
]
