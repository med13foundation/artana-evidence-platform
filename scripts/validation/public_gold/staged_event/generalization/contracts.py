"""Strict agent-owned output for one staged generalization case."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel

EventType = Literal[
    "REGULATION",
    "POSITIVE_REGULATION",
    "NEGATIVE_REGULATION",
    "GENE_EXPRESSION",
    "COMPARISON",
    "ASSOCIATION",
    "CLASSIFICATION",
    "OBSERVATION",
]
EntityType = Literal[
    "POPULATION",
    "OUTCOME",
    "EXPOSURE",
    "VARIANT",
    "GENE_OR_PROTEIN",
    "CANCER",
    "SIMPLE_CHEMICAL",
    "MEASUREMENT",
]
ArgumentRole = Literal[
    "AFFECTED_ENTITY",
    "CAUSAL_AGENT",
    "STIMULUS_OR_OBJECT",
    "POPULATION",
    "COMPARATOR",
    "OUTCOME",
    "EXPOSURE",
    "MEASUREMENT",
    "CONTEXTUAL_PARTICIPANT",
    "EFFECT_EVENT",
]
Direction = Literal[
    "INCREASED",
    "DECREASED",
    "NO_DIFFERENCE",
    "NO_ASSOCIATION",
    "ENABLES",
    "OBSERVED",
    "NOT_APPLICABLE",
]
Comparison = Literal["GREATER", "LESS", "NO_DIFFERENCE", "NOT_APPLICABLE"]
Polarity = Literal["AFFIRMED", "NEGATED", "NULL_RESULT"]
Uncertainty = Literal["ASSERTED", "PROVISIONAL", "UNCERTAIN", "HYPOTHESIS"]
StatisticalType = Literal["P_VALUE", "CONFIDENCE_INTERVAL", "EFFECT_ESTIMATE", "NONE"]
TargetKind = Literal["PARTICIPANT", "EVENT"]
AuthorInterpretation = Literal["SIGNIFICANT", "NOT_SIGNIFICANT", "NOT_CLAIMED"]


class InventoryEvent(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: EventType
    trigger_text: str = Field(min_length=1, max_length=256)
    exact_evidence: str = Field(
        min_length=1,
        max_length=4000,
        description="Complete exact source sentence containing trigger_text.",
    )
    explanation: str = Field(min_length=1, max_length=1000)


class ParticipantNode(StrictStageModel):
    participant_id: str = Field(min_length=1, max_length=128)
    entity_type: EntityType
    exact_text: str = Field(min_length=1, max_length=1000)
    exact_evidence: str = Field(
        min_length=1,
        max_length=4000,
        description="Complete exact source sentence containing exact_text.",
    )
    explanation: str = Field(min_length=1, max_length=1000)


class EventArgument(StrictStageModel):
    role: ArgumentRole
    target_kind: TargetKind
    target_id: str = Field(min_length=1, max_length=128)
    explanation: str = Field(min_length=1, max_length=1000)


class EventLinks(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    arguments: tuple[EventArgument, ...] = Field(max_length=16)


class StatisticalObservation(StrictStageModel):
    observation_type: StatisticalType
    exact_text: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_text(self) -> StatisticalObservation:
        if self.observation_type == "NONE" and self.exact_text is not None:
            raise ValueError("NONE statistical observation cannot contain text")
        if self.observation_type != "NONE" and not self.exact_text:
            raise ValueError("statistical observation requires exact text")
        return self


class SemanticAxes(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    direction: Direction
    comparison: Comparison
    polarity: Polarity
    uncertainty: Uncertainty
    statistical_observations: tuple[StatisticalObservation, ...] = Field(max_length=8)
    author_interpretation: AuthorInterpretation
    evidence_items: tuple[str, ...] = Field(min_length=1, max_length=8)
    explanation: str = Field(min_length=1, max_length=1500)


class StagedGeneralizationOutput(StrictStageModel):
    case_id: str = Field(min_length=1, max_length=128)
    inventory: tuple[InventoryEvent, ...] = Field(min_length=1, max_length=16)
    participants: tuple[ParticipantNode, ...] = Field(max_length=32)
    links: tuple[EventLinks, ...] = Field(min_length=1, max_length=16)
    semantic_axes: tuple[SemanticAxes, ...] = Field(min_length=1, max_length=16)
    root_event_id: str = Field(min_length=1, max_length=128)
    completeness: Literal["COMPLETE", "INCOMPLETE", "CONTRADICTED", "ABSTAIN"]
    structure_explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_stage_inventory(self) -> StagedGeneralizationOutput:
        event_ids = [item.event_id for item in self.inventory]
        participant_ids = [item.participant_id for item in self.participants]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event IDs must be unique")
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("participant IDs must be unique")
        if set(event_ids) & set(participant_ids):
            raise ValueError("event and participant IDs must not overlap")
        if self.root_event_id not in event_ids:
            raise ValueError("root event is absent from inventory")
        if {item.event_id for item in self.links} != set(event_ids):
            raise ValueError("link stage must cover every event exactly once")
        if {item.event_id for item in self.semantic_axes} != set(event_ids):
            raise ValueError("semantic stage must cover every event exactly once")
        for link in self.links:
            for argument in link.arguments:
                target_ids = (
                    set(participant_ids)
                    if argument.target_kind == "PARTICIPANT"
                    else set(event_ids)
                )
                if argument.target_id not in target_ids:
                    raise ValueError("argument target is absent or kind-mismatched")
        event_edges = {
            link.event_id: tuple(
                argument.target_id
                for argument in link.arguments
                if argument.target_kind == "EVENT"
            )
            for link in self.links
        }
        _reject_cycles(event_edges)
        return self


def _reject_cycles(event_edges: dict[str, tuple[str, ...]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(event_id: str) -> None:
        if event_id in visiting:
            raise ValueError("event graph must be acyclic")
        if event_id in visited:
            return
        visiting.add(event_id)
        for target_id in event_edges[event_id]:
            visit(target_id)
        visiting.remove(event_id)
        visited.add(event_id)

    for event_id in event_edges:
        visit(event_id)


__all__ = ["StagedGeneralizationOutput"]
