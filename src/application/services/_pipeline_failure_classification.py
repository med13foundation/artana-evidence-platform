"""Helpers for classifying pipeline infrastructure failures."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_CAPACITY_ERROR_MARKERS: tuple[str, ...] = (
    "toomanyconnectionserror",
    "remaining connection slots are reserved",
    "pg_use_reserved_connections",
    "too many connections",
    "connection pool exhausted",
    "connection acquisition timeout",
    "pool timeout",
    "could not acquire connection",
)


def is_capacity_failure_text(raw_value: object) -> bool:
    """Return True when the text matches a DB-capacity or pool-exhaustion failure."""
    if not isinstance(raw_value, str):
        return False
    normalized = raw_value.strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _CAPACITY_ERROR_MARKERS)


def resolve_pipeline_error_category(messages: Iterable[str]) -> str | None:
    """Resolve a stable pipeline error category from aggregated failure messages."""
    for message in messages:
        if is_capacity_failure_text(message):
            return "capacity"
    return None


__all__ = [
    "is_capacity_failure_text",
    "resolve_pipeline_error_category",
]
