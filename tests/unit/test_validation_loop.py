"""Tests for closed-loop validation.

Three flavours of "no validator reachable" must be distinguishable
from "validator said no errors": the contract is that
``validated=True`` must mean "a real validator answered OK", and
``backend='none'`` is the unvalidated escape hatch. We assert that
distinction explicitly because it's the whole point of the layer.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_1c.engines.validation import (
    ValidationResult,
    validate_bsl,
)
from mcp_1c.engines.validation.loop import _build_result, _lsp_severity

# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------


def test_unvalidated_factory_marks_backend_none() -> None:
    result = ValidationResult.unvalidated("no jar")
    assert result.validated is False
    assert result.backend == "none"
    assert result.diagnostics[0].code == "VALIDATION_UNAVAILABLE"


def test_build_result_counts_severities() -> None:
    raw = [
        {"severity": 1, "message": "broke", "range": {"start": {"line": 0, "character": 0}}},
        {"severity": 2, "message": "smell", "range": {"start": {"line": 5, "character": 3}}},
        {"severity": 3, "message": "fyi", "range": {"start": {"line": 7, "character": 0}}},
    ]
    result = _build_result(raw, backend="lsp")
    assert result.error_count == 1
    assert result.warning_count == 1
    assert result.validated is False  # Errors present.
    assert result.backend == "lsp"
    # Lines are 1-indexed in our model.
    assert result.diagnostics[0].line == 1
    assert result.diagnostics[1].line == 6


def test_build_result_no_diagnostics_validates() -> None:
    """Empty diagnostic list = validator ran and found nothing wrong."""
    result = _build_result([], backend="lsp")
    assert result.validated is True
    assert result.backend == "lsp"
    assert result.error_count == 0


def test_lsp_severity_defaults_to_error_for_unknown() -> None:
    """A malformed payload must not silently pass as info — fail closed."""
    assert _lsp_severity(None) == "error"
    assert _lsp_severity("garbage-string") == "garbage-string"
    assert _lsp_severity(99) == "error"
    assert _lsp_severity(1) == "error"
    assert _lsp_severity(2) == "warning"


# ---------------------------------------------------------------------------
# validate_bsl integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_bsl_returns_unvalidated_when_no_backends() -> None:
    """No code_engine + no CLI BSL-LS → backend='none' must be surfaced."""
    with patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.check_availability",
        new=AsyncMock(return_value=False),
    ):
        result = await validate_bsl("Процедура Х() КонецПроцедуры")

    assert result.backend == "none"
    assert result.validated is False  # Critical: must NOT report green.


@pytest.mark.asyncio
async def test_validate_bsl_uses_lsp_when_available() -> None:
    """When the code_engine LSP path returns a result, we use it."""
    fake_engine = MagicMock()
    fake_client = MagicMock()
    fake_client.did_open = AsyncMock()
    fake_client.did_close = AsyncMock()

    captured_handler: dict = {}

    def register(method: str, handler) -> None:
        captured_handler["fn"] = handler

    fake_client.on_notification = register

    fake_engine._ensure_lsp = AsyncMock(return_value=fake_client)

    async def push_diagnostics_after_open(*args, **kwargs):
        # Simulate the server posting publishDiagnostics shortly after
        # didOpen.
        await asyncio.sleep(0)
        await captured_handler["fn"](
            {
                "uri": "inmemory:///mcp-1c-validate.bsl",
                "diagnostics": [],  # No errors.
            }
        )

    fake_client.did_open.side_effect = push_diagnostics_after_open

    result = await validate_bsl(
        "Процедура Чисто() КонецПроцедуры",
        code_engine=fake_engine,
    )
    assert result.backend == "lsp"
    assert result.validated is True
    assert result.error_count == 0


@pytest.mark.asyncio
async def test_validate_bsl_reports_lsp_errors() -> None:
    fake_engine = MagicMock()
    fake_client = MagicMock()
    fake_client.did_open = AsyncMock()
    fake_client.did_close = AsyncMock()

    captured_handler: dict = {}
    fake_client.on_notification = lambda method, handler: captured_handler.update(fn=handler)
    fake_engine._ensure_lsp = AsyncMock(return_value=fake_client)

    async def push_error(*args, **kwargs):
        await asyncio.sleep(0)
        await captured_handler["fn"](
            {
                "uri": "inmemory:///mcp-1c-validate.bsl",
                "diagnostics": [
                    {
                        "severity": 1,
                        "message": "Unknown identifier",
                        "code": "BadIdent",
                        "range": {"start": {"line": 2, "character": 4}},
                    }
                ],
            }
        )

    fake_client.did_open.side_effect = push_error

    result = await validate_bsl(
        "Процедура Гнилая() Тут_какой_то_мусор; КонецПроцедуры",
        code_engine=fake_engine,
    )
    assert result.backend == "lsp"
    assert result.validated is False
    assert result.error_count == 1
    assert result.diagnostics[0].line == 3  # 1-indexed


@pytest.mark.asyncio
async def test_validate_bsl_falls_back_to_cli_when_lsp_fails() -> None:
    """When LSP raises, we should reach for the CLI before giving up."""
    fake_engine = MagicMock()
    fake_engine._ensure_lsp = AsyncMock(side_effect=RuntimeError("no jar"))

    fake_validation = MagicMock()
    fake_validation.error_count = 0
    fake_validation.warning_count = 0
    fake_validation.diagnostics = []
    fake_validation.valid = True

    with patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.check_availability",
        new=AsyncMock(return_value=True),
    ), patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.validate_file",
        new=AsyncMock(return_value=fake_validation),
    ):
        result = await validate_bsl(
            "Процедура Х() КонецПроцедуры", code_engine=fake_engine
        )

    assert result.backend == "cli"
    assert result.validated is True


@pytest.mark.asyncio
async def test_validate_bsl_with_no_engine_uses_cli_directly() -> None:
    fake_validation = MagicMock()
    fake_validation.error_count = 0
    fake_validation.warning_count = 0
    fake_validation.diagnostics = []
    fake_validation.valid = True

    with patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.check_availability",
        new=AsyncMock(return_value=True),
    ), patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.validate_file",
        new=AsyncMock(return_value=fake_validation),
    ):
        result = await validate_bsl("Процедура Х() КонецПроцедуры")

    assert result.backend == "cli"
    assert result.validated is True


@pytest.mark.asyncio
async def test_validate_bsl_distinguishes_unvalidated_from_validated_no_errors() -> None:
    """The whole point of the layer: 'no validator' ≠ 'validator said OK'."""
    # Case A: validator unavailable → backend='none', validated=False
    with patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.check_availability",
        new=AsyncMock(return_value=False),
    ):
        a = await validate_bsl("Процедура Х() КонецПроцедуры")
    assert a.backend == "none" and a.validated is False

    # Case B: validator OK with no errors → backend='cli', validated=True
    fake_validation = MagicMock()
    fake_validation.error_count = 0
    fake_validation.warning_count = 0
    fake_validation.diagnostics = []
    fake_validation.valid = True
    with patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.check_availability",
        new=AsyncMock(return_value=True),
    ), patch(
        "mcp_1c.engines.code.bsl_ls.BslLanguageServer.validate_file",
        new=AsyncMock(return_value=fake_validation),
    ):
        b = await validate_bsl("Процедура Х() КонецПроцедуры")
    assert b.backend == "cli" and b.validated is True
