"""
Local embedding client backed by sentence-transformers.

Activated when ``EmbeddingConfig.backend == "local"`` so users can run
semantic search over a 1С configuration without any cloud API key.
The model defaults to ``paraphrase-multilingual-MiniLM-L12-v2`` (384-dim,
multilingual incl. Russian, ~120 MB).

This client mirrors the public surface of ``EmbeddingClient`` so the
engine can swap implementations transparently.
"""

from __future__ import annotations

import asyncio

from mcp_1c.config import EmbeddingConfig
from mcp_1c.engines.embeddings.client import EmbeddingClientError
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class LocalEmbeddingClient:
    """In-process embedding client using sentence-transformers.

    Heavy CPU work is offloaded to a thread (`asyncio.to_thread`) so the
    event loop stays responsive while the model encodes batches.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._model = None  # lazy: load on first use to keep startup fast
        self._lock = asyncio.Lock()

    async def _ensure_model(self) -> None:
        if self._model is not None:
            return
        async with self._lock:
            if self._model is not None:
                return
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingClientError(
                    "Local embeddings backend requires `sentence-transformers`. "
                    "Install with: pip install -e \".[local-embeddings]\""
                ) from exc

            logger.info(f"Loading local embedding model: {self._config.model}")
            self._model = await asyncio.to_thread(
                SentenceTransformer, self._config.model
            )
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim != self._config.dimension:
                raise EmbeddingClientError(
                    f"Model {self._config.model} produces {actual_dim}-dim "
                    f"vectors but EmbeddingConfig.dimension={self._config.dimension}. "
                    "Set MCP_EMBEDDING_DIMENSION to match the model."
                )
            logger.info(f"Local embedding model ready ({actual_dim}-dim)")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            raise ValueError("texts list must not be empty")
        await self._ensure_model()
        assert self._model is not None
        vectors = await asyncio.to_thread(
            self._model.encode,
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    async def embed_single(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    async def embed_batched(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        batch_size = max(self._config.batch_size, 1)
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            out.extend(await self.embed(texts[i : i + batch_size]))
        return out

    async def close(self) -> None:
        """Drop the model so it can be garbage-collected."""
        self._model = None


def make_embedding_client(config: EmbeddingConfig):  # type: ignore[no-untyped-def]
    """Pick API or local client based on ``config.backend``."""
    if config.backend == "local":
        return LocalEmbeddingClient(config)
    from mcp_1c.engines.embeddings.client import EmbeddingClient

    return EmbeddingClient(config)
