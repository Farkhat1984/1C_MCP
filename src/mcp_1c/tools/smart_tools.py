"""
Smart generation tools (smart.*).

Metadata-aware tools that generate syntactically correct 1C code
by reading real object definitions from the configuration.

Each tool that produces BSL exposes an optional ``validate`` flag
(default ``true``). When set, the generated code is round-tripped
through bsl-language-server before being returned, and the result
includes structured diagnostics under ``validation``. The LLM
client can read the diagnostics and ask for a fix, closing the
"generated → submitted → broke" feedback gap.

Validation is **off** by default for ``smart-query``: query language
is a separate dialect that BSL-LS doesn't validate. The other two
generators (print form, movement code) emit BSL and turn it on.
"""

from __future__ import annotations

from typing import Any, ClassVar

from mcp_1c.engines.code import CodeEngine
from mcp_1c.engines.smart import SmartGenerator
from mcp_1c.engines.validation import ValidationResult, validate_bsl
from mcp_1c.tools.base import BaseTool, ToolError


def _validation_payload(result: ValidationResult) -> dict[str, Any]:
    """Compact serialization for inclusion in tool output.

    Splits diagnostics into errors and warnings so an LLM consuming
    the result doesn't have to filter; everything under "errors" is
    actionable and must be addressed before the code is shipped.
    """
    errors = [
        {
            "line": d.line,
            "column": d.column,
            "code": d.code,
            "message": d.message,
        }
        for d in result.diagnostics
        if d.severity == "error"
    ]
    warnings = [
        {
            "line": d.line,
            "column": d.column,
            "code": d.code,
            "message": d.message,
        }
        for d in result.diagnostics
        if d.severity == "warning"
    ]
    return {
        "validated": result.validated,
        "backend": result.backend,
        "error_count": result.error_count,
        "warning_count": result.warning_count,
        "errors": errors,
        "warnings": warnings,
    }


async def _validate_or_skip(
    code: str | None, *, requested: bool
) -> dict[str, Any] | None:
    """Run ``validate_bsl`` on demand; return ``None`` when skipped.

    Centralised because three tools need the same dance: skip when
    ``requested=False`` *or* when there's no string to validate.
    Failures inside ``validate_bsl`` are swallowed and logged — a
    flaky validator must not break a successful generation.
    """
    if not requested or not isinstance(code, str) or not code.strip():
        return None
    try:
        engine = CodeEngine.get_instance()
        result = await validate_bsl(code, code_engine=engine)
    except Exception:  # pragma: no cover — safety net for outages
        return {
            "validated": False,
            "backend": "none",
            "error_count": 0,
            "warning_count": 0,
            "errors": [],
            "warnings": [],
            "skipped_due_to": "validator_crashed",
        }
    return _validation_payload(result)


async def _extension_warnings_for(object_name: str) -> list[str]:
    """Surface a textual warning for each extension override of ``object_name``.

    1С specifics: when an extension `Adopts` (заимствует) or `Replaces`
    (замещает) an object, editing the typical-config source directly
    is the wrong action — the change must go through the extension
    file in Designer. The LLM client can act on this without parsing
    the structure, so we hand it pre-rendered Russian-language
    sentences pointing at the right tool ("Designer → Заимствование").

    Returns an empty list when:
    - ``object_name`` isn't ``Type.Name``-shaped;
    - the KG hasn't been built (``_load_or_fail`` raises);
    - no extensions override the target.

    All errors are swallowed: validation must never block a successful
    generation, and a missing KG just means we don't have the
    information yet — silence is safer than a misleading warning.
    """
    if not isinstance(object_name, str) or "." not in object_name:
        return []
    try:
        from mcp_1c.domain.graph import RelationshipType
        from mcp_1c.engines.knowledge_graph.engine import KnowledgeGraphEngine

        kg = KnowledgeGraphEngine.get_instance()
        graph = await kg._load_or_fail()  # noqa: SLF001
    except Exception:
        return []

    warnings: list[str] = []
    for rel, action in (
        (RelationshipType.EXTENSION_ADOPTS, "заимствован в расширении"),
        (RelationshipType.EXTENSION_REPLACES, "замещён в расширении"),
    ):
        for _edge, neighbor in graph.get_related(
            object_name, relationship=rel, direction="incoming"
        ):
            ext_name = neighbor.metadata.get("extension", "")
            warnings.append(
                f"Объект {object_name} {action} '{ext_name}'. "
                f"Правка через Designer → Заимствование, не напрямую."
            )
    return warnings


class SmartQueryTool(BaseTool):
    """Генерация запроса 1С по метаданным объекта."""

    name: ClassVar[str] = "smart-query"
    description: ClassVar[str] = (
        "Генерирует запрос на языке запросов 1С из реальных метаданных объекта конфигурации. "
        "Автоматически определяет типы реквизитов и разыменовывает ссылки через точку. "
        "Поддерживает включение табличных частей через LEFT JOIN.\n\n"
        "Примеры object_name: 'Document.ПриходТовара', 'Документ.ПриходТовара', "
        "'Catalog.Товары', 'Справочник.Товары'."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Полное имя объекта: Type.Name (Document.ПриходТовара или Документ.ПриходТовара)",
            },
            "include_tabular": {
                "type": "string",
                "description": "Имя табличной части для включения в запрос (необязательно)",
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Список конкретных полей для включения (необязательно, по умолчанию — все)",
            },
        },
        "required": ["object_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        generator = SmartGenerator.get_instance()
        try:
            return await generator.generate_query(
                arguments["object_name"],
                include_tabular=arguments.get("include_tabular"),
                fields=arguments.get("fields"),
            )
        except ValueError as e:
            raise ToolError(str(e), code="INVALID_INPUT") from e


class SmartPrintTool(BaseTool):
    """Генерация печатной формы по метаданным объекта."""

    name: ClassVar[str] = "smart-print"
    description: ClassVar[str] = (
        "Генерирует полную печатную форму по стандарту БСП: процедуру печати, "
        "код модуля менеджера, макет MXL и текст запроса. Все имена полей берутся "
        "из реальных метаданных объекта.\n\n"
        "Возвращает 4 артефакта: print_procedure, manager_module, mxl_template, query. "
        "При validate=true (по умолчанию) дополнительно проверяет процедуру печати "
        "через bsl-language-server и возвращает диагностики в поле validation."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "object_name": {
                "type": "string",
                "description": "Полное имя объекта: Type.Name (Document.ПриходТовара)",
            },
            "form_name": {
                "type": "string",
                "description": "Имя печатной формы (по умолчанию — имя объекта)",
            },
            "include_tabular": {
                "type": "boolean",
                "description": "Включить первую табличную часть (по умолчанию true)",
                "default": True,
            },
            "validate": {
                "type": "boolean",
                "description": (
                    "Прогнать сгенерированный BSL через bsl-language-server "
                    "и вернуть диагностики (по умолчанию true)."
                ),
                "default": True,
            },
        },
        "required": ["object_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        generator = SmartGenerator.get_instance()
        target = arguments["object_name"]
        try:
            artefacts = await generator.generate_print_form(
                target,
                include_tabular=arguments.get("include_tabular", True),
                form_name=arguments.get("form_name"),
            )
        except ValueError as e:
            raise ToolError(str(e), code="INVALID_INPUT") from e

        validation = await _validate_or_skip(
            artefacts.get("print_procedure")
            if isinstance(artefacts, dict)
            else None,
            requested=arguments.get("validate", True),
        )
        ext_warnings = await _extension_warnings_for(target)
        if isinstance(artefacts, dict):
            if validation is not None:
                artefacts["validation"] = validation
            if ext_warnings:
                # Don't clobber generator-emitted warnings; merge.
                existing = artefacts.get("warnings")
                if isinstance(existing, list):
                    artefacts["warnings"] = [*existing, *ext_warnings]
                else:
                    artefacts["warnings"] = ext_warnings
        return artefacts


class SmartMovementTool(BaseTool):
    """Генерация кода движений регистра по метаданным документа."""

    name: ClassVar[str] = "smart-movement"
    description: ClassVar[str] = (
        "Генерирует код формирования движений регистра из документа. "
        "Автоматически сопоставляет реквизиты документа с измерениями и ресурсами "
        "регистра по совпадению типов. Выбирает табличную часть с наибольшим числом совпадений.\n\n"
        "При необходимости генерирует код контроля остатков. При validate=true "
        "(по умолчанию) дополнительно проверяет сгенерированный код через "
        "bsl-language-server и возвращает диагностики."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "document_name": {
                "type": "string",
                "description": "Полное имя документа: Document.ПриходТовара",
            },
            "register_name": {
                "type": "string",
                "description": "Полное имя регистра: AccumulationRegister.ОстаткиТоваров",
            },
            "movement_type": {
                "type": "string",
                "enum": ["Приход", "Расход"],
                "description": "Вид движения (автоопределение если не указан)",
            },
            "validate": {
                "type": "boolean",
                "description": (
                    "Прогнать сгенерированный BSL через bsl-language-server "
                    "и вернуть диагностики (по умолчанию true)."
                ),
                "default": True,
            },
        },
        "required": ["document_name", "register_name"],
    }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        generator = SmartGenerator.get_instance()
        document_name = arguments["document_name"]
        register_name = arguments["register_name"]
        try:
            payload = await generator.generate_movement(
                document_name,
                register_name,
                movement_type=arguments.get("movement_type"),
            )
        except ValueError as e:
            raise ToolError(str(e), code="INVALID_INPUT") from e

        # Movement generator may return either a string (legacy) or a
        # dict with the procedure under a known key. Validate whichever
        # shape carries actual BSL.
        candidate: str | None = None
        if isinstance(payload, str):
            candidate = payload
        elif isinstance(payload, dict):
            for key in ("movement_procedure", "code", "bsl"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    candidate = value
                    break

        validation = await _validate_or_skip(
            candidate, requested=arguments.get("validate", True)
        )
        # Movement code touches both the document and the register;
        # warn if either is overridden by an extension.
        ext_warnings: list[str] = []
        for target in (document_name, register_name):
            ext_warnings.extend(await _extension_warnings_for(target))

        if validation is None and not ext_warnings:
            return payload
        if isinstance(payload, dict):
            if validation is not None:
                payload["validation"] = validation
            if ext_warnings:
                existing = payload.get("warnings")
                payload["warnings"] = (
                    [*existing, *ext_warnings] if isinstance(existing, list) else ext_warnings
                )
            return payload
        # String result: wrap so the caller can still find the code,
        # plus the new diagnostic envelope and any extension warnings.
        wrapped: dict[str, Any] = {"code": payload}
        if validation is not None:
            wrapped["validation"] = validation
        if ext_warnings:
            wrapped["warnings"] = ext_warnings
        return wrapped
