"""
XML Parser for 1C configuration files.

Parses Configuration.xml and metadata object XML files.
Uses lxml for efficient XML processing.
"""

from pathlib import Path
from typing import Any
import hashlib

from lxml import etree

from mcp_1c.domain.metadata import (
    MetadataObject,
    MetadataType,
    Attribute,
    TabularSection,
    Form,
    Template,
    Module,
    ModuleType,
    Subsystem,
)
from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

# 1C XML namespaces
NAMESPACES = {
    "v8": "http://v8.1c.ru/8.3/MDClasses",
    "core": "http://v8.1c.ru/8.1/data/core",
    "xs": "http://www.w3.org/2001/XMLSchema",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


class XmlParser:
    """
    Parser for 1C XML configuration files.

    Supports:
    - Configuration.xml parsing
    - Metadata object XML parsing
    - Subsystem XML parsing
    """

    def __init__(self) -> None:
        """Initialize parser."""
        self.logger = get_logger(__name__)

    def parse_configuration(self, config_path: Path) -> dict[str, list[str]]:
        """
        Parse Configuration.xml to get list of all objects.

        Args:
            config_path: Path to configuration root

        Returns:
            Dictionary mapping metadata type to list of object names
        """
        config_xml = config_path / "Configuration.xml"
        if not config_xml.exists():
            raise FileNotFoundError(f"Configuration.xml not found at {config_xml}")

        self.logger.info(f"Parsing configuration: {config_xml}")

        tree = etree.parse(str(config_xml))
        root = tree.getroot()

        result: dict[str, list[str]] = {}

        # Map of XML container element names (plural form) to MetadataType
        # 1C Configuration.xml uses: <Catalogs><item>Name</item></Catalogs>
        element_map = {
            "Catalogs": MetadataType.CATALOG,
            "Documents": MetadataType.DOCUMENT,
            "Enums": MetadataType.ENUM,
            "ChartsOfCharacteristicTypes": MetadataType.CHART_OF_CHARACTERISTIC_TYPES,
            "ChartsOfAccounts": MetadataType.CHART_OF_ACCOUNTS,
            "ChartsOfCalculationTypes": MetadataType.CHART_OF_CALCULATION_TYPES,
            "ExchangePlans": MetadataType.EXCHANGE_PLAN,
            "BusinessProcesses": MetadataType.BUSINESS_PROCESS,
            "Tasks": MetadataType.TASK,
            "InformationRegisters": MetadataType.INFORMATION_REGISTER,
            "AccumulationRegisters": MetadataType.ACCUMULATION_REGISTER,
            "AccountingRegisters": MetadataType.ACCOUNTING_REGISTER,
            "CalculationRegisters": MetadataType.CALCULATION_REGISTER,
            "Reports": MetadataType.REPORT,
            "DataProcessors": MetadataType.DATA_PROCESSOR,
            "Constants": MetadataType.CONSTANT,
            "CommonModules": MetadataType.COMMON_MODULE,
            "Subsystems": MetadataType.SUBSYSTEM,
            "Roles": MetadataType.ROLE,
            "CommonForms": MetadataType.COMMON_FORM,
            "CommonTemplates": MetadataType.COMMON_TEMPLATE,
            "SessionParameters": MetadataType.SESSION_PARAMETER,
            "FunctionalOptions": MetadataType.FUNCTIONAL_OPTION,
            "ScheduledJobs": MetadataType.SCHEDULED_JOB,
            "EventSubscriptions": MetadataType.EVENT_SUBSCRIPTION,
            "HTTPServices": MetadataType.HTTP_SERVICE,
            "WebServices": MetadataType.WEB_SERVICE,
        }

        for container_name, meta_type in element_map.items():
            objects = self._find_items_in_container(root, container_name)
            if objects:
                result[meta_type.value] = objects
                self.logger.debug(f"Found {len(objects)} {container_name}")

        return result

    def _find_items_in_container(
        self,
        root: etree._Element,
        container_name: str,
    ) -> list[str]:
        """
        Find all <item> elements within a container element.

        Structure: <ContainerName><item>ObjectName</item></ContainerName>
        """
        results: list[str] = []

        # Try with local-name to handle namespaces
        xpath = f".//*[local-name()='{container_name}']/*[local-name()='item']"
        try:
            elements = root.xpath(xpath)
            for elem in elements:
                if elem.text:
                    results.append(elem.text.strip())
        except Exception:
            pass

        return results

    def _find_elements_by_local_name(
        self,
        root: etree._Element,
        element_name: str,
    ) -> list[etree._Element]:
        """Find all elements by local name (ignoring namespace)."""
        xpath = f".//*[local-name()='{element_name}']"
        try:
            return root.xpath(xpath)
        except Exception:
            return []

    def _find_element_by_local_name(
        self,
        root: etree._Element,
        element_name: str,
    ) -> etree._Element | None:
        """Find first element by local name (ignoring namespace)."""
        elements = self._find_elements_by_local_name(root, element_name)
        return elements[0] if elements else None

    def _extract_name(self, element: etree._Element) -> str:
        """Extract object name from element."""
        # Try text content first
        if element.text:
            return element.text.strip()
        # Try 'name' attribute
        return element.get("name", "")

    def parse_metadata_object(
        self,
        config_path: Path,
        metadata_type: MetadataType,
        object_name: str,
    ) -> MetadataObject:
        """
        Parse a specific metadata object XML file.

        Args:
            config_path: Path to configuration root
            metadata_type: Type of metadata
            object_name: Object name

        Returns:
            Parsed MetadataObject
        """
        # Determine object path based on type
        type_folder = self._get_type_folder(metadata_type)
        object_path = config_path / type_folder / object_name

        # Find XML file (might be .xml or in Ext folder)
        xml_file = self._find_object_xml(object_path, object_name)

        if not xml_file.exists():
            self.logger.warning(f"XML file not found for {metadata_type.value}.{object_name}")
            return MetadataObject(
                name=object_name,
                metadata_type=metadata_type,
                config_path=config_path,
                object_path=object_path,
            )

        self.logger.debug(f"Parsing: {xml_file}")

        tree = etree.parse(str(xml_file))
        root = tree.getroot()

        # Calculate file hash
        file_hash = self._calculate_hash(xml_file)

        # Parse common properties
        uuid = self._get_text(root, ".//uuid", "") or self._get_attr(root, "uuid", "")
        synonym = self._get_localized_string(root, ".//Synonym")
        comment = self._get_localized_string(root, ".//Comment")

        # Parse structural elements
        attributes = self._parse_attributes(root)
        tabular_sections = self._parse_tabular_sections(root)
        forms = self._parse_forms(root, object_path)
        templates = self._parse_templates(root, object_path)
        modules = self._find_modules(object_path, metadata_type)

        # Parse register-specific elements
        dimensions = self._parse_dimensions(root) if self._is_register(metadata_type) else []
        resources = self._parse_resources(root) if self._is_register(metadata_type) else []

        # Parse document-specific elements
        register_records = self._parse_register_records(root)
        posting = self._get_bool(root, ".//Posting", False)

        return MetadataObject(
            uuid=uuid,
            name=object_name,
            synonym=synonym,
            comment=comment,
            metadata_type=metadata_type,
            config_path=config_path,
            object_path=object_path,
            attributes=attributes,
            tabular_sections=tabular_sections,
            forms=forms,
            templates=templates,
            modules=modules,
            dimensions=dimensions,
            resources=resources,
            register_records=register_records,
            posting=posting,
            file_hash=file_hash,
        )

    def parse_subsystem(
        self,
        config_path: Path,
        subsystem_name: str,
        parent: str | None = None,
    ) -> Subsystem:
        """
        Parse a subsystem XML file.

        Args:
            config_path: Path to configuration root
            subsystem_name: Subsystem name
            parent: Parent subsystem name

        Returns:
            Parsed Subsystem
        """
        if parent:
            subsystem_path = config_path / "Subsystems" / parent / "Subsystems" / subsystem_name
        else:
            subsystem_path = config_path / "Subsystems" / subsystem_name

        xml_file = subsystem_path / f"{subsystem_name}.xml"

        if not xml_file.exists():
            return Subsystem(name=subsystem_name, parent=parent)

        tree = etree.parse(str(xml_file))
        root = tree.getroot()

        synonym = self._get_localized_string(root, ".//Synonym")
        include_in_ci = self._get_bool(root, ".//IncludeInCommandInterface", True)

        # Parse content
        content: list[str] = []
        content_container = self._find_element_by_local_name(root, "Content")
        if content_container is not None:
            for child in content_container:
                local_name = etree.QName(child).localname
                if local_name == "item" and child.text:
                    content.append(child.text.strip())

        # Find child subsystems
        children: list[str] = []
        children_path = subsystem_path / "Subsystems"
        if children_path.exists():
            children = [d.name for d in children_path.iterdir() if d.is_dir()]

        return Subsystem(
            name=subsystem_name,
            synonym=synonym,
            parent=parent,
            children=children,
            content=content,
            include_in_command_interface=include_in_ci,
        )

    def _get_type_folder(self, metadata_type: MetadataType) -> str:
        """Get folder name for metadata type."""
        folder_map = {
            MetadataType.CATALOG: "Catalogs",
            MetadataType.DOCUMENT: "Documents",
            MetadataType.ENUM: "Enums",
            MetadataType.CHART_OF_CHARACTERISTIC_TYPES: "ChartsOfCharacteristicTypes",
            MetadataType.CHART_OF_ACCOUNTS: "ChartsOfAccounts",
            MetadataType.CHART_OF_CALCULATION_TYPES: "ChartsOfCalculationTypes",
            MetadataType.EXCHANGE_PLAN: "ExchangePlans",
            MetadataType.BUSINESS_PROCESS: "BusinessProcesses",
            MetadataType.TASK: "Tasks",
            MetadataType.INFORMATION_REGISTER: "InformationRegisters",
            MetadataType.ACCUMULATION_REGISTER: "AccumulationRegisters",
            MetadataType.ACCOUNTING_REGISTER: "AccountingRegisters",
            MetadataType.CALCULATION_REGISTER: "CalculationRegisters",
            MetadataType.REPORT: "Reports",
            MetadataType.DATA_PROCESSOR: "DataProcessors",
            MetadataType.CONSTANT: "Constants",
            MetadataType.COMMON_MODULE: "CommonModules",
            MetadataType.SUBSYSTEM: "Subsystems",
            MetadataType.ROLE: "Roles",
            MetadataType.COMMON_FORM: "CommonForms",
            MetadataType.COMMON_TEMPLATE: "CommonTemplates",
            MetadataType.SESSION_PARAMETER: "SessionParameters",
            MetadataType.FUNCTIONAL_OPTION: "FunctionalOptions",
            MetadataType.SCHEDULED_JOB: "ScheduledJobs",
            MetadataType.EVENT_SUBSCRIPTION: "EventSubscriptions",
            MetadataType.HTTP_SERVICE: "HTTPServices",
            MetadataType.WEB_SERVICE: "WebServices",
        }
        return folder_map.get(metadata_type, metadata_type.value + "s")

    def _find_object_xml(self, object_path: Path, object_name: str) -> Path:
        """Find the main XML file for an object."""
        # Try direct XML file
        direct = object_path / f"{object_name}.xml"
        if direct.exists():
            return direct

        # Try in Ext folder
        ext = object_path / "Ext" / "ObjectModule.xml"
        if ext.exists():
            return ext

        return direct

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file."""
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _get_text(
        self,
        root: etree._Element,
        xpath: str,
        default: str = "",
    ) -> str:
        """Get text content of element by xpath (handles namespaces)."""
        # Extract element name from xpath like ".//ElementName"
        if xpath.startswith(".//"):
            element_name = xpath[3:]
            elements = self._find_elements_by_local_name(root, element_name)
        else:
            elements = root.xpath(xpath)
        if elements and elements[0].text:
            return elements[0].text.strip()
        return default

    def _get_attr(
        self,
        root: etree._Element,
        attr_name: str,
        default: str = "",
    ) -> str:
        """Get attribute value from root."""
        return root.get(attr_name, default)

    def _get_bool(
        self,
        root: etree._Element,
        xpath: str,
        default: bool = False,
    ) -> bool:
        """Get boolean value from element."""
        text = self._get_text(root, xpath, "")
        if text.lower() in ("true", "1", "да"):
            return True
        if text.lower() in ("false", "0", "нет"):
            return False
        return default

    def _get_localized_string(
        self,
        root: etree._Element,
        xpath: str,
    ) -> str:
        """Get localized string (prefer Russian, fallback to first available)."""
        # Extract element name from xpath like ".//ElementName"
        if xpath.startswith(".//"):
            element_name = xpath[3:]
            elements = self._find_elements_by_local_name(root, element_name)
        else:
            elements = root.xpath(xpath)

        if not elements:
            return ""

        elem = elements[0]

        # Try to find Russian version in <item> children
        for child in elem:
            lang = child.get("lang", "") or child.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            if lang in ("ru", "ru_RU"):
                return child.text.strip() if child.text else ""

        # Fallback to first child with text
        for child in elem:
            if child.text:
                return child.text.strip()

        return ""

    def _parse_attributes(self, root: etree._Element) -> list[Attribute]:
        """Parse object attributes."""
        attributes: list[Attribute] = []

        # Find Attributes container, then get Attribute children
        attrs_container = self._find_element_by_local_name(root, "Attributes")
        attr_elements = []
        if attrs_container is not None:
            attr_elements = self._find_elements_by_local_name(attrs_container, "Attribute")

        for attr_elem in attr_elements:
            name_elem = self._find_element_by_local_name(attr_elem, "Name")
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            if not name:
                name = attr_elem.get("name", "")

            if not name:
                continue

            attr = Attribute(
                name=name,
                synonym=self._get_localized_string(attr_elem, ".//Synonym"),
                type=self._parse_type(attr_elem),
                comment=self._get_localized_string(attr_elem, ".//Comment"),
                indexed=self._get_bool(attr_elem, ".//Indexing", False),
            )
            attributes.append(attr)

        return attributes

    def _parse_tabular_sections(self, root: etree._Element) -> list[TabularSection]:
        """Parse tabular sections."""
        sections: list[TabularSection] = []

        # Find TabularSections container, then get TabularSection children
        ts_container = self._find_element_by_local_name(root, "TabularSections")
        ts_elements = []
        if ts_container is not None:
            ts_elements = self._find_elements_by_local_name(ts_container, "TabularSection")

        for ts_elem in ts_elements:
            name_elem = self._find_element_by_local_name(ts_elem, "Name")
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            if not name:
                name = ts_elem.get("name", "")

            if not name:
                continue

            section = TabularSection(
                name=name,
                synonym=self._get_localized_string(ts_elem, ".//Synonym"),
                attributes=self._parse_attributes(ts_elem),
                comment=self._get_localized_string(ts_elem, ".//Comment"),
            )
            sections.append(section)

        return sections

    def _parse_forms(self, root: etree._Element, object_path: Path) -> list[Form]:
        """Parse forms."""
        forms: list[Form] = []

        # Find Forms container, then get item children
        forms_container = self._find_element_by_local_name(root, "Forms")
        if forms_container is not None:
            # Forms are listed as <item>FormName</item>
            for child in forms_container:
                local_name = etree.QName(child).localname
                if local_name == "item" and child.text:
                    name = child.text.strip()
                    if name:
                        forms.append(Form(name=name, synonym=""))

        return forms

    def _parse_templates(self, root: etree._Element, object_path: Path) -> list[Template]:
        """Parse templates."""
        templates: list[Template] = []

        # Find Templates container, then get item children
        templates_container = self._find_element_by_local_name(root, "Templates")
        if templates_container is not None:
            # Templates are listed as <item>TemplateName</item>
            for child in templates_container:
                local_name = etree.QName(child).localname
                if local_name == "item" and child.text:
                    name = child.text.strip()
                    if name:
                        templates.append(Template(name=name, synonym=""))

        return templates

    def _find_modules(
        self,
        object_path: Path,
        metadata_type: MetadataType,
    ) -> list[Module]:
        """Find all modules for an object."""
        modules: list[Module] = []

        module_files = {
            "ObjectModule.bsl": ModuleType.OBJECT_MODULE,
            "ManagerModule.bsl": ModuleType.MANAGER_MODULE,
            "Module.bsl": ModuleType.COMMON_MODULE,
            "RecordSetModule.bsl": ModuleType.RECORDSET_MODULE,
            "ValueManagerModule.bsl": ModuleType.VALUE_MANAGER_MODULE,
        }

        ext_path = object_path / "Ext"
        if ext_path.exists():
            for file_name, module_type in module_files.items():
                module_path = ext_path / file_name
                if module_path.exists():
                    modules.append(Module(
                        module_type=module_type,
                        path=module_path,
                        exists=True,
                    ))

        # Check for form modules
        forms_path = object_path / "Forms"
        if forms_path.exists():
            for form_dir in forms_path.iterdir():
                if form_dir.is_dir():
                    form_module = form_dir / "Ext" / "Form" / "Module.bsl"
                    if form_module.exists():
                        modules.append(Module(
                            module_type=ModuleType.FORM_MODULE,
                            path=form_module,
                            exists=True,
                        ))

        return modules

    def _parse_type(self, elem: etree._Element) -> str:
        """Parse type description from element."""
        type_elem = self._find_element_by_local_name(elem, "Type")
        if type_elem is not None and type_elem.text:
            return type_elem.text.strip()
        return "String"

    def _is_register(self, metadata_type: MetadataType) -> bool:
        """Check if metadata type is a register."""
        return metadata_type in (
            MetadataType.INFORMATION_REGISTER,
            MetadataType.ACCUMULATION_REGISTER,
            MetadataType.ACCOUNTING_REGISTER,
            MetadataType.CALCULATION_REGISTER,
        )

    def _parse_dimensions(self, root: etree._Element) -> list[Attribute]:
        """Parse register dimensions."""
        dimensions: list[Attribute] = []

        # Find Dimensions container
        dims_container = self._find_element_by_local_name(root, "Dimensions")
        if dims_container is not None:
            dim_elements = self._find_elements_by_local_name(dims_container, "Dimension")
            for dim_elem in dim_elements:
                name_elem = self._find_element_by_local_name(dim_elem, "Name")
                name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
                if not name:
                    name = dim_elem.get("name", "")
                if name:
                    dimensions.append(Attribute(
                        name=name,
                        synonym=self._get_localized_string(dim_elem, ".//Synonym"),
                        type=self._parse_type(dim_elem),
                    ))
        return dimensions

    def _parse_resources(self, root: etree._Element) -> list[Attribute]:
        """Parse register resources."""
        resources: list[Attribute] = []

        # Find Resources container
        res_container = self._find_element_by_local_name(root, "Resources")
        if res_container is not None:
            res_elements = self._find_elements_by_local_name(res_container, "Resource")
            for res_elem in res_elements:
                name_elem = self._find_element_by_local_name(res_elem, "Name")
                name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
                if not name:
                    name = res_elem.get("name", "")
                if name:
                    resources.append(Attribute(
                        name=name,
                        synonym=self._get_localized_string(res_elem, ".//Synonym"),
                        type=self._parse_type(res_elem),
                    ))
        return resources

    def _parse_register_records(self, root: etree._Element) -> list[str]:
        """Parse document register records."""
        records: list[str] = []

        # Find RegisterRecords container
        rr_container = self._find_element_by_local_name(root, "RegisterRecords")
        if rr_container is not None:
            for child in rr_container:
                local_name = etree.QName(child).localname
                if local_name == "item" and child.text:
                    records.append(child.text.strip())

        return records
