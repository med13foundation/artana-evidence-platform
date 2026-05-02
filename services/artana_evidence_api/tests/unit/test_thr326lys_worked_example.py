"""Thr326Lys worked-example regression for evidence-selection runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
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
    EvidenceSelectionSourcePlanResult,
    build_source_plan,
    execute_evidence_selection_run,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
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
from artana_evidence_api.types.common import JSONObject

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "evidence_selection"
    / "thr326lys_worked_example.json"
)
_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_FIXED_CAPTURED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class _Thr326LysFixturePlanner:
    """Planner double that records fixture-declared source coverage gaps."""

    def __init__(self, fixture: JSONObject) -> None:
        self._fixture = fixture

    async def build_plan(
        self,
        *,
        goal: str,
        instructions: str | None,
        requested_sources: tuple[str, ...],
        source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
        candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
        inclusion_criteria: tuple[str, ...],
        exclusion_criteria: tuple[str, ...],
        population_context: str | None,
        evidence_types: tuple[str, ...],
        priority_outcomes: tuple[str, ...],
        workspace_snapshot: JSONObject,
        max_records_per_search: int,
    ) -> EvidenceSelectionSourcePlanResult:
        del workspace_snapshot, max_records_per_search
        deferred_sources = _fixture_object_list(
            self._fixture,
            key="unsupported_or_skipped_sources",
        )
        return EvidenceSelectionSourcePlanResult(
            source_plan=build_source_plan(
                goal=goal,
                instructions=instructions,
                requested_sources=requested_sources,
                source_searches=source_searches,
                candidate_searches=candidate_searches,
                inclusion_criteria=inclusion_criteria,
                exclusion_criteria=exclusion_criteria,
                population_context=population_context,
                evidence_types=evidence_types,
                priority_outcomes=priority_outcomes,
                planner_kind="deterministic",
                planner_mode="deterministic",
                planner_reason=(
                    "Thr326Lys worked-example fixture records deterministic "
                    "source coverage and unsupported-source diagnostics."
                ),
                deferred_sources=deferred_sources,
                validation_decisions=_validation_decisions(deferred_sources),
            ),
            source_searches=source_searches,
            candidate_searches=candidate_searches,
        )


@pytest.mark.asyncio
async def test_thr326lys_worked_example_stages_variant_review_candidates() -> None:
    fixture = _load_fixture()
    assert _fixture_string(fixture, key="fixture_name") == _FIXTURE_PATH.stem
    safety = _fixture_object(fixture, key="safety")
    expected = _fixture_object(fixture, key="expected")
    requested_sources = _fixture_string_tuple(fixture, key="requested_sources")
    space_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search_from_fixture(
            fixture=fixture,
            space_id=space_id,
            search_id=search_id,
        ),
        created_by=_USER_ID,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Thr326Lys Worked Example",
        input_payload={"fixture_name": _fixture_string(fixture, key="fixture_name")},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal=_fixture_string(fixture, key="goal"),
        instructions=_fixture_string(fixture, key="instructions"),
        sources=requested_sources,
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=search_id,
            ),
        ),
        max_records_per_search=3,
        max_handoffs=1,
        inclusion_criteria=("MED13", "Thr326Lys", "variant evidence"),
        exclusion_criteria=(),
        population_context=None,
        evidence_types=("variant",),
        priority_outcomes=("source coverage", "review staging"),
        parent_run_id=None,
        created_by=_USER_ID,
        run_registry=run_registry,
        artifact_store=artifact_store,
        document_store=document_store,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
        source_planner=_Thr326LysFixturePlanner(fixture),
    )

    assert safety["contains_phi"] is False
    assert safety["evidence_scope"] == "public_only"
    assert "not a clinical interpretation" in safety["medical_claim_boundary"]
    assert result.run.status == "completed"
    assert len(result.selected_records) == 1
    assert result.selected_records[0]["source_key"] == expected["selected_source_key"]
    assert result.selected_records[0]["title"] == expected["selected_record_title"]
    assert result.selected_records[0]["candidate_context"][
        "variant_aware_recommended"
    ] is True
    assert result.selected_records[0]["candidate_context"]["normalized_record"][
        "hgvs"
    ] == "NM_015335.6:c.977C>A"
    assert len(result.skipped_records) == 1
    assert result.skipped_records[0]["title"] == expected["skipped_record_title"]
    assert "weak goal overlap" in result.skipped_records[0]["reason"]
    assert "med13" not in result.skipped_records[0]["matched_terms"]
    assert "thr326lys" not in result.skipped_records[0]["matched_terms"]
    assert len(result.handoffs) == 1
    assert document_store.count_documents(space_id=space_id) == 1
    assert len(result.proposals) == 1
    assert result.proposals[0].proposal_type == expected["proposal_type"]
    assert result.proposals[0].status == "pending_review"
    assert len(result.review_items) == 1
    assert result.review_items[0].review_type == expected["review_type"]
    assert result.review_items[0].status == "pending_review"
    assert result.review_items[0].metadata["normalized_extraction"]["fields"][
        "gene_symbol"
    ] == "MED13"

    deferred_sources = result.source_plan["planner"]["deferred_sources"]
    expected_source_keys = {
        source["source_key"]
        for source in _fixture_object_list(
            fixture,
            key="unsupported_or_skipped_sources",
        )
    }
    assert {source["source_key"] for source in deferred_sources} == expected_source_keys
    validation_decisions = result.source_plan["planner"]["validation_decisions"]
    assert {
        (decision["source_key"], decision["decision"])
        for decision in validation_decisions
    } == {(source_key, "deferred") for source_key in expected_source_keys}
    assert any(
        item["source_key"] == "alphamissense" and "Unsupported" in item["reason"]
        for item in deferred_sources
    )
    gnomad_plan = next(
        source
        for source in result.source_plan["sources"]
        if source["source_key"] == "gnomad"
    )
    assert gnomad_plan["action"] == "defer_search_request"
    assert result.errors == ()


def _load_fixture() -> JSONObject:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("Thr326Lys fixture must be a JSON object.")
    return cast("JSONObject", raw)


def _clinvar_search_from_fixture(
    *,
    fixture: JSONObject,
    space_id: UUID,
    search_id: UUID,
) -> ClinVarSourceSearchResponse:
    search = _fixture_object(fixture, key="clinvar_search")
    records = _fixture_object_list(search, key="records")
    query = _fixture_string(search, key="query")
    gene_symbol = _fixture_string(search, key="gene_symbol")
    capture = source_result_capture_metadata(
        source_key="clinvar",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"clinvar:search:{search_id}",
        retrieved_at=_FIXED_CAPTURED_AT,
        search_id=str(search_id),
        query=query,
        query_payload={"gene_symbol": gene_symbol},
        result_count=len(records),
        provenance={"provider": "public-fixture"},
    )
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        gene_symbol=gene_symbol,
        max_results=10,
        record_count=len(records),
        records=list(records),
        created_at=_FIXED_CAPTURED_AT,
        completed_at=_FIXED_CAPTURED_AT,
        source_capture=SourceResultCapture.model_validate(capture),
    )


def _validation_decisions(
    deferred_sources: tuple[JSONObject, ...],
) -> tuple[JSONObject, ...]:
    return tuple(
        {
            "source_key": _fixture_string(source, key="source_key"),
            "decision": "deferred",
            "reason": "fixture_source_coverage_gap",
        }
        for source in deferred_sources
    )


def _fixture_object(fixture: JSONObject, *, key: str) -> JSONObject:
    value = fixture.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"Fixture field '{key}' must be an object.")
    return cast("JSONObject", value)


def _fixture_object_list(fixture: JSONObject, *, key: str) -> tuple[JSONObject, ...]:
    value = fixture.get(key)
    if not isinstance(value, list):
        raise TypeError(f"Fixture field '{key}' must be a list.")
    objects: list[JSONObject] = []
    for item in value:
        if not isinstance(item, dict):
            raise TypeError(f"Fixture field '{key}' must contain objects.")
        objects.append(cast("JSONObject", item))
    return tuple(objects)


def _fixture_string(fixture: JSONObject, *, key: str) -> str:
    value = fixture.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Fixture field '{key}' must be a string.")
    return value


def _fixture_string_tuple(fixture: JSONObject, *, key: str) -> tuple[str, ...]:
    value = fixture.get(key)
    if not isinstance(value, list):
        raise TypeError(f"Fixture field '{key}' must be a list.")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"Fixture field '{key}' must contain strings.")
        strings.append(item)
    return tuple(strings)
