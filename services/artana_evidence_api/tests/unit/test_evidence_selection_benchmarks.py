"""Offline benchmark checks for evidence-selection harness behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_runtime import (
    EvidenceSelectionCandidateSearch,
    execute_evidence_selection_run,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.source_search_handoff import InMemorySourceSearchHandoffStore
from artana_evidence_api.types.common import JSONObject, json_object_or_empty

_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_selection"
    / "med13_congenital_heart_disease"
)


def _load_json(name: str) -> JSONObject:
    return json_object_or_empty(json.loads((_FIXTURE_ROOT / name).read_text()))


def _fixture_search(*, space_id: UUID, search_id: UUID) -> ClinVarSourceSearchResponse:
    source_results = _load_json("source_results.json")
    records_value = source_results.get("records")
    records = (
        [json_object_or_empty(record) for record in records_value if isinstance(record, dict)]
        if isinstance(records_value, list)
        else []
    )
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
        provenance={"provider": "offline_fixture"},
    )
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="MED13",
        gene_symbol="MED13",
        max_results=10,
        record_count=len(records),
        records=records,
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )


@pytest.mark.asyncio
async def test_med13_congenital_heart_disease_fixture_selection() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    source_results = _load_json("source_results.json")
    expected_selected = _load_json("expected_selected.json")
    expected_skipped = _load_json("expected_skipped.json")
    expected_proposals = _load_json("expected_proposals.json")
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _fixture_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="MED13 benchmark",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal=str(source_results["goal"]),
        instructions=str(source_results["instructions"]),
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(source_key="clinvar", search_id=search_id),
        ),
        max_records_per_search=3,
        max_handoffs=10,
        inclusion_criteria=(),
        exclusion_criteria=(),
        population_context=None,
        evidence_types=(),
        priority_outcomes=(),
        parent_run_id=None,
        created_by=user_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        document_store=document_store,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert [record["record_index"] for record in result.selected_records] == (
        expected_selected["record_indexes"]
    )
    assert [record["record_index"] for record in result.skipped_records] == (
        expected_skipped["record_indexes"]
    )
    assert result.skipped_records[0]["reason"] == expected_skipped["required_reason"]
    assert len(result.proposals) == expected_proposals["proposal_count"]
    assert len(result.review_items) == expected_proposals["review_item_count"]
    assert result.proposals[0].proposal_type == expected_proposals["proposal_type"]
    assert result.review_items[0].review_type == expected_proposals["review_type"]
