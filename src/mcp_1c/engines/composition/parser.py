"""
Parser for 1C DataCompositionSchema (СКД) XML.

Reports in 1C store their layout in a DataCompositionSchema document — a
non-trivial XML format with namespaces under ``http://v8.1c.ru/8.1/...``.
This parser is intentionally tolerant: real schemas vary, especially
between Configurator and EDT exports, and we only need a useful subset
(data sets, fields, parameters, resources, settings).

Only the surface structure is extracted. Deep query parsing (joins,
groupings, virtual tables) belongs to the existing query engine.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from mcp_1c.domain.composition import (
    CompositionDataSet,
    CompositionField,
    CompositionParameter,
    CompositionResource,
    CompositionSettings,
    DataCompositionSchema,
    DataSetKind,
)
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.xml import safe_xml_parser

logger = get_logger(__name__)

_SECURE_PARSER = safe_xml_parser()

_DATASET_KIND_MAP = {
    "DataSetQuery": DataSetKind.QUERY,
    "DataSetObject": DataSetKind.OBJECT,
    "DataSetUnion": DataSetKind.UNION,
}


def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(elem: etree._Element | None, default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _ci_eq(a: str, b: str) -> bool:
    """Case-insensitive equality.

    Real 8.3 DCS exports use lower camelCase (``dataSet``, ``totalField``)
    while older docs and unit tests use Pascal case (``DataSet``,
    ``TotalField``). We accept both — the schema is unambiguous.
    """
    return a.lower() == b.lower()


def _find_local(elem: etree._Element, name: str) -> etree._Element | None:
    """Case-insensitive local-name lookup.

    1С DataCompositionSchema uses camelCase (``<dataSet>``, ``<dataPath>``)
    while EDT-style exports may use PascalCase. Match either by
    comparing case-folded names so the parser handles both layouts.
    """
    for child in elem:
        if _ci_eq(_localname(child.tag), name):
            return child
    return None


def _find_all_local(elem: etree._Element, name: str) -> list[etree._Element]:
    return [child for child in elem if _ci_eq(_localname(child.tag), name)]


_XSI_TYPE_KEY = "{http://www.w3.org/2001/XMLSchema-instance}type"


def _xsi_type(elem: etree._Element) -> str:
    return elem.get(_XSI_TYPE_KEY, "")


def _extract_local_string(elem: etree._Element | None) -> str:
    """Read a 1C ``LocalStringType`` element.

    The shape is ``<title><v8:item><v8:lang>ru</v8:lang><v8:content>...
    </v8:content></v8:item></title>``. We pick the ``ru`` content when
    present, otherwise fall back to the first ``<content>`` we find, and
    finally to the bare element text for non-localised strings.
    """
    if elem is None:
        return ""
    items = _find_all_local(elem, "item")
    fallback = ""
    for item in items:
        lang_node = _find_local(item, "lang")
        content_node = _find_local(item, "content")
        if content_node is None or content_node.text is None:
            continue
        text = content_node.text.strip()
        if lang_node is not None and (lang_node.text or "").strip().lower() == "ru":
            return text
        fallback = fallback or text
    if fallback:
        return fallback
    return _text(elem)


class CompositionParser:
    """Parse a DataCompositionSchema XML into a structured representation."""

    def parse(
        self,
        schema_path: Path,
        object_type: str,
        object_name: str,
        schema_name: str = "MainSchema",
    ) -> DataCompositionSchema:
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema XML not found: {schema_path}")

        tree = etree.parse(str(schema_path), _SECURE_PARSER)
        root = tree.getroot()
        schema_elem = (
            root if _localname(root.tag) == "DataCompositionSchema" else root
        )

        schema = DataCompositionSchema(
            object_type=object_type,
            object_name=object_name,
            schema_name=schema_name,
            schema_path=schema_path,
        )

        title_elem = _find_local(schema_elem, "Title")
        if title_elem is not None:
            schema.title = _text(title_elem)

        for ds_elem in _find_all_local(schema_elem, "DataSet"):
            schema.data_sets.append(self._parse_data_set(ds_elem))

        # Top-level fields list (CalculatedFields and TotalFields)
        for f_elem in _find_all_local(schema_elem, "CalculatedField"):
            schema.fields.append(self._parse_calc_field(f_elem))

        for p_elem in _find_all_local(schema_elem, "Parameter"):
            schema.parameters.append(self._parse_parameter(p_elem))

        for r_elem in _find_all_local(schema_elem, "TotalField"):
            schema.resources.append(self._parse_resource(r_elem))

        for set_elem in _find_all_local(schema_elem, "Settings"):
            schema.settings.append(self._parse_settings(set_elem))
        # Some schemas wrap variants under <SettingsVariants>
        variants_root = _find_local(schema_elem, "SettingsVariants")
        if variants_root is not None:
            for v in _find_all_local(variants_root, "SettingsVariant"):
                name = _text(_find_local(v, "Name")) or "Variant"
                title_node = _find_local(v, "Title")
                title = _text(title_node) if title_node is not None else ""
                schema.settings.append(
                    CompositionSettings(name=name, title=title)
                )

        return schema

    # ------------------------------------------------------------------
    def _parse_data_set(self, elem: etree._Element) -> CompositionDataSet:
        # 1C schemas declare the kind via xsi:type on <dataSet> itself
        # (DataSetQuery / DataSetObject / DataSetUnion); the element
        # local-name is just "dataSet".
        kind_hint = _xsi_type(elem) or _localname(elem.tag)
        kind = _DATASET_KIND_MAP.get(kind_hint, DataSetKind.UNKNOWN)
        if kind is DataSetKind.UNKNOWN:
            t = _find_local(elem, "Type")
            if t is not None and t.text:
                kind = _DATASET_KIND_MAP.get(t.text.strip(), DataSetKind.UNKNOWN)

        name = _text(_find_local(elem, "Name")) or elem.get("name", "")
        ds = CompositionDataSet(name=name or "DataSet", kind=kind)

        # <query> may carry the text directly or wrap a <queryText> child.
        query_node = _find_local(elem, "Query")
        if query_node is not None:
            qtext_node = _find_local(query_node, "QueryText") or _find_local(
                query_node, "Text"
            )
            if qtext_node is not None and qtext_node.text:
                ds.query_text = qtext_node.text.strip()
            elif query_node.text and query_node.text.strip():
                ds.query_text = query_node.text.strip()

        # Fields may live in a <Fields> container or directly under the
        # data-set. Real 8.3 export uses lowerCamelCase (<field>) directly
        # under <dataSet>; older / EDT exports use PascalCase <Field> in
        # <Fields>. A nested <dataSet> means a Union — flatten its fields
        # so the union's field list reflects the source datasets.
        seen: set[int] = set()
        container = _find_local(elem, "Fields")
        if container is not None:
            for f_elem in container:
                if _ci_eq(_localname(f_elem.tag), "field") or _ci_eq(
                    _localname(f_elem.tag), "datasetfield"
                ):
                    ds.fields.append(self._parse_data_set_field(f_elem))
                    seen.add(id(f_elem))
        for child in elem:
            if id(child) in seen:
                continue
            local = _localname(child.tag)
            if _ci_eq(local, "field") or _ci_eq(local, "datasetfield"):
                ds.fields.append(self._parse_data_set_field(child))
            elif _ci_eq(local, "dataset"):
                ds.fields.extend(self._parse_data_set(child).fields)
        return ds

    def _parse_data_set_field(self, elem: etree._Element) -> CompositionField:
        name = (
            _text(_find_local(elem, "DataPath"))
            or _text(_find_local(elem, "Field"))
            or _text(_find_local(elem, "Name"))
            or elem.get("name", "")
        )
        title_node = _find_local(elem, "Title")
        title = _extract_local_string(title_node) if title_node is not None else ""
        type_node = _find_local(elem, "ValueType")
        if type_node is None:
            type_node = _find_local(elem, "Type")
        type_str = ""
        if type_node is not None:
            inner = _find_local(type_node, "Type")
            type_str = inner.text.strip() if inner is not None and inner.text else (
                type_node.text.strip() if type_node.text else ""
            )
        role = _text(_find_local(elem, "Role")) or _xsi_type(elem)
        return CompositionField(name=name, title=title, type=type_str, role=role)

    def _parse_calc_field(self, elem: etree._Element) -> CompositionField:
        f = self._parse_data_set_field(elem)
        expr_node = _find_local(elem, "Expression")
        if expr_node is not None and expr_node.text:
            f.expression = expr_node.text.strip()
        return f

    def _parse_parameter(self, elem: etree._Element) -> CompositionParameter:
        name = _text(_find_local(elem, "Name")) or elem.get("name", "")
        title_node = _find_local(elem, "Title")
        title = _extract_local_string(title_node) if title_node is not None else ""
        type_node = _find_local(elem, "ValueType")
        if type_node is None:
            type_node = _find_local(elem, "Type")
        type_str = ""
        if type_node is not None:
            inner = _find_local(type_node, "Type")
            type_str = (
                inner.text.strip()
                if inner is not None and inner.text
                else (type_node.text.strip() if type_node.text else "")
            )
        avail_node = _find_local(elem, "AvailableForUser")
        avail = (
            _text(avail_node).lower() != "false"
            if avail_node is not None
            else True
        )
        default_node = _find_local(elem, "Value")
        default = _text(default_node)
        return CompositionParameter(
            name=name, title=title, type=type_str,
            available_for_user=avail, default_value=default,
        )

    def _parse_resource(self, elem: etree._Element) -> CompositionResource:
        field = (
            _text(_find_local(elem, "DataPath"))
            or _text(_find_local(elem, "Field"))
            or elem.get("name", "")
        )
        expr_node = _find_local(elem, "Expression")
        expr = _text(expr_node)
        title_node = _find_local(elem, "Title")
        title = _extract_local_string(title_node) if title_node is not None else ""
        return CompositionResource(field=field, expression=expr, title=title)

    def _parse_settings(self, elem: etree._Element) -> CompositionSettings:
        name = _text(_find_local(elem, "Name")) or "Default"
        title_node = _find_local(elem, "Title")
        title = _extract_local_string(title_node) if title_node is not None else ""
        selection: list[str] = []
        sel_root = _find_local(elem, "Selection")
        if sel_root is not None:
            for child in sel_root:
                path = _text(_find_local(child, "Field")) or _text(
                    _find_local(child, "DataPath")
                )
                if path:
                    selection.append(path)
        order: list[str] = []
        order_root = _find_local(elem, "Order")
        if order_root is not None:
            for child in order_root:
                path = _text(_find_local(child, "Field")) or _text(
                    _find_local(child, "DataPath")
                )
                if path:
                    order.append(path)
        return CompositionSettings(
            name=name, title=title, selection=selection, order=order
        )
