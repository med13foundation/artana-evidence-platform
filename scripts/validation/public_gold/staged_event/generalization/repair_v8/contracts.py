"""Versioned V8 semantic descriptions with an unchanged output shape."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    SemanticAxes,
    StagedGeneralizationOutput,
)

V8Polarity = Literal["AFFIRMED", "NEGATED", "NULL_RESULT"]
POLARITY_TAXONOMY = (
    "Polarity records scientific result status, not surface grammar, and is "
    "independent of direction and uncertainty. Use NULL_RESULT when a study or "
    "analysis reports absence of an association, difference, or effect, regardless "
    "of negative grammatical form. Use NEGATED only for direct denial or "
    "non-occurrence outside an analytic null finding. Use AFFIRMED for other "
    "non-null findings."
)


class V8SemanticAxes(SemanticAxes):
    """Semantic axes with the preregistered polarity boundary in the schema."""

    polarity: V8Polarity = Field(description=POLARITY_TAXONOMY)


class V8StagedGeneralizationOutput(StagedGeneralizationOutput):
    """V8 output with only the polarity field description versioned."""

    semantic_axes: tuple[V8SemanticAxes, ...] = Field(min_length=1, max_length=16)


__all__ = [
    "POLARITY_TAXONOMY",
    "V8Polarity",
    "V8SemanticAxes",
    "V8StagedGeneralizationOutput",
]
