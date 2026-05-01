"""Read/write ``.mcp_1c_project.yaml``.

The file lives at ``<config_root>/.mcp_1c_project.yaml`` by convention.
Why a dotfile: it's a developer-tool artifact, not a 1С-side file —
hiding it from the typical configuration browser keeps the conventional
1С UX clean. Designer / EDT both ignore unknown dotfiles.

Loader contract:

- Missing file → :class:`ConfigurationProfile` with defaults. No
  exception, no warning — that's the legitimate "haven't profiled yet"
  state.
- Malformed YAML or schema-incompatible content → :class:`ProfileError`
  with the underlying parser/validator message. Better to surface than
  to silently fall back to defaults: a typo in a real profile would
  otherwise silently disable a feature.

Saver contract:

- Pydantic ``model_dump`` → ``yaml.safe_dump`` with sorted keys off
  (preserve declaration order for readability).
- Header comments embedded so a developer reading the file sees what
  each section means. We don't try to round-trip *user-added*
  comments — that requires ruamel.yaml; pyyaml is enough for our
  read/write needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from mcp_1c.engines.profile.model import ConfigurationProfile

PROFILE_FILENAME = ".mcp_1c_project.yaml"


class ProfileError(Exception):
    """Raised when a YAML profile can't be parsed or doesn't satisfy schema.

    Wraps ``yaml.YAMLError`` and Pydantic ``ValidationError`` with a
    consistent message so callers don't need to catch two flavours.
    """


def profile_path(config_root: Path) -> Path:
    """Conventional location of the profile file under ``config_root``."""
    return config_root / PROFILE_FILENAME


def load_profile(config_root: Path) -> ConfigurationProfile:
    """Load the profile for a configuration root.

    Returns a default profile when the file is absent. Raises
    :class:`ProfileError` on malformed content — a partially valid
    profile is a footgun, fail loudly.
    """
    path = profile_path(config_root)
    if not path.exists():
        return ConfigurationProfile()

    try:
        raw = path.read_text(encoding="utf-8")
        data: Any = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ProfileError(f"Malformed YAML at {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError(
            f"Profile root must be a mapping, got {type(data).__name__} at {path}"
        )

    try:
        return ConfigurationProfile.model_validate(data)
    except ValidationError as exc:
        raise ProfileError(
            f"Profile schema mismatch at {path}: {exc}"
        ) from exc


_DEFAULT_HEADER = """\
# .mcp_1c_project.yaml
# Profile of this 1С configuration for the MCP-1C dev assistant.
# Generated automatically; safe to override any value below.
#
# - language       — ru | en, the language of metadata identifiers.
# - naming         — conventions: obsolete-prefixes, presentation overrides.
# - bsp            — Library of Standard Subsystems usage and version.
# - patterns       — code-generation strategies for smart-print, smart-movement.
# - extensions     — auto-discovered .cfe; override if needed.
"""


def save_profile(config_root: Path, profile: ConfigurationProfile) -> Path:
    """Write the profile to disk, returning the absolute path written.

    Always writes — caller is responsible for the "skip if unchanged"
    optimization. Pre-pends the explanatory header on every write so
    the file is self-documenting even if the developer never ran the
    detector themselves.
    """
    path = profile_path(config_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    body = yaml.safe_dump(
        profile.model_dump(mode="json", exclude_defaults=False),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    path.write_text(_DEFAULT_HEADER + "\n" + body, encoding="utf-8")
    return path


__all__ = [
    "PROFILE_FILENAME",
    "ProfileError",
    "load_profile",
    "profile_path",
    "save_profile",
]
