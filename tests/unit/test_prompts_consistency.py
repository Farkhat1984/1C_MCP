"""
Consistency guard: every tool name referenced from a Skill/Agent prompt
must correspond to a tool registered in ToolRegistry.

Catches silent regressions where a prompt instructs Claude to call a
tool that was renamed, consolidated or removed.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mcp_1c.tools.constants import ToolNames
from mcp_1c.tools.registry import ToolRegistry

PROMPTS_DIR = Path(__file__).parents[2] / "src" / "mcp_1c" / "prompts"
PROMPT_FILES = [PROMPTS_DIR / "skills.py", PROMPTS_DIR / "agents.py"]


def _collect_referenced_constants(source_file: Path) -> set[str]:
    """Walk AST and return every attribute name accessed as `T.<NAME>`."""
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "T"
        ):
            names.add(node.attr)
    return names


@pytest.fixture(scope="module")
def registered_tool_names() -> set[str]:
    registry = ToolRegistry()
    return {tool.name for tool in registry.list_tools()}


@pytest.fixture(scope="module")
def referenced_constants() -> dict[Path, set[str]]:
    return {f: _collect_referenced_constants(f) for f in PROMPT_FILES}


def test_every_referenced_constant_exists_on_toolnames(
    referenced_constants: dict[Path, set[str]],
) -> None:
    """T.<NAME> must be defined on ToolNames — typo guard."""
    missing: dict[str, set[str]] = {}
    for source, names in referenced_constants.items():
        absent = {n for n in names if not hasattr(ToolNames, n)}
        if absent:
            missing[source.name] = absent
    assert not missing, f"Undefined ToolNames constants: {missing}"


def test_every_referenced_tool_is_registered(
    referenced_constants: dict[Path, set[str]],
    registered_tool_names: set[str],
) -> None:
    """T.<NAME> must resolve to a tool that the registry actually serves."""
    broken: dict[str, dict[str, str]] = {}
    for source, names in referenced_constants.items():
        problems: dict[str, str] = {}
        for n in names:
            if not hasattr(ToolNames, n):
                continue
            tool_name = getattr(ToolNames, n)
            if tool_name not in registered_tool_names:
                problems[n] = tool_name
        if problems:
            broken[source.name] = problems
    assert not broken, (
        "Prompts reference tools that are not registered. "
        f"Either register the tool or rewrite the prompt: {broken}"
    )
