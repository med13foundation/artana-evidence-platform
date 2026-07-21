"""Frozen structured-output transport contract for lossless event extraction."""

from __future__ import annotations

from typing import cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ScientificEventExtraction,
)

PROVIDER_RESPONSE_FORMAT_DESCRIPTION = (
    "Lossless scientific events with exact source offsets and typed references."
)


def build_scientific_event_provider_format() -> dict[str, object]:
    """Return a fresh API-shaped format with an explicit stable description."""

    provider_format = cast(
        "dict[str, object]",
        type_to_text_format_param(ScientificEventExtraction),
    )
    provider_format["description"] = PROVIDER_RESPONSE_FORMAT_DESCRIPTION
    return provider_format


__all__ = [
    "PROVIDER_RESPONSE_FORMAT_DESCRIPTION",
    "build_scientific_event_provider_format",
]
