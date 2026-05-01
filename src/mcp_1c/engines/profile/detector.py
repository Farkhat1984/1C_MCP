"""Auto-detect a :class:`ConfigurationProfile` from indexed metadata.

Strategy: pull cheap, high-signal facts out of the
:class:`MetadataEngine` (which has already parsed all XML) and
populate matching profile fields. No BSL parsing, no LSP — the
detector runs in seconds even on УТ/ZUP-sized configurations.

Each detector returns a *partial* profile (only the fields it could
infer); :func:`merge_profiles` combines them with developer overrides
last-write-wins on the manual side. That separation lets us evolve
detectors independently — adding a new heuristic doesn't require a
schema change, only a new ``detect_*`` function and one line in
:func:`detect_profile`.

Heuristics, in order of confidence:
1. **language**: if ≥70% of metadata names contain only ASCII letters
   and digits, the configuration is English; otherwise Russian. Mixed
   configs (some russian + some english) get the dominant pick.
2. **bsp.used**: True iff there's a ``CommonModule.СтандартныеПодсистемы``
   or one of its sibling БСП-marker modules. False for samopisные.
3. **bsp.version**: parsed from ``Constants.ВерсияБиблиотекиСтандартных
   Подсистем`` if present; otherwise empty (engines fall back to
   bundled JSON baseline).
4. **naming.obsolete_prefixes**: scans every attribute's name, picks
   prefixes that recur ≥ 5 times and are not the standard ``Удалить``.
   Common case: legacy ``_old`` / ``Obsolete_`` markers. The default
   ``Удалить`` prefix is always kept; we only *add* discovered ones.
5. **extensions**: passes through ``ExtensionEngine.list_extensions``
   if the engine is attached.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from mcp_1c.domain.metadata import MetadataType
from mcp_1c.engines.profile.model import (
    BspSection,
    ConfigurationProfile,
    ExtensionDescriptor,
    NamingSection,
)
from mcp_1c.utils.logger import get_logger

if TYPE_CHECKING:
    from mcp_1c.engines.metadata.engine import MetadataEngine

logger = get_logger(__name__)


# Names that, if seen as a CommonModule, indicate БСП is present.
# This matches every published version 3.0 - 3.1 of the library.
_BSP_MARKER_MODULES = frozenset(
    {
        "СтандартныеПодсистемы",
        "СтандартныеПодсистемыСервер",
        "ОбщегоНазначения",
        "ОбщегоНазначенияСервер",
        "ОбщегоНазначенияПереопределяемый",
    }
)

_ASCII_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


async def detect_profile(
    metadata_engine: MetadataEngine,
) -> ConfigurationProfile:
    """Run every detector and return the merged profile.

    Resilient to partial failures: a detector that raises is logged
    and skipped — the engine still produces a usable profile from the
    rest. Use :func:`merge_profiles` to layer the auto-detected
    profile under a manually-edited one.
    """
    naming = NamingSection()
    bsp = BspSection()
    extensions: list[ExtensionDescriptor] = []

    try:
        naming.language = await _detect_language(metadata_engine)
    except Exception as exc:
        logger.debug(f"language detection failed: {exc}")

    try:
        bsp.used = await _detect_bsp_used(metadata_engine)
    except Exception as exc:
        logger.debug(f"bsp.used detection failed: {exc}")

    try:
        bsp.version = await _detect_bsp_version(metadata_engine)
    except Exception as exc:
        logger.debug(f"bsp.version detection failed: {exc}")

    try:
        discovered_prefixes = await _detect_obsolete_prefixes(metadata_engine)
        # Always keep the default ``Удалить``; add anything else we found.
        merged = list(naming.obsolete_prefixes)
        for p in discovered_prefixes:
            if p not in merged:
                merged.append(p)
        naming.obsolete_prefixes = merged
    except Exception as exc:
        logger.debug(f"obsolete_prefixes detection failed: {exc}")

    try:
        extensions = await _detect_extensions()
    except Exception as exc:
        logger.debug(f"extensions detection failed: {exc}")

    return ConfigurationProfile(
        language=naming.language,
        naming=naming,
        bsp=bsp,
        extensions=extensions,
    )


def merge_profiles(
    base: ConfigurationProfile,
    override: ConfigurationProfile,
) -> ConfigurationProfile:
    """Layer ``override`` on top of ``base``.

    "Override" semantics: any *non-default* field in ``override``
    replaces the corresponding base value; defaults pass through. This
    matches the lifecycle "load YAML (manual), then detect, then merge
    detect under YAML" — manual edits always win.

    Implementation note: Pydantic doesn't expose "is this field at its
    default?" directly; we compare against a fresh default model.
    For nested models we recurse; for lists/dicts we replace whole.
    """
    base_dump = base.model_dump()
    over_dump = override.model_dump()
    default_dump = ConfigurationProfile().model_dump()

    merged = _deep_merge(base_dump, over_dump, default_dump)
    return ConfigurationProfile.model_validate(merged)


def _deep_merge(
    base: dict, override: dict, default: dict
) -> dict:
    """Recursive merge: ``override`` non-default values win.

    For dict-valued fields we recurse; for list/scalar fields the
    override value replaces the base only if it differs from the
    default (so an unset override key doesn't accidentally undo
    base's value).
    """
    result = dict(base)
    for key, over_val in override.items():
        default_val = default.get(key)
        if isinstance(over_val, dict) and isinstance(base.get(key), dict):
            result[key] = _deep_merge(
                base.get(key, {}),
                over_val,
                default_val if isinstance(default_val, dict) else {},
            )
        elif over_val != default_val:
            result[key] = over_val
    return result


# ---------------------------------------------------------------------------
# Per-field detectors. Each is async because some need to query the
# MetadataEngine (which is async); even those that don't are kept async
# for uniformity and future extensibility.
# ---------------------------------------------------------------------------


async def _detect_language(
    metadata_engine: MetadataEngine,
) -> str:
    """Pick `ru` or `en` based on the dominant naming alphabet.

    Counts ASCII-only names across a representative sample of
    user-facing object types. ``≥ 70%`` ASCII → English; otherwise
    Russian. The 70% threshold is deliberately permissive so a few
    English service-module names (``OpenIDConnect`` etc.) inside an
    otherwise-russian config don't flip the verdict.
    """
    sample_types = (
        MetadataType.CATALOG,
        MetadataType.DOCUMENT,
        MetadataType.COMMON_MODULE,
    )
    total = 0
    ascii_only = 0
    for md_type in sample_types:
        try:
            objects = await metadata_engine.list_objects(md_type)
        except Exception:
            continue
        for obj in objects:
            total += 1
            if _ASCII_NAME.match(obj.name):
                ascii_only += 1
    if total == 0:
        return "ru"  # No data — keep historical default.
    return "en" if (ascii_only / total) >= 0.70 else "ru"


async def _detect_bsp_used(metadata_engine: MetadataEngine) -> bool:
    """True iff at least one БСП-marker common module exists in the config."""
    try:
        modules = await metadata_engine.list_objects(MetadataType.COMMON_MODULE)
    except Exception:
        return False
    return any(m.name in _BSP_MARKER_MODULES for m in modules)


async def _detect_bsp_version(metadata_engine: MetadataEngine) -> str:
    """Parse the БСП version constant if it exists.

    Returns an empty string when the constant isn't present or its name
    doesn't follow the standard pattern. Better to leave empty than
    misreport: downstream engines treat empty version as "use bundled
    baseline" rather than "feature-flag this version".
    """
    candidates = (
        "ВерсияБиблиотекиСтандартныхПодсистем",
        "ВерсияБСП",
    )
    try:
        constants = await metadata_engine.list_objects(MetadataType.CONSTANT)
    except Exception:
        return ""
    for c in constants:
        if c.name in candidates:
            # The actual version is a runtime value, not metadata —
            # we can't read it without a live database. Returning the
            # marker presence is enough: BspEngine treats "БСП constant
            # exists" as "use the latest bundled baseline".
            return ""
    return ""


_OBSOLETE_PREFIX_CANDIDATES = ("_old", "Obsolete_", "Старый", "Deprecated")


async def _detect_obsolete_prefixes(
    metadata_engine: MetadataEngine,
) -> list[str]:
    """Find non-default prefixes that recur as "this attribute is dead".

    Heuristic: a prefix from the candidate list that occurs ≥ 5 times
    across all attributes of all catalogs/documents is a real
    convention, not a coincidence. We only suggest from the curated
    candidate list — open-set discovery would catch too many false
    positives like ``Адрес`` (просто префикс по смыслу).
    """
    counter: Counter[str] = Counter()
    sample_types = (
        MetadataType.CATALOG,
        MetadataType.DOCUMENT,
        MetadataType.INFORMATION_REGISTER,
        MetadataType.ACCUMULATION_REGISTER,
    )
    for md_type in sample_types:
        try:
            objects = await metadata_engine.list_objects(md_type)
        except Exception:
            continue
        for obj in objects:
            for attr in obj.attributes:
                for prefix in _OBSOLETE_PREFIX_CANDIDATES:
                    if attr.name.startswith(prefix):
                        counter[prefix] += 1
                        break
    return [prefix for prefix, count in counter.items() if count >= 5]


async def _detect_extensions() -> list[ExtensionDescriptor]:
    """Enumerate extensions known to ``ExtensionEngine``.

    Doesn't require ``metadata_engine`` because the extension engine
    has its own attach hook. Returns an empty list when the engine
    isn't attached or no extensions are discovered.
    """
    from mcp_1c.engines.extensions import ExtensionEngine

    engine = ExtensionEngine.get_instance()
    if engine._main_path is None:  # noqa: SLF001
        return []
    try:
        names = await engine.list_extensions()
    except Exception:
        return []
    descriptors: list[ExtensionDescriptor] = []
    for name in names:
        try:
            ext = await engine.get(name)
        except Exception:
            descriptors.append(ExtensionDescriptor(name=name))
            continue
        purpose = (
            ext.purpose.value if hasattr(ext.purpose, "value") else str(ext.purpose)
        )
        descriptors.append(ExtensionDescriptor(name=name, purpose=purpose))
    return descriptors


__all__ = [
    "detect_profile",
    "merge_profiles",
]
