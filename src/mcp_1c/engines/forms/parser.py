"""
Parser for 1C managed-form XML (Form.xml).

Two on-disk layouts coexist in real configurations:

1. **Configurator export** — `<MetadataObject>/Forms/<FormName>/Ext/Form.xml`
   plus `<...>/Form/Module.bsl`. The XML uses the Form schema directly:

   ```xml
   <Form xmlns="http://v8.1c.ru/8.3/MDClasses">
     <Properties><Name>FormName</Name></Properties>
     <ChildItems>
       <Group name="..."/>
       <Button name="..."/>
       ...
     </ChildItems>
     <Attributes>
       <Attribute><Name>...</Name><MainAttribute>true</MainAttribute></Attribute>
     </Attributes>
     <Commands>...</Commands>
     <EventHandlers>...</EventHandlers>
   </Form>
   ```

2. **EDT export** — `<...>/Forms/<FormName>.form/Form.form` with a richer
   structured XML.

This parser handles both shapes by using element-name heuristics rather
than strict XPath, since real configurations vary. Unknown elements
become ``FormElementKind.UNKNOWN`` and are still surfaced in the tree.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from mcp_1c.domain.form import (
    FormAttribute,
    FormCommand,
    FormCommandInterface,
    FormElement,
    FormElementKind,
    FormEventHandler,
    FormStructure,
)
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.xml import safe_xml_parser

logger = get_logger(__name__)

_SECURE_PARSER = safe_xml_parser()

# Map of XML local-names to FormElementKind. Anything not listed becomes UNKNOWN.
_KIND_MAP = {
    "Group": FormElementKind.GROUP,
    "ContextMenu": FormElementKind.GROUP,
    "Pages": FormElementKind.PAGES,
    "Page": FormElementKind.PAGE,
    "InputField": FormElementKind.INPUT_FIELD,
    "LabelField": FormElementKind.LABEL_FIELD,
    "Field": FormElementKind.FIELD,
    "Button": FormElementKind.BUTTON,
    "Table": FormElementKind.TABLE,
    "CommandBar": FormElementKind.COMMAND_BAR,
    "Decoration": FormElementKind.DECORATION,
}

_CHILD_CONTAINERS = {"ChildItems", "ChildElements", "Items", "items"}


def _localname(tag: str) -> str:
    """Strip XML namespace from an element tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _text(elem: etree._Element | None, default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _find_local(elem: etree._Element, name: str) -> etree._Element | None:
    """Find first child by local-name (namespace-agnostic)."""
    for child in elem:
        if _localname(child.tag) == name:
            return child
    return None


def _find_all_local(elem: etree._Element, name: str) -> list[etree._Element]:
    return [child for child in elem if _localname(child.tag) == name]


class FormParser:
    """Parse a Form.xml file into a ``FormStructure``."""

    def parse(
        self,
        form_path: Path,
        object_type: str,
        object_name: str,
        form_name: str,
    ) -> FormStructure:
        """Parse ``form_path`` and return a structured representation.

        Args:
            form_path: Path to Form.xml.
            object_type: Owner metadata type (Catalog, Document, ...).
            object_name: Owner metadata name (Товары).
            form_name: Form name within the owner (ФормаСписка).
        """
        if not form_path.exists():
            raise FileNotFoundError(f"Form XML not found: {form_path}")

        tree = etree.parse(str(form_path), _SECURE_PARSER)
        root = tree.getroot()

        # The root might be <MetaDataObject><Form>...</Form></MetaDataObject>
        # or <Form> directly. Normalise to the inner <Form>.
        form_root = root if _localname(root.tag) == "Form" else _find_local(root, "Form")
        if form_root is None:
            # EDT-style: single <Form> root with namespace
            form_root = root

        structure = FormStructure(
            object_type=object_type,
            object_name=object_name,
            form_name=form_name,
            form_path=form_path,
        )

        props_elem = _find_local(form_root, "Properties")
        properties = props_elem if props_elem is not None else form_root
        title_elem = _find_local(properties, "Title")
        if title_elem is not None:
            v_node = _find_local(title_elem, "v")
            structure.title = _text(v_node if v_node is not None else title_elem)
        purpose_elem = _find_local(properties, "Purpose")
        if purpose_elem is not None:
            structure.purpose = _text(purpose_elem)

        structure.attributes = self._parse_attributes(form_root)
        structure.commands = self._parse_commands(form_root)
        structure.handlers = self._parse_handlers(form_root, owner="")
        structure.elements = self._parse_elements(form_root)
        structure.command_interface = self._parse_command_interface(form_root)
        return structure

    # ------------------------------------------------------------------
    def _parse_attributes(self, form_root: etree._Element) -> list[FormAttribute]:
        attrs_container = _find_local(form_root, "Attributes")
        if attrs_container is None:
            return []
        out: list[FormAttribute] = []
        for child in attrs_container:
            if _localname(child.tag) != "Attribute":
                continue
            name = _text(_find_local(child, "Name"))
            if not name:
                continue
            type_node = _find_local(child, "Type")
            type_str = self._extract_type(type_node)
            title = self._extract_title(_find_local(child, "Title"))
            main = _text(_find_local(child, "MainAttribute")).lower() == "true"
            save = _text(_find_local(child, "SaveData")).lower() == "true"
            attr = FormAttribute(
                name=name, type=type_str, title=title, main=main, save_data=save
            )
            columns_container = _find_local(child, "Columns")
            if columns_container is None:
                columns_container = _find_local(child, "Items")
            if columns_container is not None:
                attr.columns = [
                    FormAttribute(
                        name=_text(_find_local(c, "Name")) or "",
                        type=self._extract_type(_find_local(c, "Type")),
                    )
                    for c in columns_container
                    if _localname(c.tag) == "Attribute"
                    and _text(_find_local(c, "Name"))
                ]
            out.append(attr)
        return out

    def _parse_commands(self, form_root: etree._Element) -> list[FormCommand]:
        commands_container = _find_local(form_root, "Commands")
        if commands_container is None:
            return []
        out: list[FormCommand] = []
        for child in commands_container:
            if _localname(child.tag) != "Command":
                continue
            name = _text(_find_local(child, "Name"))
            if not name:
                continue
            title = self._extract_title(_find_local(child, "Title"))
            action = _text(_find_local(child, "Action"))
            use = _text(_find_local(child, "Use"))
            out.append(FormCommand(name=name, title=title, action=action, use=use))
        return out

    def _parse_handlers(
        self, owner_elem: etree._Element, owner: str
    ) -> list[FormEventHandler]:
        handlers_container = _find_local(owner_elem, "EventHandlers")
        if handlers_container is None:
            handlers_container = _find_local(owner_elem, "Events")
        if handlers_container is None:
            return []
        out: list[FormEventHandler] = []
        for handler in handlers_container:
            if _localname(handler.tag) not in {"EventHandler", "Handler", "Event"}:
                continue
            event = (
                _text(_find_local(handler, "Event"))
                or _text(_find_local(handler, "Name"))
                or handler.get("name", "")
            )
            procedure = (
                _text(_find_local(handler, "Procedure"))
                or _text(_find_local(handler, "Name"))
                or handler.get("procedure", "")
            )
            if not event:
                continue
            out.append(
                FormEventHandler(event=event, procedure=procedure, element=owner)
            )
        return out

    def _parse_elements(self, form_root: etree._Element) -> FormElement:
        root = FormElement(
            name="Form", kind=FormElementKind.GROUP, title="Form root"
        )
        for container_name in _CHILD_CONTAINERS:
            container = _find_local(form_root, container_name)
            if container is None:
                continue
            for child in container:
                node = self._build_element(child)
                if node is not None:
                    root.children.append(node)
            break  # only one container is expected
        return root

    def _build_element(self, elem: etree._Element) -> FormElement | None:
        local = _localname(elem.tag)
        kind = _KIND_MAP.get(local, FormElementKind.UNKNOWN)
        name = elem.get("name", "") or _text(_find_local(elem, "Name"))
        if not name and kind == FormElementKind.UNKNOWN:
            return None
        title = self._extract_title(_find_local(elem, "Title"))
        data_path = elem.get("DataPath", "") or _text(_find_local(elem, "DataPath"))
        node = FormElement(
            name=name or local,
            kind=kind,
            title=title,
            data_path=data_path,
            handlers=self._parse_handlers(elem, owner=name or local),
        )
        # Recurse into the conventional containers
        for container_name in _CHILD_CONTAINERS:
            container = _find_local(elem, container_name)
            if container is None:
                continue
            for child in container:
                sub = self._build_element(child)
                if sub is not None:
                    node.children.append(sub)
        return node

    def _parse_command_interface(
        self, form_root: etree._Element
    ) -> FormCommandInterface:
        ci = _find_local(form_root, "CommandInterface")
        if ci is None:
            return FormCommandInterface()

        def _names(container: etree._Element | None) -> list[str]:
            if container is None:
                return []
            out: list[str] = []
            for child in container:
                name = _text(_find_local(child, "Name")) or child.get("name", "")
                if name:
                    out.append(name)
            return out

        return FormCommandInterface(
            navigation_panel=_names(_find_local(ci, "NavigationPanel")),
            command_bar=_names(_find_local(ci, "CommandBar")),
        )

    @staticmethod
    def _extract_type(type_node: etree._Element | None) -> str:
        """Pull the textual type name from the <Type> XML block."""
        if type_node is None:
            return ""
        # Configurator format: <Type><Type>СправочникСсылка.Товары</Type></Type>
        inner = _find_local(type_node, "Type")
        if inner is not None and inner.text:
            return inner.text.strip()
        if type_node.text:
            return type_node.text.strip()
        return ""

    @staticmethod
    def _extract_title(title_node: etree._Element | None) -> str:
        """Title is normally <Title><v lang="ru">...</v></Title>."""
        if title_node is None:
            return ""
        for child in title_node:
            if _localname(child.tag) in {"v", "item"} and child.text:
                return child.text.strip()
        return _text(title_node)
