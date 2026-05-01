"""
Parser for 1C configuration extensions (Configuration.xml of a .cfe).

An extension's Configuration.xml differs from the main configuration's
in two ways:

1. ``<Properties><Purpose>Patch|Customization|AddOn</Purpose></Properties>``
   declares the extension's purpose.
2. Each contributed object carries an ``Adopted="true"`` or
   ``Replaced="true"`` attribute when it modifies a main-config object.
   Objects without those attributes are *own* additions.

We parse the same XML namespaces as the main configuration parser
(``http://v8.1c.ru/8.3/MDClasses``) but only extract the structure
needed for the extension domain.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from mcp_1c.domain.extension import (
    AdoptionMode,
    Extension,
    ExtensionObject,
    ExtensionPurpose,
)
from mcp_1c.utils.logger import get_logger
from mcp_1c.utils.xml import safe_xml_parser

logger = get_logger(__name__)

_SECURE_PARSER = safe_xml_parser()

_PURPOSE_MAP = {
    "Patch": ExtensionPurpose.PATCH,
    "Customization": ExtensionPurpose.CUSTOMIZATION,
    "AddOn": ExtensionPurpose.ADD_ON,
}


def _localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(elem: etree._Element | None, default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _find_local(elem: etree._Element, name: str) -> etree._Element | None:
    for child in elem:
        if _localname(child.tag) == name:
            return child
    return None


def _find_all_local(elem: etree._Element, name: str) -> list[etree._Element]:
    return [child for child in elem if _localname(child.tag) == name]


# Configurator-format object element names (singular form). Plurals like
# "Catalogs" are handled below by stripping the trailing "s".
_OBJECT_ELEMENTS = {
    "Catalog",
    "Document",
    "Enum",
    "ChartOfCharacteristicTypes",
    "ChartOfAccounts",
    "ChartOfCalculationTypes",
    "InformationRegister",
    "AccumulationRegister",
    "AccountingRegister",
    "CalculationRegister",
    "Report",
    "DataProcessor",
    "Constant",
    "CommonModule",
    "CommonForm",
    "CommonTemplate",
    "FunctionalOption",
    "ScheduledJob",
    "EventSubscription",
    "ExchangePlan",
    "HTTPService",
    "WebService",
    "Subsystem",
    "Role",
    "DefinedType",
    "CommonAttribute",
}


class ExtensionParser:
    """Parse the root Configuration.xml of a 1С extension."""

    def parse(self, config_path: Path) -> Extension:
        config_xml = config_path / "Configuration.xml"
        if not config_xml.exists():
            raise FileNotFoundError(
                f"Extension Configuration.xml not found at {config_xml}"
            )
        tree = etree.parse(str(config_xml), _SECURE_PARSER)
        root = tree.getroot()

        cfg_elem = _find_local(root, "Configuration")
        if cfg_elem is None:
            cfg_elem = root

        name = _text(_find_local(cfg_elem, "Name"))
        properties = _find_local(cfg_elem, "Properties")
        owner = properties if properties is not None else cfg_elem

        purpose_text = _text(_find_local(owner, "Purpose"))
        purpose = _PURPOSE_MAP.get(purpose_text, ExtensionPurpose.UNKNOWN)
        namespace = _text(_find_local(owner, "NamePrefix"))
        target = _text(_find_local(owner, "ConfigurationExtensionPurpose")) or _text(
            _find_local(owner, "BaseConfigurationName")
        )
        safe_mode = _text(_find_local(owner, "ExtensionConfigurationSafeMode")).lower() == "true"
        compat = _text(_find_local(owner, "UpdateCompatibilityMode"))

        ext = Extension(
            name=name,
            purpose=purpose,
            target_configuration=target,
            namespace=namespace,
            config_path=config_path,
            safe_mode=safe_mode,
            update_compatibility_mode=compat,
        )

        ext.objects = self._extract_objects(cfg_elem)
        return ext

    def _extract_objects(
        self, cfg_elem: etree._Element
    ) -> list[ExtensionObject]:
        out: list[ExtensionObject] = []
        # Two layouts coexist: <ChildObjects><Catalog Adopted="true">Name</Catalog></ChildObjects>
        # and the legacy <Catalogs><item>Name</item></Catalogs> with separate
        # adoption markers.
        child_objects = _find_local(cfg_elem, "ChildObjects")
        if child_objects is not None:
            for child in child_objects:
                local = _localname(child.tag)
                if local not in _OBJECT_ELEMENTS:
                    continue
                obj_name = (child.text or "").strip() or _text(_find_local(child, "Name"))
                if not obj_name:
                    continue
                mode = self._infer_mode(child)
                parent = ""
                # An adopted object can carry the parent path in attribute
                if mode in (AdoptionMode.ADOPTED, AdoptionMode.REPLACED):
                    parent = child.get("Parent", "") or obj_name
                out.append(
                    ExtensionObject(
                        metadata_type=local,
                        name=obj_name,
                        mode=mode,
                        parent=parent,
                    )
                )
            return out

        # Fallback: scan all <Catalogs>, <Documents>, ... containers
        for cont in cfg_elem:
            local = _localname(cont.tag)
            if not local.endswith("s"):
                continue
            singular = local[:-1]
            if singular not in _OBJECT_ELEMENTS:
                continue
            for item in cont:
                obj_name = (item.text or "").strip()
                if not obj_name:
                    continue
                mode = self._infer_mode(item)
                out.append(
                    ExtensionObject(
                        metadata_type=singular,
                        name=obj_name,
                        mode=mode,
                    )
                )
        return out

    @staticmethod
    def _infer_mode(elem: etree._Element) -> AdoptionMode:
        if elem.get("Adopted", "").lower() == "true":
            return AdoptionMode.ADOPTED
        if elem.get("Replaced", "").lower() == "true":
            return AdoptionMode.REPLACED
        return AdoptionMode.OWN
