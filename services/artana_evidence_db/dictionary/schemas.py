"""Dictionary data-type normalization and constraint schemas."""

from __future__ import annotations

from copy import deepcopy
from typing import Final

from artana_evidence_db.common_types import JSONObject

_SUPPORTED_DATA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "INTEGER",
        "FLOAT",
        "STRING",
        "DATE",
        "CODED",
        "BOOLEAN",
        "JSON",
    },
)
_DATA_TYPE_ALIASES: Final[dict[str, str]] = {
    "TEXT": "STRING",
    "STR": "STRING",
    "INT": "INTEGER",
    "LONG": "INTEGER",
    "DOUBLE": "FLOAT",
    "DECIMAL": "FLOAT",
    "NUMBER": "FLOAT",
    "BOOL": "BOOLEAN",
    "OBJECT": "JSON",
    "MAP": "JSON",
    "DICT": "JSON",
    "STRUCT": "JSON",
    "ARRAY": "JSON",
    "LIST": "JSON",
}
_CONSTRAINT_SCHEMA_BY_DATA_TYPE: Final[dict[str, JSONObject]] = {
    "INTEGER": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min": {"type": "number"},
            "max": {"type": "number"},
            "precision": {"type": "integer", "minimum": 0},
        },
    },
    "FLOAT": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min": {"type": "number"},
            "max": {"type": "number"},
            "precision": {"type": "integer", "minimum": 0},
        },
    },
    "STRING": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min_length": {"type": "integer", "minimum": 0},
            "max_length": {"type": "integer", "minimum": 0},
            "pattern": {"type": "string"},
        },
    },
    "DATE": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min_date": {"type": "string"},
            "max_date": {"type": "string"},
        },
    },
    "CODED": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value_set_id": {"type": "string"},
            "allow_other": {"type": "boolean"},
        },
    },
    "BOOLEAN": {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    },
    "JSON": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "json_schema": {"type": "object"},
        },
    },
}


def normalize_dictionary_data_type(data_type: str) -> str:
    """Normalize a dictionary data type identifier."""
    normalized = data_type.strip().upper()
    if normalized in _SUPPORTED_DATA_TYPES:
        return normalized
    alias = _DATA_TYPE_ALIASES.get(normalized)
    if alias is not None:
        return alias
    if normalized.endswith(("_LIST", "_ARRAY")):
        return "JSON"
    return normalized


def get_constraint_schema_for_data_type(data_type: str) -> JSONObject:
    """Return the JSON schema payload for a dictionary data type."""
    normalized = normalize_dictionary_data_type(data_type)
    schema = _CONSTRAINT_SCHEMA_BY_DATA_TYPE.get(normalized)
    if schema is None:
        return {}
    return deepcopy(schema)


__all__ = [
    "_CONSTRAINT_SCHEMA_BY_DATA_TYPE",
    "_DATA_TYPE_ALIASES",
    "_SUPPORTED_DATA_TYPES",
    "get_constraint_schema_for_data_type",
    "normalize_dictionary_data_type",
]
