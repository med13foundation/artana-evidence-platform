# ruff: noqa: TC001,TC003
"""Shared schema helpers and enums for dictionary admin routes."""

from __future__ import annotations

from enum import Enum


def _coerce_embedding(value: object) -> list[float] | None:
    """Normalize database embedding payloads to a float list."""
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        if not stripped:
            return []
        return [float(token) for token in stripped.split(",") if token.strip()]
    return None


class KernelDataType(str, Enum):
    """Allowed kernel dictionary data types."""

    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    DATE = "DATE"
    CODED = "CODED"
    BOOLEAN = "BOOLEAN"
    JSON = "JSON"


class KernelSensitivity(str, Enum):
    """Sensitivity classification for dictionary variables and identifiers."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    PHI = "PHI"


class KernelReviewStatus(str, Enum):
    """Review lifecycle states for dictionary entries."""

    ACTIVE = "ACTIVE"
    PENDING_REVIEW = "PENDING_REVIEW"
    REVOKED = "REVOKED"


class KernelDictionaryDimension(str, Enum):
    """Search dimensions supported by dictionary_search."""

    VARIABLES = "variables"
    ENTITY_TYPES = "entity_types"
    RELATION_TYPES = "relation_types"
    CONSTRAINTS = "constraints"


class KernelSearchMatchMethod(str, Enum):
    """Search ranking match methods."""

    EXACT = "exact"
    SYNONYM = "synonym"
    FUZZY = "fuzzy"
    VECTOR = "vector"


__all__ = [
    "KernelDataType",
    "KernelDictionaryDimension",
    "KernelReviewStatus",
    "KernelSearchMatchMethod",
    "KernelSensitivity",
    "_coerce_embedding",
]
