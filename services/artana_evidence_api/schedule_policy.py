"""Shared cadence validation and due-calculation rules for harness schedules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

_BUSINESS_WEEKDAY_LIMIT: Final[int] = 5

SUPPORTED_SCHEDULE_CADENCES: Final[tuple[str, ...]] = (
    "manual",
    "hourly",
    "daily",
    "weekday",
    "weekly",
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_schedule_cadence(cadence: str) -> str:
    """Normalize and validate one schedule cadence."""
    normalized = cadence.strip().lower()
    if normalized not in SUPPORTED_SCHEDULE_CADENCES:
        supported = ", ".join(SUPPORTED_SCHEDULE_CADENCES)
        message = f"Unsupported cadence '{cadence}'. Expected one of: {supported}"
        raise ValueError(message)
    return normalized


def is_schedule_due(
    *,
    cadence: str,
    last_run_at: datetime | None,
    now: datetime,
) -> bool:
    """Return whether one schedule should trigger in the current cadence window."""
    normalized_cadence = normalize_schedule_cadence(cadence)
    if normalized_cadence == "manual":
        return False

    resolved_now = _as_utc(now)
    if last_run_at is None:
        return (
            normalized_cadence != "weekday"
            or resolved_now.weekday() < _BUSINESS_WEEKDAY_LIMIT
        )

    resolved_last_run_at = _as_utc(last_run_at)
    if normalized_cadence == "hourly":
        return (
            resolved_now.year,
            resolved_now.month,
            resolved_now.day,
            resolved_now.hour,
        ) != (
            resolved_last_run_at.year,
            resolved_last_run_at.month,
            resolved_last_run_at.day,
            resolved_last_run_at.hour,
        )
    if normalized_cadence == "daily":
        return resolved_now.date() != resolved_last_run_at.date()
    if normalized_cadence == "weekday":
        return (
            resolved_now.weekday() < _BUSINESS_WEEKDAY_LIMIT
            and resolved_now.date() != resolved_last_run_at.date()
        )

    now_week = resolved_now.isocalendar()
    last_run_week = resolved_last_run_at.isocalendar()
    return (now_week.year, now_week.week) != (
        last_run_week.year,
        last_run_week.week,
    )


__all__ = [
    "SUPPORTED_SCHEDULE_CADENCES",
    "is_schedule_due",
    "normalize_schedule_cadence",
]
