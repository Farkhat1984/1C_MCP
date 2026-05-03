"""
HTTP transport for MCP-1C server (Streamable HTTP).

Two parallel auth mechanisms supported:

- **Plain bearer** (legacy): ``MCP_AUTH_TOKEN`` (or comma-separated
  ``MCP_AUTH_TOKENS``). Constant-time compare. Caller has all scopes.
  When neither is set, the server **refuses** to bind to a non-loopback
  host so a misconfigured deploy cannot expose tools without auth.

- **JWT** (production): set ``MCP_JWT_SECRET`` (HS256) or
  ``MCP_JWT_PUBLIC_KEY`` (RS256) plus optional ``MCP_JWT_AUDIENCE`` /
  ``MCP_JWT_ISSUER``. The middleware tries JWT first; if the token
  isn't a valid JWT, falls back to plain bearer (so a single deploy
  can run both). Verified identity is bound to the request via
  :func:`mcp_1c.auth.use_identity`; ``BaseTool._check_scope`` enforces
  the per-tool scope from there.
"""

from __future__ import annotations

import argparse
import hmac
import os
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from mcp_1c.auth import (
    AuthVerifier,
    InvalidTokenError,
    JwtVerifier,
    PlainBearerVerifier,
    current_identity,
)
from mcp_1c.server import create_server, shutdown_engines
from mcp_1c.utils.logger import get_logger, setup_logging
from mcp_1c.utils.observability import (
    PROMETHEUS_CONTENT_TYPE,
    ObservabilityConfig,
    init_observability,
    is_prometheus_enabled,
    render_prometheus_text,
)

logger = get_logger(__name__)


def _load_auth_tokens() -> set[str]:
    """Read accepted bearer tokens from env."""
    tokens: set[str] = set()
    primary = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if primary:
        tokens.add(primary)
    extras = os.environ.get("MCP_AUTH_TOKENS", "")
    for raw in extras.split(","):
        t = raw.strip()
        if t:
            tokens.add(t)
    return tokens


def _looks_like_jwt(token: str) -> bool:
    """Cheap shape check: three base64url segments separated by ``.``.

    No verification — that's the verifier's job. We use this only to
    decide which verifier gets first crack at the token, so a regular
    plain bearer that happens to contain dots doesn't trigger an
    expensive JWT decode attempt.
    """
    parts = token.split(".")
    return len(parts) == 3 and all(p for p in parts)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Authorize requests via JWT first, plain-bearer fallback.

    ``/health`` is whitelisted so monitoring works without a token.
    Plain-bearer tokens use :func:`hmac.compare_digest` so rejection
    time is independent of which character mismatched — defends against
    token-discovery timing attacks. JWTs are verified with the configured
    :class:`JwtVerifier`; on success, ``current_identity`` is bound for
    the duration of the request, and ``BaseTool._check_scope`` enforces
    the per-tool scope from there.

    Why try JWT first instead of plain? In a deployment that's
    transitioning from plain to JWT, the operator can leave both
    configured; new clients get scope enforcement, legacy clients keep
    working with full scope. Removing the plain fallback later is a
    single env-var change.
    """

    PUBLIC_PATHS = {"/health"}

    def __init__(
        self,
        app,
        *,
        plain: PlainBearerVerifier | None = None,
        jwt: JwtVerifier | None = None,
    ) -> None:
        super().__init__(app)
        self._plain = plain
        self._jwt = jwt

    @staticmethod
    def _token_matches(presented: str, accepted: tuple[str, ...]) -> bool:
        """Constant-time legacy compare.

        Kept as a static helper so existing tests can target it
        directly. The middleware itself now goes through
        :class:`PlainBearerVerifier`, which calls into the same
        primitive.
        """
        ok = 0
        presented_bytes = presented.encode("utf-8")
        for known in accepted:
            ok |= int(hmac.compare_digest(presented_bytes, known.encode("utf-8")))
        return bool(ok)

    async def dispatch(self, request: Request, call_next):
        if self._plain is None and self._jwt is None:
            return await call_next(request)
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return JSONResponse({"error": "Missing bearer token"}, status_code=401)
        token = header[len("Bearer ") :].strip()

        identity = self._verify(token)
        if identity is None:
            return JSONResponse({"error": "Invalid token"}, status_code=401)

        # Bind identity for the duration of this request. Reset
        # restores whatever was there before — important when a single
        # process handles many concurrent requests.
        token_var = current_identity.set(identity)
        try:
            return await call_next(request)
        finally:
            current_identity.reset(token_var)

    def _verify(self, token: str) -> Any | None:
        """Try every configured verifier in order; first hit wins.

        Returns ``None`` if no verifier accepts the token. Errors from
        individual verifiers are swallowed (it's normal for plain-bearer
        verification to fail when the token is actually a JWT and vice
        versa); only the final no-match outcome surfaces to the caller.
        """
        verifiers: list[AuthVerifier] = []
        # JWT only when the token has the right shape — otherwise we'd
        # spend a public-key verification on every plain-bearer attempt.
        if self._jwt is not None and _looks_like_jwt(token):
            verifiers.append(self._jwt)
        if self._plain is not None:
            verifiers.append(self._plain)

        for verifier in verifiers:
            try:
                return verifier.verify(token)
            except InvalidTokenError:
                continue
        return None


def _build_jwt_verifier_from_env() -> JwtVerifier | None:
    """Construct a ``JwtVerifier`` from environment variables, if configured.

    Recognised:

    - ``MCP_JWT_SECRET`` — symmetric key for HS256.
    - ``MCP_JWT_PUBLIC_KEY`` — PEM public key for RS256/ES256.
    - ``MCP_JWT_ALGORITHMS`` — comma-separated allowed algs (default
      depends on which key is set).
    - ``MCP_JWT_AUDIENCE``, ``MCP_JWT_ISSUER`` — optional claim
      enforcement.

    Returns ``None`` when neither secret nor public key is configured;
    deployments that don't want JWT just don't set them.
    """
    secret = os.environ.get("MCP_JWT_SECRET", "").strip() or None
    public_key = os.environ.get("MCP_JWT_PUBLIC_KEY", "").strip() or None
    if not secret and not public_key:
        return None
    algs_raw = os.environ.get("MCP_JWT_ALGORITHMS", "").strip()
    if algs_raw:
        algorithms = tuple(a.strip() for a in algs_raw.split(",") if a.strip())
    elif public_key:
        algorithms = ("RS256",)
    else:
        algorithms = ("HS256",)
    return JwtVerifier(
        secret=secret,
        public_key=public_key,
        algorithms=algorithms,
        audience=os.environ.get("MCP_JWT_AUDIENCE", "").strip() or None,
        issuer=os.environ.get("MCP_JWT_ISSUER", "").strip() or None,
    )


def create_app(host: str = "127.0.0.1", port: int = 8080) -> Starlette:  # noqa: ARG001
    """Create Starlette ASGI app with Streamable HTTP transport.

    ``port`` is accepted for API symmetry — uvicorn binds the port
    itself; we just need ``host`` here for the loopback safety check.
    """
    # Boot observability before anything starts handling traffic so the
    # Prometheus collectors exist by the time the first tool call lands.
    # Idempotent — repeat calls (e.g. tests rebuilding the app) are
    # silently ignored. Default install with no env opt-in stays inert.
    init_observability(ObservabilityConfig.from_env())

    server, registry, prompt_registry = create_server()

    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=False,
        stateless=False,
    )

    auth_tokens = _load_auth_tokens()
    jwt_verifier = _build_jwt_verifier_from_env()

    if not auth_tokens and jwt_verifier is None and host not in (
        "127.0.0.1", "localhost", "::1",
    ):
        # Refuse to expose unauthenticated MCP on a public bind.
        raise RuntimeError(
            "Refusing to start: no MCP_AUTH_TOKEN and no MCP_JWT_SECRET/"
            "MCP_JWT_PUBLIC_KEY configured, and host is not loopback. "
            "Set one of those, or bind to 127.0.0.1."
        )
    if jwt_verifier is not None:
        logger.info("JWT auth enabled")
    if auth_tokens:
        logger.info(f"Plain bearer auth enabled ({len(auth_tokens)} token(s))")
    if not auth_tokens and jwt_verifier is None:
        logger.warning("No auth configured (loopback bind)")

    @asynccontextmanager
    async def lifespan(app):  # noqa: ARG001 — Starlette lifespan signature
        try:
            await registry.initialize()

            # Always initialize the platform engine — it loads from static
            # JSON bundled in the package (engines/platform/data/) and
            # never needs a 1C config path. Without this, platform-search
            # and platform-global_context return "Platform engine not
            # initialized" on deployments without MCP_CONFIG_PATH.
            from mcp_1c.tools.platform_tools import PlatformBaseTool

            platform = PlatformBaseTool.get_engine()
            await platform.initialize()
            logger.info("Platform engine initialized")

            config_path = os.environ.get("MCP_CONFIG_PATH")
            if config_path:
                from pathlib import Path

                from mcp_1c.config import EmbeddingConfig
                from mcp_1c.engines.embeddings.engine import EmbeddingEngine
                from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
                from mcp_1c.engines.metadata.engine import MetadataEngine

                logger.info(f"Auto-initializing with config: {config_path}")
                meta = MetadataEngine.get_instance()

                from mcp_1c.config import OverlayRoot

                overlays: list[OverlayRoot] = []
                overlay_env = os.environ.get("MCP_OVERLAY_PATHS", "").strip()
                if overlay_env:
                    for entry in overlay_env.split(","):
                        entry = entry.strip()
                        if not entry or "=" not in entry:
                            continue
                        name, raw_path = entry.split("=", 1)
                        overlays.append(
                            OverlayRoot(name=name.strip(), path=Path(raw_path.strip()))
                        )
                    logger.info(f"Configured {len(overlays)} overlay(s)")

                await meta.initialize(
                    Path(config_path),
                    watch=False,
                    overlay_roots=overlays or None,
                )
                meta_stats = await meta.get_stats()
                logger.info(f"Metadata: {sum(meta_stats.values())} objects")

                kg = KnowledgeGraphEngine.get_instance()
                # Reuse the persisted graph when it has code-level
                # edges. Rebuilding on every startup is expensive
                # (~10 minutes on a 9k-object config) and was silently
                # *erasing* procedure_call edges built by an earlier
                # graph.build call — auto-init was passed no
                # code_engine, so the rebuild produced a metadata-only
                # graph and overwrote the richer one in storage.
                from mcp_1c.engines.code import CodeEngine
                code_engine = CodeEngine.get_instance()
                rebuild_needed = True
                try:
                    await kg._load_or_fail()
                    stats = await kg.get_stats()
                    has_code_edges = bool(
                        stats.get("relationship_types", {}).get("procedure_call")
                    )
                    if has_code_edges:
                        rebuild_needed = False
                        logger.info(
                            f"Knowledge graph loaded from cache: "
                            f"{stats['total_nodes']} nodes, "
                            f"{stats['total_edges']} edges (with code edges)"
                        )
                except Exception:
                    pass
                if rebuild_needed:
                    logger.info(
                        "Building knowledge graph with code edges (one-time, ~10 min)"
                    )
                    await kg.build(meta, code_engine=code_engine)
                    kg_stats = await kg.get_stats()
                    logger.info(
                        f"Knowledge graph built: {kg_stats['total_nodes']} nodes, "
                        f"{kg_stats['total_edges']} edges"
                    )

                emb_db = os.environ.get("MCP_EMBEDDINGS_DB")
                if emb_db and Path(emb_db).exists():
                    config = EmbeddingConfig.from_env()
                    emb = EmbeddingEngine.get_instance()
                    await emb.initialize(config, Path(emb_db))
                    stats = await emb.get_stats()
                    logger.info(f"Embeddings: {stats.total_documents} documents")
                logger.info("All engines auto-initialized")

            async with session_manager.run():
                yield
        except Exception:
            logger.exception("Error during server lifespan")
            raise
        finally:
            await shutdown_engines()
            logger.info("MCP-1C server shutting down")

    class StreamableHTTPApp:
        async def __call__(self, scope, receive, send):
            await session_manager.handle_request(scope, receive, send)

    async def health(request: Request) -> Response:  # noqa: ARG001 — Starlette signature
        """Liveness probe — always 200 ok with no internal detail.

        Public endpoint by design: monitoring infra needs to reach this
        without credentials, and an unauthenticated probe must not leak
        engine state, configuration paths, or tool-call counters that
        could fingerprint the deployment.
        """
        return JSONResponse({"status": "ok", "server": "mcp-1c"})

    async def metrics(request: Request) -> Response:  # noqa: ARG001 — Starlette signature
        """Detailed server state and per-tool metrics (auth-gated).

        Two response shapes:

        - **Prometheus enabled** (``MCP_PROMETHEUS_ENABLED=true``):
          returns the text-exposition snapshot so a scraper can ingest
          it without translation. Engine state and JSON details are
          dropped — Prometheus has no place for them and ops scrape
          ``/health`` separately for liveness.
        - **JSON (default)**: same shape as before — engines, auth,
          and per-tool ``tool_metrics`` for human inspection. Kept for
          back-compat with existing callers.

        Either way, the route stays behind :class:`BearerAuthMiddleware`;
        Prometheus scrape configs need to present the same bearer token
        as any other authenticated client.
        """
        if is_prometheus_enabled():
            return Response(
                render_prometheus_text(),
                media_type=PROMETHEUS_CONTENT_TYPE,
            )

        from mcp_1c.engines.embeddings.engine import EmbeddingEngine
        from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
        from mcp_1c.engines.metadata.engine import MetadataEngine
        from mcp_1c.engines.runtime.engine import RuntimeEngine
        from mcp_1c.tools.base import tool_metrics

        meta = MetadataEngine.get_instance()
        kg = KnowledgeGraphEngine.get_instance()
        emb = EmbeddingEngine.get_instance()
        runtime = RuntimeEngine.get_instance()

        data: dict[str, Any] = {
            "status": "ok",
            "server": "mcp-1c",
            "engines": {
                "metadata": {
                    "initialized": meta.is_initialized,
                    "config_path": str(meta.config_path) if meta.config_path else None,
                },
                "knowledge_graph": {"built": getattr(kg, "_built", False)},
                "embeddings": {"initialized": emb.initialized},
                "runtime": {"configured": runtime.configured, "rw": runtime.allow_writes},
            },
            "auth": {
                "plain_bearer": bool(auth_tokens),
                "jwt": jwt_verifier is not None,
            },
            "tool_metrics": tool_metrics.get_stats(),
        }
        return JSONResponse(data)

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/metrics", metrics, methods=["GET"]),
            Route("/mcp", StreamableHTTPApp(), methods=["GET", "POST", "DELETE"]),
        ],
    )
    plain_verifier = (
        PlainBearerVerifier(accepted_tokens=auth_tokens) if auth_tokens else None
    )
    if plain_verifier is not None or jwt_verifier is not None:
        app.add_middleware(
            BearerAuthMiddleware,
            plain=plain_verifier,
            jwt=jwt_verifier,
        )
    return app


def main():
    """Entry point for HTTP server."""
    parser = argparse.ArgumentParser(description="MCP-1C HTTP Server")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Bind port (default: 8080)"
    )
    args = parser.parse_args()

    level = os.environ.get("MCP_LOG_LEVEL", "INFO")
    setup_logging(level=level)
    logger.info(f"Starting MCP-1C server on {args.host}:{args.port}")

    import uvicorn

    app = create_app(args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
