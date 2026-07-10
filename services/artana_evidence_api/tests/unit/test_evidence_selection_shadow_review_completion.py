"""Tests for converting completed shadow-review packets into source inputs."""

from __future__ import annotations

import importlib
from copy import deepcopy

import pytest
from artana_evidence_api.evidence_selection.shadow_review_integrity import (
    sign_machine_packet_digest,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowReviewPacket,
    machine_packet_digest,
)
from artana_evidence_api.evidence_selection_validation import (
    ReviewRankingCalibrationStudyInput,
    compare_evidence_selection_review,
)
from pydantic import ValidationError

_RUN_ID = "00000000-0000-0000-0000-000000000048"
_GOAL = "Review BRAF V600E treatment-response evidence."


def test_completed_packet_builds_source_export_inputs() -> None:
    completion = _completion_module()

    result = completion.build_evidence_selection_shadow_review_source_inputs(
        completion.EvidenceSelectionShadowReviewSourceInputRequest(
            machine_packet=_machine_packet(),
            packet=_completed_packet(),
            adjudication_note="Reviewer A completed selection and ranking labels.",
            description="Shadow review completion fixture.",
        ),
    )

    selection_payload = result.selection_reviews_payload()
    assert selection_payload == {
        "selection_reviews": [
            {
                "run_id": _RUN_ID,
                "goal": _GOAL,
                "reviewer_id": "reviewer-a",
                "harness_selected_record_ids": ["pubmed:search-1:0"],
                "human_selected_record_ids": [
                    "pubmed:search-1:0",
                    "clinvar:search-1:2",
                ],
                "harness_skipped_record_ids": ["pubmed:search-1:1"],
                "duplicate_suggestion_ids": ["pubmed:search-1:1"],
                "explanation_quality_score": 4,
                "high_severity_overclaim_count": 0,
                "reviewer_notes": "Selected the deferred ClinVar record as useful.",
                "false_positive_notes": None,
                "false_negative_notes": None,
            },
        ],
    }
    review_report = compare_evidence_selection_review(
        result.selection_reviews[0],
    )
    assert review_report.true_positive_ids == ("pubmed:search-1:0",)
    assert review_report.false_negative_ids == ("clinvar:search-1:2",)
    assert review_report.confirmed_skip_ids == ("pubmed:search-1:1",)

    ranking_payload = result.review_ranking_payload()
    assert ranking_payload == {
        "schema_version": "evidence_selection_review_ranking_calibration.v1",
        "study_id": "shadow-study-2026-07-07",
        "adjudication_note": "Reviewer A completed selection and ranking labels.",
        "description": "Shadow review completion fixture.",
        "decisions": [
            {
                "source_kind": "proposal",
                "item_id": "proposal-1",
                "ranking_score": 0.91,
                "outcome": "positive",
                "reviewer_id": "reviewer-a",
                "goal": _GOAL,
                "evidence_shape": "variant_drug_response",
            },
            {
                "source_kind": "review_item",
                "item_id": "review-item-1",
                "ranking_score": 0.22,
                "outcome": "negative",
                "reviewer_id": "reviewer-a",
                "goal": _GOAL,
                "evidence_shape": "background_context",
            },
        ],
    }
    ReviewRankingCalibrationStudyInput.model_validate(ranking_payload)


def test_completed_packet_rejects_unknown_human_selected_record_id() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["selection_review_forms"][0]["human_selected_record_ids"] = [
        "pubmed:search-1:0",
        "unknown:record",
    ]

    with pytest.raises(ValueError, match="unknown record id"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_incomplete_selection_labels() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["selection_review_forms"][0]["reviewer_id"] = None

    with pytest.raises(ValidationError, match="reviewer_id"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_blank_selection_reviewer_id() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["selection_review_forms"][0]["reviewer_id"] = "   "

    with pytest.raises(ValidationError, match="reviewer_id"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_blank_ranking_outcome() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["review_ranking_forms"][0]["outcome"] = None

    with pytest.raises(ValidationError, match="outcome"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_blank_ranking_reviewer_id() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["review_ranking_forms"][0]["reviewer_id"] = "   "

    with pytest.raises(ValidationError, match="reviewer_id"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_changed_machine_selection_fields() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["selection_review_forms"][0]["harness_selected_record_ids"] = [
        "clinvar:search-1:2",
    ]

    with pytest.raises(ValueError, match="machine fields do not match"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_forged_machine_digest() -> None:
    completion = _completion_module()
    packet = _completed_packet()
    packet["machine_packet_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="not bound to the immutable machine packet"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=_machine_packet(),
                packet=packet,
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def test_completed_packet_rejects_forged_machine_signature() -> None:
    completion = _completion_module()
    machine_packet = _machine_packet()
    machine_packet["machine_packet_signature"] = "0" * 64

    with pytest.raises(ValueError, match="producer-signed digest"):
        completion.build_evidence_selection_shadow_review_source_inputs(
            completion.EvidenceSelectionShadowReviewSourceInputRequest(
                machine_packet=machine_packet,
                packet=_completed_packet(),
                adjudication_note="Reviewer A completed labels.",
            ),
        )


def _completion_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.shadow_review_completion",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review completion module is missing: {exc}")


def _completed_packet() -> dict[str, object]:
    packet = _machine_packet()
    selection_form = packet["selection_review_forms"][0]
    selection_form["reviewer_id"] = "reviewer-a"
    selection_form["human_selected_record_ids"] = [
        "pubmed:search-1:0",
        "clinvar:search-1:2",
    ]
    selection_form["duplicate_suggestion_ids"] = ["pubmed:search-1:1"]
    selection_form["explanation_quality_score"] = 4
    selection_form["high_severity_overclaim_count"] = 0
    selection_form["reviewer_notes"] = "Selected the deferred ClinVar record as useful."
    for index, ranking_form in enumerate(packet["review_ranking_forms"]):
        ranking_form["outcome"] = "positive" if index == 0 else "negative"
        ranking_form["reviewer_id"] = "reviewer-a"
    return packet


def _machine_packet() -> dict[str, object]:
    packet = deepcopy(_packet_payload())
    selection_form = packet["selection_review_forms"][0]
    selection_form["reviewer_id"] = None
    selection_form["human_selected_record_ids"] = []
    selection_form["duplicate_suggestion_ids"] = []
    selection_form["explanation_quality_score"] = None
    selection_form["high_severity_overclaim_count"] = None
    selection_form["reviewer_notes"] = None
    for ranking_form in packet["review_ranking_forms"]:
        ranking_form["outcome"] = None
        ranking_form["reviewer_id"] = None
    machine_model = EvidenceSelectionShadowReviewPacket.model_validate(packet)
    digest = machine_packet_digest(machine_model)
    packet["machine_packet_sha256"] = digest
    packet["machine_packet_signature"] = sign_machine_packet_digest(digest)
    return packet


def _packet_payload() -> dict[str, object]:
    return {
        "schema_version": "evidence_selection_shadow_review_packet.v1",
        "study_id": "shadow-study-2026-07-07",
        "source_run_id": _RUN_ID,
        "goal": _GOAL,
        "production_readiness_claim": False,
        "completion_status": "requires_human_labels",
        "completion_required_fields": [
            "selection_review_forms[].reviewer_id",
            "selection_review_forms[].human_selected_record_ids",
            "selection_review_forms[].explanation_quality_score",
            "selection_review_forms[].high_severity_overclaim_count",
            "review_ranking_forms[].reviewer_id",
            "review_ranking_forms[].outcome",
        ],
        "candidate_records": [
            _candidate_record("pubmed:search-1:0"),
            _candidate_record("pubmed:search-1:1"),
            _candidate_record("clinvar:search-1:2"),
        ],
        "selection_review_forms": [
            {
                "run_id": _RUN_ID,
                "goal": _GOAL,
                "reviewer_id": "reviewer-a",
                "harness_selected_record_ids": ["pubmed:search-1:0"],
                "harness_skipped_record_ids": ["pubmed:search-1:1"],
                "harness_deferred_record_ids": ["clinvar:search-1:2"],
                "human_selected_record_ids": [
                    "pubmed:search-1:0",
                    "clinvar:search-1:2",
                ],
                "duplicate_suggestion_ids": ["pubmed:search-1:1"],
                "explanation_quality_score": 4,
                "high_severity_overclaim_count": 0,
                "reviewer_notes": "Selected the deferred ClinVar record as useful.",
            },
        ],
        "review_ranking_forms": [
            {
                "source_kind": "proposal",
                "item_id": "proposal-1",
                "ranking_score": 0.91,
                "outcome": "positive",
                "reviewer_id": "reviewer-a",
                "goal": _GOAL,
                "evidence_shape": "variant_drug_response",
            },
            {
                "source_kind": "review_item",
                "item_id": "review-item-1",
                "ranking_score": 0.22,
                "outcome": "negative",
                "reviewer_id": "reviewer-a",
                "goal": _GOAL,
                "evidence_shape": "background_context",
            },
        ],
    }


def _candidate_record(record_id: str) -> dict[str, object]:
    source_key, search_id, record_index_text = record_id.split(":")
    return {
        "record_id": record_id,
        "source_key": source_key,
        "source_family": "literature",
        "search_id": search_id,
        "decision": "selected",
        "relevance_label": "strong_fit",
        "reason": "Candidate evidence fixture.",
        "record_index": int(record_index_text),
        "record_hash": f"hash-{record_index_text}",
        "title": f"Candidate {record_index_text}",
        "score": 0.8,
        "matched_terms": ["BRAF"],
        "excluded_terms": [],
        "caveats": [],
    }
