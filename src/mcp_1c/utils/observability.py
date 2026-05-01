"""Optional Prometheus + OpenTelemetry observability skeleton.

Disabled by default. Ops opts in via env:

- ``MCP_PROMETHEUS_ENABLED=true`` — register Prometheus collectors and
  switch ``/metrics`` from JSON to Prometheus text exposition format.
- ``MCP_OTEL_ENDPOINT=https://otel-collector:4318/v1/traces`` — enable
  OTLP/HTTP trace export. Empty string (default) means no tracing.
- ``MCP_OTEL_SERVICE_NAME`` — service.name resource attribute (default
  ``mcp-1c``).

Both backends are **optional dependencies**. Import their packages
lazily inside :func:`init_observability` so the module loads on a lean
install (``pip install -e .``) without ``prometheus-client`` or
``opentelemetry-*`` on disk. When a backend is requested but the
corresponding library is missing, we log a warning and stay disabled —
never crash the server.

Wire-up points:

- :class:`mcp_1c.tools.base.BaseTool.run` calls
  :func:`record_tool_call` after every invocation and wraps the call
  body in :func:`tool_span`. Both are no-ops when their backend is off,
  so the default install adds at most one bool check per call.
- :func:`mcp_1c.web.create_app` calls :func:`init_observability` on
  startup and routes ``/metrics`` to :func:`render_prometheus_text`
  when Prometheus is on.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from mcp_1c.utils.logger import get_logger

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry, Counter, Histogram

logger = get_logger(__name__)


# Histogram buckets sized for tool calls: sub-millisecond is unreachable
# (we go through MCP / aiohttp first), and most tools land between 5 ms
# (cache hit) and 30 s (full XML re-index). The tail past 30 s shows up
# in the `+Inf` overflow bucket — anything that slow needs investigation
# regardless of which exact bucket it falls into.
_LATENCY_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0,
)


class ObservabilityConfig(BaseModel):
    """Runtime configuration for Prometheus + OTel.

    Defaults match "everything off" — explicit env opt-in is required so
    the lean install doesn't pay any cost.
    """

    prometheus_enabled: bool = Field(
        default=False,
        description="Expose Prometheus metrics; set MCP_PROMETHEUS_ENABLED=true.",
    )
    otel_endpoint: str = Field(
        default="",
        description=(
            "OTLP/HTTP trace endpoint, e.g. "
            "https://otel-collector:4318/v1/traces. Empty disables tracing."
        ),
    )
    otel_service_name: str = Field(
        default="mcp-1c",
        description="Resource attribute service.name for emitted spans.",
    )

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        """Parse env vars, tolerating common boolean encodings."""
        return cls(
            prometheus_enabled=_env_bool("MCP_PROMETHEUS_ENABLED", default=False),
            otel_endpoint=os.environ.get("MCP_OTEL_ENDPOINT", "").strip(),
            otel_service_name=os.environ.get("MCP_OTEL_SERVICE_NAME", "mcp-1c").strip()
            or "mcp-1c",
        )


def _env_bool(name: str, *, default: bool) -> bool:
    """Accept the usual truthy spellings (``true``/``1``/``yes``/``on``)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


# ---------------------------------------------------------------------------
# Module-level mutable state.
#
# All five symbols stay ``None`` on a default install. ``init_observability``
# flips them once (idempotent); subsequent calls are no-ops. Tests reset
# state with :func:`_reset_for_tests` to keep one-shot init testable.
# ---------------------------------------------------------------------------
_initialized: bool = False
_prom_enabled: bool = False
_prom_registry: CollectorRegistry | None = None
_calls_counter: Counter | None = None
_latency_histogram: Histogram | None = None
_errors_counter: Counter | None = None

_otel_enabled: bool = False
_tracer: Any = None  # opentelemetry.trace.Tracer when active


def init_observability(config: ObservabilityConfig) -> None:
    """Initialise Prometheus and/or OTel exporters from ``config``.

    Idempotent: subsequent calls (with the same or different config)
    are silently ignored. Re-initialisation would risk duplicate
    Counter registration on the global registry, which Prometheus
    rejects with ``ValueError`` — and the operator already saw a config
    log line, so the second call is almost always an accidental
    re-bootstrap (e.g. test suite running ``create_app`` twice).
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    if config.prometheus_enabled:
        _try_init_prometheus()
    if config.otel_endpoint:
        _try_init_otel(config.otel_endpoint, config.otel_service_name)


def _try_init_prometheus() -> None:
    """Best-effort Prometheus init. Stays disabled if the lib is absent."""
    global _prom_enabled, _prom_registry
    global _calls_counter, _latency_histogram, _errors_counter
    try:
        from prometheus_client import REGISTRY, Counter, Histogram
    except ImportError:
        logger.warning(
            "MCP_PROMETHEUS_ENABLED is set but prometheus_client is not installed; "
            "install with `pip install mcp-1c[observability]` to enable metrics. "
            "Continuing with metrics disabled."
        )
        return

    # Use the default global registry so the standard exporter helpers
    # (text rendering, push gateway, etc.) work without extra plumbing.
    _prom_registry = REGISTRY
    _calls_counter = Counter(
        "mcp_1c_tool_calls_total",
        "Total tool invocations, labeled by tool and outcome.",
        labelnames=("tool", "status"),
    )
    _latency_histogram = Histogram(
        "mcp_1c_tool_latency_seconds",
        "Tool call latency in seconds.",
        labelnames=("tool",),
        buckets=_LATENCY_BUCKETS,
    )
    _errors_counter = Counter(
        "mcp_1c_tool_errors_total",
        "Tool errors broken down by error code.",
        labelnames=("tool", "error_code"),
    )
    _prom_enabled = True
    logger.info("Prometheus metrics enabled")


def _try_init_otel(endpoint: str, service_name: str) -> None:
    """Best-effort OTel init. Stays disabled if any required lib is missing.

    We construct an OTLP/HTTP trace exporter and wire it through a
    ``BatchSpanProcessor`` on a freshly built ``TracerProvider``. The
    provider is then installed globally so any other otel-aware
    library in the process picks it up automatically. If the global
    provider is already a real (non-NoOp) one, we leave it alone —
    that's how a host process opting into otel for its own reasons
    keeps owning the configuration.
    """
    global _otel_enabled, _tracer
    # Optional deps — mypy has no stubs for them on a lean install,
    # and we deliberately don't ship type: ignore stubs here. The
    # inline ignores keep ``mypy --strict`` clean without forcing
    # everyone to install otel-* just to type-check.
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
        )
    except ImportError:
        logger.warning(
            "MCP_OTEL_ENDPOINT is set but opentelemetry packages are not installed; "
            "install with `pip install mcp-1c[observability]` to enable tracing. "
            "Continuing with tracing disabled."
        )
        return

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    )
    # ``set_tracer_provider`` is a no-op once a provider is set; that's
    # the documented behaviour. We accept it: if the host already
    # configured otel, we still get a Tracer from ``get_tracer`` and
    # spans land wherever the host wants them.
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("mcp_1c", "0.2.0")
    _otel_enabled = True
    logger.info(f"OpenTelemetry tracing enabled -> {endpoint}")


def record_tool_call(
    tool: str,
    *,
    latency_ms: float,
    status: str,
    error_code: str | None = None,
) -> None:
    """Record one tool invocation in Prometheus.

    No-op when Prometheus isn't enabled — that's the default install
    cost: a single bool check per call.

    Args:
        tool: Tool name (e.g. ``"metadata.search"``).
        latency_ms: Wall-clock duration in milliseconds.
        status: ``"ok"`` or ``"error"``.
        error_code: Application error code if ``status == "error"``.
            ``None`` is mapped to ``"NONE"`` for the label, since
            Prometheus labels can't be ``None``.
    """
    if not _prom_enabled:
        return
    # The asserts narrow the type for mypy strict — guarded by the
    # ``_prom_enabled`` flag, both objects are always set together
    # inside ``_try_init_prometheus``.
    assert _calls_counter is not None
    assert _latency_histogram is not None
    assert _errors_counter is not None
    _calls_counter.labels(tool=tool, status=status).inc()
    _latency_histogram.labels(tool=tool).observe(latency_ms / 1000.0)
    if status == "error":
        _errors_counter.labels(tool=tool, error_code=error_code or "NONE").inc()


@contextmanager
def tool_span(tool: str) -> Iterator[Any]:
    """Span context manager — real span when OTel is on, no-op stub otherwise.

    The yielded object is whatever ``Tracer.start_as_current_span``
    returns (typically an ``opentelemetry.trace.Span``) — callers don't
    need to inspect it; this helper exists so call sites are uniform
    regardless of OTel availability.
    """
    if not _otel_enabled or _tracer is None:
        yield _NoopSpan()
        return
    with _tracer.start_as_current_span(f"tool.{tool}") as span:
        yield span


class _NoopSpan:
    """Minimal stand-in for an OTel span so callers can treat the
    yielded object uniformly.

    The OTel SDK's real Span has a much wider surface; we model only
    what tool wrappers reasonably reach for so a missed attribute fails
    loudly with ``AttributeError`` rather than silently doing nothing
    (silent no-ops on missing telemetry tend to mask drift between
    enabled and disabled paths).
    """

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        return None

    def set_status(self, status: Any) -> None:  # noqa: ARG002
        return None

    def record_exception(self, exception: BaseException) -> None:  # noqa: ARG002
        return None


def render_prometheus_text() -> str:
    """Return the Prometheus text-exposition snapshot.

    Returns the empty string when Prometheus isn't enabled — callers
    (i.e. the ``/metrics`` route) should branch on
    :func:`is_prometheus_enabled` first to choose the response format.
    """
    if not _prom_enabled or _prom_registry is None:
        return ""
    from prometheus_client import generate_latest

    return generate_latest(_prom_registry).decode("utf-8")


def is_prometheus_enabled() -> bool:
    """True iff Prometheus collectors are active."""
    return _prom_enabled


def is_otel_enabled() -> bool:
    """True iff an OTel tracer is configured."""
    return _otel_enabled


# Standard Prometheus content type, including the version tag the
# scraper uses to negotiate format. Exposed as a constant so the route
# handler doesn't have to remember the exact string.
PROMETHEUS_CONTENT_TYPE: str = "text/plain; version=0.0.4; charset=utf-8"


def _reset_for_tests() -> None:
    """Reset all module state. **Tests only** — never call from production.

    Prometheus' default registry is a process global; once a Counter
    is registered there, re-registering by the same name raises
    ``ValueError``. Tests that exercise ``init_observability`` more
    than once need a clean slate. We unregister our own collectors
    rather than swapping the registry so we don't trip up other tests
    that look at ``REGISTRY`` directly.
    """
    global _initialized, _prom_enabled, _prom_registry
    global _calls_counter, _latency_histogram, _errors_counter
    global _otel_enabled, _tracer

    if _prom_registry is not None:
        for collector in (_calls_counter, _latency_histogram, _errors_counter):
            if collector is not None:
                # Already gone is fine — the goal is "not registered".
                with suppress(KeyError, ValueError):
                    _prom_registry.unregister(collector)

    _initialized = False
    _prom_enabled = False
    _prom_registry = None
    _calls_counter = None
    _latency_histogram = None
    _errors_counter = None
    _otel_enabled = False
    _tracer = None
