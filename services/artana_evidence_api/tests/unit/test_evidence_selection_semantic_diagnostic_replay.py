"""Replay the current deterministic selector against the diagnostic corpus."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from artana_evidence_api.direct_source_search import (
    InMemoryDirectSourceSearchStore,
    PubMedSourceSearchResponse,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticCase,
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPrediction,
)
from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    score_semantic_diagnostic,
)
from artana_evidence_api.evidence_selection_candidate_screening import (
    screen_candidate_searches,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateSearch,
)
from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)

FIXTURE_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_failure_corpus_v1.json",
)


def test_current_selector_replay_remains_below_semantic_quality_targets() -> None:
    fixture = load_semantic_diagnostic_fixture(FIXTURE_PATH)
    predictions = tuple(
        prediction
        for case in fixture.cases
        for prediction in _current_selector_predictions(case)
    )

    score = score_semantic_diagnostic(fixture, predictions)

    assert score.micro.precision < 0.8
    assert score.micro.end_to_end_recall < 0.8
    assert score.macro.precision < 0.8
    assert score.macro.end_to_end_recall < 0.8
    canary = next(
        result
        for result in score.case_results
        if result.case_id == "egfr_exclusion_token_canary"
    )
    assert canary.true_positive_count == 0
    assert canary.false_negative_count == canary.record_count
    cftr = next(
        result
        for result in score.case_results
        if result.case_id == "cftr_f508del_eti_response"
    )
    assert cftr.true_positive_count == 0
    assert cftr.false_negative_count == 4
    assert cftr.false_positive_count == 3


def _current_selector_predictions(
    case: EvidenceSelectionSemanticDiagnosticCase,
) -> tuple[EvidenceSelectionSemanticPrediction, ...]:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    source_search_store = InMemoryDirectSourceSearchStore()
    source_search_store.save(
        _pubmed_search(
            case=case,
            space_id=space_id,
            owner_id=user_id,
            search_id=search_id,
        ),
        created_by=user_id,
    )
    result = screen_candidate_searches(
        space_id=space_id,
        goal=case.goal,
        instructions=case.instructions,
        inclusion_criteria=case.inclusion_criteria,
        exclusion_criteria=case.exclusion_criteria,
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="pubmed",
                search_id=search_id,
                max_records=len(case.records),
            ),
        ),
        max_records_per_search=len(case.records),
        direct_source_search_store=source_search_store,
        document_store=HarnessDocumentStore(),
    )
    decision_by_index = {
        decision.record_index: "select" for decision in result.selected_records
    }
    decision_by_index.update(
        {decision.record_index: "reject" for decision in result.skipped_records},
    )
    decision_by_index.update(
        {decision.record_index: "abstain" for decision in result.deferred_records},
    )
    assert set(decision_by_index) == set(range(len(case.records)))
    return tuple(
        EvidenceSelectionSemanticPrediction(
            record_id=record.record_id,
            decision=decision_by_index[index],
            reason="Current deterministic selector offline replay.",
        )
        for index, record in enumerate(case.records)
    )


def _pubmed_search(
    *,
    case: EvidenceSelectionSemanticDiagnosticCase,
    space_id: UUID,
    owner_id: UUID,
    search_id: UUID,
) -> PubMedSourceSearchResponse:
    now = datetime.now(UTC)
    records = [
        {
            "pmid": record.source_record_id,
            "title": record.title,
            "abstract": record.evidence_excerpt,
        }
        for record in case.records
    ]
    capture = source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"pubmed:search:{search_id}",
        retrieved_at=now,
        search_id=str(search_id),
        query=case.goal,
        query_payload={"search_term": case.goal},
        result_count=len(records),
        provenance={"provider": "offline_semantic_diagnostic_fixture"},
    )
    return PubMedSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        owner_id=owner_id,
        query=case.goal,
        query_preview=case.goal,
        parameters=AdvancedQueryParameters(
            search_term=case.goal,
            max_results=len(records),
        ),
        total_results=len(records),
        record_count=len(records),
        records=records,
        created_at=now,
        updated_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )
