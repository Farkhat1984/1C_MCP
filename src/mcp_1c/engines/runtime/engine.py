"""
Runtime engine — high-level wrapper around the MCPBridge HTTP client.

Loads configuration from environment variables and applies safety
defaults: read-only mode unless ``MCP_RUNTIME_RW=true`` is set.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from mcp_1c.engines.runtime.client import RuntimeClient, RuntimeClientError
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


class RuntimeConfig(BaseModel):
    """Connection settings for the 1C MCPBridge HTTP service."""

    base_url: str = Field(default="", description="Base URL incl. /hs/mcp prefix")
    token: str = Field(default="", description="Bearer token")
    timeout: float = Field(default=30.0)
    allow_writes: bool = Field(
        default=False,
        description="Server-side eval/method calls may write to data",
    )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    @classmethod
    def from_env(cls) -> RuntimeConfig:
        return cls(
            base_url=os.environ.get("MCP_RUNTIME_BASE_URL", ""),
            token=os.environ.get("MCP_RUNTIME_TOKEN", ""),
            timeout=float(os.environ.get("MCP_RUNTIME_TIMEOUT", "30")),
            allow_writes=os.environ.get("MCP_RUNTIME_RW", "false").lower() == "true",
        )


class RuntimeEngine:
    """Singleton runtime engine. Lazily creates a RuntimeClient on first use."""

    _instance: RuntimeEngine | None = None

    @classmethod
    def get_instance(cls) -> RuntimeEngine:
        if cls._instance is None:
            cls._instance = RuntimeEngine()
        return cls._instance

    def __init__(self) -> None:
        self._config: RuntimeConfig | None = None
        self._client: RuntimeClient | None = None

    def _ensure_client(self) -> RuntimeClient:
        if self._config is None:
            self._config = RuntimeConfig.from_env()
        if not self._config.configured:
            raise RuntimeClientError(
                "Runtime backend not configured. Set MCP_RUNTIME_BASE_URL and "
                "MCP_RUNTIME_TOKEN to enable runtime tools.",
                status=400,
            )
        if self._client is None:
            self._client = RuntimeClient(
                self._config.base_url,
                self._config.token,
                timeout=self._config.timeout,
            )
        return self._client

    @property
    def configured(self) -> bool:
        cfg = self._config or RuntimeConfig.from_env()
        return cfg.configured

    @property
    def allow_writes(self) -> bool:
        cfg = self._config or RuntimeConfig.from_env()
        return cfg.allow_writes

    async def status(self) -> dict[str, Any]:
        client = self._ensure_client()
        return await client.status()

    async def query(
        self, query_text: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        client = self._ensure_client()
        return await client.query(query_text, parameters)

    async def eval_bsl(
        self, fragment: str, allow_writes: bool | None = None
    ) -> dict[str, Any]:
        client = self._ensure_client()
        flag = self.allow_writes if allow_writes is None else allow_writes
        if flag and not self.allow_writes:
            raise RuntimeClientError(
                "Write operations disabled. Set MCP_RUNTIME_RW=true to enable.",
                status=403,
            )
        return await client.eval_bsl(fragment, allow_writes=flag)

    async def get_data(
        self, type_: str, name: str, guid: str
    ) -> dict[str, Any]:
        client = self._ensure_client()
        return await client.get_data(type_, name, guid)

    async def call_method(
        self, module: str, method: str, arguments: list[Any] | None = None
    ) -> dict[str, Any]:
        client = self._ensure_client()
        return await client.call_method(module, method, arguments)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
