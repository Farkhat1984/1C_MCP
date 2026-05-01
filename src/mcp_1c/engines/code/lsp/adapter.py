"""Convert LSP ``documentSymbol`` payloads into :class:`Procedure` objects.

bsl-language-server returns a tree of LSP ``DocumentSymbol`` nodes. We
flatten it into a list shaped like our existing regex-based output so
the rest of the codebase doesn't care which extractor produced the
data — the swap stays local to the code engine.

LSP ``SymbolKind`` reference (subset we care about):
- 12 = Function    → ``is_function = True``
- 23 = Method      → procedure / function in BSL terms; treated as
  procedure unless the name suggests otherwise
- 14 = Constant
- 13 = Variable

bsl-language-server in practice emits ``Method`` for both Procedure
and Function declarations, distinguishing via ``detail`` (e.g.
``"Function (Export)"``). We use the detail string when present.
"""

from __future__ import annotations

from typing import Any

from mcp_1c.domain.code import Parameter, Procedure

# LSP SymbolKind constants — see
# https://microsoft.github.io/language-server-protocol/specifications/specification-current/#textDocument_documentSymbol
SYMBOL_KIND_FUNCTION = 12
SYMBOL_KIND_METHOD = 6
SYMBOL_KIND_CONSTRUCTOR = 9


def lsp_symbols_to_procedures(
    symbols: list[dict[str, Any]],
    *,
    source_lines: list[str] | None = None,
) -> list[Procedure]:
    """Flatten an LSP DocumentSymbol tree into our Procedure list.

    Recurses through ``children`` so nested constructs (BSL allows
    procedures inside ``#Область`` / ``#Region`` blocks but not inside
    other procedures, but we recurse anyway in case the server
    represents regions as parents).

    When ``source_lines`` is provided, we look at the signature line
    text to disambiguate Procedure vs Function and detect Export.
    bsl-language-server (verified against 0.29.0) emits ``kind=6``
    (Method) for **both** Procedure and Function with an empty
    ``detail`` field, so the kind+detail heuristic alone misclassifies
    every function as a procedure. Source-line peek fixes that with
    a single regex per symbol — cheap and accurate.
    """
    out: list[Procedure] = []
    for sym in symbols:
        proc = _to_procedure(sym, source_lines)
        if proc is not None:
            out.append(proc)
        for child in sym.get("children") or []:
            child_proc = _to_procedure(child, source_lines)
            if child_proc is not None:
                out.append(child_proc)
            for grand in child.get("children") or []:
                grand_proc = _to_procedure(grand, source_lines)
                if grand_proc is not None:
                    out.append(grand_proc)
    return out


def _to_procedure(
    sym: dict[str, Any],
    source_lines: list[str] | None,
) -> Procedure | None:
    """Convert a single DocumentSymbol to a Procedure, or skip it."""
    name = sym.get("name")
    if not isinstance(name, str) or not name:
        return None

    kind = sym.get("kind")
    if kind not in (
        SYMBOL_KIND_FUNCTION,
        SYMBOL_KIND_METHOD,
        SYMBOL_KIND_CONSTRUCTOR,
    ):
        return None

    range_ = sym.get("range") or {}
    selection = sym.get("selectionRange") or range_
    start = (range_.get("start") or {}).get("line")
    end = (range_.get("end") or {}).get("line")
    sig_line = (selection.get("start") or {}).get("line", start)

    if start is None:
        return None

    # LSP positions are 0-based; our Procedure uses 1-based lines.
    start_line = int(start) + 1
    end_line = int(end) + 1 if end is not None else start_line
    signature_line = int(sig_line) + 1 if sig_line is not None else start_line

    detail = sym.get("detail") or ""
    # First try the cheap heuristic from kind/detail; then upgrade
    # the answer with a source-line peek when we have it.
    is_function = _is_function(detail, kind)
    is_export = _is_export(detail)
    if source_lines is not None and 0 <= start_line - 1 < len(source_lines):
        sig_text = source_lines[start_line - 1]
        kind_from_text = _detect_kind_from_signature(sig_text)
        if kind_from_text is not None:
            is_function = kind_from_text == "function"
        if not is_export:
            is_export = _has_export_keyword(sig_text)

    return Procedure(
        name=name,
        is_function=is_function,
        is_export=is_export,
        directive=None,  # bsl-ls reports it via separate symbols; not needed here
        parameters=_parse_parameters(detail),
        start_line=start_line,
        end_line=end_line,
        signature_line=signature_line,
        body="",  # body extraction stays with the legacy reader for now
        signature=detail,
        comment="",
        region=None,
    )


def _is_function(detail: str, kind: int) -> bool:
    if kind == SYMBOL_KIND_FUNCTION:
        return True
    lower = detail.lower()
    return "function" in lower or "функция" in lower


def _is_export(detail: str) -> bool:
    lower = detail.lower()
    return "export" in lower or "экспорт" in lower


# Compiled once: BSL signature keywords are case-insensitive in the
# language but we lowercase the line first so plain ``in`` checks work.
def _detect_kind_from_signature(line: str) -> str | None:
    """Return ``"function"`` / ``"procedure"`` / ``None`` from a signature line.

    Looks for the BSL keywords ``Функция``/``Function`` and
    ``Процедура``/``Procedure``. Used as the authoritative source when
    bsl-language-server emits ``kind=Method`` without disambiguating
    detail (which is its actual behaviour as of 0.29.0).
    """
    lower = line.lstrip().lower()
    # Direct prefix match — handles ``Async`` directive and plain forms.
    for prefix in ("функция ", "function "):
        if lower.startswith(prefix) or lower.startswith("асинх " + prefix) or lower.startswith("async " + prefix):
            return "function"
    for prefix in ("процедура ", "procedure "):
        if lower.startswith(prefix) or lower.startswith("асинх " + prefix) or lower.startswith("async " + prefix):
            return "procedure"
    return None


def _has_export_keyword(line: str) -> bool:
    lower = line.lower()
    return " экспорт" in lower or " export" in lower


def _parse_parameters(detail: str) -> list[Parameter]:
    """Extract a parameter list from a ``detail`` string like
    ``"Function Name(Знач X, Y = Истина) Export"``.

    Best-effort. The detail format is server-specific and may carry no
    parens at all — in that case we return an empty list and let
    callers fall back to deeper extraction if they need it.
    """
    if "(" not in detail or ")" not in detail:
        return []
    inside = detail[detail.index("(") + 1 : detail.rindex(")")].strip()
    if not inside:
        return []
    params: list[Parameter] = []
    for raw in _split_top_level(inside, ","):
        token = raw.strip()
        if not token:
            continue
        by_value = False
        if token.lower().startswith(("знач ", "val ")):
            by_value = True
            token = token.split(None, 1)[1] if " " in token else ""
        default = None
        if "=" in token:
            head, _, default_part = token.partition("=")
            token = head.strip()
            default = default_part.strip()
        if not token:
            continue
        # Strip trailing ":Type" if BSL-LS adds it (it does in some builds).
        if ":" in token:
            token = token.split(":", 1)[0].strip()
        if not token:
            continue
        params.append(
            Parameter(
                name=token,
                by_value=by_value,
                default_value=default,
                is_optional=default is not None,
            )
        )
    return params


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split ``text`` by ``sep`` ignoring nested parens.

    Default values can contain calls like ``Тип("Строка")``; a naive
    split would treat the comma inside as a separator.
    """
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            out.append("".join(buf))
            buf.clear()
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


__all__ = ["lsp_symbols_to_procedures"]
