"""
Configuration tools for accessing 1C:Enterprise configuration objects.

Tools:
- config-objects - Consolidated tool for options, constants, scheduled jobs,
                   event subscriptions, exchanges, and HTTP services
- config.options - Get functional options  (legacy, kept for internal use)
- config.constants - Get constants  (legacy, kept for internal use)
- config.scheduled_jobs - Get scheduled jobs  (legacy, kept for internal use)
- config.event_subscriptions - Get event subscriptions  (legacy, kept for internal use)
- config.exchanges - Get exchange plans  (legacy, kept for internal use)
- config.http_services - Get HTTP services  (legacy, kept for internal use)
"""

from typing import Any, ClassVar

from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.metadata import MetadataEngine
from mcp_1c.tools.base import BaseTool, ToolError

# ---------------------------------------------------------------------------
# Type-to-MetadataType mapping for the consolidated tool
# ---------------------------------------------------------------------------

_CONFIG_OBJECT_TYPES: dict[str, MetadataType] = {
    "options": MetadataType.FUNCTIONAL_OPTION,
    "constants": MetadataType.CONSTANT,
    "scheduled_jobs": MetadataType.SCHEDULED_JOB,
    "event_subscriptions": MetadataType.EVENT_SUBSCRIPTION,
    "exchanges": MetadataType.EXCHANGE_PLAN,
    "http_services": MetadataType.HTTP_SERVICE,
}

_CONFIG_TYPE_LABELS: dict[str, str] = {
    "options": "FunctionalOption",
    "constants": "Constant",
    "scheduled_jobs": "ScheduledJob",
    "event_subscriptions": "EventSubscription",
    "exchanges": "ExchangePlan",
    "http_services": "HTTPService",
}


class ConfigObjectsTool(BaseTool):
    """Consolidated tool for querying configuration objects by type.

    Replaces six separate config-* tools with a single tool that dispatches
    by a required ``type`` parameter.
    """

    name: ClassVar[str] = "config-objects"
    description: ClassVar[str] = (
        "Get configuration objects (functional options, constants, scheduled jobs, "
        "event subscriptions, exchange plans, or HTTP services). "
        "Pass 'type' to select the kind of object and optionally 'name' to get details."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "options",
                    "constants",
                    "scheduled_jobs",
                    "event_subscriptions",
                    "exchanges",
                    "http_services",
                ],
                "description": (
                    "Kind of configuration object to retrieve: "
                    "options | constants | scheduled_jobs | event_subscriptions | exchanges | http_services"
                ),
            },
            "name": {
                "type": "string",
                "description": "Object name (optional — omit to list all objects of the given type)",
            },
        },
        "required": ["type"],
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Dispatch to the appropriate config object query."""
        obj_type: str = arguments["type"]
        name: str | None = arguments.get("name")

        metadata_type = _CONFIG_OBJECT_TYPES.get(obj_type)
        if metadata_type is None:
            raise ToolError(
                f"Unknown config object type: '{obj_type}'",
                code="INVALID_TYPE",
            )

        label = _CONFIG_TYPE_LABELS[obj_type]
        engine = self._engine

        if name:
            obj = await engine.get_object(metadata_type, name)
            if not obj:
                raise ToolError(
                    f"{label} '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            result: dict[str, Any] = {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
            }

            # Type-specific enrichment
            if obj_type == "constants" and obj.attributes:
                attr = obj.attributes[0]
                result["type_info"] = attr.type
                result["type_description"] = attr.type_description
            elif obj_type == "exchanges":
                result["attributes"] = [
                    {"name": a.name, "synonym": a.synonym, "type": a.type}
                    for a in obj.attributes
                ]
                result["tabular_sections"] = [
                    {"name": ts.name, "synonym": ts.synonym, "attributes_count": len(ts.attributes)}
                    for ts in obj.tabular_sections
                ]

            return result
        else:
            objects = await engine.list_objects(metadata_type)
            items = [
                {
                    "name": o.name,
                    "synonym": o.synonym,
                    "full_name": o.full_name,
                }
                for o in objects
            ]
            return {
                "type": label,
                "count": len(items),
                "objects": items,
            }


class ConfigOptionsTool(BaseTool):
    """Get functional options from configuration."""

    name: ClassVar[str] = "config-options"
    description: ClassVar[str] = (
        "Get functional options list or details of a specific option. "
        "Functional options control availability of configuration features."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Functional option name (optional, returns list if not specified)",
            },
            "include_usage": {
                "type": "boolean",
                "description": "Include usage information",
                "default": False,
            },
        },
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get functional options."""
        name = arguments.get("name")
        include_usage = arguments.get("include_usage", False)

        engine = self._engine

        if name:
            # Get specific functional option
            obj = await engine.get_object(MetadataType.FUNCTIONAL_OPTION, name)
            if not obj:
                raise ToolError(
                    f"Functional option '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            result: dict[str, Any] = {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
            }

            if include_usage:
                # Search for parameters associated with this option
                params = await engine.list_objects(MetadataType.FUNCTIONAL_OPTIONS_PARAMETER)
                result["related_parameters"] = [
                    {"name": p.name, "synonym": p.synonym}
                    for p in params
                ]

            return result
        else:
            # List all functional options
            options = await engine.list_objects(MetadataType.FUNCTIONAL_OPTION)
            return {
                "type": "FunctionalOption",
                "count": len(options),
                "options": [
                    {
                        "name": opt.name,
                        "synonym": opt.synonym,
                        "full_name": opt.full_name,
                    }
                    for opt in options
                ],
            }


class ConfigConstantsTool(BaseTool):
    """Get constants from configuration."""

    name: ClassVar[str] = "config-constants"
    description: ClassVar[str] = (
        "Get constants list or details of a specific constant. "
        "Constants store single values that are rarely changed."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Constant name (optional, returns list if not specified)",
            },
            "include_type": {
                "type": "boolean",
                "description": "Include type information",
                "default": True,
            },
        },
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get constants."""
        name = arguments.get("name")
        include_type = arguments.get("include_type", True)

        engine = self._engine

        if name:
            # Get specific constant
            obj = await engine.get_object(MetadataType.CONSTANT, name)
            if not obj:
                raise ToolError(
                    f"Constant '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            result: dict[str, Any] = {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
            }

            if include_type and obj.attributes:
                # Constants have type info in first attribute
                attr = obj.attributes[0]
                result["type"] = attr.type
                result["type_description"] = attr.type_description

            return result
        else:
            # List all constants
            constants = await engine.list_objects(MetadataType.CONSTANT)
            return {
                "type": "Constant",
                "count": len(constants),
                "constants": [
                    {
                        "name": const.name,
                        "synonym": const.synonym,
                        "full_name": const.full_name,
                    }
                    for const in constants
                ],
            }


class ConfigScheduledJobsTool(BaseTool):
    """Get scheduled jobs from configuration."""

    name: ClassVar[str] = "config-scheduled_jobs"
    description: ClassVar[str] = (
        "Get scheduled jobs list or details of a specific job. "
        "Scheduled jobs execute procedures on a schedule."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Scheduled job name (optional, returns list if not specified)",
            },
            "include_details": {
                "type": "boolean",
                "description": "Include detailed job configuration",
                "default": True,
            },
        },
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get scheduled jobs."""
        name = arguments.get("name")
        include_details = arguments.get("include_details", True)

        engine = self._engine

        if name:
            # Get specific scheduled job
            obj = await engine.get_object(MetadataType.SCHEDULED_JOB, name)
            if not obj:
                raise ToolError(
                    f"Scheduled job '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            result: dict[str, Any] = {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
            }

            if include_details:
                result["note"] = (
                    "Schedule and method details require additional XML parsing. "
                    "Use code.module to read the handler module."
                )

            return result
        else:
            # List all scheduled jobs
            jobs = await engine.list_objects(MetadataType.SCHEDULED_JOB)
            return {
                "type": "ScheduledJob",
                "count": len(jobs),
                "scheduled_jobs": [
                    {
                        "name": job.name,
                        "synonym": job.synonym,
                        "full_name": job.full_name,
                    }
                    for job in jobs
                ],
            }


class ConfigEventSubscriptionsTool(BaseTool):
    """Get event subscriptions from configuration."""

    name: ClassVar[str] = "config-event_subscriptions"
    description: ClassVar[str] = (
        "Get event subscriptions list or details of a specific subscription. "
        "Event subscriptions handle object events (OnWrite, BeforeWrite, etc.)."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Event subscription name (optional, returns list if not specified)",
            },
            "filter_event": {
                "type": "string",
                "description": "Filter by event type (e.g., 'ПриЗаписи', 'ПередЗаписью', 'OnWrite')",
            },
        },
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get event subscriptions."""
        name = arguments.get("name")
        filter_event = arguments.get("filter_event")

        engine = self._engine

        if name:
            # Get specific event subscription
            obj = await engine.get_object(MetadataType.EVENT_SUBSCRIPTION, name)
            if not obj:
                raise ToolError(
                    f"Event subscription '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            return {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
                "note": (
                    "Event, source, and handler details require additional XML parsing. "
                    "Use code.module to read the handler module."
                ),
            }
        else:
            # List all event subscriptions
            subscriptions = await engine.list_objects(MetadataType.EVENT_SUBSCRIPTION)

            # Apply filter if specified
            if filter_event:
                filter_lower = filter_event.lower()
                subscriptions = [
                    sub for sub in subscriptions
                    if filter_lower in sub.name.lower() or filter_lower in sub.synonym.lower()
                ]

            return {
                "type": "EventSubscription",
                "count": len(subscriptions),
                "filter": filter_event,
                "event_subscriptions": [
                    {
                        "name": sub.name,
                        "synonym": sub.synonym,
                        "full_name": sub.full_name,
                    }
                    for sub in subscriptions
                ],
            }


class ConfigExchangesTool(BaseTool):
    """Get exchange plans from configuration."""

    name: ClassVar[str] = "config-exchanges"
    description: ClassVar[str] = (
        "Get exchange plans list or details of a specific exchange plan. "
        "Exchange plans define data exchange between distributed databases."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Exchange plan name (optional, returns list if not specified)",
            },
            "include_content": {
                "type": "boolean",
                "description": "Include list of objects in exchange",
                "default": True,
            },
        },
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get exchange plans."""
        name = arguments.get("name")
        include_content = arguments.get("include_content", True)

        engine = self._engine

        if name:
            # Get specific exchange plan
            obj = await engine.get_object(MetadataType.EXCHANGE_PLAN, name)
            if not obj:
                raise ToolError(
                    f"Exchange plan '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            result: dict[str, Any] = {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
                "attributes": [
                    {"name": attr.name, "synonym": attr.synonym, "type": attr.type}
                    for attr in obj.attributes
                ],
                "tabular_sections": [
                    {
                        "name": ts.name,
                        "synonym": ts.synonym,
                        "attributes_count": len(ts.attributes),
                    }
                    for ts in obj.tabular_sections
                ],
            }

            if include_content:
                result["note"] = (
                    "Exchange content (objects and auto-registration settings) "
                    "require additional XML parsing."
                )

            return result
        else:
            # List all exchange plans
            exchanges = await engine.list_objects(MetadataType.EXCHANGE_PLAN)
            return {
                "type": "ExchangePlan",
                "count": len(exchanges),
                "exchange_plans": [
                    {
                        "name": ex.name,
                        "synonym": ex.synonym,
                        "full_name": ex.full_name,
                        "attributes_count": len(ex.attributes),
                    }
                    for ex in exchanges
                ],
            }


class ConfigHttpServicesTool(BaseTool):
    """Get HTTP services from configuration."""

    name: ClassVar[str] = "config-http_services"
    description: ClassVar[str] = (
        "Get HTTP services list or details of a specific service. "
        "HTTP services provide REST API endpoints."
    )
    input_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "HTTP service name (optional, returns list if not specified)",
            },
            "include_templates": {
                "type": "boolean",
                "description": "Include URL templates and methods",
                "default": True,
            },
        },
    }

    def __init__(self, engine: MetadataEngine) -> None:
        super().__init__()
        self._engine = engine

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Get HTTP services."""
        name = arguments.get("name")
        include_templates = arguments.get("include_templates", True)

        engine = self._engine

        if name:
            # Get specific HTTP service
            obj = await engine.get_object(MetadataType.HTTP_SERVICE, name)
            if not obj:
                raise ToolError(
                    f"HTTP service '{name}' not found",
                    code="OBJECT_NOT_FOUND",
                )

            result: dict[str, Any] = {
                "name": obj.name,
                "synonym": obj.synonym,
                "comment": obj.comment,
                "uuid": obj.uuid,
                "full_name": obj.full_name,
            }

            if include_templates:
                result["note"] = (
                    "URL templates, methods, and handlers require additional XML parsing. "
                    "Use code.module to read the service module."
                )

            return result
        else:
            # List all HTTP services
            services = await engine.list_objects(MetadataType.HTTP_SERVICE)
            return {
                "type": "HTTPService",
                "count": len(services),
                "http_services": [
                    {
                        "name": svc.name,
                        "synonym": svc.synonym,
                        "full_name": svc.full_name,
                    }
                    for svc in services
                ],
            }
