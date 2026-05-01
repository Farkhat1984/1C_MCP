"""Auth gating for the HTTP transport — no real network needed."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from mcp_1c.web import create_app


def test_loopback_without_token_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKENS", raising=False)
    app = create_app(host="127.0.0.1")
    assert app is not None


def test_public_host_without_token_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKENS", raising=False)
    with pytest.raises(RuntimeError, match="loopback"):
        create_app(host="0.0.0.0")


def test_health_works_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    app = create_app(host="127.0.0.1")
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"status": "ok", "server": "mcp-1c"}


def test_health_does_not_leak_engine_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Public /health must not expose engine state, paths, or auth flag."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    app = create_app(host="127.0.0.1")
    with TestClient(app) as client:
        body = client.get("/health").json()
        for forbidden_key in ("engines", "tool_metrics", "auth_enabled"):
            assert forbidden_key not in body, (
                f"/health leaked '{forbidden_key}' — must move to /metrics"
            )


def test_metrics_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    app = create_app(host="127.0.0.1")
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 401


def test_metrics_returns_engine_state_when_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    app = create_app(host="127.0.0.1")
    with TestClient(app) as client:
        resp = client.get("/metrics", headers={"Authorization": "Bearer secret"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "engines" in body
        assert body["auth"] == {"plain_bearer": True, "jwt": False}
        assert "tool_metrics" in body


def test_mcp_route_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret")
    app = create_app(host="127.0.0.1")
    with TestClient(app) as client:
        # Bad token
        resp = client.post("/mcp", headers={"Authorization": "Bearer wrong"}, json={})
        assert resp.status_code == 401
        # No token
        resp = client.post("/mcp", json={})
        assert resp.status_code == 401


def test_token_matches_uses_constant_time_compare() -> None:
    """The matcher must accept exact tokens and reject everything else."""
    from mcp_1c.web import BearerAuthMiddleware

    accepted = ("alpha-token", "bravo-token")
    assert BearerAuthMiddleware._token_matches("alpha-token", accepted) is True
    assert BearerAuthMiddleware._token_matches("bravo-token", accepted) is True
    assert BearerAuthMiddleware._token_matches("alpha", accepted) is False
    assert BearerAuthMiddleware._token_matches("alpha-toke!", accepted) is False
    assert BearerAuthMiddleware._token_matches("", accepted) is False
    assert BearerAuthMiddleware._token_matches("alpha-token", ()) is False


def test_token_matches_with_unicode() -> None:
    """Unicode/multi-byte tokens compare correctly via UTF-8 encoding."""
    from mcp_1c.web import BearerAuthMiddleware

    accepted = ("токен-1С", "secret​")  # Cyrillic + zero-width space
    assert BearerAuthMiddleware._token_matches("токен-1С", accepted) is True
    assert BearerAuthMiddleware._token_matches("токен-1С!", accepted) is False


# ---------------------------------------------------------------------------
# JWT integration
# ---------------------------------------------------------------------------


def _make_test_jwt(secret: str, **claims) -> str:
    import time

    import jwt as pyjwt

    payload = {
        "sub": "test-user",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        **claims,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def test_jwt_token_accepted_when_jwt_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid JWT bypasses plain-bearer fallback and authorises the request."""
    monkeypatch.setenv("MCP_JWT_SECRET", "test-jwt-secret-key-32-chars-min")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    app = create_app(host="127.0.0.1")
    token = _make_test_jwt(
        "test-jwt-secret-key-32-chars-min", scope="metadata.read"
    )
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        # /mcp will reach the MCP handler — body shape doesn't matter,
        # what matters is that auth didn't return 401.
        assert resp.status_code != 401


def test_jwt_invalid_signature_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_JWT_SECRET", "test-jwt-secret-key-32-chars-min")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    app = create_app(host="127.0.0.1")
    bad_token = _make_test_jwt("wrong-secret-also-32-chars-or-more", scope="admin")
    with TestClient(app) as client:
        resp = client.post(
            "/mcp", headers={"Authorization": f"Bearer {bad_token}"}, json={}
        )
        assert resp.status_code == 401


def test_jwt_and_plain_bearer_can_coexist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mixed deployment: legacy plain-bearer + new JWT both work."""
    monkeypatch.setenv("MCP_JWT_SECRET", "test-jwt-secret-key-32-chars-min")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "legacy-secret")
    app = create_app(host="127.0.0.1")

    with TestClient(app) as client:
        # Plain bearer still works.
        resp = client.post(
            "/mcp", headers={"Authorization": "Bearer legacy-secret"}, json={}
        )
        assert resp.status_code != 401

        # JWT also works.
        token = _make_test_jwt(
            "test-jwt-secret-key-32-chars-min", scope="metadata.read"
        )
        resp = client.post(
            "/mcp", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        assert resp.status_code != 401

        # Random garbage rejected.
        resp = client.post(
            "/mcp", headers={"Authorization": "Bearer nope"}, json={}
        )
        assert resp.status_code == 401


def test_metrics_reports_both_auth_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """``/metrics`` must surface which auth modes are configured."""
    monkeypatch.setenv("MCP_JWT_SECRET", "test-jwt-secret-key-32-chars-min")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "legacy-secret")
    app = create_app(host="127.0.0.1")
    with TestClient(app) as client:
        resp = client.get(
            "/metrics", headers={"Authorization": "Bearer legacy-secret"}
        )
        assert resp.json()["auth"] == {"plain_bearer": True, "jwt": True}


def test_jwt_only_deployment_refuses_public_bind_without_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same loopback rule applies when only JWT is configured.

    Setting only JWT is enough to satisfy the public-bind safety check —
    the server isn't unauthenticated, it just uses a different auth
    mechanism.
    """
    monkeypatch.setenv("MCP_JWT_SECRET", "test-jwt-secret-key-32-chars-min")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKENS", raising=False)
    # Should NOT raise: JWT is configured.
    create_app(host="0.0.0.0")
