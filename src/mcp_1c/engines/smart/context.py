"""Active configuration profile binding for smart-builders.

The smart-builder helpers (``TypeResolver``, ``query_builder._should_skip``,
print/movement builders) accept ``profile`` as an argument; that's
the right contract for unit tests and for code that has a
``Workspace`` handle. But when ``SmartGenerator.get_instance()`` is
invoked through the singleton path (the way every smart-* tool calls
it today), the workspace isn't directly visible — and we don't want
to thread a ``profile`` parameter through five call sites just to
have it land in one helper.

This module binds the active profile via :class:`contextvars.ContextVar`
so the smart-builder reads can pull it without a parameter, while the
tool registration path (eventually the workspace boot path) sets it
once at the start of a request. ContextVar respects asyncio's
per-task copying, so concurrent requests with different profiles
don't cross-contaminate.

Default value is ``None`` — readers fall back to their pre-F4
hardcoded behaviour, preserving backward compatibility for the test
suites that drive smart-builders directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_1c.engines.profile import ConfigurationProfile

active_profile: ContextVar[ConfigurationProfile | None] = ContextVar(
    "mcp_1c.engines.smart.active_profile", default=None
)


def get_active_profile() -> ConfigurationProfile | None:
    """Return the currently bound profile, or ``None`` if none."""
    return active_profile.get()


def set_active_profile(profile: ConfigurationProfile | None) -> Token:
    """Bind ``profile`` until ``reset(token)`` is called.

    Returned ``Token`` should be passed to ``active_profile.reset(token)``
    after the request finishes; using :func:`use_active_profile` as a
    context manager is the safer ergonomic.
    """
    return active_profile.set(profile)


@contextmanager
def use_active_profile(
    profile: ConfigurationProfile | None,
) -> Iterator[None]:
    """Bind ``profile`` for the duration of the ``with`` block.

    Tests use this to assert smart-builder behaviour under specific
    profiles; the workspace bootstrap uses it (Phase 2) to scope
    profile to a single tool invocation.
    """
    token = active_profile.set(profile)
    try:
        yield
    finally:
        active_profile.reset(token)


__all__ = [
    "active_profile",
    "get_active_profile",
    "set_active_profile",
    "use_active_profile",
]
