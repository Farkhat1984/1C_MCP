"""Closed-loop wiring inside smart-* tools.

We don't run the real generator here — we patch it. The point is to
verify that when a tool emits BSL and ``validate=True``, the output
gets a ``validation`` envelope with diagnostics from the validator,
and when the validator can't run, the envelope still appears with
``backend='none'`` so the LLM never gets a silently-unverified result.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mcp_1c.engines.validation import ValidationDiagnostic, ValidationResult
from mcp_1c.tools.smart_tools import (
    SmartMovementTool,
    SmartPrintTool,
    SmartQueryTool,
    _validation_payload,
)


def _ok_result(backend: str = "lsp") -> ValidationResult:
    return ValidationResult(
        validated=True,
        backend=backend,
        diagnostics=[],
        error_count=0,
        warning_count=0,
    )


def _broken_result() -> ValidationResult:
    return ValidationResult(
        validated=False,
        backend="lsp",
        diagnostics=[
            ValidationDiagnostic(
                severity="error",
                message="Unknown identifier",
                line=4,
                column=2,
                code="BadIdent",
            ),
            ValidationDiagnostic(
                severity="warning", message="style", line=10, code="W001"
            ),
        ],
        error_count=1,
        warning_count=1,
    )


# ---------------------------------------------------------------------------
# _validation_payload
# ---------------------------------------------------------------------------


def test_validation_payload_splits_errors_and_warnings() -> None:
    payload = _validation_payload(_broken_result())
    assert payload["error_count"] == 1
    assert payload["warning_count"] == 1
    assert len(payload["errors"]) == 1
    assert len(payload["warnings"]) == 1
    assert payload["errors"][0]["line"] == 4
    assert payload["validated"] is False


def test_validation_payload_empty_when_clean() -> None:
    payload = _validation_payload(_ok_result())
    assert payload["validated"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []


# ---------------------------------------------------------------------------
# SmartPrintTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_print_attaches_validation_when_validate_true() -> None:
    tool = SmartPrintTool()
    artefacts = {
        "print_procedure": "Процедура Печать() Экспорт КонецПроцедуры",
        "manager_module": "// generated",
        "mxl_template": "...",
        "query": "ВЫБРАТЬ * ИЗ Документ.X",
    }
    with patch(
        "mcp_1c.tools.smart_tools.SmartGenerator"
    ) as mock_generator_cls, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=_ok_result(backend="cli")),
    ):
        mock_generator_cls.get_instance.return_value.generate_print_form = (
            AsyncMock(return_value=artefacts)
        )
        result = await tool.execute({"object_name": "Document.X"})

    assert "validation" in result
    assert result["validation"]["backend"] == "cli"
    assert result["validation"]["validated"] is True
    # Original artefacts preserved.
    assert "print_procedure" in result
    assert "mxl_template" in result


@pytest.mark.asyncio
async def test_smart_print_skips_validation_when_validate_false() -> None:
    tool = SmartPrintTool()
    artefacts = {
        "print_procedure": "Процедура Печать() КонецПроцедуры",
    }
    with patch(
        "mcp_1c.tools.smart_tools.SmartGenerator"
    ) as mock_generator_cls, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=_ok_result()),
    ) as mock_validate:
        mock_generator_cls.get_instance.return_value.generate_print_form = (
            AsyncMock(return_value=artefacts)
        )
        result = await tool.execute(
            {"object_name": "Document.X", "validate": False}
        )

    assert "validation" not in result
    mock_validate.assert_not_awaited()


@pytest.mark.asyncio
async def test_smart_print_surfaces_errors_in_validation_envelope() -> None:
    """Critical: when the generated BSL has errors, the LLM must see them."""
    tool = SmartPrintTool()
    artefacts = {"print_procedure": "Процедура X(]"}
    with patch(
        "mcp_1c.tools.smart_tools.SmartGenerator"
    ) as mock_generator_cls, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=_broken_result()),
    ):
        mock_generator_cls.get_instance.return_value.generate_print_form = (
            AsyncMock(return_value=artefacts)
        )
        result = await tool.execute({"object_name": "Document.X"})

    assert result["validation"]["validated"] is False
    assert result["validation"]["errors"][0]["message"] == "Unknown identifier"


# ---------------------------------------------------------------------------
# SmartMovementTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_movement_wraps_string_payload_when_validating() -> None:
    """Legacy generator returning a raw string still gets diagnostics —
    we wrap it into ``{code, validation}`` so the LLM has a stable shape."""
    tool = SmartMovementTool()
    raw_code = "Процедура ОбработкаПроведения() Экспорт КонецПроцедуры"
    with patch(
        "mcp_1c.tools.smart_tools.SmartGenerator"
    ) as mock_generator_cls, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=_ok_result()),
    ):
        mock_generator_cls.get_instance.return_value.generate_movement = (
            AsyncMock(return_value=raw_code)
        )
        result = await tool.execute(
            {
                "document_name": "Document.X",
                "register_name": "AccumulationRegister.Y",
            }
        )

    assert isinstance(result, dict)
    assert result["code"] == raw_code
    assert result["validation"]["validated"] is True


@pytest.mark.asyncio
async def test_smart_movement_attaches_validation_to_dict_payload() -> None:
    """Modern generator returning a dict gets validation under existing key."""
    tool = SmartMovementTool()
    payload = {
        "movement_procedure": "Процедура ОбработкаПроведения() Экспорт КонецПроцедуры",
        "metadata_used": ["X.Y"],
    }
    with patch(
        "mcp_1c.tools.smart_tools.SmartGenerator"
    ) as mock_generator_cls, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=_ok_result()),
    ):
        mock_generator_cls.get_instance.return_value.generate_movement = (
            AsyncMock(return_value=payload)
        )
        result = await tool.execute(
            {
                "document_name": "Document.X",
                "register_name": "AccumulationRegister.Y",
            }
        )

    assert result["movement_procedure"] == payload["movement_procedure"]
    assert result["validation"]["validated"] is True


# ---------------------------------------------------------------------------
# SmartQueryTool — should NOT validate (queries aren't BSL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_query_does_not_run_bsl_validation() -> None:
    """Query language is a separate dialect — passing it through BSL-LS
    would produce false errors. Make sure we don't accidentally do that."""
    tool = SmartQueryTool()
    with patch(
        "mcp_1c.tools.smart_tools.SmartGenerator"
    ) as mock_generator_cls, patch(
        "mcp_1c.tools.smart_tools.validate_bsl",
        new=AsyncMock(return_value=_ok_result()),
    ) as mock_validate:
        mock_generator_cls.get_instance.return_value.generate_query = AsyncMock(
            return_value="ВЫБРАТЬ * ИЗ Document.X"
        )
        await tool.execute({"object_name": "Document.X"})

    mock_validate.assert_not_awaited()
