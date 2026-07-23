"""Frozen two-lane fresh-CG reference and field-resolution contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    DirectCGEvent,  # noqa: TC001 - Pydantic runtime type.
    DirectCGParticipant,  # noqa: TC001 - Pydantic runtime type.
    ExactSourceSpan,  # noqa: TC001 - Pydantic runtime type.
    Sha256,  # noqa: TC001 - Pydantic runtime type.
)

ResolutionStatus = Literal["RESOLVED", "REVIEW_ONLY"]
INDEPENDENT_MAJORITY_COUNT = 2
PRIMARY_REVIEWER_COUNT = 2
SemanticValue = Literal[
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
    "INCREASED",
    "DECREASED",
    "NO_DIFFERENCE",
    "NO_ASSOCIATION",
    "ENABLES",
    "OBSERVED",
    "NOT_APPLICABLE",
    "GREATER",
    "LESS",
    "AFFIRMED",
    "NEGATED",
    "NULL_RESULT",
    "ASSERTED",
    "PROVISIONAL",
    "UNCERTAIN",
    "HYPOTHESIS",
]


class ResolutionMetadata(StrictStageModel):
    """Transparent agreement or tiebreak record for one semantic field."""

    status: ResolutionStatus
    agreeing_reviewer_ids: tuple[str, ...]
    reviewer_value_sha256_by_id: dict[str, Sha256]
    tiebreaker_used: bool

    @model_validator(mode="after")
    def validate_resolution(self) -> ResolutionMetadata:
        known = set(self.reviewer_value_sha256_by_id)
        if not set(self.agreeing_reviewer_ids) <= known:
            raise ValueError("agreeing reviewers must have recorded field values")
        if (
            self.status == "RESOLVED"
            and len(self.agreeing_reviewer_ids) < INDEPENDENT_MAJORITY_COUNT
        ):
            raise ValueError("resolved field requires independent majority agreement")
        if self.status == "REVIEW_ONLY" and self.agreeing_reviewer_ids:
            raise ValueError("review-only field cannot claim an agreeing majority")
        return self


class CategoricalReference(StrictStageModel):
    """Resolved Artana role or semantic axis, or an explicitly unscored field."""

    field_id: str = Field(min_length=1)
    target_anchor_id: str | None = None
    resolution: ResolutionMetadata
    value: SemanticValue | None
    accepted_evidence: tuple[ExactSourceSpan, ...]

    @model_validator(mode="after")
    def validate_value_status(self) -> CategoricalReference:
        resolved = self.resolution.status == "RESOLVED"
        if resolved != (self.value is not None):
            raise ValueError("categorical value must exist only for resolved fields")
        if resolved and not self.accepted_evidence:
            raise ValueError("resolved categorical field requires accepted evidence")
        if not resolved and self.accepted_evidence:
            raise ValueError("review-only field cannot carry accepted evidence")
        return self


class StatisticalObservationReference(StrictStageModel):
    observation_type: Literal[
        "P_VALUE",
        "CONFIDENCE_INTERVAL",
        "EFFECT_ESTIMATE",
    ]
    evidence: ExactSourceSpan


class StatisticsReferenceValue(StrictStageModel):
    observations: tuple[StatisticalObservationReference, ...]
    author_interpretation: Literal[
        "SIGNIFICANT",
        "NOT_SIGNIFICANT",
        "NOT_CLAIMED",
    ]
    interpretation_evidence: tuple[ExactSourceSpan, ...]


class StatisticsReference(StrictStageModel):
    field_id: Literal["statistics"] = "statistics"
    resolution: ResolutionMetadata
    value: StatisticsReferenceValue | None

    @model_validator(mode="after")
    def validate_value_status(self) -> StatisticsReference:
        resolved = self.resolution.status == "RESOLVED"
        if resolved != (self.value is not None):
            raise ValueError("statistics value must exist only for resolved field")
        return self


class ContextParticipantReference(StrictStageModel):
    entity_type: Literal[
        "POPULATION",
        "OUTCOME",
        "EXPOSURE",
        "VARIANT",
        "GENE_OR_PROTEIN",
        "CANCER",
        "SIMPLE_CHEMICAL",
        "MEASUREMENT",
    ]
    mention: ExactSourceSpan
    role: Literal[
        "AFFECTED_ENTITY",
        "CAUSAL_AGENT",
        "STIMULUS_OR_OBJECT",
        "POPULATION",
        "COMPARATOR",
        "OUTCOME",
        "EXPOSURE",
        "MEASUREMENT",
        "CONTEXTUAL_PARTICIPANT",
    ]


class ContextReferenceValue(StrictStageModel):
    participants: tuple[ContextParticipantReference, ...]


class ContextCandidateReference(StrictStageModel):
    """Independent inclusion vote for one exact contextual participant."""

    candidate_id: str = Field(min_length=1)
    participant: ContextParticipantReference
    resolution: ResolutionMetadata
    included: bool | None

    @model_validator(mode="after")
    def validate_inclusion_status(self) -> ContextCandidateReference:
        resolved = self.resolution.status == "RESOLVED"
        if resolved != (self.included is not None):
            raise ValueError("context inclusion must exist only for resolved candidate")
        return self


class ContextReference(StrictStageModel):
    field_id: Literal["contextual_participants"] = "contextual_participants"
    status: ResolutionStatus
    reviewer_set_sha256_by_id: dict[str, Sha256]
    candidates: tuple[ContextCandidateReference, ...]
    value: ContextReferenceValue | None

    @model_validator(mode="after")
    def validate_value_status(self) -> ContextReference:
        resolved = self.status == "RESOLVED"
        if resolved != (self.value is not None):
            raise ValueError("context value must exist only for resolved field")
        if resolved != all(
            item.resolution.status == "RESOLVED" for item in self.candidates
        ):
            raise ValueError("context status must reflect every candidate resolution")
        return self


class FreshCGCaseTwoLaneReference(StrictStageModel):
    """Direct public-CG lane plus independently resolved Artana semantics."""

    case_id: str = Field(min_length=1)
    document_id: str = Field(pattern=r"^PMID-\d+$")
    source_sha256: Sha256
    direct_cg_event: DirectCGEvent
    direct_cg_participants: tuple[DirectCGParticipant, ...] = Field(min_length=1)
    direct_cg_reference_sha256: Sha256
    argument_roles: tuple[CategoricalReference, ...] = Field(min_length=1)
    direction: CategoricalReference
    comparison: CategoricalReference
    polarity: CategoricalReference
    uncertainty: CategoricalReference
    statistics: StatisticsReference
    contextual_participants: ContextReference

    @model_validator(mode="after")
    def validate_field_identity(self) -> FreshCGCaseTwoLaneReference:
        if tuple(item.field_id for item in self.argument_roles) != tuple(
            f"role:{item.annotation_id}" for item in self.direct_cg_participants
        ):
            raise ValueError("reference role fields changed participant order")
        axis_ids = (
            self.direction.field_id,
            self.comparison.field_id,
            self.polarity.field_id,
            self.uncertainty.field_id,
        )
        if axis_ids != ("direction", "comparison", "polarity", "uncertainty"):
            raise ValueError("semantic axis field IDs changed")
        return self


class FreshCGTwoLaneReference(StrictStageModel):
    """Create-once resolved reference with reviewer and selection custody."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_two_lane_reference.v1"
    ] = "artana.staged_generalization.fresh_cg_two_lane_reference.v1"
    selection_artifact_sha256: Sha256
    review_packet_sha256: Sha256
    review_prompt_sha256: Sha256
    primary_reviewer_ids: tuple[str, str]
    reviewer_artifact_sha256_by_id: dict[str, Sha256]
    tiebreaker_reviewer_id: str | None
    case_order: tuple[str, ...] = Field(min_length=8, max_length=8)
    unresolved_field_ids: tuple[str, ...]
    cases: tuple[FreshCGCaseTwoLaneReference, ...] = Field(min_length=8, max_length=8)
    qualification_credit: Literal[False] = False
    graph_promotion_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_reference_identity(self) -> FreshCGTwoLaneReference:
        if len(set(self.primary_reviewer_ids)) != PRIMARY_REVIEWER_COUNT:
            raise ValueError("primary reviewer identities must be independent")
        expected_reviewers = set(self.primary_reviewer_ids)
        if self.tiebreaker_reviewer_id is not None:
            if self.tiebreaker_reviewer_id in expected_reviewers:
                raise ValueError("tiebreaker identity must be independent")
            expected_reviewers.add(self.tiebreaker_reviewer_id)
        if set(self.reviewer_artifact_sha256_by_id) != expected_reviewers:
            raise ValueError("reference reviewer hashes changed")
        if tuple(case.case_id for case in self.cases) != self.case_order:
            raise ValueError("reference case order changed")
        return self


__all__ = [
    "CategoricalReference",
    "ContextParticipantReference",
    "ContextCandidateReference",
    "ContextReference",
    "ContextReferenceValue",
    "FreshCGCaseTwoLaneReference",
    "FreshCGTwoLaneReference",
    "ResolutionMetadata",
    "SemanticValue",
    "StatisticsReference",
    "StatisticsReferenceValue",
    "StatisticalObservationReference",
]
