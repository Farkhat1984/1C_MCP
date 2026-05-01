"""Tests for the optional Prometheus + OTel observability skeleton.

The contract under test:

- ``record_tool_call`` is **always** safe to call. It must be a true
  no-op when Prometheus isn't configured — the default install with no
  env opt-in must add zero-cost-beyond-a-bool-check per call.
- ``init_observability`` must never crash on a missing optional dep.
  It logs a warning and stays disabled — the server keeps serving.
- When prom is on and installed, the text exposition contains the
  declared metric names plus the right ``tool=`` label so a scraper
  recognises the series.
- ``tool_span`` returns a working context manager whether OTel is
  configured or not.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from typing import Any

import pytest

from mcp_1c.utils import observability
from mcp_1c.utils.observability import (
    ObservabilityConfig,
    init_observability,
    is_otel_enabled,
    is_prometheus_enabled,
    record_tool_call,
    render_prometheus_text,
    tool_span,
)

PROM_INSTALLED = importlib.util.find_spec("prometheus_client") is not None


@pytest.fixture(autouse=True)
def _reset_observability_state() -> None:
    """Each test starts from a clean slate.

    Prometheus' default registry is process-global and rejects
    duplicate Counter registrations with ``ValueError`` — without this
    fixture, the second test that calls ``init_observability`` would
    blow up. We tear down after the test too so a failing test doesn't
    poison the next one.
    """
    observability._reset_for_tests()
    yield
    observability._reset_for_tests()


def test_record_tool_call_is_noop_when_disabled() -> None:
    """Default install path: no env, no prom, no crash."""
    # Sanity: nothing initialised yet.
    assert not is_prometheus_enabled()
    # Should not raise, regardless of the inputs we pass.
    record_tool_call("any.tool", latency_ms=12.5, status="ok")
    record_tool_call("any.tool", latency_ms=12.5, status="error", error_code="OOPS")


def test_init_idempotent() -> None:
    """Repeat ``init_observability`` calls don't double-register."""
    cfg = ObservabilityConfig(prometheus_enabled=False)
    init_observability(cfg)
    init_observability(cfg)
    init_observability(cfg)
    # Default config means everything stays off.
    assert not is_prometheus_enabled()
    assert not is_otel_enabled()


def test_init_with_prom_enabled_but_lib_missing_logs_warning_and_stays_disabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``MCP_PROMETHEUS_ENABLED=true`` without ``prometheus_client`` must
    log and continue — never crash the server."""
    # Hide ``prometheus_client`` from the import machinery for the
    # duration of this test so the inner ``try: import …`` falls into
    # the ``except ImportError`` branch even when the lib is on disk.
    monkeypatch.setitem(sys.modules, "prometheus_client", None)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="mcp_1c.utils.observability")
    init_observability(ObservabilityConfig(prometheus_enabled=True))

    assert not is_prometheus_enabled()
    assert any(
        "prometheus_client is not installed" in rec.message
        for rec in caplog.records
    ), f"expected warning about missing prometheus_client, got: {caplog.records}"


def test_init_with_otel_endpoint_but_lib_missing_stays_disabled(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """OTel endpoint set without OTel libs installed: warn and disable."""
    # Block every otel-related import path the helper tries.
    for mod in (
        "opentelemetry",
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        "opentelemetry.sdk.resources",
        "opentelemetry.sdk.trace",
        "opentelemetry.sdk.trace.export",
    ):
        monkeypatch.setitem(sys.modules, mod, None)  # type: ignore[arg-type]

    caplog.set_level(logging.WARNING, logger="mcp_1c.utils.observability")
    init_observability(
        ObservabilityConfig(
            prometheus_enabled=False,
            otel_endpoint="http://otel-collector:4318/v1/traces",
        )
    )
    assert not is_otel_enabled()
    assert any(
        "opentelemetry packages are not installed" in rec.message
        for rec in caplog.records
    )


def test_tool_span_works_when_otel_disabled() -> None:
    """The no-op span path must support attribute / status / exception
    methods without raising — call sites should look the same in both
    modes."""
    with tool_span("metadata.search") as span:
        span.set_attribute("tool.tenant", "acme")
        span.set_status("ok")
        try:
            raise RuntimeError("boom")
        except RuntimeError as exc:
            span.record_exception(exc)


@pytest.mark.skipif(
    not PROM_INSTALLED,
    reason="prometheus_client not installed; optional observability extra",
)
def test_render_text_includes_recorded_call() -> None:
    """End-to-end: enable prom, record a call, scrape → series visible."""
    init_observability(ObservabilityConfig(prometheus_enabled=True))
    assert is_prometheus_enabled()

    record_tool_call(
        "metadata.search",
        latency_ms=42.0,
        status="ok",
    )
    record_tool_call(
        "metadata.search",
        latency_ms=120.0,
        status="error",
        error_code="OBJECT_NOT_FOUND",
    )

    text = render_prometheus_text()

    # All three series we declared show up.
    assert "mcp_1c_tool_calls_total" in text
    assert "mcp_1c_tool_latency_seconds" in text
    assert "mcp_1c_tool_errors_total" in text
    # Tool label propagates to the series.
    assert 'tool="metadata.search"' in text
    # Both ok and error rows landed.
    assert 'status="ok"' in text
    assert 'status="error"' in text
    # Error code label survived the no-None remap.
    assert 'error_code="OBJECT_NOT_FOUND"' in text


@pytest.mark.skipif(
    not PROM_INSTALLED,
    reason="prometheus_client not installed; optional observability extra",
)
def test_render_text_empty_when_disabled() -> None:
    """No init → no text. Caller branches on ``is_prometheus_enabled``."""
    assert render_prometheus_text() == ""


def test_config_from_env_defaults_to_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No env vars set → everything off."""
    for var in ("MCP_PROMETHEUS_ENABLED", "MCP_OTEL_ENDPOINT", "MCP_OTEL_SERVICE_NAME"):
        monkeypatch.delenv(var, raising=False)
    cfg = ObservabilityConfig.from_env()
    assert cfg.prometheus_enabled is False
    assert cfg.otel_endpoint == ""
    assert cfg.otel_service_name == "mcp-1c"


@pytest.mark.parametrize("raw", ["true", "1", "yes", "on", "TRUE", "On"])
def test_config_from_env_parses_truthy(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("MCP_PROMETHEUS_ENABLED", raw)
    assert ObservabilityConfig.from_env().prometheus_enabled is True


@pytest.mark.parametrize("raw", ["false", "0", "no", "off", ""])
def test_config_from_env_parses_falsy(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    monkeypatch.setenv("MCP_PROMETHEUS_ENABLED", raw)
    assert ObservabilityConfig.from_env().prometheus_enabled is False


@pytest.mark.skipif(
    not PROM_INSTALLED,
    reason="prometheus_client not installed; optional observability extra",
)
@pytest.mark.asyncio
async def test_base_tool_run_records_prometheus_metric() -> None:
    """``BaseTool.run`` must drive the Prometheus counter, not just the
    in-memory ``tool_metrics``. This is the wire-up assertion."""
    from typing import ClassVar

    from mcp_1c.tools.base import BaseTool

    class _Stub(BaseTool):
        name: ClassVar[str] = "obs.test_tool"
        description: ClassVar[str] = ""
        input_schema: ClassVar[dict[str, Any]] = {
            "type": "object", "properties": {}, "required": [],
        }

        async def execute(self, arguments: dict[str, Any]) -> Any:  # noqa: ARG002
            return {"ok": True}

    init_observability(ObservabilityConfig(prometheus_enabled=True))
    await _Stub().run({})

    text = render_prometheus_text()
    assert 'tool="obs.test_tool"' in text
    assert 'status="ok"' in text
