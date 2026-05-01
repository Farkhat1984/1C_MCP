"""Configuration profile — declarative conventions of one 1С configuration.

A profile encodes everything that varies between configurations and
that the smart-* generators or analyzers need to know:

- **Language**: ``ru`` for cyrillic-named typical configs, ``en`` for
  configurations exported from EDT with English identifiers.
- **Naming conventions**: which attribute prefixes mark "deleted"
  fields (``Удалить``, ``_old``, …); which presentation field a
  reference type uses (``Наименование``, ``Номер``, custom).
- **БСП usage**: whether the configuration uses Библиотеку Стандартных
  Подсистем and which version, so smart-print can pick between the
  default standalone template and the БСП-style ``УправлениеПечатью``
  flow.
- **Generation patterns**: per-domain choices (print form layout,
  register movement style) — пользователь может оверрайдить через YAML.

Lifecycle:
1. ``load_profile(config_path)`` reads ``.mcp_1c_project.yaml`` from
   the config root, returns an empty profile if absent.
2. ``detect_profile(metadata_engine)`` infers values from the indexed
   metadata; merges into the loaded profile (loaded values win — manual
   override beats auto-detect).
3. ``save_profile(config_path, profile)`` writes the merged profile back
   with explanatory comments so the developer can review/tweak.

The profile is **per-workspace**. Phase F4.5 binds it to ``Workspace``.
"""

from mcp_1c.engines.profile.detector import detect_profile, merge_profiles
from mcp_1c.engines.profile.loader import load_profile, save_profile
from mcp_1c.engines.profile.model import (
    BspSection,
    ConfigurationProfile,
    MovementStrategy,
    NamingSection,
    PatternsSection,
    PrintFormStrategy,
)

__all__ = [
    "BspSection",
    "ConfigurationProfile",
    "MovementStrategy",
    "NamingSection",
    "PatternsSection",
    "PrintFormStrategy",
    "detect_profile",
    "load_profile",
    "merge_profiles",
    "save_profile",
]
