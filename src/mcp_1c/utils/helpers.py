"""
Helper utilities for MCP-1C.

Common functions used across the application.
"""

import re
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def normalize_name(name: str) -> str:
    """
    Normalize 1C object name for comparison.

    Removes extra whitespace and converts to lowercase.

    Args:
        name: Object name to normalize

    Returns:
        Normalized name
    """
    return re.sub(r"\s+", " ", name.strip().lower())


def camel_to_snake(name: str) -> str:
    """
    Convert CamelCase to snake_case.

    Args:
        name: CamelCase string

    Returns:
        snake_case string
    """
    pattern = re.compile(r"(?<!^)(?=[A-Z])")
    return pattern.sub("_", name).lower()


def snake_to_camel(name: str) -> str:
    """
    Convert snake_case to CamelCase.

    Args:
        name: snake_case string

    Returns:
        CamelCase string
    """
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def ensure_path(path: str | Path) -> Path:
    """
    Ensure path is a Path object.

    Args:
        path: String or Path

    Returns:
        Path object
    """
    return Path(path) if isinstance(path, str) else path


def safe_get(data: dict, *keys: str, default: T | None = None) -> T | None:
    """
    Safely get nested dictionary value.

    Args:
        data: Dictionary to search
        *keys: Sequence of keys
        default: Default value if not found

    Returns:
        Value or default
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key, default)
        else:
            return default
    return result  # type: ignore


def is_valid_1c_identifier(name: str) -> bool:
    """
    Check if name is a valid 1C identifier.

    Valid identifiers start with a letter or underscore,
    followed by letters, digits, or underscores.

    Args:
        name: Identifier to check

    Returns:
        True if valid
    """
    pattern = re.compile(r"^[a-zA-Zа-яА-ЯёЁ_][a-zA-Zа-яА-ЯёЁ0-9_]*$")
    return bool(pattern.match(name))


def split_full_name(full_name: str) -> tuple[str, str]:
    """
    Split 1C full object name into type and name.

    Example: "Справочник.Номенклатура" -> ("Справочник", "Номенклатура")

    Args:
        full_name: Full object name

    Returns:
        Tuple of (type, name)
    """
    parts = full_name.split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", full_name
