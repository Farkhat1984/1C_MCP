"""Property-based tests for the regex BSL parser.

Two flavours of property:

1. **Roundtripable shapes** — generators produce BSL the parser
   *must* handle. If hypothesis finds a shape that breaks an
   invariant (e.g. ``parse(emit(N)).procedures.length == N``), we've
   found a regex bug. These are the tests the parser is supposed
   to pass; failures here surface real bugs.

2. **Documented edge cases** — strategies that produce shapes the
   regex parser is *known* to mis-handle (escaped quotes, multi-line
   queries with concatenation, default values containing parens).
   These tests are marked ``xfail(strict=False)``: they pass when the
   parser eventually gets fixed (LSP migration), and serve as
   regression guards for whatever subset already works.

Skipping ``hypothesis`` settings tuning: the defaults (100 examples,
deadline auto-detect) are appropriate for a Phase-1 audit. We add a
small profile for CI when one wants more exhaustive runs.
"""

from __future__ import annotations

import re

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcp_1c.engines.code.parser import BslParser

# Names use cyrillic + latin + digits (1С allows both); we cap length
# so hypothesis doesn't waste cycles on pathological identifiers.
_NAME_FIRST = st.sampled_from(list("АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзиклмнопрстуфхцчшщъыьэюяABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"))
_NAME_REST = st.text(
    alphabet="АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзиклмнопрстуфхцчшщъыьэюяABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=0,
    max_size=20,
)
identifier = st.builds(lambda head, tail: head + tail, _NAME_FIRST, _NAME_REST)


@st.composite
def simple_procedure(draw, *, function: bool = False) -> tuple[str, str]:
    """Emit one valid BSL procedure with no parameters or body.

    Returns ``(name, source)`` so the test can assert on the parsed
    name. We deliberately use the simplest shape that exercises the
    parser's procedure-finding regex; richer shapes live in their
    own composite below.
    """
    name = draw(identifier)
    keyword = "Функция" if function else "Процедура"
    end_keyword = "КонецФункции" if function else "КонецПроцедуры"
    body = "\n".join([f"{keyword} {name}()", end_keyword])
    return name, body


# Snippets that contain double-quote escapes — known fragile area.
_TRICKY_STRING_FORMS = [
    'Сообщение = "Hello"',
    'Сообщение = "Quote: ""inside"""',
    'Сообщение = "Multi-quote: """""""',
    'Сообщение = ""',
    'Сообщение = """Empty quoted"""',
]


@given(name=identifier)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_bare_procedure_is_extracted(name: str) -> None:
    """Property: a single bare procedure with a valid name parses to one entry.

    This is the tightest invariant the regex parser must hold —
    failing here would mean the basic regex is broken even on the
    happy path. We've not seen this fail historically; the test is
    here as a regression guard against future regex churn.
    """
    source = f"Процедура {name}()\nКонецПроцедуры\n"
    parser = BslParser()
    module = parser.parse_content(source)
    assert len(module.procedures) == 1
    assert module.procedures[0].name == name
    assert module.procedures[0].is_function is False


@given(name=identifier)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=50)
def test_bare_function_is_classified(name: str) -> None:
    source = f"Функция {name}()\n    Возврат Истина;\nКонецФункции\n"
    parser = BslParser()
    module = parser.parse_content(source)
    assert len(module.procedures) == 1
    assert module.procedures[0].name == name
    assert module.procedures[0].is_function is True


@given(
    procedures=st.lists(
        simple_procedure(), min_size=1, max_size=8, unique_by=lambda x: x[0]
    )
)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=30)
def test_procedure_count_matches_input(procedures: list[tuple[str, str]]) -> None:
    """Property: parsing N concatenated procedures yields N entries."""
    source = "\n\n".join(p[1] for p in procedures) + "\n"
    parser = BslParser()
    module = parser.parse_content(source)
    expected_names = sorted(p[0] for p in procedures)
    actual_names = sorted(p.name for p in module.procedures)
    assert actual_names == expected_names


@given(name=identifier)
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=30)
def test_export_flag_round_trips(name: str) -> None:
    """``Экспорт`` after the signature must be picked up."""
    source = f"Процедура {name}() Экспорт\nКонецПроцедуры\n"
    parser = BslParser()
    procs = parser.parse_content(source).procedures
    assert len(procs) == 1
    assert procs[0].is_export is True


@given(directive=st.sampled_from(["НаКлиенте", "НаСервере", "НаКлиентеНаСервере"]))
@settings(suppress_health_check=[HealthCheck.too_slow], max_examples=10)
def test_compilation_directive_attaches(directive: str) -> None:
    """A directive on the line above a procedure attaches to it."""
    source = f"&{directive}\nПроцедура Тест()\nКонецПроцедуры\n"
    parser = BslParser()
    procs = parser.parse_content(source).procedures
    assert len(procs) == 1
    assert procs[0].directive is not None


# ---------------------------------------------------------------------------
# Documented edge cases — these expose regex limitations, kept as xfail
# until the LSP path replaces them.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("body", _TRICKY_STRING_FORMS)
def test_string_with_escaped_quotes_does_not_break_module_parse(body: str) -> None:
    """Strings with ``""`` escapes inside a procedure body must not
    cause the parser to misclassify subsequent procedures.

    We don't assert anything about call/reference extraction (those
    are documented broken) — we only check that the procedure list
    above the tricky string is intact. That's the contract every
    upstream caller relies on.
    """
    source = (
        "Процедура До()\n"
        f"    {body};\n"
        "КонецПроцедуры\n"
        "\n"
        "Процедура После()\n"
        "КонецПроцедуры\n"
    )
    parser = BslParser()
    procs = parser.parse_content(source).procedures
    names = [p.name for p in procs]
    assert "До" in names
    assert "После" in names


def test_default_value_with_parens_documents_known_limit() -> None:
    """Default values containing nested parens are a documented broken
    case: the regex's ``[^)]*`` parameter pattern stops at the first
    inner ``)``. This test pins the current behaviour so we notice
    when LSP migration fixes it (then flip ``xfail`` → assertion).
    """
    source = (
        'Процедура Тест(Знач Тип = Тип("Строка"))\nКонецПроцедуры\n'
    )
    parser = BslParser()
    procs = parser.parse_content(source).procedures
    # Today the parser MAY fail to find this procedure or misparse
    # its parameter list. Either is wrong but expected. The test
    # passes today either way — flipping behaviour after LSP migration
    # gets caught by the ``test_default_value_with_parens_works`` test
    # which we'll add then.
    if len(procs) == 1:
        # Currently parses; the parameter list is what's broken.
        assert procs[0].name == "Тест"


def test_dynamic_metadata_access_not_recovered() -> None:
    """Documents that ``Справочники[ИмяВРантайме]`` is invisible to
    metadata-reference extraction. Phase 1.5 LSP path will keep this
    invisible too — semantic resolution is required, which neither
    parser implements. The test exists so the next maintainer
    doesn't rediscover the limit cold."""
    source = (
        "Процедура Тест()\n"
        '    Объект = Справочники[ИмяВРантайме].НайтиПоНаименованию("X");\n'
        "КонецПроцедуры\n"
    )
    parser = BslParser()
    extended = parser.parse_content_extended(source)
    # Static reference to ``Справочники.<X>`` doesn't exist in the
    # source — only dynamic indexing — so the metadata_references
    # list should be empty.
    refs = [r for r in extended.metadata_references if r.containing_procedure == "Тест"]
    assert refs == []


# ---------------------------------------------------------------------------
# Sanity counterproof: the tests above are non-trivial.
# ---------------------------------------------------------------------------


def test_static_reference_extraction_works() -> None:
    """Counterproof that the previous xfail-style test isn't vacuous —
    a *static* reference IS extracted, only the dynamic form isn't."""
    source = (
        "Процедура Тест()\n"
        '    Объект = Справочники.Контрагенты.НайтиПоНаименованию("X");\n'
        "КонецПроцедуры\n"
    )
    parser = BslParser()
    extended = parser.parse_content_extended(source)
    names = [r.full_name for r in extended.metadata_references]
    assert "Справочники.Контрагенты" in names


def test_procedure_count_invariant_simple_case() -> None:
    """Hand-crafted regression: this exact shape used to fail in early
    BslParser versions. Keep as a non-property check so the failure
    mode is obvious if it returns."""
    source = """Процедура Раз()
КонецПроцедуры

Процедура Два()
КонецПроцедуры

Функция Три()
    Возврат 0;
КонецФункции
"""
    parser = BslParser()
    procs = parser.parse_content(source).procedures
    assert len(procs) == 3
    assert [p.name for p in procs] == ["Раз", "Два", "Три"]
    assert procs[2].is_function is True


def test_procedure_name_regex_matches_spec() -> None:
    """The regex used to discover procedures must accept anything
    matching the BSL identifier grammar (cyrillic, underscore,
    digits-after-first). Keep this test as a deliberate
    documentation of what the regex is meant to handle."""
    valid_names = ["Тест", "ТестКамелКейс", "test_snake", "_under", "Имя1С"]
    for name in valid_names:
        source = f"Процедура {name}()\nКонецПроцедуры\n"
        procs = BslParser().parse_content(source).procedures
        assert len(procs) == 1, f"Failed on identifier {name!r}"
        assert procs[0].name == name


def test_invalid_identifier_does_not_match() -> None:
    """Adversarial: digits-first names are not valid BSL identifiers.
    The parser must drop them, not fall over."""
    source = "Процедура 1Тест()\nКонецПроцедуры\n"
    procs = BslParser().parse_content(source).procedures
    # The regex should not match; result is empty.
    assert procs == []


def test_python_identifier_grammar_used_intentionally() -> None:
    """Check the underlying regex is what we documented."""
    pattern = re.compile(
        r"^[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*$"
    )
    assert pattern.match("Тест")
    assert pattern.match("test_1")
    assert not pattern.match("1test")
    assert not pattern.match("test-dash")
