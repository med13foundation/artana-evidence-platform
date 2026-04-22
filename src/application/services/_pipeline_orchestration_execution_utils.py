"""Shared utilities for unified pipeline orchestration execution."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from src.application.services._pipeline_failure_classification import (
    resolve_pipeline_error_category,
)

if TYPE_CHECKING:
    from uuid import UUID

    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)

ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS = (
    "ARTANA_PIPELINE_EXTRACTION_STAGE_TIMEOUT_SECONDS"
)
DEFAULT_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS = 900.0
ENV_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS = (
    "ARTANA_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS"
)
DEFAULT_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS = 180.0
ENV_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS = (
    "ARTANA_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS"
)
DEFAULT_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS = 300.0
ENV_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY = (
    "ARTANA_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY"
)
DEFAULT_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY = 2
EXTRACTION_STAGE_TIMEOUT_OVERHEAD_SECONDS = 15.0
ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD = (
    "ARTANA_PIPELINE_EXTRACTION_FAILURE_RATIO_THRESHOLD"
)
DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD = 1.0
ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED = (
    "ARTANA_PIPELINE_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED"
)
DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED = 0.0


def read_positive_timeout_seconds(
    env_name: str,
    *,
    default_seconds: float,
) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_seconds
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid timeout override in %s=%r; using default %.1fs",
            env_name,
            raw_value,
            default_seconds,
        )
        return default_seconds
    if parsed <= 0:
        logger.warning(
            "Non-positive timeout override in %s=%r; using default %.1fs",
            env_name,
            raw_value,
            default_seconds,
        )
        return default_seconds
    return parsed


def read_positive_int(
    env_name: str,
    *,
    default_value: int,
) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid integer override in %s=%r; using default %s",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive integer override in %s=%r; using default %s",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def json_string(payload: JSONObject, key: str) -> str | None:
    raw_value = payload.get(key)
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized if normalized else None


def json_int(payload: JSONObject, key: str) -> int | None:
    raw_value = payload.get(key)
    return raw_value if isinstance(raw_value, int) else None


def read_failure_ratio_threshold(
    env_name: str,
    *,
    default_value: float,
) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default_value
    try:
        parsed = float(raw_value)
    except ValueError:
        logger.warning(
            "Invalid ratio override in %s=%r; using default %.3f",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed < 0:
        logger.warning(
            "Negative ratio override in %s=%r; clamping to 0.0",
            env_name,
            raw_value,
        )
        return 0.0
    if parsed > 1:
        logger.warning(
            "Ratio override above 1.0 in %s=%r; clamping to 1.0",
            env_name,
            raw_value,
        )
        return 1.0
    return parsed


def resolve_extraction_failure_ratio_threshold(source_type: str | None) -> float:
    normalized_source_type = source_type.strip().lower() if source_type else None
    if normalized_source_type == "pubmed":
        return read_failure_ratio_threshold(
            ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED,
            default_value=DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD_PUBMED,
        )
    return read_failure_ratio_threshold(
        ENV_EXTRACTION_FAILURE_RATIO_THRESHOLD,
        default_value=DEFAULT_EXTRACTION_FAILURE_RATIO_THRESHOLD,
    )


def coerce_optional_uuid(raw_value: object) -> UUID | None:
    if raw_value is None:
        return None

    import uuid

    if isinstance(raw_value, uuid.UUID):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if not normalized:
            return None
        try:
            return uuid.UUID(normalized)
        except ValueError:
            return None
    return None


def first_matching_error(
    messages: tuple[str, ...] | list[str],
    *,
    category: str | None,
) -> str | None:
    if category is None:
        return None
    for message in messages:
        if resolve_pipeline_error_category((message,)) == category:
            return message
    return None


__all__ = [
    "DEFAULT_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS",
    "DEFAULT_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY",
    "DEFAULT_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS",
    "DEFAULT_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS",
    "ENV_ENTITY_RECOGNITION_AGENT_TIMEOUT_SECONDS",
    "ENV_ENTITY_RECOGNITION_BATCH_MAX_CONCURRENCY",
    "ENV_ENTITY_RECOGNITION_EXTRACTION_STAGE_TIMEOUT_SECONDS",
    "ENV_EXTRACTION_STAGE_WATCHDOG_TIMEOUT_SECONDS",
    "EXTRACTION_STAGE_TIMEOUT_OVERHEAD_SECONDS",
    "coerce_optional_uuid",
    "first_matching_error",
    "json_int",
    "json_string",
    "read_positive_int",
    "read_positive_timeout_seconds",
    "resolve_extraction_failure_ratio_threshold",
]
