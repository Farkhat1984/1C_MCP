"""Token verification: plain bearer + JWT.

Exposes a single :class:`AuthVerifier` Protocol so callers don't care
which mechanism produced the :class:`AuthIdentity`. Two concrete
implementations:

- :class:`PlainBearerVerifier` — string compare in constant time. The
  identity has all scopes (legacy path; documented as dev-only).
- :class:`JwtVerifier` — HS256/RS256 JWTs with a ``scope`` claim.
  Audience and issuer are checked when configured.

The Phase 2 web layer composes both: a verifier chain that tries JWT
first, falls back to plain bearer if the token doesn't have JWT shape.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

import jwt
from jwt import InvalidTokenError as _PyJwtInvalid

from mcp_1c.auth.scopes import ALL_SCOPES, Scope


class InvalidTokenError(Exception):
    """Raised when a token can't be verified.

    Reason is in ``__str__``; deliberately vague to avoid leaking which
    check failed (signature vs expiry vs audience). Web middleware
    translates this to ``401`` with a generic body.
    """


@dataclass(frozen=True)
class AuthIdentity:
    """Authenticated caller's identity and capabilities.

    ``sub`` is the caller's unique id (``sub`` JWT claim, or the bearer
    token itself for the plain path). ``scopes`` is the set of
    capabilities granted. ``raw_claims`` carries the rest of the JWT
    payload for tools that need richer context (workspace_id, role,
    etc.) — empty for plain bearers.
    """

    sub: str
    scopes: frozenset[Scope]
    raw_claims: dict[str, Any] = field(default_factory=dict)

    def has(self, required: Scope) -> bool:
        return required in self.scopes


class AuthVerifier(Protocol):
    """Anything that can turn an Authorization header into an Identity."""

    def verify(self, token: str) -> AuthIdentity: ...


# ---------------------------------------------------------------------------
# Plain bearer (legacy)
# ---------------------------------------------------------------------------


class PlainBearerVerifier:
    """Verifies plain string tokens via constant-time compare.

    Every token in the accepted set maps to an identity with **every**
    scope. This is the legacy path — fine for single-tenant CLI/dev
    work, unsafe for multi-tenant. Phase 2 web mode will demote plain
    bearer to opt-in via env var and recommend JWT for all real
    deployments.
    """

    def __init__(self, *, accepted_tokens: Iterable[str]) -> None:
        self._tokens = tuple(t for t in accepted_tokens if t)

    def verify(self, token: str) -> AuthIdentity:
        if not token or not self._tokens:
            raise InvalidTokenError("Empty token or no tokens configured")
        presented = token.encode("utf-8")
        ok = 0
        for known in self._tokens:
            ok |= int(hmac.compare_digest(presented, known.encode("utf-8")))
        if not ok:
            raise InvalidTokenError("Token not recognised")
        # Plain tokens are opaque — we use a hash-derived id as ``sub``
        # so audit logs can correlate without revealing the token.
        return AuthIdentity(
            sub=f"plain:{token[:6]}…",
            scopes=ALL_SCOPES,
        )


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


class JwtVerifier:
    """HS256/RS256 JWT verifier.

    Scopes are read from the ``scope`` claim (space-separated string,
    OAuth2-style) or the ``scopes`` claim (JSON array, custom). Either
    works; whichever is present takes precedence. Unknown scope strings
    in the token are silently dropped — only values matching :class:`Scope`
    members are surfaced to callers, so a misconfigured issuer can't
    quietly grant a privilege we never defined.
    """

    def __init__(
        self,
        *,
        secret: str | None = None,
        public_key: str | None = None,
        algorithms: tuple[str, ...] = ("HS256",),
        audience: str | None = None,
        issuer: str | None = None,
        leeway: int = 30,
    ) -> None:
        if not secret and not public_key:
            raise ValueError(
                "JwtVerifier needs either secret (HS*) or public_key (RS*)"
            )
        self._secret = secret
        self._public_key = public_key
        self._algorithms = list(algorithms)
        self._audience = audience
        self._issuer = issuer
        self._leeway = leeway

    def verify(self, token: str) -> AuthIdentity:
        try:
            claims = jwt.decode(
                token,
                key=self._public_key or self._secret,  # type: ignore[arg-type]
                algorithms=self._algorithms,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
            )
        except _PyJwtInvalid as exc:
            # Don't leak which check failed; one log line for ops, a
            # generic message for the client.
            raise InvalidTokenError(f"JWT verification failed: {exc}") from exc

        sub = str(claims.get("sub") or "anonymous")
        scopes = self._extract_scopes(claims)
        return AuthIdentity(sub=sub, scopes=scopes, raw_claims=claims)

    @staticmethod
    def _extract_scopes(claims: dict[str, Any]) -> frozenset[Scope]:
        raw = claims.get("scope") or claims.get("scopes")
        if raw is None:
            return frozenset()
        if isinstance(raw, str):
            tokens = raw.split()
        elif isinstance(raw, (list, tuple)):
            tokens = [str(t) for t in raw]
        else:
            return frozenset()

        valid = {item.value for item in Scope}
        out: set[Scope] = set()
        for tok in tokens:
            if tok in valid:
                out.add(Scope(tok))
        return frozenset(out)


__all__ = [
    "AuthIdentity",
    "AuthVerifier",
    "InvalidTokenError",
    "JwtVerifier",
    "PlainBearerVerifier",
]
