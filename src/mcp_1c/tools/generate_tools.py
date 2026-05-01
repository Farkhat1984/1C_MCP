"""
Code generation tools (generate.*).

Tools for generating 1C code from templates with optional BSL LS validation.
"""

import tempfile
from pathlib import Path
from typing import Any, ClassVar

from mcp_1c.engines.code.bsl_ls import BslLanguageServer
from mcp_1c.engines.templates import get_template_engine
from mcp_1c.tools.base import BaseTool


async def validate_generated_code(code: str) -> dict[str, Any]:
    """
    Validate generated BSL code using BSL Language Server.

    Args:
        code: Generated BSL code

    Returns:
        Validation result dict
    """
    bsl_ls = BslLanguageServer.get_instance()

    # Create temporary file for validation
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".bsl",
        delete=False,
        encoding="utf-8-sig",
    ) as tmp:
        tmp.write(code)
        tmp.flush()
        tmp_path = Path(tmp.name)

    try:
        result = await bsl_ls.validate_file(tmp_path)
        return {
            "valid": result.valid,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "diagnostics": [
                {
                    "code": d.code,
                    "message": d.message,
                    "severity": d.severity.value,
                    "line": d.line,
                }
                for d in result.diagnostics
            ],
        }
    finally:
        tmp_path.unlink(missing_ok=True)


class GenerateQueryTool(BaseTool):
    """Generate 1C query from template."""

    name: ClassVar[str] = "generate-query"
    description: ClassVar[str] = """
Generate 1C query code from a template.

Available query templates:
- query.select_simple: Basic SELECT query
- query.select_with_join: SELECT with LEFT JOIN
- query.select_grouped: SELECT with GROUP BY
- query.register_slice_last: Information register slice last
- query.accumulation_balance: Accumulation register balance
- query.accumulation_turnovers: Accumulation register turnovers
- query.batch_query: Batch query with temp table
- query.select_top: SELECT TOP N
- query.select_distinct: SELECT DISTINCT
- query.union: UNION of queries
- query.subquery_in: Subquery with IN
- query.full_text_search: Full-text search

Pass template_id and values dictionary with placeholder values.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Query template ID (e.g., 'query.select_simple')",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values (e.g., {'TableName': 'Справочник.Номенклатура', 'Fields': 'Ссылка, Наименование'})",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate query code."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate(template_id, values)

        response = {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "suggestions": result.suggestions,
            "error": result.error,
            "missing_placeholders": result.missing_placeholders,
        }

        # Validate if requested and generation succeeded
        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GenerateHandlerTool(BaseTool):
    """Generate 1C event handler from template."""

    name: ClassVar[str] = "generate-handler"
    description: ClassVar[str] = """
Generate 1C event handler code from a template.

Available handler templates:
- handler.before_write: BeforeWrite event handler
- handler.on_write: OnWrite event handler
- handler.filling: Filling event handler
- handler.posting: Document posting handler
- handler.undo_posting: Undo posting handler
- handler.before_delete: BeforeDelete handler
- handler.filling_check: Filling check handler
- handler.on_copy: OnCopy handler
- handler.presentation_get: Presentation get handler
- handler.form_on_create: Form OnCreateAtServer handler

Pass template_id and values dictionary with placeholder values.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Handler template ID (e.g., 'handler.before_write')",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate handler code."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate(template_id, values)

        response = {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GeneratePrintTool(BaseTool):
    """Generate 1C print form code from template."""

    name: ClassVar[str] = "generate-print"
    description: ClassVar[str] = """
Generate 1C print form code from a template.

Available print form templates:
- print.basic: Basic print form
- print.with_query: Print form with data query
- print.commands_module: Print commands module

Pass template_id and values dictionary.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Print form template ID (e.g., 'print.basic')",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate print form code."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate(template_id, values)

        response = {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GenerateMovementTool(BaseTool):
    """Generate 1C register movement code from template."""

    name: ClassVar[str] = "generate-movement"
    description: ClassVar[str] = """
Generate 1C register movement code from a template.

Available movement templates:
- movement.accumulation_income: Income movement for accumulation register
- movement.accumulation_expense: Expense movement for accumulation register
- movement.accumulation_turnovers: Movement for turnovers register
- movement.information_register: Information register movement
- movement.independent_information_register: Independent info register write
- movement.posting_full: Full document posting handler
- movement.control_balance: Balance control in posting

Pass template_id and values dictionary.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Movement template ID (e.g., 'movement.accumulation_income')",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate movement code."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate(template_id, values)

        response = {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GenerateApiTool(BaseTool):
    """Generate 1C API code from template."""

    name: ClassVar[str] = "generate-api"
    description: ClassVar[str] = """
Generate 1C API code from a template.

Available API templates:
- api.http_service_get: HTTP Service GET method
- api.http_service_post: HTTP Service POST method
- api.common_module_export: Export function in common module
- api.web_service_operation: Web service SOAP operation
- api.json_helper: JSON helper functions
- api.subscription_handler: Event subscription handler
- api.scheduled_job: Scheduled job handler

Pass template_id and values dictionary.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "API template ID (e.g., 'api.http_service_get')",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate API code."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate(template_id, values)

        response = {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GenerateFormHandlerTool(BaseTool):
    """Generate 1C form handler code."""

    name: ClassVar[str] = "generate-form_handler"
    description: ClassVar[str] = """
Generate 1C form handler code from a template.

Use handler.form_on_create or other form-related handler templates.

Pass template_id and values dictionary.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "template_id": {
                "type": "string",
                "description": "Form handler template ID",
            },
            "values": {
                "type": "object",
                "description": "Placeholder values",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["template_id", "values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate form handler code."""
        template_id = arguments["template_id"]
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate(template_id, values)

        response = {
            "success": result.success,
            "code": result.code,
            "template_id": result.template_id,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GenerateSubscriptionTool(BaseTool):
    """Generate 1C event subscription handler."""

    name: ClassVar[str] = "generate-subscription"
    description: ClassVar[str] = """
Generate 1C event subscription handler code.

Use api.subscription_handler template.

Pass values with: SubscriptionName, Sources, EventName, HandlerName, HandlerCode.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "values": {
                "type": "object",
                "description": "Placeholder values for subscription handler",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate subscription handler code."""
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate("api.subscription_handler", values)

        response = {
            "success": result.success,
            "code": result.code,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response


class GenerateScheduledJobTool(BaseTool):
    """Generate 1C scheduled job handler."""

    name: ClassVar[str] = "generate-scheduled_job"
    description: ClassVar[str] = """
Generate 1C scheduled job handler code.

Use api.scheduled_job template.

Pass values with: JobName, HandlerName, JobCode, HasLogging, LogEventName.
"""
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "values": {
                "type": "object",
                "description": "Placeholder values for scheduled job handler",
            },
            "validate": {
                "type": "boolean",
                "description": "Validate generated code using BSL Language Server",
                "default": False,
            },
        },
        "required": ["values"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._engine = get_template_engine()

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Generate scheduled job handler code."""
        values = arguments.get("values", {})
        should_validate = arguments.get("validate", False)

        result = self._engine.generate("api.scheduled_job", values)

        response = {
            "success": result.success,
            "code": result.code,
            "warnings": result.warnings,
            "error": result.error,
        }

        if should_validate and result.success and result.code:
            response["validation"] = await validate_generated_code(result.code)

        return response
