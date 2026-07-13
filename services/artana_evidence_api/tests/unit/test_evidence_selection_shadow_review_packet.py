"""Tests for evidence-selection shadow-review packet generation."""

from __future__ import annotations

import importlib
from uuid import UUID

import pytest
from artana_evidence_api.evidence_selection.ranking.contracts import (
    DeterministicRankingWeight,
    RankingCategoricalInput,
)
from artana_evidence_api.evidence_selection.shadow_review_packet import (
    EvidenceSelectionShadowReviewPacket,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionReviewInput,
    ReviewRankingCalibrationDecision,
)
from pydantic import ValidationError

_RUN_ID = UUID("00000000-0000-0000-0000-000000000047")
_SEARCH_ID = "11111111-1111-1111-1111-111111111111"
_GOAL = "Find evidence that BRAF V600E predicts response to vemurafenib."


def test_shadow_review_packet_creates_incomplete_human_label_forms() -> None:
    packet_module = _packet_module()

    packet = packet_module.build_evidence_selection_shadow_review_packet(
        packet_module.EvidenceSelectionShadowReviewPacketRequest(
            study_id="shadow-study-2026-07-07",
            run_id=_RUN_ID,
            goal=_GOAL,
            selected_records=(
                _decision(
                    source_key="pubmed",
                    decision="selected",
                    record_index=0,
                    title="BRAF V600E response to vemurafenib",
                    score=0.91,
                    reason="Direct treatment-response evidence.",
                ),
            ),
            skipped_records=(
                _decision(
                    source_key="pubmed",
                    decision="skipped",
                    record_index=1,
                    title="Background melanoma review",
                    score=0.18,
                    reason="Background-only record.",
                ),
            ),
            deferred_records=(
                _decision(
                    source_key="clinvar",
                    decision="deferred",
                    record_index=2,
                    title="BRAF pathogenicity assertion",
                    score=0.44,
                    reason="Needs human review before selection.",
                ),
            ),
            review_ranking_items=(
                packet_module.EvidenceSelectionShadowReviewRankingItem(
                    source_kind="proposal",
                    item_id="proposal-1",
                    research_question_id="question-braf",
                    operational_ranking=_operational_ranking(0.91),
                    goal=_GOAL,
                    evidence_shape="variant_drug_response",
                ),
            ),
        ),
    )

    payload = packet.model_dump(mode="json")
    assert payload["schema_version"] == "evidence_selection_shadow_review_packet.v3"
    assert payload["study_type"] == "selection_and_review_ranking"
    assert payload["production_readiness_claim"] is False
    assert payload["completion_status"] == "requires_human_labels"
    assert "selection_reviews" not in payload

    selection_form = payload["selection_review_forms"][0]
    assert selection_form["run_id"] == str(_RUN_ID)
    assert selection_form["harness_selected_record_ids"] == [
        f"pubmed:{_SEARCH_ID}:0",
    ]
    assert selection_form["harness_skipped_record_ids"] == [
        f"pubmed:{_SEARCH_ID}:1",
    ]
    assert selection_form["harness_deferred_record_ids"] == [
        f"clinvar:{_SEARCH_ID}:2",
    ]
    assert selection_form["human_selected_record_ids"] == []
    assert selection_form["explanation_assessment"] is None
    assert selection_form["high_severity_overclaim_findings"] is None
    assert "selection_review_forms[].human_selected_record_ids" in payload[
        "completion_required_fields"
    ]

    candidate_records = payload["candidate_records"]
    assert [record["record_id"] for record in candidate_records] == [
        f"pubmed:{_SEARCH_ID}:0",
        f"pubmed:{_SEARCH_ID}:1",
        f"clinvar:{_SEARCH_ID}:2",
    ]

    ranking_form = payload["review_ranking_forms"][0]
    assert ranking_form["source_kind"] == "proposal"
    assert ranking_form["item_id"] == "proposal-1"
    assert ranking_form["operational_ranking"]["value"] == 0.91
    assert ranking_form["calibrated_probability"] is None
    assert ranking_form["outcome"] is None
    assert "review_ranking_forms[].outcome" in payload["completion_required_fields"]


def test_shadow_review_packet_forms_do_not_validate_as_completed_expert_labels() -> None:
    packet_module = _packet_module()
    packet = packet_module.build_evidence_selection_shadow_review_packet(
        packet_module.EvidenceSelectionShadowReviewPacketRequest(
            study_id="shadow-study-2026-07-07",
            run_id=_RUN_ID,
            goal=_GOAL,
            selected_records=(
                _decision(source_key="pubmed", decision="selected", record_index=0),
            ),
            review_ranking_items=(
                packet_module.EvidenceSelectionShadowReviewRankingItem(
                    source_kind="review_item",
                    item_id="review-item-1",
                    research_question_id="question-braf",
                    operational_ranking=_operational_ranking(0.72),
                ),
            ),
        ),
    )
    payload = packet.model_dump(mode="json")

    with pytest.raises(ValidationError):
        EvidenceSelectionReviewInput.model_validate(payload["selection_review_forms"][0])
    with pytest.raises(ValidationError):
        ReviewRankingCalibrationDecision.model_validate(
            payload["review_ranking_forms"][0],
        )


def test_shadow_packet_without_ranking_items_is_explicitly_selection_only() -> None:
    packet_module = _packet_module()

    packet = packet_module.build_evidence_selection_shadow_review_packet(
        packet_module.EvidenceSelectionShadowReviewPacketRequest(
            study_id="selection-only-study",
            run_id=_RUN_ID,
            goal=_GOAL,
            selected_records=(
                _decision(source_key="pubmed", decision="selected", record_index=0),
            ),
        ),
    )
    payload = packet.model_dump(mode="json")

    assert payload["study_type"] == "selection_relevance"
    assert payload["review_ranking_forms"] == []
    assert all(
        not field.startswith("review_ranking_forms")
        for field in payload["completion_required_fields"]
    )


def test_shadow_review_packet_counts_shadow_mode_recommendations_as_harness_selected() -> None:
    packet_module = _packet_module()

    packet = packet_module.build_evidence_selection_shadow_review_packet(
        packet_module.EvidenceSelectionShadowReviewPacketRequest(
            study_id="shadow-study-2026-07-07",
            run_id=_RUN_ID,
            goal=_GOAL,
            selected_records=(),
            deferred_records=(
                {
                    **_decision(
                        source_key="clinvar",
                        decision="deferred",
                        record_index=0,
                    ),
                    "deferral_reason": "shadow_mode",
                    "shadow_decision": "selected",
                    "would_have_been_selected": True,
                },
                {
                    **_decision(
                        source_key="pubmed",
                        decision="deferred",
                        record_index=1,
                    ),
                    "deferral_reason": "run_handoff_budget",
                },
            ),
        ),
    )
    selection_form = packet.model_dump(mode="json")["selection_review_forms"][0]

    assert selection_form["harness_selected_record_ids"] == [
        f"clinvar:{_SEARCH_ID}:0",
    ]
    assert selection_form["harness_deferred_record_ids"] == [
        f"pubmed:{_SEARCH_ID}:1",
    ]


def test_shadow_review_packet_schema_enforces_incomplete_collection_invariants() -> None:
    with pytest.raises(ValidationError):
        EvidenceSelectionShadowReviewPacket.model_validate(
            {
                "schema_version": "evidence_selection_shadow_review_packet.v3",
                "study_id": "shadow-study-2026-07-07",
                "study_type": "selection_relevance",
                "source_run_id": _RUN_ID,
                "goal": _GOAL,
                "production_readiness_claim": True,
                "completion_status": "requires_human_labels",
                "completion_required_fields": [],
                "candidate_records": [],
                "selection_review_forms": [],
                "review_ranking_forms": [],
            },
        )


def test_shadow_review_packet_rejects_records_without_durable_ids() -> None:
    packet_module = _packet_module()

    with pytest.raises(ValueError, match="record_index"):
        packet_module.build_evidence_selection_shadow_review_packet(
            packet_module.EvidenceSelectionShadowReviewPacketRequest(
                study_id="shadow-study-2026-07-07",
                run_id=_RUN_ID,
                goal=_GOAL,
                selected_records=(
                    {
                        "source_key": "pubmed",
                        "search_id": _SEARCH_ID,
                        "decision": "selected",
                        "relevance_label": "strong_fit",
                        "reason": "Missing record index should block packets.",
                        "score": 0.91,
                    },
                ),
            ),
        )


def test_shadow_review_packet_rejects_duplicate_candidate_record_ids() -> None:
    packet_module = _packet_module()

    with pytest.raises(ValueError, match="duplicate candidate record id"):
        packet_module.build_evidence_selection_shadow_review_packet(
            packet_module.EvidenceSelectionShadowReviewPacketRequest(
                study_id="shadow-study-2026-07-07",
                run_id=_RUN_ID,
                goal=_GOAL,
                selected_records=(
                    _decision(source_key="pubmed", decision="selected", record_index=0),
                ),
                skipped_records=(
                    _decision(source_key="pubmed", decision="skipped", record_index=0),
                ),
            ),
        )


def _packet_module() -> object:
    try:
        return importlib.import_module(
            "artana_evidence_api.evidence_selection.shadow_review_packet",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review packet module is missing: {exc}")


def _decision(
    *,
    source_key: str,
    decision: str,
    record_index: int,
    title: str = "Candidate evidence record",
    score: float = 0.7,
    reason: str = "Candidate reason.",
) -> dict[str, object]:
    return {
        "source_key": source_key,
        "source_family": "literature" if source_key == "pubmed" else "variant",
        "search_id": _SEARCH_ID,
        "decision": decision,
        "relevance_label": "strong_fit" if decision == "selected" else "context_only",
        "reason": reason,
        "record_index": record_index,
        "record_hash": f"{source_key}-hash-{record_index}",
        "title": title,
        "operational_ranking": _operational_ranking(score).model_dump(mode="json"),
        "matched_terms": ["BRAF", "vemurafenib"],
        "excluded_terms": [],
        "caveats": [],
    }


def _operational_ranking(value: float) -> DeterministicRankingWeight:
    return DeterministicRankingWeight(
        value=value,
        policy_id="test_review_ranking",
        policy_version="v1",
        mapping_version="v1",
        categorical_inputs=(
            RankingCategoricalInput(field="evidence_state", value="supported"),
        ),
    )
