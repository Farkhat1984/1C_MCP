"""Authentication and authorization layer.

Two parallel mechanisms in Phase 0/1:

- **Plain bearer** (legacy) — string compare via ``hmac.compare_digest``.
  Used by Phase 0 deployments that don't yet have a JWT issuer. The
  caller has effectively all scopes — this is documented and only safe
  for dev/single-tenant.
- **JWT bearer** (Phase 1+) — RS256/HS256-signed token with a ``scope``
  claim. Each tool declares the scope it needs; the call is authorised
  if the token's scope set is a superset.

Phase 2 web mode wires this into ``BearerAuthMiddleware``: if a token
parses as a JWT (header has the right shape and signature), use its
scopes; otherwise treat it as a plain bearer string.
"""

from mcp_1c.auth.context import current_identity, use_identity
from mcp_1c.auth.scopes import (
    ALL_SCOPES,
    Scope,
    ToolScopeMap,
    default_tool_scopes,
)
from mcp_1c.auth.token import (
    AuthIdentity,
    AuthVerifier,
    InvalidTokenError,
    JwtVerifier,
    PlainBearerVerifier,
)

__all__ = [
    "ALL_SCOPES",
    "AuthIdentity",
    "AuthVerifier",
    "InvalidTokenError",
    "JwtVerifier",
    "PlainBearerVerifier",
    "Scope",
    "ToolScopeMap",
    "current_identity",
    "default_tool_scopes",
    "use_identity",
]
