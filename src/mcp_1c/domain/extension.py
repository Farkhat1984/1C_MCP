"""
Domain models for 1C configuration extensions (.cfe).

Extensions live alongside the main configuration and contribute objects
in three modes:

- **Own** — the extension introduces a new object that doesn't exist in
  the main configuration.
- **Adopted (заимствованный)** — the extension borrows a typical object
  from the main configuration to add fields, forms, or modules to it.
- **Replaced (заменённый)** — the extension overrides a method of the
  main object's module.

The extension's ``Configuration.xml`` declares purpose, target name,
update modes, and the list of contributed objects with their mode.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ExtensionPurpose(str, Enum):
    PATCH = "Patch"
    CUSTOMIZATION = "Customization"
    ADD_ON = "AddOn"
    UNKNOWN = "Unknown"


class AdoptionMode(str, Enum):
    OWN = "Own"
    ADOPTED = "Adopted"
    REPLACED = "Replaced"
    UNKNOWN = "Unknown"


class ExtensionObject(BaseModel):
    """A single object contributed by the extension."""

    metadata_type: str
    name: str
    mode: AdoptionMode = AdoptionMode.UNKNOWN
    parent: str = Field(default="", description="Parent main-config object for Adopted/Replaced")

    model_config = ConfigDict(use_enum_values=False)


class Extension(BaseModel):
    """Top-level extension descriptor."""

    name: str
    purpose: ExtensionPurpose = ExtensionPurpose.UNKNOWN
    target_configuration: str = Field(default="", description="Name of the main config")
    namespace: str = Field(default="", description="Префикс расширения")
    config_path: Path
    objects: list[ExtensionObject] = Field(default_factory=list)
    safe_mode: bool = Field(
        default=False, description="Запуск в безопасном режиме платформы"
    )
    update_compatibility_mode: str = Field(default="")

    @property
    def own_objects(self) -> list[ExtensionObject]:
        return [o for o in self.objects if o.mode == AdoptionMode.OWN]

    @property
    def adopted_objects(self) -> list[ExtensionObject]:
        return [o for o in self.objects if o.mode == AdoptionMode.ADOPTED]

    @property
    def replaced_objects(self) -> list[ExtensionObject]:
        return [o for o in self.objects if o.mode == AdoptionMode.REPLACED]
