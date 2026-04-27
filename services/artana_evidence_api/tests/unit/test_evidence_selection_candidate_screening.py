"""Tests for focused evidence-selection candidate screening."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_candidate_screening import (
    apply_handoff_budget,
    defer_selected_for_shadow_mode,
    screen_candidate_searches,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionDecisionDeferralReason,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
    record_hash,
)
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
        result_count=2,
        provenance={"provider": "test"},
    )
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="MED13",
        gene_symbol="MED13",
        max_results=10,
        record_count=2,
        records=[
            {
                "accession": "VCV000001",
                "gene_symbol": "MED13",
                "title": "MED13 congenital heart disease variant",
                "clinical_significance": "Pathogenic",
            },
            {
                "accession": "VCV000002",
                "gene_symbol": "BRCA1",
                "title": "BRCA1 breast cancer variant",
            },
        ],
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )


def test_candidate_screening_selects_relevant_records_without_runtime() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )

    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=(),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=search_id,
                max_records=1,
            ),
        ),
        max_records_per_search=3,
        direct_source_search_store=search_store,
        document_store=HarnessDocumentStore(),
    )

    assert result.errors == ()
    assert len(result.selected_records) == 1
    assert result.selected_records[0].source_key == "clinvar"
    assert result.selected_records[0].relevance_label == (
        EvidenceSelectionDecisionRelevance.STRONG_FIT
    )
    assert result.skipped_records[0].relevance_label == (
        EvidenceSelectionDecisionRelevance.OFF_OBJECTIVE
    )


def test_candidate_screening_skips_existing_source_document() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    search = _clinvar_search(space_id=space_id, search_id=search_id)
    selected_record = search.records[0]
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(search, created_by=user_id)
    document_store = HarnessDocumentStore()
    document_store.create_document(
        space_id=space_id,
        created_by=user_id,
        title="Existing ClinVar record",
        source_type="clinvar",
        filename=None,
        media_type="application/json",
        sha256=record_hash(selected_record),
        byte_size=1,
        page_count=None,
        text_content="MED13 congenital heart disease variant",
        ingestion_run_id=uuid4(),
        enrichment_status="pending",
        extraction_status="pending",
        metadata={
            "source_search_id": str(search_id),
            "selected_record_index": 0,
            "selected_record": selected_record,
        },
    )

    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=(),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=search_id,
                max_records=1,
            ),
        ),
        max_records_per_search=3,
        direct_source_search_store=search_store,
        document_store=document_store,
    )

    assert result.selected_records == ()
    assert result.skipped_records[0].relevance_label == (
        EvidenceSelectionDecisionRelevance.CONTEXT_ONLY
    )
    assert result.skipped_records[0].original_relevance_label == (
        EvidenceSelectionDecisionRelevance.STRONG_FIT
    )
    assert "already selected" in result.skipped_records[0].reason


def test_candidate_screening_defers_selected_records_with_consistent_semantics() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )

    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=(),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=search_id,
                max_records=0,
            ),
        ),
        max_records_per_search=3,
        direct_source_search_store=search_store,
        document_store=HarnessDocumentStore(),
    )

    assert result.selected_records == ()
    assert len(result.deferred_records) == 1
    deferred = result.deferred_records[0]
    assert deferred.decision == EvidenceSelectionDecisionState.DEFERRED
    assert deferred.relevance_label == EvidenceSelectionDecisionRelevance.STRONG_FIT
    assert deferred.original_relevance_label == (
        EvidenceSelectionDecisionRelevance.STRONG_FIT
    )
    assert deferred.deferral_reason == (
        EvidenceSelectionDecisionDeferralReason.PER_SEARCH_BUDGET
    )


def test_candidate_screening_defers_missing_source_search() -> None:
    space_id = uuid4()
    search_id = uuid4()

    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=(),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=search_id,
            ),
        ),
        max_records_per_search=3,
        direct_source_search_store=InMemoryDirectSourceSearchStore(),
        document_store=HarnessDocumentStore(),
    )

    assert result.selected_records == ()
    assert result.skipped_records == ()
    assert len(result.deferred_records) == 1
    assert result.deferred_records[0].decision == (
        EvidenceSelectionDecisionState.DEFERRED
    )
    assert result.deferred_records[0].relevance_label == (
        EvidenceSelectionDecisionRelevance.DEFERRED
    )
    assert result.deferred_records[0].deferral_reason == (
        EvidenceSelectionDecisionDeferralReason.MISSING_SOURCE_SEARCH
    )
    assert result.errors == (f"Source search clinvar/{search_id} was not found.",)


def test_candidate_screening_marks_weak_match_for_human_review() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search_with_records(
            space_id=space_id,
            search_id=search_id,
            records=(
                {
                    "accession": "VCV000003",
                    "gene_symbol": "MED13",
                    "title": "MED13 note",
                },
            ),
        ),
        created_by=user_id,
    )

    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=(),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(source_key="clinvar", search_id=search_id),
        ),
        max_records_per_search=3,
        direct_source_search_store=search_store,
        document_store=HarnessDocumentStore(),
    )

    assert result.selected_records == ()
    assert result.skipped_records[0].relevance_label == (
        EvidenceSelectionDecisionRelevance.NEEDS_HUMAN_REVIEW
    )


def test_candidate_screening_skips_explicit_exclusion_matches() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )

    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=("pathogenic",),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(source_key="clinvar", search_id=search_id),
        ),
        max_records_per_search=3,
        direct_source_search_store=search_store,
        document_store=HarnessDocumentStore(),
    )

    assert result.selected_records == ()
    assert result.skipped_records[0].relevance_label == (
        EvidenceSelectionDecisionRelevance.OFF_OBJECTIVE
    )
    assert result.skipped_records[0].excluded_terms == ("pathogenic",)


def test_candidate_screening_budget_and_shadow_helpers_are_typed() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    result = screen_candidate_searches(
        space_id=space_id,
        goal="Find MED13 congenital heart disease evidence",
        instructions=None,
        inclusion_criteria=(),
        exclusion_criteria=(),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(source_key="clinvar", search_id=search_id),
        ),
        max_records_per_search=3,
        direct_source_search_store=search_store,
        document_store=HarnessDocumentStore(),
    )

    kept, run_budget_deferred = apply_handoff_budget(
        list(result.selected_records),
        max_handoffs=0,
    )
    shadow_deferred = defer_selected_for_shadow_mode(list(result.selected_records))

    assert kept == []
    assert run_budget_deferred[0].deferral_reason == (
        EvidenceSelectionDecisionDeferralReason.RUN_HANDOFF_BUDGET
    )
    assert run_budget_deferred[0].relevance_label == (
        run_budget_deferred[0].original_relevance_label
    )
    assert shadow_deferred[0].deferral_reason == (
        EvidenceSelectionDecisionDeferralReason.SHADOW_MODE
    )
    assert shadow_deferred[0].shadow_decision == EvidenceSelectionDecisionState.SELECTED
    assert shadow_deferred[0].would_have_been_selected is True


def test_handoff_budget_uses_deterministic_tie_breakers() -> None:
    first_search_id = uuid4()
    second_search_id = uuid4()
    decisions = [
        _selected_decision(
            source_key="pubmed",
            search_id=str(second_search_id),
            record_index=2,
            record_hash="record-c",
        ),
        _selected_decision(
            source_key="clinvar",
            search_id=str(first_search_id),
            record_index=1,
            record_hash="record-b",
        ),
        _selected_decision(
            source_key="alphafold",
            search_id=str(first_search_id),
            record_index=0,
            record_hash="record-a",
        ),
    ]

    kept, deferred = apply_handoff_budget(decisions, max_handoffs=2)

    assert [decision.source_key for decision in kept] == ["alphafold", "clinvar"]
    assert [decision.source_key for decision in deferred] == ["pubmed"]
    assert deferred[0].deferral_reason == (
        EvidenceSelectionDecisionDeferralReason.RUN_HANDOFF_BUDGET
    )


def _selected_decision(
    *,
    source_key: str,
    search_id: str,
    record_index: int,
    record_hash: str,
) -> EvidenceSelectionCandidateDecision:
    return EvidenceSelectionCandidateDecision(
        source_key=source_key,
        source_family="literature",
        search_id=search_id,
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=EvidenceSelectionDecisionRelevance.STRONG_FIT,
        reason="Selected.",
        record_index=record_index,
        record_hash=record_hash,
        score=6.0,
    )


def _clinvar_search_with_records(
    *,
    space_id: UUID,
    search_id: UUID,
    records: tuple[dict[str, object], ...],
) -> ClinVarSourceSearchResponse:
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
        result_count=len(records),
        provenance={"provider": "test"},
    )
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="MED13",
        gene_symbol="MED13",
        max_results=10,
        record_count=len(records),
        records=list(records),
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )
