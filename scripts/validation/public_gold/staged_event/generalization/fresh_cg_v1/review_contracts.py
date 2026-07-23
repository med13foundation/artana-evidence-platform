"""Typed independent-review contracts for source-semantic fields absent from CG."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    ExactSourceSpan,  # noqa: TC001 - Pydantic resolves this type at runtime.
    Sha256,  # noqa: TC001 - Pydantic resolves this type at runtime.
)


class ReviewOccurrenceAnchor(StrictStageModel):
    """Blinded occurrence anchor without CG type, role, or expected label."""

    anchor_id: str = Field(min_length=1)
    mention: ExactSourceSpan


class FreshCGReviewCasePacket(StrictStageModel):
    """Source-only case presented independently to a semantic reviewer."""

    case_id: str = Field(min_length=1)
    document_id: str = Field(pattern=r"^PMID-\d+$")
    source_sha256: Sha256
    permitted_context: ExactSourceSpan
    event_anchor: ReviewOccurrenceAnchor
    participant_anchors: tuple[ReviewOccurrenceAnchor, ...] = Field(min_length=1)
    pubmed_url: str = Field(pattern=r"^https://pubmed\.ncbi\.nlm\.nih\.gov/\d+/$")
    primary_retrieval_url: str = Field(
        pattern=r"^https://eutils\.ncbi\.nlm\.nih\.gov/entrez/eutils/efetch\.fcgi\?"
    )


class FreshCGReviewPacket(StrictStageModel):
    """Eight source-only cases shared identically with independent reviewers."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_review_packet.v1"
    ] = "artana.staged_generalization.fresh_cg_review_packet.v1"
    selection_artifact_sha256: Sha256
    case_order: tuple[str, ...] = Field(min_length=8, max_length=8)
    cases: tuple[FreshCGReviewCasePacket, ...] = Field(min_length=8, max_length=8)
    omitted_from_packet: tuple[str, ...]

    @model_validator(mode="after")
    def validate_case_order(self) -> FreshCGReviewPacket:
        if tuple(case.case_id for case in self.cases) != self.case_order:
            raise ValueError("semantic review case order changed")
        return self


class RetrievedPrimarySource(StrictStageModel):
    """Reviewer-recorded custody for the public primary retrieval."""

    document_id: str = Field(pattern=r"^PMID-\d+$")
    retrieval_url: str = Field(min_length=1)
    retrieved_at_utc: str = Field(min_length=1)
    response_bytes_sha256: Sha256
    context_verified: bool


class ReviewedArgument(StrictStageModel):
    """Artana role for one anchored direct-CG participant occurrence."""

    target_anchor_id: str = Field(min_length=1)
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
        "EFFECT_EVENT",
    ]
    evidence: ExactSourceSpan
    rationale: str = Field(min_length=1)


class ReviewedAxis(StrictStageModel):
    """One source-semantic categorical axis with exact evidence."""

    value: str = Field(min_length=1)
    evidence: ExactSourceSpan
    rationale: str = Field(min_length=1)


class ReviewedDirection(ReviewedAxis):
    value: Literal[
        "INCREASED",
        "DECREASED",
        "NO_DIFFERENCE",
        "NO_ASSOCIATION",
        "ENABLES",
        "OBSERVED",
        "NOT_APPLICABLE",
    ]


class ReviewedComparison(ReviewedAxis):
    value: Literal["GREATER", "LESS", "NO_DIFFERENCE", "NOT_APPLICABLE"]


class ReviewedPolarity(ReviewedAxis):
    value: Literal["AFFIRMED", "NEGATED", "NULL_RESULT"]


class ReviewedUncertainty(ReviewedAxis):
    value: Literal["ASSERTED", "PROVISIONAL", "UNCERTAIN", "HYPOTHESIS"]


class ReviewedStatisticalObservation(StrictStageModel):
    """One explicit statistical observation, if present."""

    observation_type: Literal[
        "P_VALUE",
        "CONFIDENCE_INTERVAL",
        "EFFECT_ESTIMATE",
    ]
    evidence: ExactSourceSpan
    rationale: str = Field(min_length=1)


class ReviewedStatistics(StrictStageModel):
    """Separate observed statistics from an author's significance interpretation."""

    observations: tuple[ReviewedStatisticalObservation, ...]
    author_interpretation: Literal[
        "SIGNIFICANT",
        "NOT_SIGNIFICANT",
        "NOT_CLAIMED",
    ]
    interpretation_evidence: ExactSourceSpan | None
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_interpretation_evidence(self) -> ReviewedStatistics:
        claimed = self.author_interpretation != "NOT_CLAIMED"
        if claimed != (self.interpretation_evidence is not None):
            raise ValueError("claimed statistical interpretation needs exact evidence")
        return self


class ReviewedContextParticipant(StrictStageModel):
    """Additional explicit participant permitted by the selected source context."""

    context_id: str = Field(min_length=1)
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
    rationale: str = Field(min_length=1)


class FreshCGCaseSemanticReview(StrictStageModel):
    """One reviewer's independent source-semantic judgment for a selected case."""

    case_id: str = Field(min_length=1)
    event_anchor_id: str = Field(min_length=1)
    arguments: tuple[ReviewedArgument, ...] = Field(min_length=1)
    direction: ReviewedDirection
    comparison: ReviewedComparison
    polarity: ReviewedPolarity
    uncertainty: ReviewedUncertainty
    statistics: ReviewedStatistics
    permitted_contextual_participants: tuple[ReviewedContextParticipant, ...]
    overall_rationale: str = Field(min_length=1)


class FreshCGReviewerArtifact(StrictStageModel):
    """Complete independent review with explicit blindness and retrieval custody."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_reviewer.v1"
    ] = "artana.staged_generalization.fresh_cg_reviewer.v1"
    reviewer_id: str = Field(min_length=1)
    reviewer_task_identity: str = Field(min_length=1)
    reviewer_model_identity: str = Field(min_length=1)
    review_prompt_sha256: Sha256
    review_packet_sha256: Sha256
    internet_enabled: Literal[True] = True
    model_output_blinded: Literal[True] = True
    other_reviewer_output_blinded: Literal[True] = True
    implementation_reference_blinded: Literal[True] = True
    retrieved_sources: tuple[RetrievedPrimarySource, ...] = Field(
        min_length=8,
        max_length=8,
    )
    cases: tuple[FreshCGCaseSemanticReview, ...] = Field(min_length=8, max_length=8)
    independence_declaration: str = Field(min_length=1)


__all__ = [
    "FreshCGCaseSemanticReview",
    "FreshCGReviewCasePacket",
    "FreshCGReviewPacket",
    "FreshCGReviewerArtifact",
    "RetrievedPrimarySource",
    "ReviewOccurrenceAnchor",
    "ReviewedArgument",
    "ReviewedAxis",
    "ReviewedComparison",
    "ReviewedContextParticipant",
    "ReviewedDirection",
    "ReviewedPolarity",
    "ReviewedStatistics",
    "ReviewedStatisticalObservation",
    "ReviewedUncertainty",
]
