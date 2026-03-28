"""
Code domain models.

Represents BSL (1C:Enterprise Script Language) code elements.
"""

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class CompilationDirective(str, Enum):
    """BSL compilation directives."""

    AT_SERVER = "&НаСервере"
    AT_CLIENT = "&НаКлиенте"
    AT_SERVER_WITHOUT_CONTEXT = "&НаСервереБезКонтекста"
    AT_CLIENT_AT_SERVER = "&НаКлиентеНаСервере"
    AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT = "&НаКлиентеНаСервереБезКонтекста"

    # English variants
    AT_SERVER_EN = "&AtServer"
    AT_CLIENT_EN = "&AtClient"
    AT_SERVER_WITHOUT_CONTEXT_EN = "&AtServerNoContext"
    AT_CLIENT_AT_SERVER_EN = "&AtClientAtServer"
    AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT_EN = "&AtClientAtServerNoContext"

    @classmethod
    def from_string(cls, value: str) -> "CompilationDirective | None":
        """Parse directive from string."""
        normalized = value.strip()
        for directive in cls:
            if directive.value.lower() == normalized.lower():
                return directive
        return None

    def is_server(self) -> bool:
        """Check if directive runs on server."""
        return self in (
            self.AT_SERVER,
            self.AT_SERVER_EN,
            self.AT_SERVER_WITHOUT_CONTEXT,
            self.AT_SERVER_WITHOUT_CONTEXT_EN,
            self.AT_CLIENT_AT_SERVER,
            self.AT_CLIENT_AT_SERVER_EN,
            self.AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT,
            self.AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT_EN,
        )

    def is_client(self) -> bool:
        """Check if directive runs on client."""
        return self in (
            self.AT_CLIENT,
            self.AT_CLIENT_EN,
            self.AT_CLIENT_AT_SERVER,
            self.AT_CLIENT_AT_SERVER_EN,
            self.AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT,
            self.AT_CLIENT_AT_SERVER_WITHOUT_CONTEXT_EN,
        )


class Region(BaseModel):
    """Code region (#Region ... #EndRegion)."""

    name: str = Field(..., description="Region name")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    nested_regions: list["Region"] = Field(
        default_factory=list,
        description="Nested regions",
    )


class Parameter(BaseModel):
    """Procedure/function parameter."""

    name: str = Field(..., description="Parameter name")
    by_value: bool = Field(
        default=False,
        description="Passed by value (Знач)",
    )
    default_value: str | None = Field(
        default=None,
        description="Default value if optional",
    )
    is_optional: bool = Field(default=False, description="Is optional")


class Procedure(BaseModel):
    """Procedure or function definition."""

    name: str = Field(..., description="Procedure/function name")
    is_function: bool = Field(
        default=False,
        description="True if function, False if procedure",
    )
    is_export: bool = Field(default=False, description="Has Export keyword")
    directive: CompilationDirective | None = Field(
        default=None,
        description="Compilation directive",
    )
    parameters: list[Parameter] = Field(
        default_factory=list,
        description="Parameters",
    )

    # Location in file
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    signature_line: int = Field(..., description="Signature line number")

    # Code content
    body: str = Field(default="", description="Full body text")
    signature: str = Field(default="", description="Signature line")

    # Documentation
    comment: str = Field(default="", description="Documentation comment")

    # Containing region
    region: str | None = Field(
        default=None,
        description="Containing region name",
    )

    @property
    def is_async(self) -> bool:
        """Check if this is async procedure (by naming convention)."""
        async_prefixes = ("Асинх", "Async")
        return any(self.name.startswith(prefix) for prefix in async_prefixes)


class BslModule(BaseModel):
    """Parsed BSL module."""

    path: Path = Field(..., description="Path to .bsl file")
    content: str = Field(default="", description="Full module content")

    # Parsed elements
    procedures: list[Procedure] = Field(
        default_factory=list,
        description="Procedures and functions",
    )
    regions: list[Region] = Field(
        default_factory=list,
        description="Code regions",
    )

    # Module info
    line_count: int = Field(default=0, description="Total line count")
    encoding: str = Field(default="utf-8-sig", description="File encoding")

    # Owner information
    owner_type: str = Field(default="", description="Owner metadata type")
    owner_name: str = Field(default="", description="Owner object name")
    module_type: str = Field(default="", description="Module type")

    def get_procedure(self, name: str) -> Procedure | None:
        """Find procedure by name (case-insensitive)."""
        name_lower = name.lower()
        for proc in self.procedures:
            if proc.name.lower() == name_lower:
                return proc
        return None

    def get_procedures_in_region(self, region_name: str) -> list[Procedure]:
        """Get all procedures in a specific region."""
        return [
            proc
            for proc in self.procedures
            if proc.region and proc.region.lower() == region_name.lower()
        ]

    def get_exported_procedures(self) -> list[Procedure]:
        """Get all exported procedures and functions."""
        return [proc for proc in self.procedures if proc.is_export]

    def get_server_procedures(self) -> list[Procedure]:
        """Get all server-side procedures."""
        return [
            proc
            for proc in self.procedures
            if proc.directive and proc.directive.is_server()
        ]

    def get_client_procedures(self) -> list[Procedure]:
        """Get all client-side procedures."""
        return [
            proc
            for proc in self.procedures
            if proc.directive and proc.directive.is_client()
        ]


class CodeLocation(BaseModel):
    """Location of code element."""

    file_path: Path = Field(..., description="File path")
    line: int = Field(..., description="Line number")
    column: int = Field(default=0, description="Column number")
    end_line: int | None = Field(default=None, description="End line")
    end_column: int | None = Field(default=None, description="End column")

    def __str__(self) -> str:
        """Format as file:line."""
        return f"{self.file_path}:{self.line}"


class CodeReference(BaseModel):
    """Reference to code element (for usages/definitions)."""

    location: CodeLocation = Field(..., description="Code location")
    context: str = Field(default="", description="Surrounding context")
    reference_type: str = Field(
        default="usage",
        description="Type: usage, definition, declaration",
    )


# =============================================================================
# Phase 2: Advanced parsing models
# =============================================================================


class MethodCall(BaseModel):
    """Method call extracted from code."""

    name: str = Field(..., description="Method name being called")
    object_name: str | None = Field(
        default=None,
        description="Object on which method is called (e.g., 'СправочникМенеджер')",
    )
    arguments_text: str = Field(default="", description="Raw arguments text")
    argument_count: int = Field(default=0, description="Number of arguments")
    line: int = Field(..., description="Line number")
    column: int = Field(default=0, description="Column number")

    # Context
    containing_procedure: str | None = Field(
        default=None,
        description="Procedure/function containing this call",
    )
    is_async_call: bool = Field(
        default=False,
        description="Is async call (uses Ждать/Await)",
    )


class MetadataReferenceType(str, Enum):
    """Types of metadata references in code."""

    CATALOG = "Catalog"  # Справочники
    DOCUMENT = "Document"  # Документы
    ENUM = "Enum"  # Перечисления
    REPORT = "Report"  # Отчёты
    DATA_PROCESSOR = "DataProcessor"  # Обработки
    INFORMATION_REGISTER = "InformationRegister"  # РегистрыСведений
    ACCUMULATION_REGISTER = "AccumulationRegister"  # РегистрыНакопления
    CALCULATION_REGISTER = "CalculationRegister"  # РегистрыРасчёта
    ACCOUNTING_REGISTER = "AccountingRegister"  # РегистрыБухгалтерии
    BUSINESS_PROCESS = "BusinessProcess"  # БизнесПроцессы
    TASK = "Task"  # Задачи
    CHART_OF_ACCOUNTS = "ChartOfAccounts"  # ПланыСчетов
    CHART_OF_CHARACTERISTIC_TYPES = "ChartOfCharacteristicTypes"  # ПланыВидовХарактеристик
    CHART_OF_CALCULATION_TYPES = "ChartOfCalculationTypes"  # ПланыВидовРасчёта
    EXCHANGE_PLAN = "ExchangePlan"  # ПланыОбмена
    CONSTANT = "Constant"  # Константы
    SEQUENCE = "Sequence"  # Последовательности
    WEB_SERVICE = "WebService"  # WebСервисы
    HTTP_SERVICE = "HTTPService"  # HTTPСервисы
    COMMON_MODULE = "CommonModule"  # ОбщиеМодули
    SESSION_PARAMETER = "SessionParameter"  # ПараметрыСеанса
    FUNCTIONAL_OPTION = "FunctionalOption"  # ФункциональныеОпции
    DEFINED_TYPE = "DefinedType"  # ОпределяемыеТипы
    COMMON_ATTRIBUTE = "CommonAttribute"  # ОбщиеРеквизиты
    SUBSYSTEM = "Subsystem"  # Подсистемы
    UNKNOWN = "Unknown"


class MetadataReference(BaseModel):
    """Reference to metadata object in code."""

    reference_type: MetadataReferenceType = Field(
        ...,
        description="Type of metadata reference",
    )
    object_name: str = Field(..., description="Object name (e.g., 'Номенклатура')")
    full_name: str = Field(
        ...,
        description="Full reference (e.g., 'Справочники.Номенклатура')",
    )
    access_type: str = Field(
        default="manager",
        description="Access type: manager, ref, selection, object",
    )
    line: int = Field(..., description="Line number")
    column: int = Field(default=0, description="Column number")

    # Context
    containing_procedure: str | None = Field(
        default=None,
        description="Procedure/function containing this reference",
    )


class VariableUsage(BaseModel):
    """Variable usage in code."""

    name: str = Field(..., description="Variable name")
    line: int = Field(..., description="Line number")
    column: int = Field(default=0, description="Column number")
    is_assignment: bool = Field(
        default=False,
        description="Is this an assignment (left side of =)",
    )
    containing_procedure: str | None = Field(
        default=None,
        description="Procedure/function containing this usage",
    )


class QueryReference(BaseModel):
    """Query found in code."""

    query_text: str = Field(..., description="Query text")
    start_line: int = Field(..., description="Start line number")
    end_line: int = Field(..., description="End line number")
    tables: list[str] = Field(
        default_factory=list,
        description="Tables referenced in query",
    )
    containing_procedure: str | None = Field(
        default=None,
        description="Procedure/function containing this query",
    )


class DependencyEdge(BaseModel):
    """Edge in dependency graph."""

    source: str = Field(..., description="Source node (caller)")
    target: str = Field(..., description="Target node (callee)")
    edge_type: str = Field(
        default="calls",
        description="Edge type: calls, uses_metadata, uses_module",
    )
    count: int = Field(default=1, description="Number of references")
    locations: list[CodeLocation] = Field(
        default_factory=list,
        description="Locations of references",
    )


class DependencyGraph(BaseModel):
    """Graph of dependencies."""

    nodes: dict[str, dict] = Field(
        default_factory=dict,
        description="Nodes: procedure/module -> metadata",
    )
    edges: list[DependencyEdge] = Field(
        default_factory=list,
        description="Edges between nodes",
    )

    def add_node(self, name: str, node_type: str, metadata: dict | None = None) -> None:
        """Add node to graph."""
        self.nodes[name] = {
            "type": node_type,
            "metadata": metadata or {},
        }

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str = "calls",
        location: CodeLocation | None = None,
    ) -> None:
        """Add or update edge in graph."""
        # Find existing edge
        for edge in self.edges:
            if edge.source == source and edge.target == target and edge.edge_type == edge_type:
                edge.count += 1
                if location:
                    edge.locations.append(location)
                return

        # Create new edge
        edge = DependencyEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            count=1,
            locations=[location] if location else [],
        )
        self.edges.append(edge)

    def get_callees(self, node: str) -> list[str]:
        """Get all nodes called by given node."""
        return [e.target for e in self.edges if e.source == node]

    def get_callers(self, node: str) -> list[str]:
        """Get all nodes that call given node."""
        return [e.source for e in self.edges if e.target == node]

    def get_dependencies(
        self,
        node: str,
        depth: int = 1,
        _visited: set[str] | None = None,
    ) -> dict:
        """Get dependency tree for node with cycle detection.

        Args:
            node: Node identifier
            depth: Maximum recursion depth
            _visited: Internal set tracking visited nodes to prevent cycles
        """
        if _visited is None:
            _visited = set()

        if depth <= 0 or node in _visited:
            return {"node": node, "callees": [], "callers": []}

        _visited.add(node)

        callees = []
        for callee in self.get_callees(node):
            if depth > 1:
                callees.append(self.get_dependencies(callee, depth - 1, _visited))
            else:
                callees.append({"node": callee})

        callers = []
        for caller in self.get_callers(node):
            if depth > 1:
                callers.append(self.get_dependencies(caller, depth - 1, _visited))
            else:
                callers.append({"node": caller})

        return {
            "node": node,
            "callees": callees,
            "callers": callers,
        }


class ExtendedBslModule(BslModule):
    """Extended BSL module with Phase 2 analysis."""

    method_calls: list[MethodCall] = Field(
        default_factory=list,
        description="Method calls found in module",
    )
    metadata_references: list[MetadataReference] = Field(
        default_factory=list,
        description="Metadata references found in module",
    )
    variable_usages: list[VariableUsage] = Field(
        default_factory=list,
        description="Variable usages found in module",
    )
    queries: list[QueryReference] = Field(
        default_factory=list,
        description="Queries found in module",
    )

    def get_calls_in_procedure(self, procedure_name: str) -> list[MethodCall]:
        """Get all method calls in a procedure."""
        return [
            call
            for call in self.method_calls
            if call.containing_procedure
            and call.containing_procedure.lower() == procedure_name.lower()
        ]

    def get_metadata_in_procedure(self, procedure_name: str) -> list[MetadataReference]:
        """Get all metadata references in a procedure."""
        return [
            ref
            for ref in self.metadata_references
            if ref.containing_procedure
            and ref.containing_procedure.lower() == procedure_name.lower()
        ]

    def get_unique_called_methods(self) -> list[str]:
        """Get list of unique method names called."""
        return list({call.name for call in self.method_calls})

    def get_unique_metadata_objects(self) -> list[str]:
        """Get list of unique metadata objects referenced."""
        return list({ref.full_name for ref in self.metadata_references})
