"""Closed-loop validation for code generators.

Smart and template-based code-generation tools (``smart-query``,
``generate-print``, …) currently emit text without checking whether
1С would accept it. This package wraps a generator with
:func:`validate_bsl`, which submits the generated BSL to
bsl-language-server (or the legacy CLI fallback) and returns
diagnostics. Phase 4 will extend this with an LLM retry loop;
the Phase 1.5 surface only validates and reports.
"""

from mcp_1c.engines.validation.loop import (
    ValidationDiagnostic,
    ValidationResult,
    validate_bsl,
)

__all__ = [
    "ValidationDiagnostic",
    "ValidationResult",
    "validate_bsl",
]
