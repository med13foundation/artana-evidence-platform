"""Unit tests for the evidence-selection harness runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    DirectSourceSearchStore,
    InMemoryDirectSourceSearchStore,
    UniProtSourceSearchResponse,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_runtime import (
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionSourcePlanResult,
    execute_evidence_selection_run,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchRunner,
)
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryResult
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoveryProvider,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    PubMedDiscoveryService,
    RunPubmedSearchRequest,
)
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.source_search_handoff import InMemorySourceSearchHandoffStore
from artana_evidence_api.types.common import JSONObject


def _clinvar_search(
    *,
    space_id: UUID,
    search_id: UUID,
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


def _uniprot_search(
    *,
    space_id: UUID,
    search_id: UUID,
) -> UniProtSourceSearchResponse:
    now = datetime.now(UTC)
    capture = source_result_capture_metadata(
        source_key="uniprot",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"uniprot:search:{search_id}",
        retrieved_at=now,
        search_id=str(search_id),
        query="MED13",
        query_payload={"query": "MED13"},
        result_count=1,
        provenance={"provider": "test"},
    )
    return UniProtSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="MED13",
        uniprot_id=None,
        max_results=10,
        fetched_records=1,
        record_count=1,
        records=[
            {
                "uniprot_id": "Q9UHV7",
                "gene_name": "MED13",
                "title": "MED13 protein annotation",
                "protein_name": "Mediator complex subunit 13",
                "organism": "Homo sapiens",
                "function": "Mediator complex transcription regulation.",
            },
        ],
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )


class _FakeSourceSearchRunner(EvidenceSelectionSourceSearchRunner):
    """Test runner that saves a supplied ClinVar search instead of calling the network."""

    def __init__(self, result: ClinVarSourceSearchResponse) -> None:
        self._result = result

    async def run_search(
        self,
        *,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> ClinVarSourceSearchResponse:
        assert self._result.space_id == space_id
        assert source_search.source_key == "clinvar"
        return store.save(self._result, created_by=created_by)


class _SlowSourceSearchRunner(EvidenceSelectionSourceSearchRunner):
    """Source runner that exceeds the harness timeout in tests."""

    async def run_search(
        self,
        *,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> ClinVarSourceSearchResponse:
        del space_id, created_by, source_search, store
        await asyncio.sleep(1.0)
        raise AssertionError("timeout should happen before this returns")


class _FakeSourcePlanner:
    """Source planner double proving the runtime asks the planner seam."""

    def __init__(self) -> None:
        self.calls = 0

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
        del (
            requested_sources,
            source_searches,
            candidate_searches,
            inclusion_criteria,
            exclusion_criteria,
            population_context,
            evidence_types,
            priority_outcomes,
            workspace_snapshot,
            max_records_per_search,
        )
        self.calls += 1
        return EvidenceSelectionSourcePlanResult(
            source_plan={
                "goal": goal,
                "instructions": instructions,
                "sources": [
                    {
                        "source_key": "clinvar",
                        "source_family": "variant",
                        "action": "screen_saved_searches",
                        "reason": "Planner double selected ClinVar.",
                    },
                ],
                "planner": {
                    "kind": "agent",
                    "agent_invoked": True,
                    "reason": "fake planner invoked",
                    "active_skill": "graph_harness.source_relevance",
                },
            },
            source_searches=(),
            candidate_searches=(),
        )


class _LiveSourcePlanner:
    """Planner double proving executable plans can add source searches."""

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
        del (
            instructions,
            requested_sources,
            source_searches,
            candidate_searches,
            inclusion_criteria,
            exclusion_criteria,
            population_context,
            evidence_types,
            priority_outcomes,
            workspace_snapshot,
            max_records_per_search,
        )
        planned_search = EvidenceSelectionLiveSourceSearch(
            source_key="clinvar",
            query_payload={"gene_symbol": "MED13"},
            max_records=2,
        )
        return EvidenceSelectionSourcePlanResult(
            source_plan={
                "goal": goal,
                "sources": [
                    {
                        "source_key": "clinvar",
                        "action": "run_and_screen_source_searches",
                        "reason": "Fake agent planned a ClinVar search from the goal.",
                    },
                ],
                "planner": {
                    "kind": "agent",
                    "agent_invoked": True,
                    "reason": "fake executable planner invoked",
                },
            },
            source_searches=(planned_search,),
            candidate_searches=(),
        )


class _OutsideRequestedSourcePlanner:
    """Planner double that violates the requested source envelope."""

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
        del (
            goal,
            instructions,
            requested_sources,
            source_searches,
            candidate_searches,
            inclusion_criteria,
            exclusion_criteria,
            population_context,
            evidence_types,
            priority_outcomes,
            workspace_snapshot,
            max_records_per_search,
        )
        return EvidenceSelectionSourcePlanResult(
            source_plan={"planner": {"kind": "agent"}},
            source_searches=(
                EvidenceSelectionLiveSourceSearch(
                    source_key="clinvar",
                    query_payload={"gene_symbol": "MED13"},
                    max_records=2,
                ),
            ),
            candidate_searches=(),
        )


class _TooLongTimeoutPlanner:
    """Planner double that violates the per-source timeout ceiling."""

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
        del (
            goal,
            instructions,
            requested_sources,
            source_searches,
            candidate_searches,
            inclusion_criteria,
            exclusion_criteria,
            population_context,
            evidence_types,
            priority_outcomes,
            workspace_snapshot,
            max_records_per_search,
        )
        return EvidenceSelectionSourcePlanResult(
            source_plan={"planner": {"kind": "agent"}},
            source_searches=(
                EvidenceSelectionLiveSourceSearch(
                    source_key="clinvar",
                    query_payload={"gene_symbol": "MED13"},
                    timeout_seconds=999.0,
                ),
            ),
            candidate_searches=(),
        )


class _TooManyLiveSourceSearchesPlanner:
    """Planner double that violates the live source-search count budget."""

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
        del (
            goal,
            instructions,
            requested_sources,
            source_searches,
            candidate_searches,
            inclusion_criteria,
            exclusion_criteria,
            population_context,
            evidence_types,
            priority_outcomes,
            workspace_snapshot,
            max_records_per_search,
        )
        return EvidenceSelectionSourcePlanResult(
            source_plan={"planner": {"kind": "agent"}},
            source_searches=tuple(
                EvidenceSelectionLiveSourceSearch(
                    source_key="clinvar",
                    query_payload={"gene_symbol": "MED13"},
                )
                for _ in range(51)
            ),
            candidate_searches=(),
        )


class _FakePubMedDiscoveryService(PubMedDiscoveryService):
    """PubMed discovery double that records the harness-created request."""

    def __init__(self, *, result: DiscoverySearchJob) -> None:
        self._result = result
        self.requests: list[RunPubmedSearchRequest] = []

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        assert owner_id == self._result.owner_id
        self.requests.append(request)
        return self._result.model_copy(update={"parameters": request.parameters})

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        if owner_id == self._result.owner_id and job_id == self._result.id:
            return self._result
        return None

    def close(self) -> None:
        return None


class _FakeMarrvelDiscoveryService:
    """MARRVEL discovery double that records the harness-created request."""

    def __init__(self, *, result: MarrvelDiscoveryResult) -> None:
        self._result = result
        self.requests: list[dict[str, object]] = []
        self.close_count = 0

    async def search(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: tuple[str, ...] | list[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        assert owner_id == self._result.owner_id
        assert space_id == self._result.space_id
        self.requests.append(
            {
                "gene_symbol": gene_symbol,
                "variant_hgvs": variant_hgvs,
                "protein_variant": protein_variant,
                "taxon_id": taxon_id,
                "panels": list(panels or []),
            },
        )
        return self._result

    def close(self) -> None:
        self.close_count += 1


@contextmanager
def _pubmed_service_context(
    service: _FakePubMedDiscoveryService,
) -> Iterator[_FakePubMedDiscoveryService]:
    yield service


@pytest.mark.asyncio
async def test_evidence_selection_selects_relevant_records_and_creates_handoffs() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Prioritize ClinVar records.",
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=search_id,
            ),
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert result.run.status == "completed"
    assert len(result.selected_records) == 1
    assert result.selected_records[0]["record_index"] == 0
    assert len(result.skipped_records) == 1
    assert result.skipped_records[0]["record_index"] == 1
    assert len(result.handoffs) == 1
    assert result.handoffs[0].target_document_id is not None
    assert document_store.count_documents(space_id=space_id) == 1
    result_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="evidence_selection_result",
    )
    assert result_artifact is not None
    assert result_artifact.content["review_gate"] == {
        "trusted_graph_promotion": "review_required",
        "selected_records_are": "candidate_evidence",
        "approved_graph_facts_created": 0,
    }


@pytest.mark.asyncio
async def test_evidence_selection_asks_source_planner() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    planner = _FakeSourcePlanner()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Planner Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Ask the planner first.",
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
        source_planner=planner,
    )

    assert planner.calls == 1
    assert result.source_plan["planner"] == {
        "kind": "agent",
        "agent_invoked": True,
        "reason": "fake planner invoked",
        "active_skill": "graph_harness.source_relevance",
    }


@pytest.mark.asyncio
async def test_evidence_selection_executes_planner_added_live_searches() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Executable Planner Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Let the planner choose source searches.",
        sources=(),
        proposal_mode="review_required",
        mode="guarded",
        live_network_allowed=True,
        source_searches=(),
        candidate_searches=(),
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
        source_search_runner=_FakeSourceSearchRunner(
            _clinvar_search(space_id=space_id, search_id=search_id),
        ),
        source_planner=_LiveSourcePlanner(),
    )

    assert result.source_plan["planner"]["agent_invoked"] is True
    assert len(result.selected_records) == 1
    assert len(result.proposals) == 1


@pytest.mark.asyncio
async def test_evidence_selection_guarded_mode_requires_review_item_store() -> None:
    space_id = uuid4()
    user_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Missing Review Store",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    with pytest.raises(RuntimeError, match="requires a review item store"):
        await execute_evidence_selection_run(
            space_id=space_id,
            run=run,
            goal="Find MED13 evidence.",
            instructions=None,
            sources=("clinvar",),
            proposal_mode="review_required",
            mode="guarded",
            candidate_searches=(),
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
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            direct_source_search_store=InMemoryDirectSourceSearchStore(),
            source_search_handoff_store=InMemorySourceSearchHandoffStore(),
        )


@pytest.mark.asyncio
async def test_evidence_selection_rejects_planner_source_outside_request() -> None:
    space_id = uuid4()
    user_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Invalid Planner Output",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    with pytest.raises(ValueError, match="outside requested sources"):
        await execute_evidence_selection_run(
            space_id=space_id,
            run=run,
            goal="Find MED13 evidence.",
            instructions=None,
            sources=("pubmed",),
            proposal_mode="review_required",
            mode="guarded",
            live_network_allowed=True,
            candidate_searches=(),
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
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            review_item_store=HarnessReviewItemStore(),
            direct_source_search_store=InMemoryDirectSourceSearchStore(),
            source_search_handoff_store=InMemorySourceSearchHandoffStore(),
            source_planner=_OutsideRequestedSourcePlanner(),
        )


@pytest.mark.asyncio
async def test_evidence_selection_rejects_planner_timeout_above_ceiling() -> None:
    space_id = uuid4()
    user_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Invalid Planner Timeout",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    with pytest.raises(ValueError, match="above the 120 second limit"):
        await execute_evidence_selection_run(
            space_id=space_id,
            run=run,
            goal="Find MED13 evidence.",
            instructions=None,
            sources=("clinvar",),
            proposal_mode="review_required",
            mode="guarded",
            live_network_allowed=True,
            candidate_searches=(),
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
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            review_item_store=HarnessReviewItemStore(),
            direct_source_search_store=InMemoryDirectSourceSearchStore(),
            source_search_handoff_store=InMemorySourceSearchHandoffStore(),
            source_planner=_TooLongTimeoutPlanner(),
        )


@pytest.mark.asyncio
async def test_evidence_selection_rejects_planner_source_search_budget_overflow() -> None:
    space_id = uuid4()
    user_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Invalid Planner Search Budget",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    with pytest.raises(ValueError, match="above the 50 search run budget"):
        await execute_evidence_selection_run(
            space_id=space_id,
            run=run,
            goal="Find MED13 evidence.",
            instructions=None,
            sources=("clinvar",),
            proposal_mode="review_required",
            mode="guarded",
            live_network_allowed=True,
            candidate_searches=(),
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
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            review_item_store=HarnessReviewItemStore(),
            direct_source_search_store=InMemoryDirectSourceSearchStore(),
            source_search_handoff_store=InMemorySourceSearchHandoffStore(),
            source_planner=_TooManyLiveSourceSearchesPlanner(),
        )


@pytest.mark.asyncio
async def test_evidence_selection_skips_duplicate_records_within_one_run() -> None:
    space_id = uuid4()
    user_id = uuid4()
    first_search_id = uuid4()
    second_search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=first_search_id),
        created_by=user_id,
    )
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=second_search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Duplicate Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="The same source record appears in two saved searches.",
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=first_search_id,
            ),
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=second_search_id,
            ),
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert len(result.selected_records) == 1
    assert len(result.handoffs) == 1
    assert document_store.count_documents(space_id=space_id) == 1
    duplicate_skips = [
        record
        for record in result.skipped_records
        if record["reason"] == (
            "This source record was already selected or captured in the "
            "research space."
        )
    ]
    assert len(duplicate_skips) == 1


@pytest.mark.asyncio
async def test_evidence_selection_follow_up_skips_existing_source_document() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    parent = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Parent Evidence Selection",
        input_payload={"goal": "Find MED13 evidence."},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=parent)

    await execute_evidence_selection_run(
        space_id=space_id,
        run=parent,
        goal="Find MED13 congenital heart disease evidence.",
        instructions=None,
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )
    follow_up = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Follow-up Evidence Selection",
        input_payload={"goal": "Find MED13 evidence.", "parent_run_id": parent.id},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=follow_up)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=follow_up,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Re-check the same saved source search.",
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
        parent_run_id=parent.id,
        created_by=user_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        document_store=document_store,
        proposal_store=proposal_store,
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert result.workspace_snapshot["parent_run_id"] == parent.id
    assert result.workspace_snapshot["prior_evidence_run_count"] == 1
    assert len(result.handoffs) == 0
    assert any(
        skipped["reason"]
        == (
            "This source record was already selected or captured in the "
            "research space."
        )
        for skipped in result.skipped_records
    )


@pytest.mark.asyncio
async def test_evidence_selection_replays_duplicate_handoff_from_stale_snapshot() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    first_document_store = HarnessDocumentStore()
    stale_document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    first = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="First Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=first)
    first_result = await execute_evidence_selection_run(
        space_id=space_id,
        run=first,
        goal="Find MED13 congenital heart disease evidence.",
        instructions=None,
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
        document_store=first_document_store,
        proposal_store=proposal_store,
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )
    second = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Second Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=second)

    second_result = await execute_evidence_selection_run(
        space_id=space_id,
        run=second,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Repeat from a stale worker view.",
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
        document_store=stale_document_store,
        proposal_store=proposal_store,
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert first_result.handoffs[0].target_document_id == (
        second_result.handoffs[0].target_document_id
    )
    assert second_result.handoffs[0].replayed is True
    assert second_result.errors == ()


@pytest.mark.asyncio
async def test_evidence_selection_shadow_mode_recommends_without_handoff() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Shadow Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions=None,
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="shadow",
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
        direct_source_search_store=search_store,
        source_search_handoff_store=None,
    )

    assert result.selected_records == ()
    assert len(result.deferred_records) == 1
    assert result.deferred_records[0]["reason"] == (
        "Shadow mode records the recommendation without creating a source handoff."
    )
    assert result.deferred_records[0]["relevance_label"] == "deferred"
    assert result.deferred_records[0]["would_have_been_selected"] is True
    assert document_store.count_documents(space_id=space_id) == 0


@pytest.mark.asyncio
async def test_evidence_selection_finishes_with_error_status_for_missing_search() -> None:
    space_id = uuid4()
    user_id = uuid4()
    missing_search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Missing Source Search",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions=None,
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="clinvar",
                search_id=missing_search_id,
            ),
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert result.run.status == "completed_with_errors"
    assert len(result.errors) == 1
    assert "was not found" in result.errors[0]
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "completed_with_errors"
    assert "was not found" in str(workspace.snapshot["error"])


@pytest.mark.asyncio
async def test_evidence_selection_rejects_unknown_runtime_mode() -> None:
    space_id = uuid4()
    user_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Invalid Mode",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    with pytest.raises(ValueError, match="Unsupported evidence-selection mode"):
        await execute_evidence_selection_run(
            space_id=space_id,
            run=run,
            goal="Find MED13 evidence.",
            instructions=None,
            sources=("clinvar",),
            proposal_mode="review_required",
            mode="unknown",
            candidate_searches=(),
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
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            direct_source_search_store=InMemoryDirectSourceSearchStore(),
            source_search_handoff_store=InMemorySourceSearchHandoffStore(),
        )


@pytest.mark.asyncio
async def test_evidence_selection_global_budget_defers_selected_records() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Budgeted Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions=None,
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(source_key="clinvar", search_id=search_id),
        ),
        max_records_per_search=3,
        max_handoffs=0,
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert result.selected_records == ()
    assert result.handoffs == ()
    assert result.deferred_records[0]["reason"] == (
        "Run handoff budget reached before this record."
    )


@pytest.mark.asyncio
async def test_evidence_selection_keeps_biomedical_goal_terms() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    now = datetime.now(UTC)
    capture = source_result_capture_metadata(
        source_key="clinvar",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"clinvar:search:{search_id}",
        retrieved_at=now,
        search_id=str(search_id),
        query="variant evidence",
        query_payload={"gene_symbol": "MED13"},
        result_count=2,
        provenance={"provider": "test"},
    )
    search = ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="variant evidence",
        gene_symbol="MED13",
        max_results=10,
        record_count=2,
        records=[
            {"title": "variant evidence"},
            {"title": "unrelated background"},
        ],
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(search, created_by=user_id)
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Biomedical Terms",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="variant evidence",
        instructions=None,
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
    )

    assert result.selected_records[0]["record_index"] == 0
    assert result.selected_records[0]["matched_terms"] == ["evidence", "variant"]
    assert result.selected_records[0]["relevance_label"] == "strong_fit"


@pytest.mark.asyncio
async def test_evidence_selection_runs_live_source_search_and_stages_review_outputs() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Live Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Search ClinVar directly.",
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        live_network_allowed=True,
        source_searches=(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"gene_symbol": "MED13"},
                max_records=2,
                timeout_seconds=0.001,
            ),
        ),
        candidate_searches=(),
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
        source_search_runner=_FakeSourceSearchRunner(
            _clinvar_search(space_id=space_id, search_id=search_id),
        ),
    )

    assert len(result.selected_records) == 1
    assert result.selected_records[0]["relevance_label"] == "strong_fit"
    assert len(result.handoffs) == 1
    assert len(result.proposals) == 1
    assert result.proposals[0].status == "pending_review"
    assert result.proposals[0].document_id == str(result.handoffs[0].target_document_id)
    assert result.proposals[0].metadata["source_search_id"] == str(search_id)
    assert len(result.review_items) == 1
    assert result.review_items[0].status == "pending_review"
    assert result.review_items[0].metadata["selected_record_hash"] == (
        result.selected_records[0]["record_hash"]
    )
    assert result.review_items[0].metadata["relevance_label"] == "strong_fit"
    decisions_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="evidence_selection_decisions",
    )
    assert decisions_artifact is not None
    assert decisions_artifact.content["selected_records"][0]["relevance_label"] == (
        "strong_fit"
    )
    assert result.workspace_snapshot["graph_state_summary"] == {
        "approved_evidence_count": 0,
        "approved_action_count": 0,
        "pending_review_count": 0,
        "rejected_evidence_count": 0,
        "summary_basis": (
            "Evidence API proposal and approval state; trusted graph facts are "
            "still read through the graph service."
        ),
    }


@pytest.mark.asyncio
async def test_evidence_selection_stages_source_specific_uniprot_proposal() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    search_store.save(
        _uniprot_search(space_id=space_id, search_id=search_id),
        created_by=user_id,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="UniProt Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 protein evidence.",
        instructions="Prioritize UniProt protein records.",
        sources=("uniprot",),
        proposal_mode="review_required",
        mode="guarded",
        candidate_searches=(
            EvidenceSelectionCandidateSearch(source_key="uniprot", search_id=search_id),
        ),
        max_records_per_search=3,
        max_handoffs=10,
        inclusion_criteria=(),
        exclusion_criteria=(),
        population_context=None,
        evidence_types=("protein",),
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

    assert len(result.proposals) == 1
    assert result.proposals[0].proposal_type == "protein_annotation_candidate"
    assert result.review_items[0].review_type == "protein_annotation_review"
    normalized = result.proposals[0].metadata["normalized_extraction"]
    assert normalized["evidence_role"] == "protein annotation context candidate"
    assert normalized["fields"] == {
        "uniprot_id": "Q9UHV7",
        "gene_name": "MED13",
        "protein_name": "Mediator complex subunit 13",
        "organism": "Homo sapiens",
        "function": "Mediator complex transcription regulation.",
    }


@pytest.mark.asyncio
async def test_evidence_selection_live_source_search_times_out() -> None:
    space_id = uuid4()
    user_id = uuid4()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Slow Live Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Search ClinVar directly, but the source is slow.",
        sources=("clinvar",),
        proposal_mode="review_required",
        mode="guarded",
        live_network_allowed=True,
        source_searches=(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"gene_symbol": "MED13"},
                max_records=2,
                timeout_seconds=0.001,
            ),
        ),
        candidate_searches=(),
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
        review_item_store=HarnessReviewItemStore(),
        direct_source_search_store=search_store,
        source_search_handoff_store=handoff_store,
        source_search_runner=_SlowSourceSearchRunner(),
    )

    assert result.run.status == "completed_with_errors"
    assert result.selected_records == ()
    assert result.handoffs == ()
    assert result.errors == (
        "Timed out creating clinvar source search after 0.001 seconds.",
    )


@pytest.mark.asyncio
async def test_evidence_selection_runner_creates_live_pubmed_search() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    now = datetime.now(UTC)
    pubmed_service = _FakePubMedDiscoveryService(
        result=DiscoverySearchJob(
            id=search_id,
            owner_id=user_id,
            session_id=space_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview="MED13 congenital heart disease",
            parameters=AdvancedQueryParameters(
                search_term="MED13 congenital heart disease",
            ),
            total_results=1,
            result_metadata={
                "preview_records": [
                    {
                        "pmid": "12345",
                        "title": "MED13 congenital heart disease report",
                        "abstract": (
                            "MED13 variant evidence in congenital heart disease."
                        ),
                    },
                ],
            },
            created_at=now,
            updated_at=now,
            completed_at=now,
        ),
    )
    runner = EvidenceSelectionSourceSearchRunner(
        pubmed_discovery_service_factory=lambda: _pubmed_service_context(
            pubmed_service,
        ),
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Live PubMed Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Search PubMed directly.",
        sources=("pubmed",),
        proposal_mode="review_required",
        mode="guarded",
        live_network_allowed=True,
        source_searches=(
            EvidenceSelectionLiveSourceSearch(
                source_key="pubmed",
                query_payload={
                    "parameters": {
                        "search_term": "MED13 congenital heart disease",
                    },
                },
                max_records=1,
            ),
        ),
        candidate_searches=(),
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
        source_search_runner=runner,
    )

    assert pubmed_service.requests[0].parameters.max_results == 1
    assert len(result.selected_records) == 1
    assert result.selected_records[0]["source_key"] == "pubmed"
    assert result.proposals[0].proposal_type == "literature_evidence_candidate"
    assert result.review_items[0].review_type == "literature_extraction_review"


@pytest.mark.asyncio
async def test_evidence_selection_runner_creates_live_marrvel_search() -> None:
    space_id = uuid4()
    user_id = uuid4()
    search_id = uuid4()
    now = datetime.now(UTC)
    marrvel_service = _FakeMarrvelDiscoveryService(
        result=MarrvelDiscoveryResult(
            id=search_id,
            space_id=space_id,
            owner_id=user_id,
            query_mode="gene",
            query_value="MED13",
            gene_symbol="MED13",
            resolved_gene_symbol="MED13",
            resolved_variant=None,
            taxon_id=9606,
            status="completed",
            gene_found=True,
            gene_info={
                "symbol": "MED13",
                "description": "Mediator subunit linked to heart development.",
            },
            omim_count=1,
            variant_count=0,
            panel_counts={"omim": 1},
            panels={
                "omim": [
                    {
                        "title": "MED13 congenital heart disease phenotype",
                        "phenotype": "congenital heart disease",
                    },
                ],
            },
            available_panels=["omim"],
            created_at=now,
        ),
    )
    runner = EvidenceSelectionSourceSearchRunner(
        marrvel_discovery_service_factory=lambda: marrvel_service,
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Live MARRVEL Evidence Selection",
        input_payload={},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)

    result = await execute_evidence_selection_run(
        space_id=space_id,
        run=run,
        goal="Find MED13 congenital heart disease evidence.",
        instructions="Search MARRVEL directly.",
        sources=("marrvel",),
        proposal_mode="review_required",
        mode="guarded",
        live_network_allowed=True,
        source_searches=(
            EvidenceSelectionLiveSourceSearch(
                source_key="marrvel",
                query_payload={"gene_symbol": "MED13", "panels": ["omim"]},
                max_records=1,
            ),
        ),
        candidate_searches=(),
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
        source_search_runner=runner,
    )

    assert marrvel_service.requests == [
        {
            "gene_symbol": "MED13",
            "variant_hgvs": None,
            "protein_variant": None,
            "taxon_id": 9606,
            "panels": ["omim"],
        },
    ]
    assert marrvel_service.close_count == 1
    assert len(result.selected_records) == 1
    assert result.selected_records[0]["source_key"] == "marrvel"
    assert result.proposals[0].proposal_type == "variant_evidence_candidate"
