"""Build incomplete evidence-selection packets for human shadow review."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from artana_evidence_api.evidence_selection_candidates import (
    record_dedup_key,
    required_decision_int,
    required_decision_string,
    score_from_decision,
)
from artana_evidence_api.evidence_selection_validation import ReviewRankingSourceKind
from artana_evidence_api.types.common import JSONObject, JSONValue
from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceSelectionShadowReviewPacketSchemaVersion = Literal[
    "evidence_selection_shadow_review_packet.v1"
]
EvidenceSelectionShadowReviewCompletionStatus = Literal["requires_human_labels"]

_COMPLETION_REQUIRED_FIELDS = (
    "selection_review_forms[].reviewer_id",
    "selection_review_forms[].human_selected_record_ids",
    "selection_review_forms[].explanation_quality_score",
    "selection_review_forms[].high_severity_overclaim_count",
    "review_ranking_forms[].reviewer_id",
    "review_ranking_forms[].outcome",
)


@dataclass(frozen=True, slots=True)
class EvidenceSelectionShadowReviewPacketRequest:
    """Existing run outputs needed to stage a human shadow-review packet."""

    study_id: str
    run_id: UUID | str
    goal: str
    selected_records: tuple[JSONObject, ...] = ()
    skipped_records: tuple[JSONObject, ...] = ()
    deferred_records: tuple[JSONObject, ...] = ()
    review_ranking_items: tuple[EvidenceSelectionShadowReviewRankingItem, ...] = ()


class EvidenceSelectionShadowCandidateRecord(BaseModel):
    """One source candidate the human reviewer can inspect."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_id: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    source_family: str | None = Field(default=None, min_length=1)
    search_id: str = Field(min_length=1)
    decision: str = Field(min_length=1)
    relevance_label: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1)
    record_index: int = Field(ge=0)
    record_hash: str | None = Field(default=None, min_length=1)
    title: str | None = Field(default=None, min_length=1)
    score: float = Field(ge=0.0)
    matched_terms: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    @field_validator("matched_terms", "excluded_terms", "caveats", mode="before")
    @classmethod
    def _accept_json_string_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class EvidenceSelectionShadowSelectionReviewForm(BaseModel):
    """Incomplete selection-review form that must be filled by a human."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    run_id: UUID
    goal: str = Field(min_length=1)
    reviewer_id: None = None
    harness_selected_record_ids: tuple[str, ...]
    harness_skipped_record_ids: tuple[str, ...] = ()
    harness_deferred_record_ids: tuple[str, ...] = ()
    human_selected_record_ids: tuple[str, ...] = ()
    duplicate_suggestion_ids: tuple[str, ...] = ()
    explanation_quality_score: None = None
    high_severity_overclaim_count: None = None
    reviewer_notes: None = None


class EvidenceSelectionShadowReviewRankingItem(BaseModel):
    """Scored queue item that needs a human positive/negative outcome."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    ranking_score: float = Field(ge=0.0, le=1.0)
    goal: str | None = Field(default=None, min_length=1)
    evidence_shape: str | None = Field(default=None, min_length=1)


class EvidenceSelectionShadowReviewRankingForm(BaseModel):
    """Incomplete ranking-calibration form that must be labeled by a human."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    ranking_score: float = Field(ge=0.0, le=1.0)
    outcome: None = None
    reviewer_id: None = None
    goal: str | None = Field(default=None, min_length=1)
    evidence_shape: str | None = Field(default=None, min_length=1)


class EvidenceSelectionShadowReviewPacket(BaseModel):
    """Reviewer packet that cannot be mistaken for completed expert evidence."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: EvidenceSelectionShadowReviewPacketSchemaVersion
    study_id: str = Field(min_length=1)
    source_run_id: UUID
    goal: str = Field(min_length=1)
    production_readiness_claim: Literal[False] = False
    completion_status: EvidenceSelectionShadowReviewCompletionStatus = (
        "requires_human_labels"
    )
    completion_required_fields: tuple[str, ...] = _COMPLETION_REQUIRED_FIELDS
    candidate_records: tuple[EvidenceSelectionShadowCandidateRecord, ...]
    selection_review_forms: tuple[EvidenceSelectionShadowSelectionReviewForm, ...]
    review_ranking_forms: tuple[EvidenceSelectionShadowReviewRankingForm, ...] = ()

    @field_validator("completion_required_fields")
    @classmethod
    def _completion_fields_must_match_packet_contract(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if tuple(value) != _COMPLETION_REQUIRED_FIELDS:
            msg = "completion_required_fields must match the shadow packet contract."
            raise ValueError(msg)
        return value


def build_evidence_selection_shadow_review_packet(
    request: EvidenceSelectionShadowReviewPacketRequest,
) -> EvidenceSelectionShadowReviewPacket:
    """Build a human-label packet from one evidence-selection run output."""

    run_id = _run_id(request.run_id)
    study_id = _required_text(request.study_id, field_name="study_id")
    goal = _required_text(request.goal, field_name="goal")
    selected = tuple(
        _candidate_record(record) for record in request.selected_records
    )
    skipped = tuple(_candidate_record(record) for record in request.skipped_records)
    deferred = tuple(_candidate_record(record) for record in request.deferred_records)
    shadow_selected = tuple(
        _candidate_record(record)
        for record in request.deferred_records
        if _is_shadow_selected_decision(record)
    )
    review_deferred = tuple(
        _candidate_record(record)
        for record in request.deferred_records
        if not _is_shadow_selected_decision(record)
    )
    review_selected = (*selected, *shadow_selected)
    candidate_records = (*selected, *skipped, *deferred)
    _reject_duplicate_candidate_ids(candidate_records)
    return EvidenceSelectionShadowReviewPacket(
        schema_version="evidence_selection_shadow_review_packet.v1",
        study_id=study_id,
        source_run_id=run_id,
        goal=goal,
        candidate_records=candidate_records,
        selection_review_forms=(
            EvidenceSelectionShadowSelectionReviewForm(
                run_id=run_id,
                goal=goal,
                harness_selected_record_ids=tuple(
                    record.record_id for record in review_selected
                ),
                harness_skipped_record_ids=tuple(
                    record.record_id for record in skipped
                ),
                harness_deferred_record_ids=tuple(
                    record.record_id for record in review_deferred
                ),
            ),
        ),
        review_ranking_forms=tuple(
            EvidenceSelectionShadowReviewRankingForm(
                source_kind=item.source_kind,
                item_id=item.item_id,
                ranking_score=item.ranking_score,
                goal=item.goal,
                evidence_shape=item.evidence_shape,
            )
            for item in request.review_ranking_items
        ),
    )


def _is_shadow_selected_decision(decision: JSONObject) -> bool:
    return (
        decision.get("shadow_decision") == "selected"
        or decision.get("would_have_been_selected") is True
    )


def _run_id(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except ValueError as exc:
        msg = "run_id must be a UUID."
        raise ValueError(msg) from exc


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized == "":
        msg = f"{field_name} must not be empty."
        raise ValueError(msg)
    return normalized


def _candidate_record(decision: JSONObject) -> EvidenceSelectionShadowCandidateRecord:
    source_key = required_decision_string(decision, "source_key")
    search_id = required_decision_string(decision, "search_id")
    record_index = required_decision_int(decision, "record_index")
    return EvidenceSelectionShadowCandidateRecord(
        record_id=record_dedup_key(
            source_key=source_key,
            search_id=search_id,
            record_index=record_index,
        ),
        source_key=source_key,
        source_family=_optional_string(decision, "source_family"),
        search_id=search_id,
        decision=required_decision_string(decision, "decision"),
        relevance_label=_optional_string(decision, "relevance_label"),
        reason=required_decision_string(decision, "reason"),
        record_index=record_index,
        record_hash=_optional_string(decision, "record_hash"),
        title=_optional_string(decision, "title"),
        score=score_from_decision(decision),
        matched_terms=_string_tuple(decision.get("matched_terms")),
        excluded_terms=_string_tuple(decision.get("excluded_terms")),
        caveats=_string_tuple(decision.get("caveats")),
    )


def _optional_string(decision: JSONObject, key: str) -> str | None:
    value = decision.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _string_tuple(value: JSONValue | None) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _reject_duplicate_candidate_ids(
    candidate_records: tuple[EvidenceSelectionShadowCandidateRecord, ...],
) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for record in candidate_records:
        if record.record_id in seen:
            duplicates.append(record.record_id)
        seen.add(record.record_id)
    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        msg = f"Evidence-selection shadow packet has duplicate candidate record id: {duplicate_list}."
        raise ValueError(msg)


__all__ = [
    "EvidenceSelectionShadowCandidateRecord",
    "EvidenceSelectionShadowReviewPacket",
    "EvidenceSelectionShadowReviewPacketRequest",
    "EvidenceSelectionShadowReviewRankingForm",
    "EvidenceSelectionShadowReviewRankingItem",
    "EvidenceSelectionShadowSelectionReviewForm",
    "build_evidence_selection_shadow_review_packet",
]
