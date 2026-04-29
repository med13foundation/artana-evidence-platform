"""Shared public source-route error formatting."""

from __future__ import annotations

from pydantic import ValidationError


def validation_error_text(error: ValidationError) -> str:
    """Return compact validation text for generic direct-source route payloads."""

    messages: list[str] = []
    for validation_error in error.errors():
        raw_location = validation_error.get("loc")
        message = str(validation_error.get("msg", "Validation error")).strip()
        if message.startswith("Value error, "):
            message = message.removeprefix("Value error, ").strip()
        if isinstance(raw_location, tuple | list) and raw_location:
            location = " -> ".join(str(part) for part in raw_location)
            messages.append(f"{location}: {message}")
        else:
            messages.append(message or "Validation error")
    return "; ".join(dict.fromkeys(messages)) or "Validation error"


__all__ = [
    "validation_error_text",
]
