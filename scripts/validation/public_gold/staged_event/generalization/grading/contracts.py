"""Strict contracts for blinded reviews and frozen dual-lane grading policy."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    ArgumentRole,  # noqa: TC001 - Pydantic resolves this annotation at runtime.
    EntityType,  # noqa: TC001 - Pydantic resolves this annotation at runtime.
)

ContextClassification = Literal[
    "PERMITTED_CONTEXT",
    "AMBIGUOUS_REVIEW_ONLY",
    "FORBIDDEN",
]
EvidenceKind = Literal[
    "PRIMARY_ARTICLE",
    "OFFICIAL_BENCHMARK",
    "LOCAL_EXPOSED_SOURCE",
]
_PRIMARY_REVIEWER_COUNT = 2
_SHA256_LENGTH = 64


class ReviewerIdentity(StrictStageModel):
    reviewer_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    reviewer_kind: Literal["INTERNET_SOURCE_GRADER", "SOURCE_ONLY_GRADER"]
    internet_access: bool


class PrimarySourceEvidence(StrictStageModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    kind: EvidenceKind
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    retrieved_at: str = Field(min_length=1, max_length=64)
    retrieved_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewedContextArgument(StrictStageModel):
    event_trigger_text: str = Field(min_length=1, max_length=256)
    role: ArgumentRole


class ContextParticipantJudgment(StrictStageModel):
    judgment_id: str = Field(min_length=1, max_length=128)
    classification: ContextClassification
    entity_type: EntityType
    acceptable_texts: tuple[str, ...] = Field(min_length=1, max_length=8)
    allowed_arguments: tuple[ReviewedContextArgument, ...] = Field(
        min_length=1,
        max_length=8,
    )
    rationale: str = Field(min_length=1, max_length=1500)

    @model_validator(mode="after")
    def validate_unique_values(self) -> ContextParticipantJudgment:
        if len(set(self.acceptable_texts)) != len(self.acceptable_texts):
            raise ValueError("context participant texts must be unique")
        argument_keys = {
            (argument.event_trigger_text, argument.role)
            for argument in self.allowed_arguments
        }
        if len(argument_keys) != len(self.allowed_arguments):
            raise ValueError("context participant arguments must be unique")
        return self


class CaseContextReview(StrictStageModel):
    case_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inventory_complete: Literal[True]
    judgments: tuple[ContextParticipantJudgment, ...] = Field(max_length=32)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    explanation: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_judgment_ids(self) -> CaseContextReview:
        ids = [judgment.judgment_id for judgment in self.judgments]
        if len(ids) != len(set(ids)):
            raise ValueError("context judgment IDs must be unique within a case")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("case evidence IDs must be unique")
        return self


class GraderReviewBatch(StrictStageModel):
    schema_version: Literal["artana.staged_generalization.context_review.v1"]
    reviewer: ReviewerIdentity
    reviewed_at: str = Field(min_length=1, max_length=64)
    production_output_seen: Literal[False]
    benchmark_labels_seen: Literal[False]
    frozen_core_reference_seen: Literal[False]
    evidence: tuple[PrimarySourceEvidence, ...] = Field(min_length=1, max_length=32)
    cases: tuple[CaseContextReview, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_batch_identity(self) -> GraderReviewBatch:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("review case IDs must be unique")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("review evidence IDs must be unique")
        known_evidence = set(evidence_ids)
        for case in self.cases:
            if not set(case.evidence_ids) <= known_evidence:
                raise ValueError("case cites evidence absent from the review batch")
        return self


class FrozenAllowedContextArgument(StrictStageModel):
    event_key: str = Field(min_length=1, max_length=128)
    role: ArgumentRole


class FrozenContextParticipant(StrictStageModel):
    judgment_id: str = Field(min_length=1, max_length=128)
    classification: ContextClassification
    entity_type: EntityType
    acceptable_texts: tuple[str, ...] = Field(min_length=1, max_length=8)
    allowed_arguments: tuple[FrozenAllowedContextArgument, ...] = Field(
        min_length=1,
        max_length=8,
    )
    rationale: str = Field(min_length=1, max_length=1500)


class FrozenCasePolicy(StrictStageModel):
    case_id: str = Field(min_length=1, max_length=128)
    source_id: str = Field(min_length=1, max_length=256)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contextual_participants: tuple[FrozenContextParticipant, ...] = Field(max_length=32)
    excluded_core_duplicate_judgment_ids: tuple[str, ...] = Field(max_length=32)
    unlisted_additions: Literal["UNSUPPORTED"]
    ambiguous_additions: Literal["REVIEW_ONLY_BLOCKS_PASS"]


class FrozenDualLanePolicy(StrictStageModel):
    schema_version: Literal["artana.staged_generalization.dual_lane_policy.v1"]
    policy_id: str = Field(min_length=1, max_length=128)
    frozen_at: str = Field(min_length=1, max_length=64)
    primary_reviewers: tuple[ReviewerIdentity, ReviewerIdentity]
    tiebreaker_reviewer: ReviewerIdentity | None
    review_artifact_sha256: dict[str, str]
    evidence: tuple[PrimarySourceEvidence, ...] = Field(min_length=1, max_length=64)
    cases: tuple[FrozenCasePolicy, ...] = Field(min_length=1, max_length=32)
    benchmark_lane: Literal["SEPARATE_EVALUATION_ONLY_REVIEW_ONLY"]
    qualification_credit: Literal[False]
    graph_promotion_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_policy_identity(self) -> FrozenDualLanePolicy:
        reviewer_ids = [reviewer.reviewer_id for reviewer in self.primary_reviewers]
        if len(set(reviewer_ids)) != _PRIMARY_REVIEWER_COUNT:
            raise ValueError("primary graders must use distinct identities")
        if self.tiebreaker_reviewer is not None:
            if self.tiebreaker_reviewer.reviewer_id in reviewer_ids:
                raise ValueError("tiebreaker identity must be independent")
            reviewer_ids.append(self.tiebreaker_reviewer.reviewer_id)
        if set(self.review_artifact_sha256) != set(reviewer_ids):
            raise ValueError("review hashes must bind every reviewer and no others")
        if any(
            len(value) != _SHA256_LENGTH
            or any(char not in "0123456789abcdef" for char in value)
            for value in self.review_artifact_sha256.values()
        ):
            raise ValueError("review artifact hashes must be lowercase SHA-256")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("frozen policy case IDs must be unique")
        return self


__all__ = [
    "CaseContextReview",
    "ContextClassification",
    "ContextParticipantJudgment",
    "FrozenAllowedContextArgument",
    "FrozenCasePolicy",
    "FrozenContextParticipant",
    "FrozenDualLanePolicy",
    "GraderReviewBatch",
    "PrimarySourceEvidence",
    "ReviewedContextArgument",
    "ReviewerIdentity",
]
