"""
Domain models for 1C managed forms (Form.xml).

A 1C managed form is a structured XML document describing:
- A tree of UI elements (groups, fields, buttons, tables, ...)
- Form attributes (data items bound to UI fields)
- Commands and their event handlers
- The command interface (navigation panel, command bar)

These models are produced by ``engines/forms/parser.py`` and consumed by
``tools/form_tools.py``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FormElementKind(str, Enum):
    """Kinds of form elements supported by the 1C platform."""

    GROUP = "Group"
    FIELD = "Field"
    INPUT_FIELD = "InputField"
    LABEL_FIELD = "LabelField"
    BUTTON = "Button"
    TABLE = "Table"
    COMMAND_BAR = "CommandBar"
    PAGE = "Page"
    PAGES = "Pages"
    DECORATION = "Decoration"
    UNKNOWN = "Unknown"


class FormEventHandler(BaseModel):
    """Reference from a form element/command to a procedure in the form module."""

    event: str = Field(..., description="Event name, e.g. 'OnChange', 'OnClick'")
    procedure: str = Field(..., description="Procedure name in the form module")
    element: str = Field(default="", description="Owning element name (empty = form-level)")


class FormAttribute(BaseModel):
    """Reactive data attribute bound to form elements."""

    name: str
    type: str = Field(default="", description="1C type description")
    title: str = Field(default="", description="Synonym / displayed title")
    main: bool = Field(default=False, description="Main attribute (basic data of the form)")
    save_data: bool = Field(default=False, description="Persist between sessions")
    columns: list[FormAttribute] = Field(
        default_factory=list,
        description="Columns of a tabular attribute (DynamicList/ValueTable)",
    )


class FormCommand(BaseModel):
    """Form-level command bound to a button or shortcut."""

    name: str
    title: str = Field(default="")
    action: str = Field(default="", description="Procedure name in the form module")
    use: str = Field(default="", description="ForObject / ForBoth / ForServer")


class FormElement(BaseModel):
    """Node in the form element tree.

    The same model represents groups (which carry children) and leaf widgets
    (Field, Button, Decoration, ...). Distinguish via ``kind``.
    """

    name: str
    kind: FormElementKind = FormElementKind.UNKNOWN
    title: str = Field(default="")
    data_path: str = Field(default="", description="Bound attribute path (e.g. 'Object.Артикул')")
    visible: bool = True
    enabled: bool = True
    handlers: list[FormEventHandler] = Field(default_factory=list)
    children: list[FormElement] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=False)


class FormCommandInterface(BaseModel):
    """Aggregated command interface (navigation panel + command bar) entries."""

    navigation_panel: list[str] = Field(default_factory=list)
    command_bar: list[str] = Field(default_factory=list)


class FormStructure(BaseModel):
    """Parsed structure of a 1C managed form."""

    object_type: str = Field(..., description="Owner metadata type, e.g. 'Catalog'")
    object_name: str = Field(..., description="Owner metadata name, e.g. 'Товары'")
    form_name: str = Field(..., description="Form name, e.g. 'ФормаСписка'")
    form_path: Path = Field(..., description="Path to the parsed Form.xml file")
    title: str = Field(default="")
    purpose: str = Field(default="", description="Form purpose declared in metadata")
    attributes: list[FormAttribute] = Field(default_factory=list)
    commands: list[FormCommand] = Field(default_factory=list)
    handlers: list[FormEventHandler] = Field(
        default_factory=list,
        description="Form-level handlers (OnCreateAtServer, BeforeWriteAtServer, ...)",
    )
    elements: FormElement = Field(
        default_factory=lambda: FormElement(
            name="Form", kind=FormElementKind.GROUP
        ),
        description="Root of the element tree",
    )
    command_interface: FormCommandInterface = Field(default_factory=FormCommandInterface)

    @property
    def full_name(self) -> str:
        return f"{self.object_type}.{self.object_name}.Form.{self.form_name}"


# Allow self-reference in nested element/attribute trees
FormElement.model_rebuild()
FormAttribute.model_rebuild()
