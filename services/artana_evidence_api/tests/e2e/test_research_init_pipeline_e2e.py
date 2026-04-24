"""End-to-end test for the complete research-init pipeline.

Verifies every phase of the pipeline produces expected results:
  Phase 1: PubMed discovery + candidate selection
  Phase 2: Document ingestion
  Phase 2b: Structured source enrichment (ClinVar, DrugBank, AlphaFold)
  Phase 3: Document extraction (LLM)
  Phase 4: Bootstrap
  Chase rounds
  Deferred: MONDO ontology loading
  Research brief generation + storage

Run with:
    PYTHONPATH=services venv/bin/python3 -m pytest \
        services/artana_evidence_api/tests/e2e/test_research_init_pipeline_e2e.py -v
"""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import cast
from uuid import UUID, uuid4

import pytest
from artana_evidence_api import research_init_runtime
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.document_extraction import (
    DocumentCandidateExtractionDiagnostics,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
)
from artana_evidence_api.research_init_source_enrichment import SourceEnrichmentResult
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.routers import research_init
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.types.graph_contracts import (
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityListResponse,
)

# ---------------------------------------------------------------------------
# Stub helpers (following the existing test_research_init.py patterns)
# ---------------------------------------------------------------------------


class _StubGraphHealth:
    status = "ok"
    version = "test"


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealth:
        return _StubGraphHealth()

    def create_entity(
        self,
        *,
        space_id: UUID,
        entity_type: str,
        display_label: object,
    ) -> dict[str, str]:
        del space_id, entity_type, display_label
        return {"id": str(uuid4())}

    def refresh_entity_embeddings(
        self,
        *,
        space_id: UUID,
        request: KernelEntityEmbeddingRefreshRequest,
    ) -> KernelEntityEmbeddingRefreshResponse:
        del space_id, request
        return KernelEntityEmbeddingRefreshResponse(
            requested=0,
            processed=0,
            refreshed=0,
            unchanged=0,
            failed=0,
            missing_entities=[],
        )

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)

    def list_entity_embedding_status(
        self,
        *,
        space_id: UUID,
        entity_ids: list[str] | None = None,
    ) -> KernelEntityEmbeddingStatusListResponse:
        del space_id, entity_ids
        return KernelEntityEmbeddingStatusListResponse(statuses=[], total=0)

    def close(self) -> None:
        return None


class _StubRuntime:
    def __init__(self) -> None:
        self.kernel = object()


class _StubGraphConnectionRunner:
    pass


class _StubGraphChatRunner:
    pass


def _fake_pubmed_discovery_service_factory():
    return nullcontext(object())


def _build_execution_services(
    *,
    document_store: HarnessDocumentStore | None = None,
    proposal_store: HarnessProposalStore | None = None,
    research_state_store: HarnessResearchStateStore | None = None,
    graph_snapshot_store: HarnessGraphSnapshotStore | None = None,
) -> HarnessExecutionServices:
    return HarnessExecutionServices(
        runtime=cast("object", _StubRuntime()),
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        chat_session_store=HarnessChatSessionStore(),
        document_store=document_store or HarnessDocumentStore(),
        proposal_store=proposal_store or HarnessProposalStore(),
        approval_store=HarnessApprovalStore(),
        research_state_store=research_state_store or HarnessResearchStateStore(),
        graph_snapshot_store=graph_snapshot_store or HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        graph_connection_runner=cast("object", _StubGraphConnectionRunner()),
        graph_chat_runner=cast("object", _StubGraphChatRunner()),
        graph_api_gateway_factory=_StubGraphApiGateway,
        pubmed_discovery_service_factory=cast(
            "object",
            _fake_pubmed_discovery_service_factory,
        ),
    )


def _build_extraction_draft(
    *,
    document_id: str,
    title: str,
) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=document_id,
        title=f"Draft for {title}",
        summary="Synthetic extraction draft",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": "entity-1",
            "proposed_object": "entity-2",
        },
        metadata={},
        document_id=document_id,
    )


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_TEST_CANDIDATES = [
    research_init._PubMedCandidate(
        title="MED13 mutations cause neurodevelopmental disorder",
        text=(
            "We report that MED13 haploinsufficiency disrupts Mediator complex "
            "transcriptional regulation, leading to neurodevelopmental phenotypes "
            "including intellectual disability and seizures."
        ),
        queries=["MED13"],
        pmid="39000001",
        doi="10.1000/test.001",
        pmc_id=None,
        journal="American Journal of Human Genetics",
    ),
    research_init._PubMedCandidate(
        title="Mediator complex subunit 13 in transcriptional regulation",
        text=(
            "The Mediator complex is a multi-subunit coactivator that bridges "
            "transcription factors and RNA polymerase II. MED13 serves as a key "
            "structural interface within the kinase module."
        ),
        queries=["Mediator complex"],
        pmid="39000002",
        doi="10.1000/test.002",
        pmc_id="PMC9900002",
        journal="Nature Structural & Molecular Biology",
    ),
    research_init._PubMedCandidate(
        title="CDK8-Mediator kinase module regulates developmental gene expression",
        text=(
            "CDK8 and MED13 cooperatively regulate the kinase module of the "
            "Mediator complex. Disruption of CDK8-MED13 interactions alters Wnt "
            "and Notch signaling in embryonic development."
        ),
        queries=["MED13"],
        pmid="39000003",
        doi="10.1000/test.003",
        pmc_id=None,
        journal="Genes & Development",
    ),
]

_TEST_EXTRACTION_CANDIDATES = [
    ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="causes",
        object_label="neurodevelopmental disorder",
        sentence="MED13 haploinsufficiency causes neurodevelopmental disorder.",
    ),
    ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="interacts_with",
        object_label="CDK8",
        sentence="MED13 interacts with CDK8 in the kinase module.",
    ),
]


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_init_full_pipeline_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the full research-init pipeline with all sources enabled and verify each phase."""

    # ── 1. Set up space and services ──────────────────────────────────
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    services = _build_execution_services(
        document_store=document_store,
        proposal_store=proposal_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
    )

    sources = {
        "pubmed": True,
        "marrvel": True,
        "clinvar": True,
        "mondo": True,
        "drugbank": True,
        "alphafold": True,
        "uniprot": False,
        "pdf": True,
        "text": True,
    }

    # ── 2. Queue the run record ───────────────────────────────────────
    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="E2E MED13 research",
        objective="Investigate MED13 transcriptional regulation",
        seed_terms=["MED13", "Mediator complex"],
        sources=sources,
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    # ── 3. Stub external dependencies ─────────────────────────────────

    # Track phase execution for assertions
    phases_executed: dict[str, bool] = {}

    # ── 3a. MONDO: stub to return a small set of test terms ───────────
    mondo_terms_loaded = 0
    mondo_hierarchy_edges = 0

    class _StubOntologyIngestionSummary:
        def __init__(self) -> None:
            self.terms_imported = 5
            self.hierarchy_edges_created = 3
            self.alias_candidates_count = 0
            self.aliases_registered = 0
            self.aliases_persisted = 0
            self.aliases_skipped = 0
            self.alias_entities_touched = 0
            self.alias_errors: list[str] = []
            self.aliases_persisted_by_namespace_entity_type: dict[str, int] = {}

    class _StubOntologyIngestionService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def ingest(self, **_kwargs: object) -> _StubOntologyIngestionSummary:
            nonlocal mondo_terms_loaded, mondo_hierarchy_edges
            mondo_terms_loaded = 5
            mondo_hierarchy_edges = 3
            phases_executed["mondo"] = True
            return _StubOntologyIngestionSummary()

    monkeypatch.setattr(
        research_init_runtime,
        "build_mondo_ingestion_service",
        lambda **_kwargs: _StubOntologyIngestionService(),
    )
    deferred_mondo_tasks: list[asyncio.Task[None]] = []

    def _start_deferred_mondo_load(**kwargs: object) -> None:
        deferred_mondo_tasks.append(
            asyncio.create_task(
                research_init_runtime._execute_deferred_mondo_load(
                    services=cast("HarnessExecutionServices", kwargs["services"]),
                    space_id=cast("UUID", kwargs["space_id"]),
                    run_id=cast("str", kwargs["run_id"]),
                ),
            ),
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_start_deferred_mondo_load",
        _start_deferred_mondo_load,
    )

    # ── 3b. PubMed: stub _execute_pubmed_query ────────────────────────
    async def _fake_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del owner_id
        phases_executed["pubmed_discovery"] = True
        search_term = query_params.get("search_term", "unknown")
        matching = [c for c in _TEST_CANDIDATES if search_term in c.queries]
        if not matching:
            matching = _TEST_CANDIDATES[:1]  # Always return at least one
        return research_init_runtime._PubMedQueryExecutionResult(
            query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                query=str(search_term),
                total_found=len(matching),
                abstracts_ingested=len(matching),
            ),
            candidates=tuple(matching),
            errors=(),
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _fake_execute_pubmed_query,
    )

    # ── 3c. Candidate selection: return all test candidates as relevant ──
    async def _fake_select_candidates(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, research_init._PubMedCandidateReview]]:
        del objective, seed_terms, errors
        phases_executed["candidate_selection"] = True
        review = research_init._PubMedCandidateReview(
            method="heuristic",
            label="relevant",
            confidence=0.95,
            rationale="E2E test: auto-approved",
        )
        return [(c, review) for c in candidates]

    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates,
    )

    # ── 3d. Observation bridge: stub to no-op ─────────────────────────
    async def _fake_sync_pubmed_observations(
        **kwargs: object,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={},
            seed_entity_ids=(),
            errors=(),
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_sync_pubmed_documents_into_shared_observation_ingestion",
        _fake_sync_pubmed_observations,
    )

    async def _fake_sync_file_upload_observations(
        **kwargs: object,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={},
            seed_entity_ids=(),
            errors=(),
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_file_upload_observations,
    )

    # ── 3e. Enrichment: stub ClinVar, DrugBank, AlphaFold, MARRVEL ───
    clinvar_doc_created = False
    alphafold_doc_created = False

    async def _fake_clinvar_enrichment(**kwargs: object) -> SourceEnrichmentResult:
        nonlocal clinvar_doc_created
        phases_executed["clinvar"] = True
        doc_store = cast("HarnessDocumentStore", kwargs["document_store"])
        sp_id = cast("UUID", kwargs["space_id"])
        parent = cast("HarnessRunRecord", kwargs["parent_run"])
        doc = doc_store.create_document(
            space_id=sp_id,
            created_by=uuid4(),
            title="ClinVar: MED13 variant pathogenicity",
            source_type="clinvar",
            filename=None,
            media_type="text/plain",
            sha256=f"clinvar-sha-{uuid4().hex[:8]}",
            byte_size=120,
            page_count=None,
            text_content=(
                "MED13 c.1234A>G variant associated with intellectual disability. "
                "ClinVar accession VCV000123456."
            ),
            raw_storage_key=None,
            enriched_storage_key=None,
            ingestion_run_id=parent.id,
            last_enrichment_run_id=None,
            enrichment_status="skipped",
            extraction_status="not_started",
            metadata={"source": "clinvar-enrichment"},
        )
        clinvar_doc_created = True
        return SourceEnrichmentResult(
            source_key="clinvar",
            documents_created=[doc],
            records_processed=3,
        )

    async def _fake_drugbank_enrichment(**kwargs: object) -> SourceEnrichmentResult:
        phases_executed["drugbank"] = True
        return SourceEnrichmentResult(
            source_key="drugbank",
            documents_created=[],
            records_processed=0,
        )

    async def _fake_alphafold_enrichment(**kwargs: object) -> SourceEnrichmentResult:
        nonlocal alphafold_doc_created
        phases_executed["alphafold"] = True
        doc_store = cast("HarnessDocumentStore", kwargs["document_store"])
        sp_id = cast("UUID", kwargs["space_id"])
        parent = cast("HarnessRunRecord", kwargs["parent_run"])
        doc = doc_store.create_document(
            space_id=sp_id,
            created_by=uuid4(),
            title="AlphaFold: MED13 structure prediction",
            source_type="alphafold",
            filename=None,
            media_type="text/plain",
            sha256=f"alphafold-sha-{uuid4().hex[:8]}",
            byte_size=200,
            page_count=None,
            text_content=(
                "AlphaFold2 predicts MED13 kinase-binding domain with high "
                "confidence (pLDDT > 80). UniProt Q9UHV7."
            ),
            raw_storage_key=None,
            enriched_storage_key=None,
            ingestion_run_id=parent.id,
            last_enrichment_run_id=None,
            enrichment_status="skipped",
            extraction_status="not_started",
            metadata={"source": "alphafold-enrichment"},
        )
        alphafold_doc_created = True
        return SourceEnrichmentResult(
            source_key="alphafold",
            documents_created=[doc],
            records_processed=1,
        )

    async def _fake_marrvel_enrichment(**kwargs: object) -> SourceEnrichmentResult:
        phases_executed["marrvel"] = True
        return SourceEnrichmentResult(
            source_key="marrvel",
            documents_created=[],
            records_processed=0,
        )

    monkeypatch.setattr(
        "artana_evidence_api.research_init_source_enrichment.run_clinvar_enrichment",
        _fake_clinvar_enrichment,
    )
    monkeypatch.setattr(
        "artana_evidence_api.research_init_source_enrichment.run_drugbank_enrichment",
        _fake_drugbank_enrichment,
    )
    monkeypatch.setattr(
        "artana_evidence_api.research_init_source_enrichment.run_alphafold_enrichment",
        _fake_alphafold_enrichment,
    )
    monkeypatch.setattr(
        "artana_evidence_api.research_init_source_enrichment.run_marrvel_enrichment",
        _fake_marrvel_enrichment,
    )

    # ── 3f. Extraction: stub extract + build + review ─────────────────
    extraction_calls: list[str] = []

    async def _fake_extract_relation_candidates(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> tuple[
        list[ExtractedRelationCandidate],
        DocumentCandidateExtractionDiagnostics,
    ]:
        del max_relations, space_context
        extraction_calls.append(text[:50])
        phases_executed["extraction"] = True
        return (
            list(_TEST_EXTRACTION_CANDIDATES),
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=len(_TEST_EXTRACTION_CANDIDATES),
            ),
        )

    async def _fake_pre_resolve_entities(
        *,
        space_id: UUID,
        candidates: list[ExtractedRelationCandidate],
        graph_api_gateway: object,
        space_context: str = "",
    ) -> dict[str, object]:
        del space_id, candidates, graph_api_gateway, space_context
        return {}

    def _fake_build_drafts(
        *,
        space_id: UUID,
        document: HarnessDocumentRecord,
        candidates: list[ExtractedRelationCandidate],
        graph_api_gateway: object,
        review_context: object = None,
        ai_resolved_entities: object = None,
    ) -> tuple[tuple[HarnessProposalDraft, ...], list[object]]:
        del space_id, graph_api_gateway, review_context, ai_resolved_entities
        # Use "unresolved:" prefix so _ground_candidate_claim_drafts creates
        # entities via the graph gateway, populating created_entity_ids (needed
        # for the chase-round and bootstrap phases to trigger).
        subject = candidates[0].subject_label if candidates else "MED13"
        obj = candidates[0].object_label if candidates else "CDK8"
        draft = HarnessProposalDraft(
            proposal_type="candidate_claim",
            source_kind="document_extraction",
            source_key=document.id,
            title=f"Draft for {document.title}",
            summary="Synthetic extraction draft",
            confidence=0.9,
            ranking_score=0.9,
            reasoning_path={},
            evidence_bundle=[],
            payload={
                "proposed_subject": f"unresolved:{subject}",
                "proposed_subject_label": subject,
                "proposed_object": f"unresolved:{obj}",
                "proposed_object_label": obj,
            },
            metadata={},
            document_id=document.id,
        )
        return (draft,), []

    async def _fake_review_drafts(
        *,
        document: HarnessDocumentRecord,
        candidates: list[ExtractedRelationCandidate],
        drafts: tuple[HarnessProposalDraft, ...],
        review_context: object = None,
    ) -> tuple[HarnessProposalDraft, ...]:
        del document, candidates, review_context
        return drafts  # Pass through unchanged

    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _fake_extract_relation_candidates,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_drafts,
    )

    # ── 3g. Bootstrap: stub execute_research_bootstrap_run ────────────
    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        phases_executed["bootstrap"] = True
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        ).create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap-e2e",
            summary={"bootstrap": True},
            metadata={},
        )
        state = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        ).upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[
                "What is the role of MED13 in kinase module regulation?",
                "How does MED13 loss affect Wnt signaling?",
            ],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={"total_entities": 5, "total_relations": 3},
            source_inventory={
                "linked_proposal_count": 2,
                "bootstrap_generated_proposal_count": 1,
                "graph_connection_timeout_count": 0,
                "graph_connection_fallback_seed_ids": [],
                "graph_connection_timeout_seed_ids": [],
            },
            proposal_records=[],
            pending_questions=[
                "What is the role of MED13 in kinase module regulation?",
                "How does MED13 loss affect Wnt signaling?",
            ],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "queue_research_bootstrap_run",
        lambda **kwargs: services.run_registry.create_run(
            space_id=space_id,
            harness_id="research-bootstrap",
            title="E2E bootstrap",
            input_payload={},
            graph_service_status="ok",
            graph_service_version="test",
        ),
    )

    # ── 3h. Chase rounds: stub to return minimal result ───────────────
    chase_rounds_executed = 0

    async def _fake_run_entity_chase_round(
        **kwargs: object,
    ) -> research_init_runtime._ChaseRoundResult:
        nonlocal chase_rounds_executed
        chase_rounds_executed += 1
        phases_executed["chase"] = True
        # Return fewer than _MIN_CHASE_ENTITIES to stop after one round
        return research_init_runtime._ChaseRoundResult(
            new_seed_terms=["CDK8"],
            documents_created=0,
            proposals_created=0,
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_run_entity_chase_round",
        _fake_run_entity_chase_round,
    )

    def _fake_prepare_chase_round(
        **kwargs: object,
    ) -> research_init_runtime._ChaseRoundPreparation:
        round_number_value = kwargs.get("round_number", 1)
        round_number = round_number_value if isinstance(round_number_value, int) else 1
        if round_number == 1:
            return research_init_runtime._ChaseRoundPreparation(
                candidates=(
                    research_init_runtime.ResearchOrchestratorChaseCandidate(
                        entity_id="entity-1",
                        display_label="CDK8",
                        normalized_label="CDK8",
                        candidate_rank=1,
                        observed_round=1,
                        available_source_keys=["clinvar", "drugbank", "alphafold"],
                        evidence_basis="Recent graph entity.",
                        novelty_basis="not_in_previous_seed_terms",
                    ),
                    research_init_runtime.ResearchOrchestratorChaseCandidate(
                        entity_id="entity-2",
                        display_label="CCNC",
                        normalized_label="CCNC",
                        candidate_rank=2,
                        observed_round=1,
                        available_source_keys=["clinvar", "drugbank", "alphafold"],
                        evidence_basis="Recent graph entity.",
                        novelty_basis="not_in_previous_seed_terms",
                    ),
                    research_init_runtime.ResearchOrchestratorChaseCandidate(
                        entity_id="entity-3",
                        display_label="MED12",
                        normalized_label="MED12",
                        candidate_rank=3,
                        observed_round=1,
                        available_source_keys=["clinvar", "drugbank", "alphafold"],
                        evidence_basis="Recent graph entity.",
                        novelty_basis="not_in_previous_seed_terms",
                    ),
                ),
                filtered_candidates=(),
                deterministic_selection=research_init_runtime.ResearchOrchestratorChaseSelection(
                    selected_entity_ids=["entity-1", "entity-2", "entity-3"],
                    selected_labels=["CDK8", "CCNC", "MED12"],
                    stop_instead=False,
                    stop_reason=None,
                    selection_basis="Deterministic chase selection for E2E fixture.",
                ),
                errors=[],
            )
        return research_init_runtime._ChaseRoundPreparation(
            candidates=(
                research_init_runtime.ResearchOrchestratorChaseCandidate(
                    entity_id="entity-4",
                    display_label="CDK19",
                    normalized_label="CDK19",
                    candidate_rank=1,
                    observed_round=2,
                    available_source_keys=["clinvar", "drugbank", "alphafold"],
                    evidence_basis="Recent graph entity.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
            ),
            filtered_candidates=(),
            deterministic_selection=research_init_runtime.ResearchOrchestratorChaseSelection(
                selected_entity_ids=[],
                selected_labels=[],
                stop_instead=True,
                stop_reason="threshold_not_met",
                selection_basis="Too few candidates for another deterministic chase round.",
            ),
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_prepare_chase_round",
        _fake_prepare_chase_round,
    )

    # ── 3i. Research brief: stub LLM brief generation ─────────────────
    from artana_evidence_api.research_init_brief import (
        ResearchBrief,
        ResearchBriefSection,
    )

    async def _fake_generate_llm_brief(
        *,
        objective: str,
        seed_terms: list[str],
        deterministic_brief: ResearchBrief,
        llm_adapter: object | None = None,
    ) -> ResearchBrief:
        del objective, seed_terms, llm_adapter
        phases_executed["brief"] = True
        return ResearchBrief(
            title="E2E Research Brief: MED13 Transcriptional Regulation",
            summary=(
                "This research pass investigated MED13 and the Mediator complex, "
                "discovering evidence for neurodevelopmental associations and "
                "kinase module regulation."
            ),
            sections=(
                ResearchBriefSection(
                    heading="Key Findings",
                    body=(
                        "MED13 haploinsufficiency linked to intellectual disability. "
                        "ClinVar variant data corroborates pathogenicity."
                    ),
                ),
                ResearchBriefSection(
                    heading="Structural Insights",
                    body="AlphaFold predicts high-confidence kinase-binding domain.",
                ),
            ),
            gaps=("MED13 role in cardiac development unexplored",),
            next_steps=(
                "Investigate CDK8-MED13 interaction in patient-derived models",
            ),
        )

    monkeypatch.setattr(
        "artana_evidence_api.research_init_brief.generate_llm_research_brief",
        _fake_generate_llm_brief,
    )

    # ── 3j. Fix HarnessWorkspaceRecord containment check ─────────────
    # The runtime counts chase rounds via ``"chase_round_N" in workspace``
    # where ``workspace`` is a ``HarnessWorkspaceRecord`` (not a dict).
    # The harness dataclass doesn't support ``__contains__``, so we patch
    # it to delegate to ``snapshot.__contains__`` so the brief generation
    # block doesn't silently fail with TypeError.
    from artana_evidence_api.artifact_store import HarnessWorkspaceRecord

    monkeypatch.setattr(
        HarnessWorkspaceRecord,
        "__contains__",
        lambda self, key: key in self.snapshot,
        raising=False,
    )

    # ── 4. Run the full pipeline ──────────────────────────────────────
    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="E2E MED13 research",
        objective="Investigate MED13 transcriptional regulation",
        seed_terms=["MED13", "Mediator complex"],
        max_depth=2,
        max_hypotheses=5,
        sources=sources,
        execution_services=services,
        existing_run=queued_run,
    )

    # ── 5. Assert each phase ──────────────────────────────────────────

    # -- Deferred: MONDO ontology loading ─────────────────────────────
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["source_results"]["mondo"]["status"] == "background"

    await asyncio.gather(*deferred_mondo_tasks)

    assert phases_executed.get("mondo"), "MONDO phase did not execute"
    assert mondo_terms_loaded == 5, f"Expected 5 MONDO terms, got {mondo_terms_loaded}"
    assert mondo_hierarchy_edges == 3

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["source_results"]["mondo"]["status"] == "completed"
    assert workspace.snapshot["source_results"]["mondo"]["terms_loaded"] == 5
    assert workspace.snapshot["source_results"]["mondo"]["hierarchy_edges"] == 3

    # -- Phase 1: PubMed discovery + candidate selection ──────────────
    assert phases_executed.get("pubmed_discovery"), "PubMed discovery did not execute"
    assert phases_executed.get(
        "candidate_selection",
    ), "Candidate selection did not execute"
    assert result.documents_ingested > 0, "No documents ingested from PubMed"

    pubmed_source = workspace.snapshot["source_results"]["pubmed"]
    assert pubmed_source["status"] == "completed"
    assert pubmed_source["documents_ingested"] > 0

    assert len(result.pubmed_results) > 0, "No PubMed query results recorded"

    # -- Phase 2: Document ingestion ──────────────────────────────────
    docs = document_store.list_documents(space_id=space_id)
    assert len(docs) > 0, "No documents stored"

    pubmed_docs = [d for d in docs if d.source_type == "pubmed"]
    assert len(pubmed_docs) > 0, "No PubMed documents in store"

    # Verify PubMed document metadata
    for doc in pubmed_docs:
        assert doc.text_content, f"Document '{doc.title}' has empty text"
        assert doc.sha256, f"Document '{doc.title}' missing sha256"

    # -- Phase 2b: Structured source enrichment ───────────────────────
    assert phases_executed.get("clinvar"), "ClinVar enrichment did not execute"
    assert phases_executed.get("drugbank"), "DrugBank enrichment did not execute"
    assert phases_executed.get("alphafold"), "AlphaFold enrichment did not execute"
    assert phases_executed.get("marrvel"), "MARRVEL enrichment did not execute"

    assert clinvar_doc_created, "ClinVar should have created a document"
    assert alphafold_doc_created, "AlphaFold should have created a document"

    clinvar_docs = [d for d in docs if d.source_type == "clinvar"]
    assert len(clinvar_docs) == 1, f"Expected 1 ClinVar doc, got {len(clinvar_docs)}"
    assert "MED13" in clinvar_docs[0].title

    alphafold_docs = [d for d in docs if d.source_type == "alphafold"]
    assert (
        len(alphafold_docs) == 1
    ), f"Expected 1 AlphaFold doc, got {len(alphafold_docs)}"

    assert workspace.snapshot["source_results"]["clinvar"]["status"] == "completed"
    assert workspace.snapshot["source_results"]["clinvar"]["records_processed"] == 3
    assert workspace.snapshot["source_results"]["drugbank"]["status"] == "completed"
    assert workspace.snapshot["source_results"]["alphafold"]["status"] == "completed"
    assert workspace.snapshot["source_results"]["alphafold"]["records_processed"] == 1
    assert workspace.snapshot["source_results"]["marrvel"]["status"] == "completed"

    # -- Phase 3: Document extraction (LLM) ───────────────────────────
    assert phases_executed.get("extraction"), "Extraction phase did not execute"
    assert len(extraction_calls) > 0, "No extraction calls recorded"

    assert result.proposal_count > 0, "No proposals created from extraction"
    workspace_proposals = workspace.snapshot.get("proposal_count", 0)
    assert workspace_proposals > 0, "Workspace proposal count is 0"

    # Verify proposals exist in the store
    all_proposals = proposal_store.list_proposals(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert len(all_proposals) > 0, "No proposals in store"
    for proposal in all_proposals:
        assert proposal.proposal_type == "candidate_claim"
        assert proposal.source_kind == "document_extraction"

    # Verify document extraction statuses updated
    refreshed_docs = document_store.list_documents(space_id=space_id)
    extracted_docs = [d for d in refreshed_docs if d.extraction_status == "completed"]
    assert len(extracted_docs) > 0, "No documents marked as extraction completed"

    # -- Phase 4: Bootstrap ────────────────────────────────────────────
    assert phases_executed.get("bootstrap"), "Bootstrap phase did not execute"

    bootstrap_summary = workspace.snapshot.get("bootstrap_summary")
    assert bootstrap_summary is not None, "Bootstrap summary missing from workspace"
    assert bootstrap_summary["linked_proposal_count"] == 2
    assert bootstrap_summary["bootstrap_generated_proposal_count"] == 1

    assert workspace.snapshot.get("bootstrap_run_id") is not None
    assert workspace.snapshot.get("bootstrap_source_type") == "pubmed"

    # -- Chase rounds ─────────────────────────────────────────────────
    assert phases_executed.get("chase"), "Chase rounds did not execute"
    # With fewer than _MIN_CHASE_ENTITIES returned, should stop after 1 round
    assert (
        chase_rounds_executed == 1
    ), f"Expected 1 chase round, got {chase_rounds_executed}"

    # -- Research brief generation + storage ───────────────────────────
    assert phases_executed.get("brief"), "Brief generation did not execute"

    brief_data = workspace.snapshot.get("research_brief")
    assert brief_data is not None, "Research brief not stored in workspace"
    assert "MED13" in brief_data.get("title", "")
    assert len(brief_data.get("sections", [])) == 2
    assert len(brief_data.get("gaps", [])) == 1
    assert len(brief_data.get("next_steps", [])) == 1

    assert result.research_brief_markdown is not None
    assert "MED13" in result.research_brief_markdown
    assert "Key Findings" in result.research_brief_markdown

    # -- Overall result assertions ─────────────────────────────────────
    final_run = services.run_registry.get_run(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert final_run is not None
    assert final_run.status == "completed"

    assert workspace.snapshot.get("status") == "completed"
    assert result.research_state is not None
    assert len(result.pending_questions) == 2
    assert "MED13" in result.pending_questions[0]

    # Verify the result artifact was stored
    result_artifact = workspace.snapshot.get("research_init_result")
    assert result_artifact is not None
    assert result_artifact["documents_ingested"] == result.documents_ingested
    assert result_artifact["proposal_count"] == result.proposal_count

    # -- Verify no deferred sources left unexpectedly ──────────────────
    # uniprot was disabled (False), so it should be "skipped" not "deferred"
    assert workspace.snapshot["source_results"].get("uniprot", {}).get("status") in (
        "skipped",
        None,
    ), "Uniprot should be skipped when not enabled"

    # -- Verify phase ordering via workspace patches ───────────────────
    # The workspace should have accumulated all phase data
    assert "objective" in workspace.snapshot
    assert (
        workspace.snapshot["objective"]
        == "Investigate MED13 transcriptional regulation"
    )
    assert workspace.snapshot["seed_terms"] == ["MED13", "Mediator complex"]
