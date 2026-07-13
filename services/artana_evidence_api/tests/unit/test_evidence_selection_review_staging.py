"""Tests for focused evidence-selection review staging."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.evidence_selection.ranking.contracts import (
    DeterministicRankingWeight,
    RankingCategoricalInput,
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
from artana_evidence_api.runtime.agent_output_schema import RetrievalAlgorithmNumber
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
        operational_ranking=DeterministicRankingWeight(
            value=9.0,
            policy_id="test_selection_ranking",
            policy_version="v1",
            mapping_version="v1",
            categorical_inputs=(
                RankingCategoricalInput(field="objective_match", value="direct"),
            ),
        ),
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
    assert proposals[0].ranking_score == 9.0
    assert proposals[0].confidence == 0.8
    assert proposals[0].metadata["selection_confidence_projection"] == {
        "origin": "deterministic_policy",
        "value": 0.8,
        "category": "strong_fit",
        "policy_id": "evidence_selection_review_confidence",
        "policy_version": "v1",
        "semantics": "deterministic_weight_not_probability",
    }
    assert proposals[0].metadata["normalized_extraction"]["source_key"] == "clinvar"
    assert len(review_items) == 1
    assert review_items[0].review_type == "variant_source_record_review"
    assert review_items[0].priority == "high"
    assert review_items[0].confidence == 0.8
    assert review_items[0].ranking_score == 9.0


def test_review_staging_rejects_retrieval_only_ranking() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
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
        retrieval_ranking=RetrievalAlgorithmNumber(
            value=9.0,
            provider_algorithm_id="legacy_retrieval_test",
            algorithm_version="v1",
            query_input_hash="0" * 64,
            affected_candidate_acquisition=True,
        ),
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=EvidenceSelectionDecisionRelevance.STRONG_FIT,
        reason="Retrieval candidate only.",
    )

    proposals, review_items, errors = stage_selected_records_for_review(
        space_id=space_id,
        run_id=str(uuid4()),
        selected_records=(decision,),
        handoffs=(),
        search_store=search_store,
        proposal_store=HarnessProposalStore(),
        review_item_store=HarnessReviewItemStore(),
    )

    assert proposals == []
    assert review_items == []
    assert len(errors) == 1
    assert "without deterministic operational ranking provenance" in errors[0]
