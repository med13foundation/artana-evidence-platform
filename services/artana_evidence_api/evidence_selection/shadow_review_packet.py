"""Build incomplete evidence-selection packets for human shadow review."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from artana_evidence_api.evidence_selection.ranking.contracts import (
    CalibratedRankingProbability,
    DeterministicRankingWeight,
    ReviewRankingCalibrationProtocol,
)
from artana_evidence_api.evidence_selection.ranking.protocol_integrity import (
    authenticate_calibration_protocol,
)
from artana_evidence_api.evidence_selection.shadow_review_integrity import (
    sign_machine_packet_digest,
)
from artana_evidence_api.evidence_selection_candidates import (
    record_dedup_key,
    required_decision_int,
    required_decision_string,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyType,
    ReviewRankingSourceKind,
)
from artana_evidence_api.runtime.agent_output_schema import RetrievalAlgorithmNumber
from artana_evidence_api.types.common import JSONObject, JSONValue
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EvidenceSelectionShadowReviewPacketSchemaVersion = Literal[
    "evidence_selection_shadow_review_packet.v3"
]
EvidenceSelectionShadowReviewCompletionStatus = Literal["requires_human_labels"]

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
class EvidenceSelectionShadowReviewPacketRequest:
    """Existing run outputs needed to stage a human shadow-review packet."""

    study_id: str
    run_id: UUID | str
    goal: str
    selected_records: tuple[JSONObject, ...] = ()
    skipped_records: tuple[JSONObject, ...] = ()
    deferred_records: tuple[JSONObject, ...] = ()
    review_ranking_items: tuple[EvidenceSelectionShadowReviewRankingItem, ...] = ()
    calibration_protocol: ReviewRankingCalibrationProtocol | None = None


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
    operational_ranking: DeterministicRankingWeight | None = None
    retrieval_ranking: RetrievalAlgorithmNumber | None = None
    matched_terms: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    @field_validator("matched_terms", "excluded_terms", "caveats", mode="before")
    @classmethod
    def _accept_json_string_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _ranking_origin_must_be_unambiguous(
        self,
    ) -> EvidenceSelectionShadowCandidateRecord:
        if self.operational_ranking is not None and self.retrieval_ranking is not None:
            msg = "candidate records cannot mix operational and retrieval ranking"
            raise ValueError(msg)
        return self


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
    explanation_assessment: None = None
    high_severity_overclaim_findings: None = None
    reviewer_notes: None = None

    @field_validator("run_id", mode="before")
    @classmethod
    def _accept_json_run_id(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value

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


class EvidenceSelectionShadowReviewRankingItem(BaseModel):
    """Scored queue item that needs a human positive/negative outcome."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    research_question_id: str = Field(min_length=1)
    operational_ranking: DeterministicRankingWeight
    calibrated_probability: CalibratedRankingProbability | None = None
    goal: str | None = Field(default=None, min_length=1)
    evidence_shape: str | None = Field(default=None, min_length=1)


class EvidenceSelectionShadowReviewRankingForm(BaseModel):
    """Incomplete ranking-calibration form that must be labeled by a human."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    source_kind: ReviewRankingSourceKind
    item_id: str = Field(min_length=1)
    research_question_id: str = Field(min_length=1)
    operational_ranking: DeterministicRankingWeight
    calibrated_probability: CalibratedRankingProbability | None = None
    outcome: None = None
    reviewer_id: None = None
    goal: str | None = Field(default=None, min_length=1)
    evidence_shape: str | None = Field(default=None, min_length=1)


class EvidenceSelectionShadowReviewPacket(BaseModel):
    """Reviewer packet that cannot be mistaken for completed expert evidence."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: EvidenceSelectionShadowReviewPacketSchemaVersion
    study_id: str = Field(min_length=1)
    study_type: EvidenceSelectionExpertStudyType
    source_run_id: UUID
    goal: str = Field(min_length=1)
    production_readiness_claim: Literal[False] = False
    completion_status: EvidenceSelectionShadowReviewCompletionStatus = (
        "requires_human_labels"
    )
    machine_packet_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    machine_packet_signature: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    completion_required_fields: tuple[str, ...]
    calibration_protocol: ReviewRankingCalibrationProtocol | None = None
    candidate_records: tuple[EvidenceSelectionShadowCandidateRecord, ...]
    selection_review_forms: tuple[EvidenceSelectionShadowSelectionReviewForm, ...]
    review_ranking_forms: tuple[EvidenceSelectionShadowReviewRankingForm, ...] = ()

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
    def _validate_packet_contract(
        self,
    ) -> EvidenceSelectionShadowReviewPacket:
        expected_fields = _completion_required_fields(self.study_type)
        if self.completion_required_fields != expected_fields:
            msg = "completion_required_fields must match the shadow packet contract."
            raise ValueError(msg)
        if self.study_type == "selection_relevance" and self.review_ranking_forms:
            msg = "selection_relevance packets must not include ranking forms."
            raise ValueError(msg)
        if self.study_type == "selection_relevance" and self.calibration_protocol:
            msg = "selection_relevance packets must not include calibration protocol."
            raise ValueError(msg)
        if (
            self.study_type == "selection_and_review_ranking"
            and not self.review_ranking_forms
        ):
            msg = "selection_and_review_ranking packets require ranking forms."
            raise ValueError(msg)
        probabilities = tuple(
            form.calibrated_probability
            for form in self.review_ranking_forms
            if form.calibrated_probability is not None
        )
        if probabilities and self.calibration_protocol is None:
            msg = "calibrated probabilities require an immutable calibration protocol."
            raise ValueError(msg)
        if self.calibration_protocol is not None and any(
            not _probability_matches_protocol(
                probability=probability,
                protocol=self.calibration_protocol,
            )
            for probability in probabilities
        ):
            msg = "calibrated probability provenance must match the packet protocol."
            raise ValueError(msg)
        if (
            self.machine_packet_sha256 is not None
            and self.machine_packet_sha256 != machine_packet_digest(self)
        ):
            msg = "machine_packet_sha256 must match the packet machine-owned fields."
            raise ValueError(msg)
        return self


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
    study_type: EvidenceSelectionExpertStudyType = (
        "selection_and_review_ranking"
        if request.review_ranking_items
        else "selection_relevance"
    )
    calibration_protocol = (
        authenticate_calibration_protocol(request.calibration_protocol)
        if request.calibration_protocol is not None
        else None
    )
    packet = EvidenceSelectionShadowReviewPacket(
        schema_version="evidence_selection_shadow_review_packet.v3",
        study_id=study_id,
        study_type=study_type,
        source_run_id=run_id,
        goal=goal,
        completion_required_fields=_completion_required_fields(study_type),
        calibration_protocol=calibration_protocol,
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
                research_question_id=item.research_question_id,
                operational_ranking=item.operational_ranking,
                calibrated_probability=item.calibrated_probability,
                goal=item.goal,
                evidence_shape=item.evidence_shape,
            )
            for item in request.review_ranking_items
        ),
    )
    digest = machine_packet_digest(packet)
    return packet.model_copy(
        update={
            "machine_packet_sha256": digest,
            "machine_packet_signature": sign_machine_packet_digest(digest),
        },
    )


def machine_packet_digest(packet: EvidenceSelectionShadowReviewPacket) -> str:
    """Return the stable digest of fields that humans must not alter."""

    payload = {
        "schema_version": packet.schema_version,
        "study_id": packet.study_id,
        "study_type": packet.study_type,
        "source_run_id": str(packet.source_run_id),
        "goal": packet.goal,
        "production_readiness_claim": packet.production_readiness_claim,
        "completion_status": packet.completion_status,
        "completion_required_fields": list(packet.completion_required_fields),
        "calibration_protocol": (
            packet.calibration_protocol.model_dump(mode="json")
            if packet.calibration_protocol is not None
            else None
        ),
        "candidate_records": [
            record.model_dump(mode="json") for record in packet.candidate_records
        ],
        "selection_review_forms": [
            {
                "run_id": str(form.run_id),
                "goal": form.goal,
                "harness_selected_record_ids": list(form.harness_selected_record_ids),
                "harness_skipped_record_ids": list(form.harness_skipped_record_ids),
                "harness_deferred_record_ids": list(form.harness_deferred_record_ids),
            }
            for form in packet.selection_review_forms
        ],
        "review_ranking_forms": [
            {
                "source_kind": form.source_kind,
                "item_id": form.item_id,
                "research_question_id": form.research_question_id,
                "operational_ranking": form.operational_ranking.model_dump(
                    mode="json",
                ),
                "calibrated_probability": (
                    form.calibrated_probability.model_dump(mode="json")
                    if form.calibrated_probability is not None
                    else None
                ),
                "goal": form.goal,
                "evidence_shape": form.evidence_shape,
            }
            for form in packet.review_ranking_forms
        ],
    }
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_payload).hexdigest()


def _completion_required_fields(
    study_type: EvidenceSelectionExpertStudyType,
) -> tuple[str, ...]:
    if study_type == "selection_and_review_ranking":
        return (
            *_SELECTION_COMPLETION_REQUIRED_FIELDS,
            *_RANKING_COMPLETION_REQUIRED_FIELDS,
        )
    return _SELECTION_COMPLETION_REQUIRED_FIELDS


def _probability_matches_protocol(
    *,
    probability: CalibratedRankingProbability,
    protocol: ReviewRankingCalibrationProtocol,
) -> bool:
    return (
        probability.identity == protocol.identity
        and probability.training_set_sha256 == protocol.training_set_sha256
        and probability.partition_manifest_sha256
        == protocol.partition_manifest_sha256
        and probability.held_out_protocol == protocol.held_out_protocol
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
        operational_ranking=_optional_operational_ranking(decision),
        retrieval_ranking=_optional_retrieval_ranking(decision),
        matched_terms=_string_tuple(decision.get("matched_terms")),
        excluded_terms=_string_tuple(decision.get("excluded_terms")),
        caveats=_string_tuple(decision.get("caveats")),
    )


def _optional_operational_ranking(
    decision: JSONObject,
) -> DeterministicRankingWeight | None:
    value = decision.get("operational_ranking")
    if value is None:
        return None
    return DeterministicRankingWeight.model_validate(value)


def _optional_retrieval_ranking(
    decision: JSONObject,
) -> RetrievalAlgorithmNumber | None:
    value = decision.get("retrieval_ranking")
    if value is None:
        return None
    return RetrievalAlgorithmNumber.model_validate(value)


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
    "machine_packet_digest",
]
