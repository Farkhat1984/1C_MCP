"""Per-request identity carried via ``ContextVar``.

The MCP transport sits several asyncio layers between Starlette
middleware (where we verify the token) and the BaseTool (where we want
to enforce the scope). Passing the identity through every signature
would touch every tool; a ``ContextVar`` instead is invisible to
existing code and respects asyncio's per-task copying semantics.

Web middleware sets ``current_identity`` after verifying a JWT;
``BaseTool.run`` reads it. When unset (stdio mode, dev, legacy plain
bearer) the value is ``None`` — callers that need a strict mode should
fail-closed explicitly, but the default is permissive so we don't
break the existing CLI workflow.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from mcp_1c.auth.token import AuthIdentity

current_identity: ContextVar[AuthIdentity | None] = ContextVar(
    "mcp_1c.current_identity", default=None
)


@contextmanager
def use_identity(identity: AuthIdentity | None) -> Iterator[None]:
    """Bind ``identity`` for the duration of the ``with`` block.

    Tests can use this to assert that a tool call is forbidden when
    the active identity lacks the required scope. Web middleware does
    the same via direct ``set`` / ``reset`` for proper async lifecycle.
    """
    token: Token[AuthIdentity | None] = current_identity.set(identity)
    try:
        yield
    finally:
        current_identity.reset(token)


__all__ = ["current_identity", "use_identity"]
