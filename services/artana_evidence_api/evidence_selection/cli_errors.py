"""Safe diagnostic rendering for human-provided evidence-selection files."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError


def cli_error_message(error: Exception) -> str:
    """Return a user-safe error message without echoing invalid input values."""

    if not isinstance(error, ValidationError):
        return str(error)
    locations = tuple(
        _location_text(detail.get("loc"))
        for detail in error.errors(
            include_context=False,
            include_input=False,
            include_url=False,
        )
    )
    if not locations:
        return "validation failed"
    return "validation failed for fields: " + ", ".join(locations[:5])


def _location_text(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return "input"
    location = ".".join(str(part) for part in value)
    return location or "input"


__all__ = ["cli_error_message"]
