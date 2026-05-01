"""Unit tests for the configuration diff and test-data tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.tools.diff_tools import ConfigurationDiffTool

SIMPLE_CONFIG_LEFT = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Configuration>
    <Catalogs>
      <item>Товары</item>
      <item>Контрагенты</item>
    </Catalogs>
    <Documents>
      <item>ПриходТовара</item>
    </Documents>
  </Configuration>
</MetaDataObject>
"""

SIMPLE_CONFIG_RIGHT = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Configuration>
    <Catalogs>
      <item>Товары</item>
      <item>Услуги</item>
    </Catalogs>
    <Documents>
      <item>ПриходТовара</item>
      <item>РасходТовара</item>
    </Documents>
  </Configuration>
</MetaDataObject>
"""


@pytest.mark.asyncio
async def test_diff_added_removed_common(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "Configuration.xml").write_text(SIMPLE_CONFIG_LEFT, encoding="utf-8")
    (right / "Configuration.xml").write_text(SIMPLE_CONFIG_RIGHT, encoding="utf-8")

    tool = ConfigurationDiffTool()
    result = await tool.execute({"left": str(left), "right": str(right)})

    catalog_diff = result["by_type"]["Catalog"]
    assert catalog_diff["added"] == ["Услуги"]
    assert catalog_diff["removed"] == ["Контрагенты"]
    assert catalog_diff["common"] == ["Товары"]

    doc_diff = result["by_type"]["Document"]
    assert doc_diff["added"] == ["РасходТовара"]
    assert doc_diff["removed"] == []
    assert doc_diff["common"] == ["ПриходТовара"]

    assert result["totals"]["added"] == 2
    assert result["totals"]["removed"] == 1
