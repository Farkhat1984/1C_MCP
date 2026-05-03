"""
BSP (Library of Standard Subsystems) knowledge engine.

Loads static JSON knowledge base bundled with the package and provides
search/lookup over it. Treat this as a curated cheat-sheet — it doesn't
replace official БСП documentation but lets the model reach for the
right module/hook quickly.

Design follows ``engines/platform/engine.py``: load JSON once on first
use, search via simple inverted index over names and tags.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).parent / "data"


@dataclass
class BspProcedure:
    name: str
    exported: bool
    signature: str = ""
    description: str = ""


@dataclass
class BspModule:
    name: str
    kind: str
    purpose: str
    tags: list[str]
    procedures: list[BspProcedure]


@dataclass
class BspHook:
    name: str
    module: str
    purpose: str
    template: str = ""


@dataclass
class BspPattern:
    name: str
    task: str
    description: str
    modules: list[str]
    example: str = ""


class BspEngine:
    """Singleton facade over the bundled BSP knowledge JSON."""

    _instance: BspEngine | None = None

    @classmethod
    def get_instance(cls) -> BspEngine:
        if cls._instance is None:
            cls._instance = BspEngine()
        return cls._instance

    def __init__(self) -> None:
        self._modules: list[BspModule] = []
        self._hooks: list[BspHook] = []
        self._patterns: list[BspPattern] = []
        self._versions: list[dict[str, Any]] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._modules = self._load_modules()
        self._hooks = self._load_hooks()
        self._patterns = self._load_patterns()
        with (DATA_DIR / "versions.json").open(encoding="utf-8") as fh:
            self._versions = json.load(fh).get("versions", [])
        self._loaded = True
        logger.info(
            f"BSP knowledge loaded: {len(self._modules)} modules, "
            f"{len(self._hooks)} hooks, {len(self._patterns)} patterns"
        )

    @staticmethod
    def _load_modules() -> list[BspModule]:
        with (DATA_DIR / "common_modules.json").open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return [
            BspModule(
                name=m["name"],
                kind=m.get("kind", ""),
                purpose=m.get("purpose", ""),
                tags=m.get("tags", []),
                procedures=[
                    BspProcedure(
                        name=p["name"],
                        exported=p.get("exported", False),
                        signature=p.get("signature", ""),
                        description=p.get("description", ""),
                    )
                    for p in m.get("procedures", [])
                ],
            )
            for m in raw.get("modules", [])
        ]

    @staticmethod
    def _load_hooks() -> list[BspHook]:
        with (DATA_DIR / "hooks.json").open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return [BspHook(**h) for h in raw.get("hooks", [])]

    @staticmethod
    def _load_patterns() -> list[BspPattern]:
        with (DATA_DIR / "patterns.json").open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return [BspPattern(**p) for p in raw.get("patterns", [])]

    # ------------------------------------------------------------------
    def find(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Substring search over modules, procedures, hooks, patterns."""
        self._ensure_loaded()
        q = query.lower().strip()
        if not q:
            return []
        results: list[dict[str, Any]] = []

        # Genre queries: when the user types a category name we list
        # everything from that category, otherwise a "hooks" search
        # returns 0 just because no entry happens to contain "хук" in
        # its description. The token list is intentionally short — only
        # category labels, not arbitrary content keywords.
        genre_hooks = {"хук", "хуки", "hook", "hooks", "переопределяемый"}
        genre_patterns = {"паттерн", "паттерны", "pattern", "patterns"}
        genre_modules = {"модуль", "модули", "module", "modules"}
        if q in genre_hooks:
            return [
                {"kind": "hook", "name": h.name, "module": h.module, "purpose": h.purpose}
                for h in self._hooks
            ][:limit]
        if q in genre_patterns:
            return [
                {"kind": "pattern", "name": p.name, "task": p.task, "modules": p.modules}
                for p in self._patterns
            ][:limit]
        if q in genre_modules:
            return [
                {"kind": "module", "name": m.name, "purpose": m.purpose}
                for m in self._modules
            ][:limit]

        for m in self._modules:
            haystack = " ".join(
                [m.name, m.purpose, " ".join(m.tags)]
            ).lower()
            if q in haystack:
                results.append({"kind": "module", "name": m.name, "purpose": m.purpose})
            for p in m.procedures:
                proc_hay = f"{p.name} {p.description}".lower()
                if q in proc_hay:
                    results.append(
                        {
                            "kind": "procedure",
                            "module": m.name,
                            "name": p.name,
                            "signature": p.signature,
                            "description": p.description,
                            "exported": p.exported,
                        }
                    )

        for h in self._hooks:
            if q in f"{h.name} {h.module} {h.purpose}".lower():
                results.append(
                    {
                        "kind": "hook",
                        "name": h.name,
                        "module": h.module,
                        "purpose": h.purpose,
                    }
                )

        for p in self._patterns:
            if q in f"{p.name} {p.task} {p.description}".lower():
                results.append(
                    {
                        "kind": "pattern",
                        "name": p.name,
                        "task": p.task,
                        "modules": p.modules,
                    }
                )
        return results[:limit]

    def list_modules(self, tag: str | None = None) -> list[BspModule]:
        self._ensure_loaded()
        if tag is None:
            return list(self._modules)
        return [m for m in self._modules if tag in m.tags]

    def get_module(self, name: str) -> BspModule | None:
        self._ensure_loaded()
        for m in self._modules:
            if m.name.lower() == name.lower():
                return m
        return None

    def get_hook(self, name: str) -> BspHook | None:
        self._ensure_loaded()
        for h in self._hooks:
            if h.name.lower() == name.lower():
                return h
        return None

    def list_hooks(self) -> list[BspHook]:
        self._ensure_loaded()
        return list(self._hooks)

    def list_patterns(self) -> list[BspPattern]:
        self._ensure_loaded()
        return list(self._patterns)

    def review_code(self, code: str) -> list[dict[str, str]]:
        """Cheap rule-based review for BSP-style violations.

        The catalog is intentionally tiny — extending it requires more BSP
        domain expertise. Each rule emits {rule, severity, message, line=?}.
        """
        self._ensure_loaded()
        findings: list[dict[str, str]] = []
        for n, line in enumerate(code.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            if "ТекущаяДата()" in stripped:
                findings.append(
                    {
                        "rule": "BSP_TIMEZONE",
                        "severity": "warning",
                        "line": str(n),
                        "message": (
                            "Используйте `ОбщегоНазначения.ТекущаяДатаПользователя()` "
                            "вместо `ТекущаяДата()` — у пользователя может быть свой часовой пояс."
                        ),
                    }
                )
            if "Сообщить(" in stripped and "СообщитьПользователю" not in stripped:
                findings.append(
                    {
                        "rule": "BSP_USER_MESSAGE",
                        "severity": "info",
                        "line": str(n),
                        "message": (
                            "Используйте `ОбщегоНазначения.СообщитьПользователю` для адресных сообщений."
                        ),
                    }
                )
            if "Запрос.Выполнить()" in stripped and ".Выгрузить(" not in code:
                findings.append(
                    {
                        "rule": "BSP_QUERY_RESULT",
                        "severity": "info",
                        "line": str(n),
                        "message": (
                            "Если результат запроса не выгружается, проверьте — возможно стоит использовать выборку или ИмеетСтроки()."
                        ),
                    }
                )
        return findings
