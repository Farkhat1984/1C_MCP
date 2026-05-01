"""
HTTP client for the MCPBridge 1С extension.

The 1С side ships an extension `MCPBridge.cfe` exposing a small JSON
HTTP service:

  POST /query    — execute a 1С query, return JSON rows
  POST /eval     — evaluate a BSL fragment in a sandbox
  GET  /data     — fetch object by reference (type/name/guid)
  POST /method   — call an exported procedure of a CommonModule
  GET  /status   — health probe

Authentication: ``Authorization: Bearer <token>`` matching a constant
on the 1С side.

The client is intentionally thin: it serialises arguments, sends the
request, surfaces server errors as ``RuntimeClientError`` with HTTP
status. Domain logic stays in ``RuntimeEngine``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class RuntimeClientError(Exception):
    """Raised when the 1C HTTP service returns an error or the call fails."""

    def __init__(self, message: str, status: int = 0, payload: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload


class RuntimeClient:
    """Async HTTP client for the MCPBridge 1С extension."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._max_retries = max_retries
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._token}",
                },
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        session = await self._get_session()
        url = f"{self._base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                async with session.request(
                    method, url, params=params, json=json
                ) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        try:
                            payload = await resp.json(content_type=None)
                        except Exception:
                            payload = text
                        raise RuntimeClientError(
                            f"MCPBridge {resp.status}: {payload}",
                            status=resp.status,
                            payload=payload,
                        )
                    if not text:
                        return None
                    try:
                        return await resp.json(content_type=None)
                    except Exception:
                        return text
            except aiohttp.ClientError as exc:
                last_error = RuntimeClientError(f"Connection error: {exc}")
            except RuntimeClientError as exc:
                # 4xx responses are not retried; only 5xx
                if 500 <= exc.status < 600 and attempt < self._max_retries:
                    last_error = exc
                else:
                    raise
            if attempt < self._max_retries:
                await asyncio.sleep(0.5 * (2 ** attempt))

        raise last_error or RuntimeClientError("All retries exhausted")

    # Public surface -----------------------------------------------------
    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/status")

    async def query(
        self, query_text: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/query",
            json={"query": query_text, "parameters": parameters or {}},
        )

    async def eval_bsl(
        self, fragment: str, *, allow_writes: bool = False
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/eval",
            json={"fragment": fragment, "allow_writes": allow_writes},
        )

    async def get_data(
        self, type_: str, name: str, guid: str
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/data",
            params={"type": type_, "name": name, "guid": guid},
        )

    async def call_method(
        self,
        module: str,
        method: str,
        arguments: list[Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/method",
            json={"module": module, "method": method, "arguments": arguments or []},
        )
