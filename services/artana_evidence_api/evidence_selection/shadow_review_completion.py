"""Convert completed shadow-review packets into expert-study source inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowCandidateRecord,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationDecision,
    ReviewRankingCalibrationStudyInput,
    ReviewRankingOutcome,
    ReviewRankingSourceKind,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_COMPLETION_REQUIRED_FIELDS = (
    "selection_review_forms[].reviewer_id",
    "selection_review_forms[].human_selected_record_ids",
    "selection_review_forms[].explanation_quality_score",
    "selection_review_forms[].high_severity_overclaim_count",
    "review_ranking_forms[].reviewer_id",
    "review_ranking_forms[].outcome",
)


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewSourceInputRequest:
    """Completed packet plus study-level fields needed for source inputs."""

    packet: JSONObject
    adjudication_note: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewSourceInputs:
    """Selection-review labels and review-ranking study input."""

    selection_reviews: tuple[EvidenceSelectionReviewInput, ...]
    review_ranking: ReviewRankingCalibrationStudyInput

    def selection_reviews_payload(self) -> JSONObject:
        """Return the JSON input expected by the source-export writer."""

        return {
            "selection_reviews": [
                cast("JSONObject", review.model_dump(mode="json"))
                for review in self.selection_reviews
            ],
        }

    def review_ranking_payload(self) -> JSONObject:
        """Return the JSON input expected by the source-export writer."""

        return cast("JSONObject", self.review_ranking.model_dump(mode="json"))


class _CompletedSelectionReviewForm(BaseModel):
    """Human-completed selection-review form from a shadow-review packet."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: UUID
    goal: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    harness_selected_record_ids: tuple[str, ...]
    harness_skipped_record_ids: tuple[str, ...] = ()
    harness_deferred_record_ids: tuple[str, ...] = ()
    human_selected_record_ids: tuple[str, ...]
    duplicate_suggestion_ids: tuple[str, ...] = ()
    explanation_quality_score: int = Field(ge=1, le=5)
    high_severity_overclaim_count: int = Field(ge=0)
    reviewer_notes: str | None = Field(default=None, min_length=1)

    @field_validator("run_id", mode="before")
    @classmethod
    def _accept_json_run_id(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value

    @field_validator("reviewer_id")
    @classmethod
    def _reviewer_id_must_not_be_blank(cls, value: str) -> str:
        return _required_text(value, field_name="reviewer_id")

    @field_validator(
        "harness_selected_record_ids",
        "harness_skipped_record_ids",
        "harness_deferred_record_ids",
        "human_selected_record_ids",
        "duplicate_suggestion_ids",
        mode="before",
    )
    @classmethod
    def _accept_json_record_id_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class _CompletedReviewRankingForm(BaseModel):
    """Human-completed review-ranking form from a shadow-review packet."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    ranking_score: float = Field(ge=0.0, le=1.0)
    outcome: ReviewRankingOutcome
    reviewer_id: str = Field(min_length=1)
    goal: str | None = Field(default=None, min_length=1)
    evidence_shape: str | None = Field(default=None, min_length=1)

    @field_validator("reviewer_id")
    @classmethod
    def _reviewer_id_must_not_be_blank(cls, value: str) -> str:
        return _required_text(value, field_name="reviewer_id")


class _CompletedShadowReviewPacket(BaseModel):
    """Strict completed form of a shadow-review packet."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_shadow_review_packet.v1"]
    study_id: str = Field(min_length=1)
    source_run_id: UUID
    goal: str = Field(min_length=1)
    production_readiness_claim: Literal[False]
    completion_status: Literal["requires_human_labels"]
    completion_required_fields: tuple[str, ...]
    candidate_records: tuple[EvidenceSelectionShadowCandidateRecord, ...]
    selection_review_forms: tuple[_CompletedSelectionReviewForm, ...] = Field(
        min_length=1,
    )
    review_ranking_forms: tuple[_CompletedReviewRankingForm, ...] = ()

    @field_validator("source_run_id", mode="before")
    @classmethod
    def _accept_json_source_run_id(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value

    @field_validator(
        "completion_required_fields",
        "candidate_records",
        "selection_review_forms",
        "review_ranking_forms",
        mode="before",
    )
    @classmethod
    def _accept_json_arrays(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("completion_required_fields")
    @classmethod
    def _required_fields_must_match_packet_contract(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if tuple(value) != _COMPLETION_REQUIRED_FIELDS:
            msg = "completion_required_fields must match the shadow packet contract."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _forms_must_match_packet_candidates(self) -> _CompletedShadowReviewPacket:
        candidate_ids = {record.record_id for record in self.candidate_records}
        for form in self.selection_review_forms:
            if form.run_id != self.source_run_id:
                msg = "selection review run_id must match packet source_run_id."
                raise ValueError(msg)
            if form.goal != self.goal:
                msg = "selection review goal must match packet goal."
                raise ValueError(msg)
            _reject_unknown_record_ids(
                candidate_ids=candidate_ids,
                record_ids=(
                    *form.harness_selected_record_ids,
                    *form.harness_skipped_record_ids,
                    *form.harness_deferred_record_ids,
                    *form.human_selected_record_ids,
                    *form.duplicate_suggestion_ids,
                ),
            )
        return self


def build_evidence_selection_shadow_review_source_inputs(
    request: EvidenceSelectionShadowReviewSourceInputRequest,
) -> EvidenceSelectionShadowReviewSourceInputs:
    """Convert a completed packet into source-export writer input objects."""

    packet = _CompletedShadowReviewPacket.model_validate(request.packet)
    adjudication_note = _required_text(
        request.adjudication_note,
        field_name="adjudication_note",
    )
    description = (
        _required_text(request.description, field_name="description")
        if request.description is not None
        else None
    )
    selection_reviews = tuple(
        EvidenceSelectionReviewInput(
            run_id=form.run_id,
            goal=form.goal,
            reviewer_id=form.reviewer_id,
            harness_selected_record_ids=form.harness_selected_record_ids,
            human_selected_record_ids=form.human_selected_record_ids,
            harness_skipped_record_ids=form.harness_skipped_record_ids,
            duplicate_suggestion_ids=form.duplicate_suggestion_ids,
            explanation_quality_score=form.explanation_quality_score,
            high_severity_overclaim_count=form.high_severity_overclaim_count,
            reviewer_notes=form.reviewer_notes,
        )
        for form in packet.selection_review_forms
    )
    review_ranking = ReviewRankingCalibrationStudyInput(
        schema_version="evidence_selection_review_ranking_calibration.v1",
        study_id=packet.study_id,
        decisions=tuple(
            ReviewRankingCalibrationDecision(
                source_kind=form.source_kind,
                item_id=form.item_id,
                ranking_score=form.ranking_score,
                outcome=form.outcome,
                reviewer_id=form.reviewer_id,
                goal=form.goal,
                evidence_shape=form.evidence_shape,
            )
            for form in packet.review_ranking_forms
        ),
        adjudication_note=adjudication_note,
        description=description,
    )
    return EvidenceSelectionShadowReviewSourceInputs(
        selection_reviews=selection_reviews,
        review_ranking=review_ranking,
    )


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized == "":
        msg = f"{field_name} must not be empty."
        raise ValueError(msg)
    return normalized


def _reject_unknown_record_ids(
    *,
    candidate_ids: set[str],
    record_ids: tuple[str, ...],
) -> None:
    unknown_ids = sorted(set(record_ids) - candidate_ids)
    if unknown_ids:
        msg = f"Completed shadow-review packet references unknown record id: {', '.join(unknown_ids)}."
        raise ValueError(msg)


__all__ = [
    "EvidenceSelectionShadowReviewSourceInputRequest",
    "EvidenceSelectionShadowReviewSourceInputs",
    "build_evidence_selection_shadow_review_source_inputs",
]
