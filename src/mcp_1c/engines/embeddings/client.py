"""
Async client for embeddings API (OpenAI-compatible endpoint).

Supports DeepInfra and any OpenAI-compatible embeddings service.
Uses aiohttp for non-blocking HTTP calls with retry logic.
"""

from __future__ import annotations

import asyncio

import aiohttp

from mcp_1c.config import EmbeddingConfig
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingClientError(Exception):
    """Raised when the embeddings API returns an error."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class EmbeddingClient:
    """Async client for OpenAI-compatible embeddings API.

    Handles batching, retries with exponential backoff,
    concurrency limiting via semaphore, and session lifecycle management.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the HTTP session."""
        needs_new = (
            self._session is None
            or self._session.closed
            or self._session._loop.is_closed()  # type: ignore[attr-defined]
        )
        if needs_new:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._config.api_key}",
                },
                timeout=aiohttp.ClientTimeout(total=self._config.timeout),
            )
        return self._session

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text,
            in the same order as the input.

        Raises:
            EmbeddingClientError: If the API returns an error after all retries.
            ValueError: If texts list is empty.
        """
        if not texts:
            raise ValueError("texts list must not be empty")

        session = await self._get_session()
        payload = {
            "input": texts,
            "model": self._config.model,
            "encoding_format": "float",
        }

        last_error: Exception | None = None
        async with self._semaphore:
            for attempt in range(self._config.max_retries):
                try:
                    async with session.post(self._config.api_url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # Sort by index to guarantee input order
                            sorted_data = sorted(data["data"], key=lambda x: x["index"])
                            return [item["embedding"] for item in sorted_data]

                        error_text = await resp.text()
                        last_error = EmbeddingClientError(
                            f"Embedding API error {resp.status}: {error_text}",
                            status_code=resp.status,
                        )

                        # Don't retry on client errors (4xx) except 429 (rate limit)
                        if 400 <= resp.status < 500 and resp.status != 429:
                            raise last_error

                except aiohttp.ClientError as exc:
                    last_error = EmbeddingClientError(f"Connection error: {exc}")

                # Exponential backoff with jitter
                if attempt < self._config.max_retries - 1:
                    delay = min(2**attempt * 0.5, 10.0)
                    logger.warning(
                        f"Embedding API attempt {attempt + 1} failed, "
                        f"retrying in {delay:.1f}s: {last_error}"
                    )
                    await asyncio.sleep(delay)

        raise last_error or EmbeddingClientError("All retry attempts exhausted")

    async def embed_single(self, text: str) -> list[float]:
        """Get embedding for a single text.

        Args:
            text: Text string to embed.

        Returns:
            Embedding vector.
        """
        results = await self.embed([text])
        return results[0]

    async def embed_batched(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in sequential batches to bound memory usage.

        Processes one batch at a time to avoid accumulating all embedding
        vectors in memory simultaneously.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors in input order.
        """
        if not texts:
            return []

        batch_size = self._config.batch_size
        batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]

        if len(batches) == 1:
            return await self.embed(batches[0])

        all_embeddings: list[list[float]] = []
        for idx, batch in enumerate(batches):
            result = await self.embed(batch)
            logger.debug(f"Embedded batch {idx + 1}/{len(batches)} ({len(batch)} texts)")
            all_embeddings.extend(result)
        return all_embeddings

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
