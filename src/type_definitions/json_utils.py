"""
Helpers for working with JSON-like payloads in a type-safe way.

These utilities narrow `JSONValue` unions to concrete Python types so that
parsers and normalizers can operate without resorting to untyped fallbacks.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Iterable, Protocol, TypeGuard  # noqa: UP035

from .common import JSONObject, JSONValue  # noqa: TC001


class DataclassInstance(Protocol):
    """Protocol describing dataclass instances for type narrowing."""

    __dataclass_fields__: dict[str, object]


def _is_dataclass_instance(value: object) -> TypeGuard[DataclassInstance]:
    """Type guard ensuring value is a dataclass instance."""
    return is_dataclass(value)


def as_object(value: JSONValue | None) -> JSONObject:
    """Return the value as a JSON object or an empty dict when not a mapping."""
    if isinstance(value, dict):
        return value
    return {}


def as_list(value: JSONValue | None) -> list[JSONValue]:
    """Return the value as a JSON list or an empty list when not a list."""
    if isinstance(value, list):
        return value
    return []


def list_of_objects(value: JSONValue | None) -> list[JSONObject]:
    """Return a list containing only dict entries from the provided value."""
    return [item for item in as_list(value) if isinstance(item, dict)]


def list_of_strings(value: JSONValue | None) -> list[str]:
    """Return a list of stringified entries from the provided value."""
    result: list[str] = []
    for item in as_list(value):
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, int | float):
            result.append(str(item))
    return result


def as_str(value: JSONValue | None, *, fallback: str | None = None) -> str | None:
    """Return the value as a string if possible."""
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return fallback


def as_int(value: JSONValue | None) -> int | None:
    """Return the value as an integer when coercion is safe."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def as_float(value: JSONValue | None) -> float | None:
    """Return the value as a float when coercion is safe."""
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def extend_unique(collection: list[str], new_values: Iterable[str]) -> None:
    """Extend a list with new values while preserving uniqueness."""
    for value in new_values:
        if value not in collection:
            collection.append(value)


def to_json_value(value: object) -> JSONValue:
    """
    Convert arbitrary Python objects into a JSONValue structure.

    Dataclasses, enums, datetime objects, and nested containers are serialised
    into JSON-compatible primitives so downstream code stays fully typed.
    """

    result: JSONValue
    if value is None or isinstance(value, str | int | float | bool):
        result = value
    elif isinstance(value, datetime | date):
        result = value.isoformat()
    elif isinstance(value, Enum):
        enum_value = value.value
        if isinstance(enum_value, str | int | float | bool):
            result = enum_value
        else:
            result = str(enum_value)
    elif _is_dataclass_instance(value):
        dataclass_dict = asdict(value)  # type: ignore[call-overload]
        result = {key: to_json_value(item) for key, item in dataclass_dict.items()}
    elif isinstance(value, dict):
        result = {str(key): to_json_value(item) for key, item in value.items()}
    elif isinstance(value, list | tuple | set):
        result = [to_json_value(item) for item in value]
    else:
        result = str(value)

    return result
