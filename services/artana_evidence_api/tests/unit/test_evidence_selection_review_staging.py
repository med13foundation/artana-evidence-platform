"""Tests for focused evidence-selection review staging."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
)
from artana_evidence_api.evidence_selection_review_staging import (
    stage_selected_records_for_review,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)


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


def test_review_staging_creates_proposal_and_review_item_without_runtime() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_id = str(uuid4())
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    decision = EvidenceSelectionCandidateDecision(
        source_key="clinvar",
        source_family="variant",
        search_id=str(search_id),
        record_index=0,
        record_hash="record-hash",
        title="MED13 congenital heart disease variant",
        score=9.0,
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=EvidenceSelectionDecisionRelevance.STRONG_FIT,
        reason="Record matches the goal/instructions through: med13.",
        matched_terms=("med13",),
        caveats=("Variant-level records do not prove disease causality by themselves.",),
    )

    proposals, review_items, errors = stage_selected_records_for_review(
        space_id=space_id,
        run_id=run_id,
        selected_records=(decision,),
        handoffs=(),
        search_store=search_store,
        proposal_store=HarnessProposalStore(),
        review_item_store=HarnessReviewItemStore(),
    )

    assert errors == []
    assert len(proposals) == 1
    assert proposals[0].proposal_type == "variant_evidence_candidate"
    assert proposals[0].payload["review_gate"] == "pending_human_review"
    assert proposals[0].metadata["relevance_label"] == "strong_fit"
    assert proposals[0].metadata["normalized_extraction"]["source_key"] == "clinvar"
    assert len(review_items) == 1
    assert review_items[0].review_type == "variant_source_record_review"
    assert review_items[0].priority == "high"
