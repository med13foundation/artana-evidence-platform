"""
Serialization utilities for bulk export formatting.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject, JSONValue

__all__ = [
    "coerce_scalar",
    "item_to_csv_row",
    "resolve_nested_value",
    "serialize_item",
]


def serialize_item(item: object) -> JSONValue:
    """Serialize arbitrary objects into JSON-compatible values."""
    if isinstance(item, datetime):
        return item.isoformat()

    if _is_namedtuple(item):
        return _serialize_namedtuple(item)

    if isinstance(item, dict):
        return {key: serialize_item(value) for key, value in item.items()}

    if hasattr(item, "__dict__"):
        return _serialize_object(item)

    if isinstance(item, list | tuple):
        return _serialize_sequence(item)

    return coerce_scalar(item)


def item_to_csv_row(item: object, field_names: list[str]) -> dict[str, str]:
    """Take a serialized item and return a CSV-ready row."""
    serialized_raw = serialize_item(item)
    serialized = (
        serialized_raw
        if isinstance(serialized_raw, dict)
        else {"value": serialized_raw}
    )
    row: dict[str, str] = {}

    for field in field_names:
        value: JSONValue = serialized.get(field, "")
        if "." in field:
            value = resolve_nested_value(serialized, field.split("."))

        if isinstance(value, list | tuple):
            rendered: str = ";".join(str(v) for v in value)
        elif value is None:
            rendered = ""
        else:
            rendered = str(value)
        row[field] = rendered

    return row


def resolve_nested_value(source: JSONValue, path: Sequence[str]) -> JSONValue:
    """Resolve dotted-path fields for nested JSON data."""
    current: JSONValue = source
    for part in path:
        if isinstance(current, dict):
            current = current.get(part, "")
        elif hasattr(current, part):
            current = coerce_scalar(getattr(current, part, ""))
        else:
            return ""
    return current


def coerce_scalar(value: object) -> JSONValue:
    """Convert non-JSON values into strings."""
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _is_namedtuple(candidate: object) -> bool:
    fields = getattr(candidate, "_fields", [])
    return bool(fields) and all(isinstance(field, str) for field in fields)


def _serialize_namedtuple(item: object) -> JSONObject:
    field_names = getattr(item, "_fields", ())
    if not isinstance(field_names, Sequence):
        return {}
    return {str(field): serialize_item(getattr(item, field)) for field in field_names}


def _serialize_object(item: object) -> JSONObject:
    result: JSONObject = {}
    for key, value in vars(item).items():
        if key.startswith("_"):
            continue
        result[key] = serialize_item(value)
    return result


def _serialize_sequence(items: Sequence[object]) -> list[JSONValue]:
    return [serialize_item(value) for value in items]
