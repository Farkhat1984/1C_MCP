"""Scope definitions and tool→scope mapping.

Six scopes cover the surface today:

- ``metadata.read`` — list/get/search metadata, build KG, browse forms.
- ``code.read`` — read BSL modules, run static analysis (lint/format).
- ``code.write`` — generators that produce new code (smart-*, generate-*).
- ``runtime.read`` — query a live 1С base, read-only ``eval``, get_data.
- ``runtime.write`` — mutating ``eval`` / ``method`` calls.
- ``admin`` — server administration (``/metrics``, audit dump, workspace
  management).

Names follow the OAuth2 ``resource.action`` convention so they're
familiar to anyone who's wired RBAC before. The set is intentionally
small — finer granularity (per-tool scopes) creates a maintenance tax
that pays off only at scale we don't have yet.
"""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    """Authorization scope. ``StrEnum`` so values compare cleanly with
    raw strings from JWT claims (Python 3.11+)."""

    METADATA_READ = "metadata.read"
    CODE_READ = "code.read"
    CODE_WRITE = "code.write"
    RUNTIME_READ = "runtime.read"
    RUNTIME_WRITE = "runtime.write"
    ADMIN = "admin"


ALL_SCOPES: frozenset[Scope] = frozenset(Scope)

ToolScopeMap = dict[str, Scope]


def default_tool_scopes() -> ToolScopeMap:
    """Return the canonical tool→scope mapping.

    Tools not in this map default to ``metadata.read`` at the call site
    — that is the safest assumption for unrecognised names. Override
    individual entries per deployment by overlaying onto this dict.
    """
    return {
        # metadata.* — read-only browse / search
        "metadata-init": Scope.ADMIN,  # full reindex is operational
        "metadata-list": Scope.METADATA_READ,
        "metadata-get": Scope.METADATA_READ,
        "metadata-search": Scope.METADATA_READ,
        "config-objects": Scope.METADATA_READ,
        "config-roles": Scope.METADATA_READ,
        "config-role-rights": Scope.METADATA_READ,
        "config-compare": Scope.METADATA_READ,
        # graph / impact / analysis
        "graph-build": Scope.ADMIN,
        "graph-impact": Scope.METADATA_READ,
        "graph-related": Scope.METADATA_READ,
        "graph-stats": Scope.METADATA_READ,
        "graph-callers": Scope.METADATA_READ,
        "graph-callees": Scope.METADATA_READ,
        "graph-references": Scope.METADATA_READ,
        # code.* — read source, lint, format
        "code-module": Scope.CODE_READ,
        "code-procedure": Scope.CODE_READ,
        "code-dependencies": Scope.CODE_READ,
        "code-callgraph": Scope.CODE_READ,
        "code-validate": Scope.CODE_READ,
        "code-lint": Scope.CODE_READ,
        "code-format": Scope.CODE_READ,
        "code-complexity": Scope.CODE_READ,
        "code-deadcode": Scope.CODE_READ,
        # query / pattern (search-only)
        "query-validate": Scope.CODE_READ,
        "query-optimize": Scope.CODE_READ,
        "pattern-list": Scope.METADATA_READ,
        "pattern-apply": Scope.CODE_WRITE,
        "pattern-suggest": Scope.METADATA_READ,
        # template (MXL) — generation
        "template-get": Scope.METADATA_READ,
        "template-generate-fill-code": Scope.CODE_WRITE,
        "template-find": Scope.METADATA_READ,
        # platform reference
        "platform-search": Scope.METADATA_READ,
        "platform-global-context": Scope.METADATA_READ,
        # smart-* — code generation, all write
        "smart-query": Scope.CODE_WRITE,
        "smart-print": Scope.CODE_WRITE,
        "smart-movement": Scope.CODE_WRITE,
        # generate-* — template-based code generation
        "generate-query": Scope.CODE_WRITE,
        "generate-handler": Scope.CODE_WRITE,
        "generate-print": Scope.CODE_WRITE,
        "generate-movement": Scope.CODE_WRITE,
        "generate-api": Scope.CODE_WRITE,
        "generate-form-handler": Scope.CODE_WRITE,
        "generate-subscription": Scope.CODE_WRITE,
        "generate-scheduled-job": Scope.CODE_WRITE,
        # form / composition / extension introspection
        "form-get": Scope.METADATA_READ,
        "form-handlers": Scope.METADATA_READ,
        "form-attributes": Scope.METADATA_READ,
        "composition-get": Scope.METADATA_READ,
        "composition-fields": Scope.METADATA_READ,
        "composition-datasets": Scope.METADATA_READ,
        "composition-settings": Scope.METADATA_READ,
        "extension-list": Scope.METADATA_READ,
        "extension-objects": Scope.METADATA_READ,
        "extension-impact": Scope.METADATA_READ,
        # BSP knowledge — static / read-only
        "bsp-find": Scope.METADATA_READ,
        "bsp-hook": Scope.METADATA_READ,
        "bsp-modules": Scope.METADATA_READ,
        "bsp-review": Scope.CODE_READ,
        # embeddings — index is admin, search is read
        "embedding-index": Scope.ADMIN,
        "embedding-search": Scope.METADATA_READ,
        "embedding-similar": Scope.METADATA_READ,
        "embedding-stats": Scope.METADATA_READ,
        # runtime against live 1С base
        "runtime-status": Scope.RUNTIME_READ,
        "runtime-query": Scope.RUNTIME_READ,
        "runtime-data": Scope.RUNTIME_READ,
        "runtime-eval": Scope.RUNTIME_READ,  # default read-only; tool itself
                                             # checks `allow_writes` and may
                                             # raise without RUNTIME_WRITE.
        "runtime-method": Scope.RUNTIME_WRITE,
        # premium tools
        "configuration-diff": Scope.METADATA_READ,
        "test-data-generate": Scope.CODE_WRITE,
    }


__all__ = [
    "ALL_SCOPES",
    "Scope",
    "ToolScopeMap",
    "default_tool_scopes",
]
