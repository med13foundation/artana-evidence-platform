"""Strict sidecar contracts for absolute source occurrence identity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel

SCHEMA_VERSION: Literal[
    "artana.staged_generalization.occurrence_bindings.v2"
] = "artana.staged_generalization.occurrence_bindings.v2"


class AbsoluteSourceSpan(StrictStageModel):
    """Half-open absolute offsets into the frozen case source."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> AbsoluteSourceSpan:
        if self.end <= self.start:
            raise ValueError("source span end must be greater than start")
        return self


class MentionIdentity(StrictStageModel):
    """Absolute identity for one mention and its declared evidence."""

    evidence_span: AbsoluteSourceSpan
    mention_span: AbsoluteSourceSpan


class NodeMentionBinding(StrictStageModel):
    """Bind one event or participant node to an explicit source occurrence."""

    node_id: str = Field(min_length=1, max_length=128)
    identity: MentionIdentity


class SemanticEvidenceBinding(StrictStageModel):
    """Bind ordered semantic evidence and statistical observations to source."""

    event_id: str = Field(min_length=1, max_length=128)
    evidence_item_spans: tuple[AbsoluteSourceSpan, ...] = Field(
        min_length=1,
        max_length=8,
    )
    statistical_observation_spans: tuple[AbsoluteSourceSpan | None, ...] = Field(
        max_length=8,
    )


class OccurrenceAwareBindings(StrictStageModel):
    """Complete occurrence sidecar for one scientific extraction."""

    schema_version: Literal[
        "artana.staged_generalization.occurrence_bindings.v2"
    ] = SCHEMA_VERSION
    case_id: str = Field(min_length=1, max_length=128)
    event_mentions: tuple[NodeMentionBinding, ...] = Field(
        min_length=1,
        max_length=16,
    )
    participant_mentions: tuple[NodeMentionBinding, ...] = Field(max_length=32)
    semantic_evidence: tuple[SemanticEvidenceBinding, ...] = Field(
        min_length=1,
        max_length=16,
    )

    @model_validator(mode="after")
    def validate_unique_binding_ids(self) -> OccurrenceAwareBindings:
        _require_unique(
            (binding.node_id for binding in self.event_mentions),
            "event mention binding IDs",
        )
        _require_unique(
            (binding.node_id for binding in self.participant_mentions),
            "participant mention binding IDs",
        )
        _require_unique(
            (binding.event_id for binding in self.semantic_evidence),
            "semantic evidence binding IDs",
        )
        return self


def _require_unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(items) != len(set(items)):
        raise ValueError(f"{label} must be unique")


__all__ = [
    "AbsoluteSourceSpan",
    "MentionIdentity",
    "NodeMentionBinding",
    "OccurrenceAwareBindings",
    "SCHEMA_VERSION",
    "SemanticEvidenceBinding",
]
