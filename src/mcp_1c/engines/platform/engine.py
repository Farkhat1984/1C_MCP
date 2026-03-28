"""
Platform Knowledge Base engine.

Provides access to 1C:Enterprise 8.3 platform API documentation.
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ...domain.platform import (
    ExecutionContext,
    GlobalContext,
    GlobalContextSection,
    MethodParameter,
    ObjectEvent,
    ParameterDirection,
    PlatformKnowledgeBase,
    PlatformMethod,
    PlatformProperty,
    PlatformType,
)

logger = logging.getLogger(__name__)

_TOKEN_SPLIT_RE = re.compile(r"[\s.,;:()\[\]{}/\\|]+")
_MIN_TOKEN_LEN = 2


class PlatformEngine:
    """Engine for accessing platform knowledge base."""

    def __init__(self) -> None:
        """Initialize the platform engine."""
        self._knowledge_base: PlatformKnowledgeBase | None = None
        self._data_dir = Path(__file__).parent / "data"
        self._loaded = False
        self._search_index: dict[str, set[str]] = defaultdict(set)

    async def initialize(self) -> None:
        """Load the knowledge base from JSON files."""
        if self._loaded:
            return

        try:
            global_context = await self._load_global_context()
            types = await self._load_types()
            events = await self._load_events()

            self._knowledge_base = PlatformKnowledgeBase(
                version="8.3.24",
                global_context=global_context,
                types=types,
                events=events,
            )
            self._build_search_index()
            self._loaded = True
            logger.info("Platform knowledge base loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load platform knowledge base: {e}")
            raise

    async def _load_global_context(self) -> GlobalContext:
        """Load global context from JSON."""
        file_path = self._data_dir / "global_context.json"
        data = self._read_json(file_path)

        sections = []
        all_methods = []

        for section_data in data.get("sections", []):
            methods = [
                self._parse_method(m) for m in section_data.get("methods", [])
            ]
            sections.append(
                GlobalContextSection(
                    name=section_data.get("name", ""),
                    name_en=section_data.get("name_en", ""),
                    description=section_data.get("description", ""),
                    methods=methods,
                )
            )
            all_methods.extend(methods)

        return GlobalContext(
            platform_version=data.get("version", "8.3.24"),
            sections=sections,
            all_methods=all_methods,
        )

    async def _load_types(self) -> list[PlatformType]:
        """Load types from JSON."""
        file_path = self._data_dir / "types.json"
        data = self._read_json(file_path)

        types = []
        for type_data in data.get("types", []):
            constructors = [
                self._parse_method(c) for c in type_data.get("constructors", [])
            ]
            methods = [
                self._parse_method(m) for m in type_data.get("methods", [])
            ]
            properties = [
                self._parse_property(p) for p in type_data.get("properties", [])
            ]

            types.append(
                PlatformType(
                    name=type_data.get("name", ""),
                    name_en=type_data.get("name_en", ""),
                    description=type_data.get("description", ""),
                    category=type_data.get("category", "other"),
                    constructors=constructors,
                    methods=methods,
                    properties=properties,
                    since_version=type_data.get("since_version", "8.0"),
                )
            )

        return types

    async def _load_events(self) -> list[ObjectEvent]:
        """Load events from JSON."""
        file_path = self._data_dir / "events.json"
        data = self._read_json(file_path)

        events = []
        for event_data in data.get("events", []):
            parameters = [
                self._parse_parameter(p) for p in event_data.get("parameters", [])
            ]

            events.append(
                ObjectEvent(
                    name=event_data.get("name", ""),
                    name_en=event_data.get("name_en", ""),
                    description=event_data.get("description", ""),
                    category=event_data.get("category", "object"),
                    object_types=event_data.get("object_types", []),
                    parameters=parameters,
                    execution_context=event_data.get(
                        "execution_context", ExecutionContext.SERVER
                    ),
                    can_cancel=event_data.get("can_cancel", False),
                    cancel_parameter=event_data.get("cancel_parameter"),
                    execution_order=event_data.get("execution_order", 0),
                    related_events=event_data.get("related_events", []),
                    examples=event_data.get("examples", []),
                    notes=event_data.get("notes", []),
                    since_version=event_data.get("since_version", "8.0"),
                )
            )

        return events

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        """Read JSON file."""
        if not file_path.exists():
            logger.warning(f"JSON file not found: {file_path}")
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _parse_method(self, data: dict[str, Any]) -> PlatformMethod:
        """Parse method from JSON data."""
        parameters = [
            self._parse_parameter(p) for p in data.get("parameters", [])
        ]

        return PlatformMethod(
            name=data.get("name", ""),
            name_en=data.get("name_en", ""),
            description=data.get("description", ""),
            category=data.get("category", "common"),
            parameters=parameters,
            return_types=data.get("return_types", []),
            return_description=data.get("return_description", ""),
            available_contexts=data.get("available_contexts", []),
            since_version=data.get("since_version", "8.0"),
            examples=data.get("examples", []),
            related_methods=data.get("related_methods", []),
            notes=data.get("notes", []),
            keywords=data.get("keywords", []),
        )

    def _parse_parameter(self, data: dict[str, Any]) -> MethodParameter:
        """Parse parameter from JSON data."""
        direction_str = data.get("direction", "in")
        direction = ParameterDirection.IN
        if direction_str == "out":
            direction = ParameterDirection.OUT
        elif direction_str == "in_out":
            direction = ParameterDirection.IN_OUT

        return MethodParameter(
            name=data.get("name", ""),
            name_en=data.get("name_en", ""),
            description=data.get("description", ""),
            types=data.get("types", []),
            default_value=data.get("default_value"),
            required=data.get("required", True),
            direction=direction,
        )

    def _parse_property(self, data: dict[str, Any]) -> PlatformProperty:
        """Parse property from JSON data."""
        return PlatformProperty(
            name=data.get("name", ""),
            name_en=data.get("name_en", ""),
            description=data.get("description", ""),
            types=data.get("types", []),
            readable=data.get("readable", True),
            writable=data.get("writable", False),
        )

    def _build_search_index(self) -> None:
        """Build inverted index for fast text search across methods, types, and events."""
        assert self._knowledge_base is not None
        self._search_index.clear()

        # Index global context methods
        for method in self._knowledge_base.global_context.all_methods:
            ref = f"method:{method.name}"
            for token in self._tokenize(method.name):
                self._search_index[token].add(ref)
            if method.name_en:
                for token in self._tokenize(method.name_en):
                    self._search_index[token].add(ref)
            if method.description:
                for token in self._tokenize(method.description):
                    self._search_index[token].add(ref)
            for kw in method.keywords:
                for token in self._tokenize(kw):
                    self._search_index[token].add(ref)

        # Index types
        for platform_type in self._knowledge_base.types:
            ref = f"type:{platform_type.name}"
            for token in self._tokenize(platform_type.name):
                self._search_index[token].add(ref)
            if platform_type.name_en:
                for token in self._tokenize(platform_type.name_en):
                    self._search_index[token].add(ref)
            if platform_type.description:
                for token in self._tokenize(platform_type.description):
                    self._search_index[token].add(ref)
            for kw in platform_type.keywords:
                for token in self._tokenize(kw):
                    self._search_index[token].add(ref)

        # Index events
        for event in self._knowledge_base.events:
            ref = f"event:{event.name}"
            for token in self._tokenize(event.name):
                self._search_index[token].add(ref)
            if event.name_en:
                for token in self._tokenize(event.name_en):
                    self._search_index[token].add(ref)
            if event.description:
                for token in self._tokenize(event.description):
                    self._search_index[token].add(ref)
            for ot in event.object_types:
                for token in self._tokenize(ot):
                    self._search_index[token].add(ref)

        total_tokens = len(self._search_index)
        logger.debug(f"Search index built with {total_tokens} unique tokens")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split text into lowercase tokens for indexing.

        Args:
            text: Text to tokenize

        Returns:
            List of lowercase tokens with length >= 2
        """
        return [
            w.lower()
            for w in _TOKEN_SPLIT_RE.split(text)
            if len(w) >= _MIN_TOKEN_LEN
        ]

    def _search_index_lookup(
        self,
        query: str,
        category: str | None = None,
    ) -> set[str]:
        """Look up matching refs from the inverted index.

        Tokenizes the query and intersects results for all tokens.
        Each token matches any indexed token that contains it as a substring.

        Args:
            query: Search query
            category: Optional category filter ("method", "type", or "event")

        Returns:
            Set of matching references like "method:Name", "type:Name", etc.
        """
        tokens = self._tokenize(query)
        if not tokens:
            return set()

        candidates: set[str] | None = None
        for token in tokens:
            matches: set[str] = set()
            for indexed_token, refs in self._search_index.items():
                if token in indexed_token:
                    matches |= refs
            if candidates is None:
                candidates = matches
            else:
                candidates &= matches

        if candidates is None:
            return set()

        if category:
            prefix = f"{category}:"
            candidates = {r for r in candidates if r.startswith(prefix)}

        return candidates

    def _ensure_loaded(self) -> None:
        """Ensure knowledge base is loaded."""
        if not self._loaded or self._knowledge_base is None:
            raise RuntimeError("Platform engine not initialized. Call initialize() first.")

    # Public API methods

    def get_method(self, name: str) -> PlatformMethod | None:
        """Get global context method by name."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.global_context.get_method(name)

    def search_methods(self, query: str) -> list[PlatformMethod]:
        """Search global context methods using inverted index."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        refs = self._search_index_lookup(query, category="method")
        if not refs:
            return []
        # Extract names from refs and look up method objects
        method_names = {r.split(":", 1)[1].lower() for r in refs}
        return [
            m for m in self._knowledge_base.global_context.all_methods
            if m.name.lower() in method_names
        ]

    def get_type(self, name: str) -> PlatformType | None:
        """Get type by name."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.get_type(name)

    def search_types(self, query: str) -> list[PlatformType]:
        """Search types using inverted index."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        refs = self._search_index_lookup(query, category="type")
        if not refs:
            return []
        type_names = {r.split(":", 1)[1].lower() for r in refs}
        return [
            t for t in self._knowledge_base.types
            if t.name.lower() in type_names
        ]

    def get_event(self, name: str) -> ObjectEvent | None:
        """Get event by name."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.get_event(name)

    def search_events(self, query: str) -> list[ObjectEvent]:
        """Search events using inverted index."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        refs = self._search_index_lookup(query, category="event")
        if not refs:
            return []
        event_names = {r.split(":", 1)[1].lower() for r in refs}
        return [
            e for e in self._knowledge_base.events
            if e.name.lower() in event_names
        ]

    def get_events_for_object(self, object_type: str) -> list[ObjectEvent]:
        """Get events for a specific object type."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.get_events_for_object(object_type)

    def get_type_method(self, type_name: str, method_name: str) -> PlatformMethod | None:
        """Get method of a specific type."""
        platform_type = self.get_type(type_name)
        if platform_type:
            return platform_type.get_method(method_name)
        return None

    def get_type_property(self, type_name: str, property_name: str) -> PlatformProperty | None:
        """Get property of a specific type."""
        platform_type = self.get_type(type_name)
        if platform_type:
            return platform_type.get_property(property_name)
        return None

    def get_all_methods(self) -> list[PlatformMethod]:
        """Get all global context methods."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.global_context.all_methods

    def get_all_types(self) -> list[PlatformType]:
        """Get all platform types."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.types

    def get_all_events(self) -> list[ObjectEvent]:
        """Get all events."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.events

    def get_global_context_sections(self) -> list[GlobalContextSection]:
        """Get all global context sections."""
        self._ensure_loaded()
        assert self._knowledge_base is not None
        return self._knowledge_base.global_context.sections

    def search_all(self, query: str) -> dict[str, list]:
        """Search across methods, types, and events."""
        return {
            "methods": self.search_methods(query),
            "types": self.search_types(query),
            "events": self.search_events(query),
        }
