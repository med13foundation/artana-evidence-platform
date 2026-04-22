"""Shared helpers for kernel API schema modules."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID


def _to_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _to_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _to_required_utc_datetime(
    value: datetime | None,
    *,
    field_name: str,
) -> datetime:
    normalized = _to_utc_datetime(value)
    if normalized is None:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return normalized


__all__ = [
    "_to_required_utc_datetime",
    "_to_utc_datetime",
    "_to_uuid",
]
