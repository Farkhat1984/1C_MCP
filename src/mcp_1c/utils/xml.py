"""Hardened XML parser factory.

Single source of truth for XML parsing across all engines. Defaults
disable every feature that lets a malicious document reach outside the
file: external entities, network fetches, DTDs. This blocks XXE
(SSRF/file-disclosure) and billion-laughs DoS variants that rely on
DTD entity expansion.

Always use ``safe_xml_parser()`` instead of constructing
``etree.XMLParser`` directly. Any new XML reading code in this codebase
must go through here.
"""

from __future__ import annotations

from lxml import etree


def safe_xml_parser(*, huge_tree: bool = False) -> etree.XMLParser:
    """Return a fresh hardened lxml parser.

    Args:
        huge_tree: Allow parsing of very large documents. Off by default
            so that pathological input can't allocate unbounded memory.
            Enable explicitly for legitimate giant exports (e.g. full
            ERP configuration trees) when the caller controls the file.

    Returns:
        A new ``etree.XMLParser`` with all unsafe XML features disabled.
        Each call returns a new instance — XMLParser is not thread-safe
        across simultaneous parses.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        huge_tree=huge_tree,
    )


__all__ = ["safe_xml_parser"]
