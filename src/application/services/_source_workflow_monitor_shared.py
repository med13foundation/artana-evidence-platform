"""Shared utilities for source workflow monitoring services."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


PENDING_DOCUMENT_STATUSES: tuple[str, ...] = ("pending", "in_progress")
PENDING_RELATION_STATUSES: tuple[str, ...] = ("DRAFT", "UNDER_REVIEW")


def coerce_json_object(raw_value: object) -> JSONObject:
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): value for key, value in raw_value.items()}


def coerce_json_list(raw_value: object) -> list[object]:
    if not isinstance(raw_value, list):
        return []
    return list(raw_value)


def normalize_optional_string(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def safe_int(raw_value: object) -> int:
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return 0
    return 0


def parse_uuid_runtime(raw_value: object) -> uuid.UUID | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        return uuid.UUID(normalized)
    except ValueError:
        return None


@dataclass(frozen=True)
class PipelineRunRecord:
    payload: JSONObject
    run_id: str
    job_id: str


__all__ = [
    "PENDING_DOCUMENT_STATUSES",
    "PENDING_RELATION_STATUSES",
    "PipelineRunRecord",
    "coerce_json_list",
    "coerce_json_object",
    "normalize_optional_string",
    "parse_uuid_runtime",
    "safe_int",
]
