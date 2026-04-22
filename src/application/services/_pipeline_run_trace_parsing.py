"""Parsing helpers for persisted pipeline timing and cost metadata."""

from __future__ import annotations

from pydantic import ValidationError

from src.type_definitions.data_sources import (
    PipelineRunCostMetadata,
    PipelineRunTimingMetadata,
)
from src.type_definitions.json_utils import as_float


def parse_timing_summary(raw_value: object) -> PipelineRunTimingMetadata | None:
    """Parse persisted timing summary metadata when available."""
    if not isinstance(raw_value, dict):
        return None
    try:
        return PipelineRunTimingMetadata.model_validate(raw_value)
    except ValidationError:
        return None


def parse_cost_summary(raw_value: object) -> PipelineRunCostMetadata | None:
    """Parse persisted cost summary metadata when available."""
    if not isinstance(raw_value, dict):
        return None
    try:
        normalized_payload = dict(raw_value)
        total_cost = as_float(normalized_payload.get("total_cost_usd"))
        if total_cost is not None:
            normalized_payload["total_cost_usd"] = max(total_cost, 0.0)
        return PipelineRunCostMetadata.model_validate(normalized_payload)
    except ValidationError:
        return None


__all__ = ["parse_cost_summary", "parse_timing_summary"]
