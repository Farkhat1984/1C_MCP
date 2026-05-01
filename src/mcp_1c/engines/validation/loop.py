"""Validate generated BSL against bsl-language-server.

The contract is narrow on purpose: take a string, return diagnostics.
No retry loop, no LLM coupling — just enough to wire ``smart-*`` and
``generate-*`` tool outputs through a syntax check before they hit
the user's clipboard.

Implementation strategy:

1. **LSP path (preferred)**: open a virtual document via
   ``textDocument/didOpen``, wait for ``textDocument/publishDiagnostics``,
   close the document. Subsecond on a warm JVM.

2. **CLI fallback**: write the snippet to a temp file, run
   ``BslLanguageServer.validate_file`` (which today shells out to
   ``--analyze``). Slower but works without an LSP-aware build.

3. **No-server fallback**: when neither works, return an "unvalidated"
   result rather than a wrong "valid" one — the caller can decide
   whether to ship the unverified code or surface the absence to the
   user. This is critical: silently treating no-validator as
   green-light is exactly the failure mode the closed-loop is meant
   to prevent.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationDiagnostic:
    """One diagnostic returned by the validator.

    Source-agnostic: shape matches both LSP ``Diagnostic`` and
    bsl-language-server's CLI report. Severity is ``"error"`` |
    ``"warning"`` | ``"info"`` | ``"hint"``; tools usually only act on
    errors, but warnings are surfaced too so the user can see them.
    """

    severity: str
    message: str
    line: int = 0
    column: int = 0
    code: str = ""
    source: str = "bsl-ls"


@dataclass
class ValidationResult:
    """Outcome of validating a BSL snippet.

    ``validated`` is the contract the caller cares about most:
    ``True`` → no errors found by a real validator (warnings allowed);
    ``False`` → errors found OR no validator was reachable. Use the
    ``backend`` attribute to distinguish "validator said no" from
    "validator wasn't available" — the second case puts ``backend``
    at ``"none"``.
    """

    validated: bool
    backend: str  # "lsp" | "cli" | "none"
    diagnostics: list[ValidationDiagnostic] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    raw: dict[str, Any] | None = None  # backend-specific extras for debugging

    @classmethod
    def unvalidated(cls, reason: str) -> ValidationResult:
        """Build a result for the no-validator-available case."""
        return cls(
            validated=False,
            backend="none",
            diagnostics=[
                ValidationDiagnostic(
                    severity="info",
                    message=f"Validation skipped: {reason}",
                    code="VALIDATION_UNAVAILABLE",
                )
            ],
            raw={"reason": reason},
        )


async def validate_bsl(
    code: str,
    *,
    code_engine: Any | None = None,
    timeout: float = 30.0,
) -> ValidationResult:
    """Validate a BSL snippet end-to-end.

    Args:
        code: The BSL source to check. Can be a fragment (a single
            procedure) or a full module — the validator handles both.
        code_engine: Optional :class:`mcp_1c.engines.code.engine.CodeEngine`
            for the LSP path. When omitted, only the CLI fallback is
            tried. Phase 2 web mode injects the workspace's CodeEngine.
        timeout: Hard cap on the total validation time. Real-world
            BSL-LS warm-state validation runs in <500ms; the budget
            here exists to bound cold-start outliers.

    Returns:
        :class:`ValidationResult` with ``validated`` reflecting whether
        a real validator answered "no errors". A failure to reach any
        validator returns ``backend="none"`` and ``validated=False`` —
        callers must distinguish this from a "validator said no".
    """
    if code_engine is not None:
        try:
            result = await asyncio.wait_for(
                _validate_via_lsp(code, code_engine), timeout=timeout
            )
            if result is not None:
                return result
        except TimeoutError:
            logger.warning("LSP validation timed out; falling back to CLI")
        except Exception as exc:
            logger.warning(f"LSP validation failed; falling back to CLI: {exc}")

    cli_result = await _validate_via_cli(code, timeout=timeout)
    if cli_result is not None:
        return cli_result

    return ValidationResult.unvalidated(
        "no bsl-language-server backend reachable"
    )


# ---------------------------------------------------------------------------
# LSP backend
# ---------------------------------------------------------------------------


async def _validate_via_lsp(
    code: str, code_engine: Any
) -> ValidationResult | None:
    """Open a virtual document, collect publishDiagnostics, close.

    Returns ``None`` when the LSP layer isn't reachable so the caller
    can fall back. Raises :class:`Exception` on unexpected failures —
    those are logged and trigger CLI fallback at the call site.
    """
    if not hasattr(code_engine, "_ensure_lsp"):
        return None

    try:
        client = await code_engine._ensure_lsp()  # noqa: SLF001
    except Exception:
        return None

    diagnostics_event = asyncio.Event()
    received: list[dict[str, Any]] = []
    uri = "inmemory:///mcp-1c-validate.bsl"

    async def _capture(params: dict[str, Any]) -> None:
        if params.get("uri") != uri:
            return
        received.extend(params.get("diagnostics") or [])
        diagnostics_event.set()

    client.on_notification("textDocument/publishDiagnostics", _capture)

    try:
        await client.did_open(uri, code)
        # bsl-language-server emits publishDiagnostics shortly after
        # didOpen for the document. We wait up to 5 seconds — beyond
        # that the server is unhealthy and the outer wait_for kills us.
        # No diagnostics published is *not* an error: it means the
        # server didn't find anything to flag, so a timeout here is OK.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(diagnostics_event.wait(), timeout=5.0)
    finally:
        try:
            await client.did_close(uri)
        except Exception as exc:
            logger.debug(f"did_close after validation raised: {exc}")

    return _build_result(received, backend="lsp")


def _build_result(
    raw_diagnostics: list[dict[str, Any]], *, backend: str
) -> ValidationResult:
    """Translate raw LSP diagnostics into our :class:`ValidationResult`."""
    diags: list[ValidationDiagnostic] = []
    error_count = 0
    warning_count = 0
    for d in raw_diagnostics:
        severity = _lsp_severity(d.get("severity"))
        if severity == "error":
            error_count += 1
        elif severity == "warning":
            warning_count += 1
        rng = (d.get("range") or {}).get("start") or {}
        diags.append(
            ValidationDiagnostic(
                severity=severity,
                message=str(d.get("message", "")),
                line=int(rng.get("line", 0)) + 1,  # LSP is 0-indexed
                column=int(rng.get("character", 0)) + 1,
                code=str(d.get("code", "") or ""),
                source=str(d.get("source", "bsl-ls") or "bsl-ls"),
            )
        )
    return ValidationResult(
        validated=error_count == 0,
        backend=backend,
        diagnostics=diags,
        error_count=error_count,
        warning_count=warning_count,
        raw={"diagnostics_count": len(diags)},
    )


_LSP_SEVERITY_MAP = {1: "error", 2: "warning", 3: "info", 4: "hint"}


def _lsp_severity(value: Any) -> str:
    """Map LSP DiagnosticSeverity ints to human strings.

    LSP spec says severity is optional; treat ``None`` as "error" so
    a malformed payload doesn't accidentally pass validation.
    """
    if isinstance(value, int):
        return _LSP_SEVERITY_MAP.get(value, "error")
    if isinstance(value, str):
        return value.lower()
    return "error"


# ---------------------------------------------------------------------------
# CLI fallback
# ---------------------------------------------------------------------------


async def _validate_via_cli(
    code: str, *, timeout: float = 30.0
) -> ValidationResult | None:
    """Write the snippet to a tempfile and shell out to BSL-LS CLI.

    Slower than LSP (cold JVM per call) but works against any release
    of bsl-language-server, including the build the user already has
    installed via the :mod:`mcp_1c.engines.code.bsl_ls` integration.

    Returns ``None`` when even the CLI is unreachable, so the caller
    can degrade gracefully.
    """
    from mcp_1c.engines.code.bsl_ls import (
        BslLanguageServer,
        DiagnosticSeverity,
    )

    bsl_ls = BslLanguageServer.get_instance()
    if not await bsl_ls.check_availability():
        return None

    with tempfile.TemporaryDirectory(prefix="mcp_1c_validate_") as tmpdir:
        tmp_path = Path(tmpdir) / "snippet.bsl"
        tmp_path.write_text(code, encoding="utf-8")
        try:
            result = await asyncio.wait_for(
                bsl_ls.validate_file(tmp_path), timeout=timeout
            )
        except TimeoutError:
            return None

    diags: list[ValidationDiagnostic] = []
    for d in result.diagnostics:
        severity_str = (
            d.severity.value
            if isinstance(d.severity, DiagnosticSeverity)
            else str(d.severity)
        )
        diags.append(
            ValidationDiagnostic(
                severity=severity_str,
                message=d.message,
                line=d.line,
                column=d.column,
                code=d.code,
                source=d.source,
            )
        )
    return ValidationResult(
        validated=result.error_count == 0,
        backend="cli",
        diagnostics=diags,
        error_count=result.error_count,
        warning_count=result.warning_count,
        raw={"valid": result.valid},
    )


__all__ = [
    "ValidationDiagnostic",
    "ValidationResult",
    "validate_bsl",
]
