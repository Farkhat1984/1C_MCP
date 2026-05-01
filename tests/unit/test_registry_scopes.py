"""End-to-end RBAC: registry binds scopes, BaseTool enforces them.

The full pipeline is JWT → AuthIdentity → current_identity ContextVar
→ BaseTool._check_scope. Here we verify the registry side: scoped
tools come out of registration with ``required_scope`` set, and a
real (mocked) call respects it.
"""

from __future__ import annotations

import json

import pytest

from mcp_1c.auth import AuthIdentity, Scope, default_tool_scopes, use_identity
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def _reset_metadata_singleton() -> None:
    """Tools rely on MetadataEngine._instance — reset between tests."""
    MetadataEngine._instance = None
    yield
    MetadataEngine._instance = None


def test_registry_binds_scopes_from_default_map() -> None:
    """Every registered tool that has a scope mapping ends up scoped."""
    registry = ToolRegistry()
    expected = default_tool_scopes()
    for name, scope in expected.items():
        tool = registry.get(name)
        if tool is None:
            # Some defaults reference legacy names (graph.build vs
            # graph-build) — skip if not registered.
            continue
        assert tool.required_scope == scope, (
            f"{name} expected {scope}, got {tool.required_scope}"
        )


def test_runtime_eval_requires_runtime_read_minimum() -> None:
    registry = ToolRegistry()
    tool = registry.get("runtime-eval")
    if tool is None:
        pytest.skip("runtime-eval not registered in this build")
    assert tool.required_scope == Scope.RUNTIME_READ


def test_smart_query_requires_code_write() -> None:
    registry = ToolRegistry()
    tool = registry.get("smart-query")
    if tool is None:
        pytest.skip("smart-query not registered in this build")
    assert tool.required_scope == Scope.CODE_WRITE


@pytest.mark.asyncio
async def test_metadata_read_token_blocks_smart_query() -> None:
    """A read-only token must not be able to invoke a write-scoped tool."""
    registry = ToolRegistry()
    tool = registry.get("smart-query")
    if tool is None:
        pytest.skip("smart-query not registered in this build")

    read_only = AuthIdentity(sub="dev", scopes=frozenset({Scope.METADATA_READ}))
    with use_identity(read_only):
        # We don't care about argument validity — the scope check
        # fires before execute(), so even invalid args produce
        # FORBIDDEN, not a parameter error.
        result = await tool.run({})
    parsed = json.loads(result)
    assert parsed.get("error_code") == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_token_can_call_admin_scoped_tools() -> None:
    """An admin-scoped token reaches the body of an admin tool.

    Admin tools (graph-build, embedding-index, metadata-init) typically
    fail with NOT_INITIALIZED in this fixture — but that's *past*
    the scope check, which is what we want to confirm.
    """
    registry = ToolRegistry()
    tool = registry.get("graph.build") or registry.get("graph-build")
    if tool is None:
        pytest.skip("graph build tool not registered in this build")

    admin = AuthIdentity(
        sub="ops",
        scopes=frozenset({Scope.ADMIN, Scope.METADATA_READ}),
    )
    with use_identity(admin):
        result = await tool.run({})
    parsed = json.loads(result)
    # The scope check passed. Whatever happened next (validation,
    # initialization error) is not FORBIDDEN.
    assert parsed.get("error_code") != "FORBIDDEN"
