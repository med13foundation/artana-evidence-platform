"""Tests for focused evidence-selection candidate handoff creation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_candidate_handoffs import (
    create_selected_handoffs,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
)
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.source_search_handoff import InMemorySourceSearchHandoffStore


def _clinvar_search(*, space_id: UUID, search_id: UUID) -> ClinVarSourceSearchResponse:
    now = datetime.now(UTC)
    capture = source_result_capture_metadata(
        source_key="clinvar",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"clinvar:search:{search_id}",
        retrieved_at=now,
        search_id=str(search_id),
        query="MED13",
        query_payload={"gene_symbol": "MED13"},
        result_count=1,
        provenance={"provider": "test"},
    )
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="MED13",
        gene_symbol="MED13",
        max_results=10,
        record_count=1,
        records=[
            {
                "accession": "VCV000001",
                "gene_symbol": "MED13",
                "title": "MED13 congenital heart disease variant",
                "clinical_significance": "Pathogenic",
            },
        ],
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )


def test_candidate_handoff_creates_source_document_without_runtime() -> None:
    space_id = uuid4()
    created_by = uuid4()
    search_id = uuid4()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=created_by,
    )

    document_store = HarnessDocumentStore()
    handoffs, errors = create_selected_handoffs(
        space_id=space_id,
        created_by=created_by,
        selected_records=(_selected_decision(search_id=search_id),),
        search_store=search_store,
        handoff_store=InMemorySourceSearchHandoffStore(),
        document_store=document_store,
        run_registry=HarnessRunRegistry(),
    )

    assert errors == []
    assert len(handoffs) == 1
    assert handoffs[0].source_key == "clinvar"
    assert handoffs[0].target_document_id is not None
    document = document_store.get_document(
        space_id=space_id,
        document_id=handoffs[0].target_document_id,
    )
    assert document is not None
    assert document.metadata["client_metadata"] == {
        "selected_by": "evidence-selection",
        "selected_record_hash": "record-hash",
    }


def test_candidate_handoff_reports_missing_store() -> None:
    handoffs, errors = create_selected_handoffs(
        space_id=uuid4(),
        created_by=uuid4(),
        selected_records=(),
        search_store=InMemoryDirectSourceSearchStore(),
        handoff_store=None,
        document_store=HarnessDocumentStore(),
        run_registry=HarnessRunRegistry(),
    )

    assert handoffs == []
    assert errors == ["Handoff store is unavailable."]


def _selected_decision(*, search_id: UUID) -> EvidenceSelectionCandidateDecision:
    return EvidenceSelectionCandidateDecision(
        source_key="clinvar",
        source_family="variant",
        search_id=str(search_id),
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=EvidenceSelectionDecisionRelevance.STRONG_FIT,
        reason="Record matches the goal/instructions through: med13.",
        record_index=0,
        record_hash="record-hash",
        title="MED13 congenital heart disease variant",
        score=9.0,
        matched_terms=("med13",),
    )
