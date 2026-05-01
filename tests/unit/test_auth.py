"""Auth/scopes layer — verifies tokens, maps tools to scopes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from mcp_1c.auth.scopes import (
    ALL_SCOPES,
    Scope,
    default_tool_scopes,
)
from mcp_1c.auth.token import (
    AuthIdentity,
    InvalidTokenError,
    JwtVerifier,
    PlainBearerVerifier,
)

# ---------------------------------------------------------------------------
# Scope mapping
# ---------------------------------------------------------------------------


def test_default_scope_map_covers_known_tools() -> None:
    """Every entry must be a real Scope, no typos."""
    mapping = default_tool_scopes()
    assert mapping
    for tool, scope in mapping.items():
        assert isinstance(scope, Scope), f"{tool} → {scope!r} not a Scope"


def test_runtime_method_requires_runtime_write() -> None:
    """Mutating runtime tool must not be reachable with read-only scope."""
    mapping = default_tool_scopes()
    assert mapping["runtime-method"] == Scope.RUNTIME_WRITE


def test_metadata_init_is_admin_scope() -> None:
    """Reindexing is operational — should require admin."""
    assert default_tool_scopes()["metadata-init"] == Scope.ADMIN


def test_smart_tools_require_code_write() -> None:
    """Generators must not be reachable from a metadata.read-only token."""
    mapping = default_tool_scopes()
    for tool in ("smart-query", "smart-print", "smart-movement"):
        assert mapping[tool] == Scope.CODE_WRITE


# ---------------------------------------------------------------------------
# Plain bearer
# ---------------------------------------------------------------------------


def test_plain_bearer_accepts_known_token() -> None:
    verifier = PlainBearerVerifier(accepted_tokens=["secret-1", "secret-2"])
    identity = verifier.verify("secret-2")
    assert identity.scopes == ALL_SCOPES
    assert "plain:" in identity.sub


def test_plain_bearer_rejects_unknown_token() -> None:
    verifier = PlainBearerVerifier(accepted_tokens=["secret-1"])
    with pytest.raises(InvalidTokenError):
        verifier.verify("totally-different")


def test_plain_bearer_rejects_empty_string() -> None:
    verifier = PlainBearerVerifier(accepted_tokens=["secret-1"])
    with pytest.raises(InvalidTokenError):
        verifier.verify("")


def test_plain_bearer_with_no_configured_tokens_rejects_all() -> None:
    verifier = PlainBearerVerifier(accepted_tokens=[])
    with pytest.raises(InvalidTokenError):
        verifier.verify("anything")


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def _make_jwt(
    secret: str,
    *,
    sub: str = "alice",
    scopes: list[str] | str | None = None,
    audience: str | None = None,
    issuer: str | None = None,
    expires_in: int = 3600,
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(UTC)
    claims: dict = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    if scopes is not None:
        claims["scope" if isinstance(scopes, str) else "scopes"] = scopes
    if audience is not None:
        claims["aud"] = audience
    if issuer is not None:
        claims["iss"] = issuer
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, secret, algorithm="HS256")


def test_jwt_verifier_extracts_scopes_from_space_string() -> None:
    """OAuth2 ``scope`` claim is space-separated."""
    verifier = JwtVerifier(secret="s3cret")
    token = _make_jwt("s3cret", scopes="metadata.read code.read")
    identity = verifier.verify(token)
    assert identity.scopes == frozenset({Scope.METADATA_READ, Scope.CODE_READ})


def test_jwt_verifier_extracts_scopes_from_list() -> None:
    """Custom ``scopes`` claim as JSON array — both styles work."""
    verifier = JwtVerifier(secret="s3cret")
    token = _make_jwt("s3cret", scopes=["runtime.read", "admin"])
    identity = verifier.verify(token)
    assert identity.scopes == frozenset({Scope.RUNTIME_READ, Scope.ADMIN})


def test_jwt_verifier_drops_unknown_scopes() -> None:
    """A misconfigured issuer that emits ``superuser`` must not silently
    grant a privilege we never defined."""
    verifier = JwtVerifier(secret="s3cret")
    token = _make_jwt("s3cret", scopes="superuser metadata.read")
    identity = verifier.verify(token)
    assert identity.scopes == frozenset({Scope.METADATA_READ})


def test_jwt_verifier_rejects_bad_signature() -> None:
    verifier = JwtVerifier(secret="real-secret")
    bad_token = _make_jwt("attacker-secret", scopes="admin")
    with pytest.raises(InvalidTokenError):
        verifier.verify(bad_token)


def test_jwt_verifier_rejects_expired_token() -> None:
    verifier = JwtVerifier(secret="s3cret", leeway=0)
    expired = _make_jwt("s3cret", expires_in=-10)
    with pytest.raises(InvalidTokenError):
        verifier.verify(expired)


def test_jwt_verifier_enforces_audience_when_configured() -> None:
    verifier = JwtVerifier(secret="s3cret", audience="mcp-1c")
    correct = _make_jwt("s3cret", audience="mcp-1c", scopes="metadata.read")
    wrong = _make_jwt("s3cret", audience="other-service", scopes="metadata.read")

    assert verifier.verify(correct).has(Scope.METADATA_READ)
    with pytest.raises(InvalidTokenError):
        verifier.verify(wrong)


def test_jwt_verifier_enforces_issuer_when_configured() -> None:
    verifier = JwtVerifier(secret="s3cret", issuer="https://issuer.example")
    correct = _make_jwt(
        "s3cret", issuer="https://issuer.example", scopes="metadata.read"
    )
    wrong = _make_jwt(
        "s3cret", issuer="https://elsewhere.example", scopes="metadata.read"
    )

    assert verifier.verify(correct).has(Scope.METADATA_READ)
    with pytest.raises(InvalidTokenError):
        verifier.verify(wrong)


def test_jwt_verifier_includes_raw_claims() -> None:
    verifier = JwtVerifier(secret="s3cret")
    token = _make_jwt(
        "s3cret",
        scopes="metadata.read",
        extra_claims={"workspace_id": "ws-uta", "role": "developer"},
    )
    identity = verifier.verify(token)
    assert identity.raw_claims["workspace_id"] == "ws-uta"
    assert identity.raw_claims["role"] == "developer"


def test_jwt_verifier_rejects_token_without_scopes_silently() -> None:
    """A token with no scope claim is valid but powerless — verifier
    returns identity with empty scope set, caller decides what to do."""
    verifier = JwtVerifier(secret="s3cret")
    token = _make_jwt("s3cret", scopes=None)
    identity = verifier.verify(token)
    assert identity.scopes == frozenset()


def test_jwt_verifier_requires_secret_or_public_key() -> None:
    with pytest.raises(ValueError, match="secret"):
        JwtVerifier()


# ---------------------------------------------------------------------------
# AuthIdentity
# ---------------------------------------------------------------------------


def test_identity_has_checks_membership() -> None:
    identity = AuthIdentity(
        sub="alice", scopes=frozenset({Scope.METADATA_READ})
    )
    assert identity.has(Scope.METADATA_READ)
    assert not identity.has(Scope.RUNTIME_WRITE)
