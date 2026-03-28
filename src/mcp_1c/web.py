"""
HTTP transport for MCP-1C server (Streamable HTTP).
"""

import argparse
import os
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from mcp_1c.server import create_server, shutdown_engines
from mcp_1c.utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


def create_app(host: str = "0.0.0.0", port: int = 8080) -> Starlette:
    """Create Starlette ASGI app with Streamable HTTP transport."""
    server, registry, prompt_registry = create_server()

    # Streamable HTTP transport (new standard)
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=False,
        stateless=False,
    )

    @asynccontextmanager
    async def lifespan(app):
        """Initialize on startup, cleanup on shutdown."""
        try:
            await registry.initialize()

            # Auto-initialize engines if MCP_CONFIG_PATH is set
            config_path = os.environ.get("MCP_CONFIG_PATH")
            if config_path:
                from pathlib import Path
                from mcp_1c.engines.metadata.engine import MetadataEngine
                from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine
                from mcp_1c.engines.embeddings.engine import EmbeddingEngine
                from mcp_1c.config import EmbeddingConfig

                logger.info(f"Auto-initializing with config: {config_path}")
                meta = MetadataEngine.get_instance()
                await meta.initialize(Path(config_path), watch=False)
                meta_stats = await meta.get_stats()
                logger.info(f"Metadata: {sum(meta_stats.values())} objects")

                from mcp_1c.tools.platform_tools import PlatformBaseTool
                platform = PlatformBaseTool.get_engine()
                await platform.initialize()
                logger.info("Platform engine initialized")

                kg = KnowledgeGraphEngine.get_instance()
                await kg.build(meta)
                kg_stats = await kg.get_stats()
                logger.info(f"Knowledge graph: {kg_stats['total_nodes']} nodes, {kg_stats['total_edges']} edges")

                emb_db = os.environ.get("MCP_EMBEDDINGS_DB")
                api_key = os.environ.get("DEEPINFRA_API_KEY") or os.environ.get("MCP_EMBEDDING_API_KEY")
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

    async def health(request):
        """Health check endpoint with optional tool metrics."""
        from mcp_1c.tools.base import tool_metrics

        data: dict[str, Any] = {"status": "ok", "server": "mcp-1c"}
        if request.query_params.get("metrics") == "1":
            data["tool_metrics"] = tool_metrics.get_stats()
        return JSONResponse(data)

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/mcp", StreamableHTTPApp(), methods=["GET", "POST", "DELETE"]),
        ],
    )

    return app


def main():
    """Entry point for HTTP server."""
    parser = argparse.ArgumentParser(description="MCP-1C HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    args = parser.parse_args()

    level = os.environ.get("MCP_LOG_LEVEL", "INFO")
    setup_logging(level=level)
    logger.info(f"Starting MCP-1C server on {args.host}:{args.port}")

    import uvicorn

    app = create_app(args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
