"""Strict agent-owned contracts for the staged scientific-event comparison."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,  # noqa: TC001 - required at runtime by Pydantic
)


class StrictStageModel(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class StatementKind(str, Enum):
    EXPLICIT_RESULT = "EXPLICIT_RESULT"
    MECHANISM = "MECHANISM"
    BACKGROUND = "BACKGROUND"
    METHOD = "METHOD"
    HYPOTHESIS = "HYPOTHESIS"


class ParticipantTargetKind(str, Enum):
    PARTICIPANT = "PARTICIPANT"
    EVENT = "EVENT"


class SourceEntityType(str, Enum):
    AMINO_ACID = "Amino_acid"
    ANATOMICAL_SYSTEM = "Anatomical_system"
    CANCER = "Cancer"
    CELL = "Cell"
    CELLULAR_COMPONENT = "Cellular_component"
    DNA_DOMAIN_OR_REGION = "DNA_domain_or_region"
    DEVELOPING_ANATOMICAL_STRUCTURE = "Developing_anatomical_structure"
    GENE_OR_GENE_PRODUCT = "Gene_or_gene_product"
    IMMATERIAL_ANATOMICAL_ENTITY = "Immaterial_anatomical_entity"
    MULTI_TISSUE_STRUCTURE = "Multi-tissue_structure"
    ORGAN = "Organ"
    ORGANISM = "Organism"
    ORGANISM_SUBDIVISION = "Organism_subdivision"
    ORGANISM_SUBSTANCE = "Organism_substance"
    PATHOLOGICAL_FORMATION = "Pathological_formation"
    PROTEIN_DOMAIN_OR_REGION = "Protein_domain_or_region"
    SIMPLE_CHEMICAL = "Simple_chemical"
    TISSUE = "Tissue"


class SourceArgumentRole(str, Enum):
    AT_LOC = "AtLoc"
    C_SITE = "CSite"
    CAUSE = "Cause"
    FROM_LOC = "FromLoc"
    INSTRUMENT = "Instrument"
    INSTRUMENT_2 = "Instrument2"
    INSTRUMENT_3 = "Instrument3"
    PARTICIPANT = "Participant"
    PARTICIPANT_2 = "Participant2"
    PARTICIPANT_3 = "Participant3"
    PARTICIPANT_4 = "Participant4"
    SITE = "Site"
    THEME = "Theme"
    THEME_2 = "Theme2"
    THEME_3 = "Theme3"
    TO_LOC = "ToLoc"


class ModifierDecision(str, Enum):
    NEGATED = "NEGATED"
    SPECULATIVE = "SPECULATIVE"
    BOTH = "BOTH"
    NEITHER = "NEITHER"
    ABSTAIN = "ABSTAIN"


class VerificationVerdict(str, Enum):
    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    ABSTAIN = "ABSTAIN"


class VerificationAxisDecision(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ABSTAIN = "ABSTAIN"


class DiscoveryCandidate(StrictStageModel):
    trigger_text: str = Field(min_length=1, max_length=512)
    event_passage: str = Field(min_length=1, max_length=12000)
    source_event_type: SourceEventType = Field(strict=False)
    statement_kind: StatementKind = Field(strict=False)
    explanation: str = Field(min_length=1, max_length=2000)


class EventDiscoveryOutput(StrictStageModel):
    decision: Literal["DISCOVERED", "ABSTAIN"]
    candidates: tuple[DiscoveryCandidate, ...] = Field(max_length=128)
    abstention_reason: str | None = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> EventDiscoveryOutput:
        if self.decision == "ABSTAIN":
            if self.candidates or not self.abstention_reason:
                raise ValueError("ABSTAIN requires no candidates and a reason")
        elif not self.candidates or self.abstention_reason is not None:
            raise ValueError("DISCOVERED requires candidates and no abstention reason")
        return self


class ParticipantCandidate(StrictStageModel):
    participant_key: str = Field(min_length=1, max_length=128)
    exact_text: str = Field(min_length=1, max_length=12000)
    occurrence_id: str = Field(pattern=r"^occurrence-[0-9]+$", max_length=64)
    occurrence_index: int = Field(ge=0, le=128)
    candidate_target_kind: ParticipantTargetKind = Field(strict=False)
    source_entity_type: SourceEntityType | None = Field(default=None, strict=False)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_entity_type(self) -> ParticipantCandidate:
        if self.candidate_target_kind is ParticipantTargetKind.PARTICIPANT:
            if self.source_entity_type is None:
                raise ValueError("direct participants require a source entity type")
        elif self.source_entity_type is not None:
            raise ValueError("event targets cannot include a source entity type")
        return self


class EventParticipantInventory(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    decision: Literal["INVENTORIED", "ABSTAIN"]
    participants: tuple[ParticipantCandidate, ...] = Field(max_length=64)
    abstention_reason: str | None = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> EventParticipantInventory:
        if self.decision == "ABSTAIN":
            if self.participants or not self.abstention_reason:
                raise ValueError(
                    "participant ABSTAIN requires no participants and a reason"
                )
        elif self.abstention_reason is not None:
            raise ValueError("INVENTORIED cannot include an abstention reason")
        return self


class ParticipantInventoryOutput(StrictStageModel):
    inventories: tuple[EventParticipantInventory, ...] = Field(max_length=128)


class RoleAssignment(StrictStageModel):
    participant_key: str = Field(min_length=1, max_length=128)
    source_role: SourceArgumentRole = Field(strict=False)
    target_kind: ParticipantTargetKind = Field(strict=False)
    target_event_id: str | None = Field(default=None, max_length=128)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_target(self) -> RoleAssignment:
        if self.target_kind is ParticipantTargetKind.EVENT:
            if not self.target_event_id:
                raise ValueError("EVENT role assignments require target_event_id")
        elif self.target_event_id is not None:
            raise ValueError("PARTICIPANT role assignments cannot target an event")
        return self


class EventRoleAssignment(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    decision: Literal["ASSIGNED", "ABSTAIN"]
    assignments: tuple[RoleAssignment, ...] = Field(max_length=64)
    abstention_reason: str | None = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_decision(self) -> EventRoleAssignment:
        if self.decision == "ABSTAIN":
            if self.assignments or not self.abstention_reason:
                raise ValueError("role ABSTAIN requires no assignments and a reason")
        elif self.abstention_reason is not None:
            raise ValueError("ASSIGNED cannot include an abstention reason")
        return self


class RoleAssignmentOutput(StrictStageModel):
    events: tuple[EventRoleAssignment, ...] = Field(max_length=128)


class EventModifierFinding(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    decision: ModifierDecision = Field(strict=False)
    exact_evidence: str | None = Field(default=None, max_length=12000)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_evidence(self) -> EventModifierFinding:
        if self.decision is ModifierDecision.NEITHER:
            if self.exact_evidence is not None:
                raise ValueError("NEITHER cannot include modifier evidence")
        elif not self.exact_evidence:
            raise ValueError("modifier findings other than NEITHER require evidence")
        return self


class ModifierOutput(StrictStageModel):
    events: tuple[EventModifierFinding, ...] = Field(max_length=128)


class VerificationAxisFinding(StrictStageModel):
    decision: VerificationAxisDecision = Field(strict=False)
    explanation: str = Field(min_length=1, max_length=2000)


class VerificationAxes(StrictStageModel):
    event_type: VerificationAxisFinding
    trigger: VerificationAxisFinding
    participants: VerificationAxisFinding
    roles: VerificationAxisFinding
    nesting: VerificationAxisFinding
    modifier: VerificationAxisFinding
    evidence: VerificationAxisFinding


class EventVerification(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    verdict: VerificationVerdict = Field(strict=False)
    exact_evidence: str | None = Field(default=None, max_length=12000)
    axes: VerificationAxes
    explanation: str = Field(min_length=1, max_length=2000)
    falsification_explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_evidence(self) -> EventVerification:
        if self.verdict is VerificationVerdict.ENTAILED and not self.exact_evidence:
            raise ValueError("ENTAILED requires exact evidence")
        decisions = tuple(
            finding.decision
            for finding in (
                self.axes.event_type,
                self.axes.trigger,
                self.axes.participants,
                self.axes.roles,
                self.axes.nesting,
                self.axes.modifier,
                self.axes.evidence,
            )
        )
        if self.verdict is VerificationVerdict.ENTAILED and any(
            decision is not VerificationAxisDecision.PASS for decision in decisions
        ):
            raise ValueError("ENTAILED requires every verification axis to PASS")
        if self.verdict is VerificationVerdict.CONTRADICTED and not any(
            decision is VerificationAxisDecision.FAIL for decision in decisions
        ):
            raise ValueError("CONTRADICTED requires a failed verification axis")
        if self.verdict in {
            VerificationVerdict.INSUFFICIENT,
            VerificationVerdict.ABSTAIN,
        } and not any(
            decision is VerificationAxisDecision.ABSTAIN for decision in decisions
        ):
            raise ValueError("INSUFFICIENT or ABSTAIN requires an abstained axis")
        return self


class MissingSupportedEvent(StrictStageModel):
    trigger_text: str = Field(min_length=1, max_length=512)
    event_passage: str = Field(min_length=1, max_length=12000)
    source_event_type: SourceEventType = Field(strict=False)
    statement_kind: StatementKind = Field(strict=False)
    exact_evidence: str = Field(min_length=1, max_length=12000)
    falsification_explanation: str = Field(min_length=1, max_length=2000)


class VerificationOutput(StrictStageModel):
    events: tuple[EventVerification, ...] = Field(max_length=128)
    missing_supported_events: tuple[MissingSupportedEvent, ...] = Field(max_length=32)


class CompletionEvent(StrictStageModel):
    event_id: str = Field(min_length=1, max_length=128)
    participants: tuple[ParticipantCandidate, ...] = Field(max_length=64)
    roles: tuple[RoleAssignment, ...] = Field(max_length=64)
    modifier: EventModifierFinding
    verification: EventVerification


class CompletionOutput(StrictStageModel):
    events: tuple[CompletionEvent, ...] = Field(max_length=32)


__all__ = [
    "CompletionEvent",
    "CompletionOutput",
    "DiscoveryCandidate",
    "EventDiscoveryOutput",
    "EventModifierFinding",
    "EventParticipantInventory",
    "EventRoleAssignment",
    "EventVerification",
    "MissingSupportedEvent",
    "ModifierDecision",
    "ModifierOutput",
    "ParticipantCandidate",
    "ParticipantInventoryOutput",
    "ParticipantTargetKind",
    "RoleAssignment",
    "RoleAssignmentOutput",
    "SourceArgumentRole",
    "SourceEntityType",
    "StatementKind",
    "VerificationOutput",
    "VerificationAxes",
    "VerificationAxisDecision",
    "VerificationAxisFinding",
    "VerificationVerdict",
]
