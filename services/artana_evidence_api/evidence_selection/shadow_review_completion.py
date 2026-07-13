"""Convert completed shadow-review packets into expert-study source inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from artana_evidence_api.evidence_selection.review.assessment import (
    EvidenceSelectionExplanationAssessment,
    EvidenceSelectionOverclaimFinding,
)
from artana_evidence_api.evidence_selection.shadow_review_integrity import (
    verify_machine_packet_signature,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowCandidateRecord,
    EvidenceSelectionShadowReviewPacket,
    EvidenceSelectionShadowReviewRankingForm,
    EvidenceSelectionShadowSelectionReviewForm,
    machine_packet_digest,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyType,
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationDecision,
    ReviewRankingCalibrationStudyInput,
    ReviewRankingOutcome,
    ReviewRankingSourceKind,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SELECTION_COMPLETION_REQUIRED_FIELDS = (
    "selection_review_forms[].reviewer_id",
    "selection_review_forms[].human_selected_record_ids",
    "selection_review_forms[].explanation_assessment",
    "selection_review_forms[].high_severity_overclaim_findings",
)
_RANKING_COMPLETION_REQUIRED_FIELDS = (
    "review_ranking_forms[].reviewer_id",
    "review_ranking_forms[].outcome",
)


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewSourceInputRequest:
    """Completed packet plus study-level fields needed for source inputs."""

    machine_packet: JSONObject
    packet: JSONObject
    adjudication_note: str | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewSourceInputs:
    """Selection-review labels and review-ranking study input."""

    study_id: str
    study_type: EvidenceSelectionExpertStudyType
    selection_reviews: tuple[EvidenceSelectionReviewInput, ...]
    review_ranking: ReviewRankingCalibrationStudyInput | None

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

        if self.review_ranking is None:
            msg = "Selection-only source inputs do not contain review-ranking data."
            raise ValueError(msg)
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
    explanation_assessment: EvidenceSelectionExplanationAssessment
    high_severity_overclaim_findings: tuple[EvidenceSelectionOverclaimFinding, ...]
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
        "high_severity_overclaim_findings",
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

    schema_version: Literal["evidence_selection_shadow_review_packet.v2"]
    study_id: str = Field(min_length=1)
    study_type: EvidenceSelectionExpertStudyType
    source_run_id: UUID
    goal: str = Field(min_length=1)
    production_readiness_claim: Literal[False]
    completion_status: Literal["requires_human_labels"]
    machine_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    machine_packet_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
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

    @model_validator(mode="after")
    def _forms_must_match_packet_candidates(self) -> _CompletedShadowReviewPacket:
        if self.completion_required_fields != _completion_required_fields(
            self.study_type,
        ):
            msg = "completion_required_fields must match the shadow packet contract."
            raise ValueError(msg)
        if self.study_type == "selection_relevance" and self.review_ranking_forms:
            msg = "selection_relevance packets must not include ranking forms."
            raise ValueError(msg)
        if (
            self.study_type == "selection_and_review_ranking"
            and not self.review_ranking_forms
        ):
            msg = "selection_and_review_ranking packets require ranking forms."
            raise ValueError(msg)
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
                    *(
                        citation.record_id
                        for citation in form.explanation_assessment.cited_evidence
                    ),
                    *(
                        finding.record_id
                        for finding in form.high_severity_overclaim_findings
                    ),
                    *(
                        citation.record_id
                        for finding in form.high_severity_overclaim_findings
                        for citation in finding.cited_evidence
                    ),
                ),
            )
        return self


def build_evidence_selection_shadow_review_source_inputs(
    request: EvidenceSelectionShadowReviewSourceInputRequest,
) -> EvidenceSelectionShadowReviewSourceInputs:
    """Convert a completed packet into source-export writer input objects."""

    machine_packet = EvidenceSelectionShadowReviewPacket.model_validate(
        request.machine_packet,
    )
    packet = _CompletedShadowReviewPacket.model_validate(request.packet)
    _validate_completed_packet_integrity(
        machine_packet=machine_packet,
        completed_packet=packet,
    )
    adjudication_note = (
        _required_text(request.adjudication_note, field_name="adjudication_note")
        if request.adjudication_note is not None
        else None
    )
    if (
        packet.study_type == "selection_and_review_ranking"
        and adjudication_note is None
    ):
        msg = "adjudication_note is required for review-ranking studies."
        raise ValueError(msg)
    description = (
        _required_text(request.description, field_name="description")
        if request.description is not None
        else None
    )
    selection_reviews = tuple(
        EvidenceSelectionReviewInput(
            run_id=machine_form.run_id,
            goal=machine_form.goal,
            reviewer_id=completed_form.reviewer_id,
            candidate_record_ids=tuple(
                record.record_id for record in machine_packet.candidate_records
            ),
            harness_selected_record_ids=machine_form.harness_selected_record_ids,
            human_selected_record_ids=completed_form.human_selected_record_ids,
            harness_skipped_record_ids=machine_form.harness_skipped_record_ids,
            duplicate_suggestion_ids=completed_form.duplicate_suggestion_ids,
            explanation_assessment=completed_form.explanation_assessment,
            high_severity_overclaim_findings=(
                completed_form.high_severity_overclaim_findings
            ),
            reviewer_notes=completed_form.reviewer_notes,
        )
        for machine_form, completed_form in zip(
            machine_packet.selection_review_forms,
            packet.selection_review_forms,
            strict=True,
        )
    )
    review_ranking = (
        ReviewRankingCalibrationStudyInput(
            schema_version="evidence_selection_review_ranking_calibration.v1",
            study_id=machine_packet.study_id,
            decisions=tuple(
                ReviewRankingCalibrationDecision(
                    source_kind=machine_form.source_kind,
                    item_id=machine_form.item_id,
                    ranking_score=machine_form.ranking_score,
                    outcome=completed_form.outcome,
                    reviewer_id=completed_form.reviewer_id,
                    goal=machine_form.goal,
                    evidence_shape=machine_form.evidence_shape,
                )
                for machine_form, completed_form in zip(
                    machine_packet.review_ranking_forms,
                    packet.review_ranking_forms,
                    strict=True,
                )
            ),
            adjudication_note=adjudication_note,
            description=description,
        )
        if packet.study_type == "selection_and_review_ranking"
        else None
    )
    return EvidenceSelectionShadowReviewSourceInputs(
        study_id=machine_packet.study_id,
        study_type=packet.study_type,
        selection_reviews=selection_reviews,
        review_ranking=review_ranking,
    )


def _validate_completed_packet_integrity(
    *,
    machine_packet: EvidenceSelectionShadowReviewPacket,
    completed_packet: _CompletedShadowReviewPacket,
) -> None:
    expected_digest = machine_packet_digest(machine_packet)
    if machine_packet.machine_packet_sha256 != expected_digest:
        msg = (
            "Immutable machine packet digest is missing or does not match its contents."
        )
        raise ValueError(msg)
    if machine_packet.machine_packet_signature is None:
        msg = "Immutable machine packet is missing its producer signature."
        raise ValueError(msg)
    verify_machine_packet_signature(
        digest=expected_digest,
        signature=machine_packet.machine_packet_signature,
    )
    if completed_packet.machine_packet_sha256 != expected_digest:
        msg = "Completed packet is not bound to the immutable machine packet digest."
        raise ValueError(msg)
    if (
        completed_packet.machine_packet_signature
        != machine_packet.machine_packet_signature
    ):
        msg = "Completed packet is not bound to the immutable machine packet signature."
        raise ValueError(msg)
    if not _top_level_machine_fields_match(
        machine_packet=machine_packet,
        completed_packet=completed_packet,
    ):
        msg = "Completed packet machine-owned fields do not match the immutable machine packet."
        raise ValueError(msg)
    if len(machine_packet.selection_review_forms) != len(
        completed_packet.selection_review_forms,
    ):
        msg = "Completed packet selection form count does not match the immutable machine packet."
        raise ValueError(msg)
    if len(machine_packet.review_ranking_forms) != len(
        completed_packet.review_ranking_forms,
    ):
        msg = "Completed packet review-ranking form count does not match the immutable machine packet."
        raise ValueError(msg)
    if any(
        not _selection_machine_fields_match(
            machine_form=machine_form,
            completed_form=completed_form,
        )
        for machine_form, completed_form in zip(
            machine_packet.selection_review_forms,
            completed_packet.selection_review_forms,
            strict=True,
        )
    ):
        msg = "Completed packet selection machine fields do not match the immutable machine packet."
        raise ValueError(msg)
    if any(
        not _ranking_machine_fields_match(
            machine_form=machine_form,
            completed_form=completed_form,
        )
        for machine_form, completed_form in zip(
            machine_packet.review_ranking_forms,
            completed_packet.review_ranking_forms,
            strict=True,
        )
    ):
        msg = "Completed packet ranking machine fields do not match the immutable machine packet."
        raise ValueError(msg)


def _top_level_machine_fields_match(
    *,
    machine_packet: EvidenceSelectionShadowReviewPacket,
    completed_packet: _CompletedShadowReviewPacket,
) -> bool:
    return (
        machine_packet.schema_version == completed_packet.schema_version
        and machine_packet.study_id == completed_packet.study_id
        and machine_packet.study_type == completed_packet.study_type
        and machine_packet.source_run_id == completed_packet.source_run_id
        and machine_packet.goal == completed_packet.goal
        and machine_packet.production_readiness_claim
        == completed_packet.production_readiness_claim
        and machine_packet.completion_status == completed_packet.completion_status
        and machine_packet.machine_packet_signature
        == completed_packet.machine_packet_signature
        and machine_packet.completion_required_fields
        == completed_packet.completion_required_fields
        and machine_packet.candidate_records == completed_packet.candidate_records
    )


def _completion_required_fields(
    study_type: EvidenceSelectionExpertStudyType,
) -> tuple[str, ...]:
    if study_type == "selection_and_review_ranking":
        return (
            *_SELECTION_COMPLETION_REQUIRED_FIELDS,
            *_RANKING_COMPLETION_REQUIRED_FIELDS,
        )
    return _SELECTION_COMPLETION_REQUIRED_FIELDS


def _selection_machine_fields_match(
    *,
    machine_form: EvidenceSelectionShadowSelectionReviewForm,
    completed_form: _CompletedSelectionReviewForm,
) -> bool:
    return (
        machine_form.run_id == completed_form.run_id
        and machine_form.goal == completed_form.goal
        and machine_form.harness_selected_record_ids
        == completed_form.harness_selected_record_ids
        and machine_form.harness_skipped_record_ids
        == completed_form.harness_skipped_record_ids
        and machine_form.harness_deferred_record_ids
        == completed_form.harness_deferred_record_ids
    )


def _ranking_machine_fields_match(
    *,
    machine_form: EvidenceSelectionShadowReviewRankingForm,
    completed_form: _CompletedReviewRankingForm,
) -> bool:
    return (
        machine_form.source_kind == completed_form.source_kind
        and machine_form.item_id == completed_form.item_id
        and machine_form.ranking_score == completed_form.ranking_score
        and machine_form.goal == completed_form.goal
        and machine_form.evidence_shape == completed_form.evidence_shape
    )


def machine_packet_sidecar_path(completed_packet_path: Path) -> Path:
    """Return the required immutable machine-packet sidecar path."""

    suffix = completed_packet_path.suffix
    stem = completed_packet_path.stem
    sidecar_name = f"{stem}.machine{suffix}" if suffix else f"{stem}.machine"
    return completed_packet_path.with_name(sidecar_name)


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
    "machine_packet_sidecar_path",
]
