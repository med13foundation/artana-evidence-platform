"""Tests for typed evidence-selection candidate decision contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionDecisionDeferralReason,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
    record_dedup_key,
    record_hash,
    relevance_label_for_selected_score,
    required_decision_int,
    required_decision_string,
    score_from_decision,
)
from artana_evidence_api.source_document_selection_identity import (
    source_document_record_hash,
)
from artana_evidence_api.types.common import JSONObject


def test_candidate_decision_serializes_only_at_artifact_boundary() -> None:
    decision = EvidenceSelectionCandidateDecision(
        source_key="clinvar",
        source_family="variant",
        search_id=str(uuid4()),
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=EvidenceSelectionDecisionRelevance.STRONG_FIT,
        reason="Record matches the goal/instructions through: med13.",
        record_index=0,
        record_hash="record-hash",
        title="MED13 variant",
        score=9.0,
        matched_terms=("med13",),
        excluded_terms=(),
        caveats=("Variant-level record needs review.",),
        candidate_context={"provider_external_id": "VCV000001"},
    )

    payload = decision.to_artifact_payload()

    assert payload["decision"] == "selected"
    assert payload["relevance_label"] == "strong_fit"
    assert payload["record_index"] == 0
    assert payload["matched_terms"] == ["med13"]
    assert payload["candidate_context"] == {"provider_external_id": "VCV000001"}
    assert "deferral_reason" not in payload
    assert "would_have_been_selected" not in payload


def test_candidate_decision_deferral_preserves_original_relevance() -> None:
    selected = EvidenceSelectionCandidateDecision(
        source_key="clinvar",
        source_family="variant",
        search_id=str(uuid4()),
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=EvidenceSelectionDecisionRelevance.STRONG_FIT,
        reason="Selected.",
        record_index=0,
        record_hash="record-hash",
        score=9.0,
    )

    deferred = selected.with_decision(
        decision=EvidenceSelectionDecisionState.DEFERRED,
        reason="Run handoff budget reached before this record.",
        deferral_reason=EvidenceSelectionDecisionDeferralReason.RUN_HANDOFF_BUDGET,
    )
    payload = deferred.to_artifact_payload()

    assert deferred.relevance_label == EvidenceSelectionDecisionRelevance.STRONG_FIT
    assert deferred.original_relevance_label == (
        EvidenceSelectionDecisionRelevance.STRONG_FIT
    )
    assert payload["decision"] == "deferred"
    assert payload["relevance_label"] == "strong_fit"
    assert payload["original_relevance_label"] == "strong_fit"
    assert payload["deferral_reason"] == "run_handoff_budget"


def test_candidate_helpers_keep_existing_serialized_payload_contract() -> None:
    payload: JSONObject = {
        "source_key": "clinvar",
        "record_index": 3,
        "score": 4.5,
    }

    assert required_decision_string(payload, "source_key") == "clinvar"
    assert required_decision_int(payload, "record_index") == 3
    assert score_from_decision(payload) == 4.5
    assert relevance_label_for_selected_score(5.0) == (
        EvidenceSelectionDecisionRelevance.STRONG_FIT
    )
    assert relevance_label_for_selected_score(4.0) == (
        EvidenceSelectionDecisionRelevance.PLAUSIBLE_FIT
    )
    with pytest.raises(ValueError, match="missing string field"):
        required_decision_string(payload, "missing")


def test_source_document_record_hash_matches_candidate_record_hash_for_sources() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    document_store = HarnessDocumentStore()
    source_records: tuple[tuple[str, JSONObject], ...] = (
        (
            "clinvar",
            {
                "accession": "VCV000001",
                "gene_symbol": "MED13",
                "title": "MED13 congenital heart disease variant",
            },
        ),
        (
            "pubmed",
            {
                "pmid": "12345",
                "title": "MED13 congenital heart disease review",
            },
        ),
    )

    for record_index, (source_key, record) in enumerate(source_records):
        document = document_store.create_document(
            space_id=space_id,
            created_by=user_id,
            title=f"{source_key} source record",
            source_type=source_key,
            filename=None,
            media_type="application/json",
            sha256=record_hash(record),
            byte_size=1,
            page_count=None,
            text_content=str(record),
            ingestion_run_id=uuid4(),
            enrichment_status="pending",
            extraction_status="pending",
            metadata={
                "source_search_id": str(search_id),
                "selected_record_index": record_index,
                "selected_record": record,
            },
        )

        assert source_document_record_hash(document) == record_hash(record)
        assert record_dedup_key(
            source_key=source_key,
            search_id=search_id,
            record_index=record_index,
        ) == f"{source_key}:{search_id}:{record_index}"
