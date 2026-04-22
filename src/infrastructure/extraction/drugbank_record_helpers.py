"""Small parsing helpers for DrugBank extraction processors."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def first_scalar(payload: JSONObject, keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty scalar value for one of the provided keys."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int):
            return str(value)
    return None


def extract_string_list(
    payload: JSONObject,
    keys: tuple[str, ...],
) -> list[str]:
    """Extract a list of strings from the first matching source field."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            extracted: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    extracted.append(item.strip())
                elif isinstance(item, dict):
                    for nested_key in ("name", "value", "synonym", "brand_name"):
                        nested_value = item.get(nested_key)
                        if isinstance(nested_value, str) and nested_value.strip():
                            extracted.append(nested_value.strip())
                            break
            return extracted
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return [stripped]
    return []


def dedupe_strings(values: list[str]) -> list[str]:
    """Normalize and deduplicate extracted source text values."""
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.split())
        if not normalized:
            continue
        normalized_key = normalized.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        deduped.append(normalized)
    return deduped


__all__ = ["dedupe_strings", "extract_string_list", "first_scalar"]
