"""Shared JSON type aliases for the public SDK."""

from __future__ import annotations

from pydantic import JsonValue as PydanticJsonValue

type JSONPrimitive = str | int | float | bool | None
type JSONValue = PydanticJsonValue
type JSONObject = dict[str, PydanticJsonValue]

__all__ = ["JSONObject", "JSONPrimitive", "JSONValue"]
