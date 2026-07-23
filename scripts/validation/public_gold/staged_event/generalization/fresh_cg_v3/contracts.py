"""Typed V3 contracts for adjudication consensus, reference, and replay."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    DirectCGEvent,  # noqa: TC001 - Pydantic runtime contract.
    DirectCGParticipant,  # noqa: TC001 - Pydantic runtime contract.
    ExactSourceSpan,  # noqa: TC001 - Pydantic runtime contract.
    Sha256,  # noqa: TC001 - Pydantic runtime contract.
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    ContextParticipantReference,  # noqa: TC001 - Pydantic runtime contract.
    StatisticsReferenceValue,  # noqa: TC001 - Pydantic runtime contract.
)

RootCauseClassification = Literal[
    "MODEL_ERROR",
    "REFERENCE_ERROR",
    "EVALUATOR_MAPPING_ERROR",
    "TAXONOMY_AMBIGUITY",
    "UNRESOLVED_EXPERT_REVIEW_REQUIRED",
]


class ClassifiedIssue(StrictStageModel):
    issue_id: str = Field(min_length=1)
    classification: RootCauseClassification
    independent_error: bool
    depends_on: tuple[str, ...]


class ConsensusCorrection(StrictStageModel):
    classification: RootCauseClassification
    source_general_rule: str = Field(min_length=1)
    selected_candidate_id: str | None = None


class ConsensusCorrections(StrictStageModel):
    contextual_participants: ConsensusCorrection
    direction: ConsensusCorrection
    direct_attachment: ConsensusCorrection
    direct_participant_occurrence: ConsensusCorrection
    terminal: ConsensusCorrection
    uncertainty: ConsensusCorrection
    unsupported_count: ConsensusCorrection


class RootCauseConsensus(StrictStageModel):
    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_v2_root_cause_consensus.v1"
    ]
    case_id: str = Field(min_length=1)
    dispute_packet_sha256: Sha256
    adjudicator_sha256_by_id: dict[str, Sha256]
    classifications: tuple[ClassifiedIssue, ...]
    corrections: ConsensusCorrections
    tiebreaker_run: Literal[False]
    no_tiebreak_reason: str = Field(min_length=1)
    model_output_used_to_choose_reference_values: Literal[False]
    remaining_fresh_cases_consumed: Literal[0]
    graph_writes: Literal[0]
    qualification_credit: Literal[False]
    human_expert_qualification_credit: Literal[False]

    @model_validator(mode="after")
    def validate_issue_resolution(self) -> RootCauseConsensus:
        issue_ids = tuple(item.issue_id for item in self.classifications)
        if len(issue_ids) != len(set(issue_ids)):
            raise ValueError("consensus issue IDs must be unique")
        unresolved = {
            item.issue_id
            for item in self.classifications
            if item.classification == "UNRESOLVED_EXPERT_REVIEW_REQUIRED"
        }
        if unresolved:
            raise ValueError("unresolved classifications require expert review")
        return self


class V3CategoricalReference(StrictStageModel):
    field_id: str = Field(min_length=1)
    value: str = Field(min_length=1)
    accepted_evidence: tuple[ExactSourceSpan, ...] = Field(min_length=1)
    source_general_rule: str = Field(min_length=1)


class ExposedCaseReferenceV3(StrictStageModel):
    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_exposed_reference.v3"
    ] = "artana.staged_generalization.fresh_cg_exposed_reference.v3"
    case_id: str = Field(min_length=1)
    document_id: str = Field(pattern=r"^PMID-\d+$")
    source_sha256: Sha256
    direct_cg_event: DirectCGEvent
    direct_cg_participants: tuple[DirectCGParticipant, ...] = Field(min_length=1)
    direct_cg_reference_sha256: Sha256
    role: V3CategoricalReference
    direction: V3CategoricalReference
    comparison: V3CategoricalReference
    polarity: V3CategoricalReference
    uncertainty: V3CategoricalReference
    statistics: StatisticsReferenceValue
    contextual_participants: tuple[ContextParticipantReference, ...]
    dispute_packet_sha256: Sha256
    consensus_sha256: Sha256
    adjudicator_sha256_by_id: dict[str, Sha256]
    source_general_corrections: tuple[str, ...]
    exposed_case_only: Literal[True] = True
    v2_artifacts_modified: Literal[False] = False
    v2_rescored: Literal[False] = False
    model_output_used_to_choose_reference_values: Literal[False] = False
    qualification_credit: Literal[False] = False
    graph_promotion_allowed: Literal[False] = False


class FieldReplay(StrictStageModel):
    field_id: str = Field(min_length=1)
    status: Literal["MATCH", "MISMATCH", "BLOCKED_BY_OCCURRENCE"]
    independent_error: bool
    depends_on: tuple[str, ...]


class ExposedCaseReplayV3(StrictStageModel):
    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_exposed_replay.v3"
    ] = "artana.staged_generalization.fresh_cg_exposed_replay.v3"
    case_id: str = Field(min_length=1)
    v3_reference_sha256: Sha256
    v2_raw_output_sha256: Sha256
    direct_cg_event_exact: bool
    direct_cg_participant_exact: bool
    participant_identity_recognized_diagnostic_only: bool
    fields: tuple[FieldReplay, ...]
    genuine_model_error_issue_ids: tuple[str, ...]
    reference_error_issue_ids: tuple[str, ...]
    evaluator_mapping_error_issue_ids: tuple[str, ...]
    taxonomy_ambiguity_issue_ids: tuple[str, ...]
    raw_v2_unsupported_count: int = Field(ge=0)
    independent_unsupported_root_count: int = Field(ge=0)
    cascaded_structural_miss_count: int = Field(ge=0)
    contradiction_count: int = Field(ge=0)
    active_terminal_reason: str = Field(min_length=1)
    diagnostic_decision: Literal["MODEL_CORRECTION_REQUIRED"]
    scientific_pass_fail_recalculated: Literal[False] = False
    frozen_v2_grader_invoked: Literal[False] = False
    remaining_fresh_cases_consumed: Literal[0] = 0
    graph_writes: Literal[0] = 0
    qualification_credit: Literal[False] = False


__all__ = [
    "ClassifiedIssue",
    "ConsensusCorrection",
    "ConsensusCorrections",
    "ExposedCaseReferenceV3",
    "ExposedCaseReplayV3",
    "FieldReplay",
    "RootCauseClassification",
    "RootCauseConsensus",
    "V3CategoricalReference",
]
