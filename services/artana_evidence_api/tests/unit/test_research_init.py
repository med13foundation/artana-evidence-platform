"""Unit tests for research-init query building and candidate gating."""

from __future__ import annotations

import asyncio
import hashlib
import time
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from artana_evidence_api import (
    full_ai_orchestrator_runtime,
    research_init_completion_runtime,
    research_init_guarded,
    research_init_helpers,
    research_init_observation_bridge,
    research_init_runtime,
    research_init_source_results,
)
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,
    HarnessWorkspaceRecord,
)
from artana_evidence_api.auth import HarnessUser, HarnessUserRole, HarnessUserStatus
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
from artana_evidence_api.document_extraction import (
    DocumentCandidateExtractionDiagnostics,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.identity.local_gateway import LocalIdentityGateway
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapClaimCurationSummary,
    ResearchBootstrapExecutionResult,
)
from artana_evidence_api.research_init.source_caps import ResearchInitSourceCaps
from artana_evidence_api.research_init_models import _ChaseRoundPreparation
from artana_evidence_api.research_init_source_enrichment_common import (
    SourceEnrichmentResult,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.routers import research_init
from artana_evidence_api.routers.documents import (
    normalize_text_document,
    sha256_hex,
)
from artana_evidence_api.routers.health import ProcessHealth
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.source_document_bridges import (
    DocumentExtractionStatus,
    DocumentFormat,
    SourceDocument,
    SqlAlchemySourceDocumentRepository,
)
from artana_evidence_api.source_registry import (
    SourceCapability,
    research_plan_source_keys,
)
from artana_evidence_api.types.graph_contracts import (
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimResponse,
)
from fastapi import HTTPException


def test_build_pubmed_queries_preserves_objective_anchor_terms() -> None:
    objective = (
        "create a research cohort based on nodal biology of underlying mechanism "
        "of biology shared with the mediator complex including med13 and "
        "neurodevelopmental biology"
    )

    queries = research_init._build_pubmed_queries(objective, [])

    assert queries
    search_terms = [query["search_term"] for query in queries]
    assert any("med13" in term.casefold() for term in search_terms)
    assert any("neurodevelopmental" in term.casefold() for term in search_terms)
    assert any("mediator" in term.casefold() for term in search_terms)
    assert "create" not in queries[0]["search_term"].casefold()
    assert "cohort" not in queries[0]["search_term"].casefold()
    assert "biology" not in queries[0]["search_term"].casefold()
    assert "underlying" not in queries[0]["search_term"].casefold()


def test_build_pubmed_queries_only_uses_gene_symbol_for_gene_like_seed_terms() -> None:
    queries = research_init._build_pubmed_queries(
        "study mediator complex function in neurodevelopment",
        ["MED13", "mediator complex", "neurodevelopment"],
    )

    query_map = {
        query["search_term"]: query.get("gene_symbol")
        for query in queries
        if query["search_term"] in {"MED13", "mediator complex", "neurodevelopment"}
    }

    assert query_map["MED13"] == "MED13"
    assert query_map["mediator complex"] is None
    assert query_map["neurodevelopment"] is None


def test_build_pubmed_queries_skips_generic_focus_seed_terms() -> None:
    queries = research_init._build_pubmed_queries(
        "Parkinson disease treatment discovery",
        ["Parkinson disease", "treatment evidence", "new hypotheses"],
    )

    search_terms = [query["search_term"] for query in queries]

    assert "Parkinson disease" in search_terms
    assert "treatment evidence" not in search_terms
    assert "new hypotheses" not in search_terms


def test_build_pubmed_queries_skips_generic_single_term_seed_terms_and_counts() -> None:
    objective = (
        "Five years ago, I wrote a piece in Cell about how my breast "
        "angiosarcoma diagnosis redefined my life. We have now added 157 "
        "transcriptomes alongside clinical and molecular data from 274 "
        "angiosarcoma patients, creating an open resource for an ultra-rare "
        "cancer."
    )
    queries = research_init._build_pubmed_queries(
        objective,
        [
            "angiosarcoma",
            "breast angiosarcoma",
            "Broad Institute",
            "transcriptome",
            "Cell",
            "ultra-rare cancer",
        ],
    )

    search_terms = [query["search_term"] for query in queries]

    assert "transcriptome" not in search_terms
    assert "Cell" not in search_terms
    assert all("157" not in term for term in search_terms)
    assert all("274" not in term for term in search_terms)
    assert any("angiosarcoma" in term.casefold() for term in search_terms)


def test_build_scope_refinement_questions_uses_specific_bio_anchor() -> None:
    questions = research_init._build_scope_refinement_questions(
        objective="gene therapy ideas",
        seed_terms=["Parkinson disease", "LRRK2", "treatment evidence"],
    )

    assert len(questions) == 1
    assert "Parkinson disease" in questions[0]
    assert "PubMed" not in questions[0], "Message should be source-neutral"
    assert "research pass" in questions[0]


def test_review_candidate_with_heuristics_marks_relevant_and_off_target_papers() -> (
    None
):
    objective = (
        "define shared biology between MED13, the mediator complex, and "
        "neurodevelopmental disorders"
    )
    seed_terms = ["MED13", "mediator complex", "neurodevelopmental disorders"]

    relevant_candidate = research_init._PubMedCandidate(
        title="MED13 coordinates mediator complex programs in neurodevelopment",
        text=(
            "MED13 regulates mediator complex activity during cortical "
            "neurodevelopment."
        ),
        queries=["MED13 mediator complex neurodevelopment"],
        pmid="12345",
    )
    off_target_candidate = research_init._PubMedCandidate(
        title="PTI-ETI crosstalk: an integrative view of plant immunity.",
        text=(
            "This review discusses recent advances in our understanding of the "
            "relationship between the two layers of plant innate immunity."
        ),
        queries=["mediator complex MED13 neurodevelopment"],
        pmid="67890",
    )

    relevant_review = research_init._review_candidate_with_heuristics(
        relevant_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )
    off_target_review = research_init._review_candidate_with_heuristics(
        off_target_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )

    assert relevant_review.label == "relevant"
    assert off_target_review.label == "non_relevant"


def test_review_candidate_with_heuristics_prefers_focused_topic_matches() -> None:
    objective = "COVID-19 mechanism and host-response research"
    seed_terms = [
        "COVID-19",
        "SARS-CoV-2",
        "host response",
        "immune response",
        "innate immunity",
    ]

    broad_candidate = research_init._PubMedCandidate(
        title="Rapid diagnostic testing for COVID-19",
        text="A review of diagnostic methods used during the COVID-19 pandemic.",
        queries=["COVID-19"],
        pmid="30001",
    )
    focused_candidate = research_init._PubMedCandidate(
        title="Innate immune response programs in severe COVID-19",
        text=(
            "This study characterizes host response and innate immunity changes "
            "in severe SARS-CoV-2 infection."
        ),
        queries=["COVID-19 SARS-CoV-2 host response", "innate immunity"],
        pmid="30002",
    )

    broad_review = research_init._review_candidate_with_heuristics(
        broad_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )
    focused_review = research_init._review_candidate_with_heuristics(
        focused_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )

    assert focused_review.focus_signal_count > broad_review.focus_signal_count
    assert focused_review.query_specificity > broad_review.query_specificity


def test_review_candidate_with_heuristics_rejects_generic_transcriptome_match() -> None:
    objective = (
        "Build an angiosarcoma research resource with transcriptomic and "
        "clinical data for breast angiosarcoma."
    )
    seed_terms = [
        "angiosarcoma",
        "breast angiosarcoma",
        "transcriptome",
        "Cell",
        "ultra-rare cancer",
    ]

    off_target_candidate = research_init._PubMedCandidate(
        title=(
            "High-definition spatial transcriptomic profiling of immune cell "
            "populations in colorectal cancer."
        ),
        text=(
            "Spatial transcriptomics reveals immune populations across "
            "colorectal tumors."
        ),
        queries=["transcriptome"],
        pmid="60001",
    )
    focused_candidate = research_init._PubMedCandidate(
        title=(
            "Transcriptomic profiling defines molecular subtypes in breast "
            "angiosarcoma."
        ),
        text=(
            "This study profiles angiosarcoma tumors and identifies distinct "
            "breast angiosarcoma programs."
        ),
        queries=["breast angiosarcoma transcriptomics"],
        pmid="60002",
    )

    off_target_review = research_init._review_candidate_with_heuristics(
        off_target_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )
    focused_review = research_init._review_candidate_with_heuristics(
        focused_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )

    assert off_target_review.label == "non_relevant"
    assert focused_review.label == "relevant"


def test_review_candidate_with_heuristics_requires_core_anchor_signal() -> None:
    objective = (
        "Build an angiosarcoma research resource with transcriptomic and "
        "clinical data for breast angiosarcoma."
    )
    seed_terms = [
        "angiosarcoma",
        "breast angiosarcoma",
        "transcriptome",
        "Cell",
        "ultra-rare cancer",
    ]

    off_target_candidate = research_init._PubMedCandidate(
        title="Transcriptomic profiling of breast cancer immune microenvironments.",
        text=(
            "Breast tumors show transcriptomic immune programs in cancer progression."
        ),
        queries=["breast angiosarcoma transcriptomics"],
        pmid="70001",
    )
    focused_candidate = research_init._PubMedCandidate(
        title=(
            "Transcriptomic profiling defines molecular subtypes in breast "
            "angiosarcoma."
        ),
        text=(
            "This study profiles angiosarcoma tumors and identifies distinct "
            "breast angiosarcoma programs."
        ),
        queries=["breast angiosarcoma transcriptomics"],
        pmid="70002",
    )

    off_target_review = research_init._review_candidate_with_heuristics(
        off_target_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )
    focused_review = research_init._review_candidate_with_heuristics(
        focused_candidate,
        objective=objective,
        seed_terms=seed_terms,
    )

    assert off_target_review.label == "non_relevant"
    assert "core_signals=none" in off_target_review.rationale
    assert "requires_core_signal=yes" in off_target_review.rationale
    assert focused_review.label == "relevant"
    assert "core_signals=angiosarcoma,breast angiosarcoma" in focused_review.rationale


def test_shortlist_candidates_for_llm_review_keeps_focused_query_families() -> None:
    broad_candidates = [
        (
            research_init._PubMedCandidate(
                title=f"COVID-19 general paper {index}",
                text="General COVID-19 coverage.",
                queries=["COVID-19"],
                pmid=str(40000 + index),
            ),
            research_init._PubMedCandidateReview(
                method="heuristic",
                label="relevant",
                confidence=0.55,
                rationale="broad",
                signal_count=1,
                focus_signal_count=0,
                query_specificity=3,
            ),
        )
        for index in range(11)
    ]
    focused_candidates = [
        (
            research_init._PubMedCandidate(
                title=f"COVID-19 host response paper {index}",
                text="Host response and innate immunity in SARS-CoV-2 infection.",
                queries=["COVID-19 SARS-CoV-2 host response", "innate immunity"],
                pmid=str(41000 + index),
            ),
            research_init._PubMedCandidateReview(
                method="heuristic",
                label="relevant",
                confidence=0.9,
                rationale="focused",
                signal_count=4,
                focus_signal_count=3,
                query_specificity=12,
            ),
        )
        for index in range(2)
    ]

    shortlisted = research_init._shortlist_candidates_for_llm_review(
        broad_candidates + focused_candidates,
    )

    shortlisted_pmids = {candidate.pmid for candidate, _review in shortlisted}

    assert len(shortlisted) == 12
    assert {"41000", "41001"}.issubset(shortlisted_pmids)


@pytest.mark.asyncio
async def test_select_candidates_for_ingestion_falls_back_to_heuristics_on_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = research_init._PubMedCandidate(
        title="MED13 coordinates mediator complex programs in neurodevelopment",
        text="MED13 and the mediator complex shape neurodevelopmental biology.",
        queries=["MED13 mediator complex neurodevelopment"],
        pmid="12345",
    )
    errors: list[str] = []

    async def _raise_llm_error(
        candidate: research_init._PubMedCandidate,
        *,
        objective: str,
    ) -> research_init._PubMedCandidateReview:
        del candidate, objective
        raise RuntimeError("synthetic llm outage")

    monkeypatch.setattr(
        research_init_helpers, "_review_candidate_with_llm", _raise_llm_error
    )

    selected = await research_init._select_candidates_for_ingestion(
        [candidate],
        objective=(
            "define shared biology between MED13, the mediator complex, and "
            "neurodevelopmental disorders"
        ),
        seed_terms=["MED13", "mediator complex"],
        errors=errors,
    )

    assert len(selected) == 1
    assert selected[0][0].title == candidate.title
    assert selected[0][1].method == "heuristic"
    assert errors == [
        "PubMed relevance review fell back to heuristics: synthetic llm outage",
    ]


@pytest.mark.asyncio
async def test_select_candidates_for_ingestion_falls_back_to_heuristics_on_llm_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = research_init._PubMedCandidate(
        title="MED13 coordinates mediator complex programs in neurodevelopment",
        text="MED13 and the mediator complex shape neurodevelopmental biology.",
        queries=["MED13 mediator complex neurodevelopment"],
        pmid="12345",
    )
    errors: list[str] = []

    async def _slow_llm_review(
        candidate: research_init._PubMedCandidate,
        *,
        objective: str,
    ) -> research_init._PubMedCandidateReview:
        del candidate, objective
        await asyncio.sleep(0.05)
        return research_init._PubMedCandidateReview(
            method="llm",
            label="relevant",
            confidence=0.9,
            rationale="slow success",
        )

    monkeypatch.setattr(
        research_init_helpers, "_review_candidate_with_llm", _slow_llm_review
    )
    monkeypatch.setattr(research_init_helpers, "_LLM_RELEVANCE_TIMEOUT_SECONDS", 0.01)

    selected = await research_init._select_candidates_for_ingestion(
        [candidate],
        objective=(
            "define shared biology between MED13, the mediator complex, and "
            "neurodevelopmental disorders"
        ),
        seed_terms=["MED13", "mediator complex"],
        errors=errors,
    )

    assert len(selected) == 1
    assert selected[0][0].title == candidate.title
    assert selected[0][1].method == "heuristic"
    assert errors == [
        "PubMed relevance review fell back to heuristics: timed out after 0.0s",
    ]


@pytest.mark.asyncio
async def test_select_candidates_for_ingestion_keeps_llm_non_relevant_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = research_init._PubMedCandidate(
        title="MED13 coordinates mediator complex programs in neurodevelopment",
        text="MED13 and the mediator complex shape neurodevelopmental biology.",
        queries=["MED13 mediator complex neurodevelopment"],
        pmid="12345",
    )

    async def _reject_with_llm(
        candidate: research_init._PubMedCandidate,
        *,
        objective: str,
    ) -> research_init._PubMedCandidateReview:
        del candidate, objective
        return research_init._PubMedCandidateReview(
            method="llm",
            label="non_relevant",
            confidence=0.91,
            rationale="not aligned enough",
        )

    monkeypatch.setattr(
        research_init_helpers, "_review_candidate_with_llm", _reject_with_llm
    )

    selected = await research_init._select_candidates_for_ingestion(
        [candidate],
        objective=(
            "define shared biology between MED13, the mediator complex, and "
            "neurodevelopmental disorders"
        ),
        seed_terms=["MED13", "mediator complex"],
        errors=[],
    )

    assert selected == []


@pytest.mark.asyncio
async def test_select_candidates_for_ingestion_reviews_llm_shortlist_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        research_init._PubMedCandidate(
            title=f"MED13 paper {index}",
            text="MED13 and the mediator complex shape neurodevelopmental biology.",
            queries=["MED13 mediator complex neurodevelopment"],
            pmid=str(12000 + index),
        )
        for index in range(3)
    ]
    current_concurrency = 0
    max_concurrency = 0

    async def _track_concurrency(
        candidate: research_init._PubMedCandidate,
        *,
        objective: str,
    ) -> research_init._PubMedCandidateReview:
        del candidate, objective
        nonlocal current_concurrency, max_concurrency
        current_concurrency += 1
        max_concurrency = max(max_concurrency, current_concurrency)
        try:
            await asyncio.sleep(0.01)
            return research_init._PubMedCandidateReview(
                method="llm",
                label="relevant",
                confidence=0.93,
                rationale="aligned",
            )
        finally:
            current_concurrency -= 1

    monkeypatch.setattr(
        research_init_helpers, "_review_candidate_with_llm", _track_concurrency
    )

    selected = await research_init._select_candidates_for_ingestion(
        candidates,
        objective=(
            "define shared biology between MED13, the mediator complex, and "
            "neurodevelopmental disorders"
        ),
        seed_terms=["MED13", "mediator complex"],
        errors=[],
    )

    assert len(selected) == len(candidates)
    assert max_concurrency > 1


def test_resolve_research_init_sources_uses_saved_space_settings_when_request_missing() -> (
    None
):
    resolved = research_init._resolve_research_init_sources(
        request_sources=None,
        space_settings={
            "sources": {
                "pubmed": False,
                "marrvel": True,
                "pdf": False,
                "text": False,
            },
        },
    )

    # Space settings override defaults; unmentioned keys keep their defaults
    assert resolved["pubmed"] is False
    assert resolved["marrvel"] is True
    assert resolved["pdf"] is False
    assert resolved["text"] is False


def test_prioritize_marrvel_gene_labels_promotes_objective_match_and_filters_noise() -> (
    None
):
    prioritized = research_init._prioritize_marrvel_gene_labels(
        ["ADHD", "BRCA1", "ASD", "MED13", "TP53"],
        objective="Investigate MED13 syndrome in neurodevelopment",
        limit=3,
    )

    assert prioritized == ["MED13", "BRCA1", "TP53"]


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

    def create_claim(
        self,
        *,
        space_id: UUID,
        request: KernelRelationClaimCreateRequest,
    ) -> KernelRelationClaimResponse:
        from datetime import datetime

        del space_id
        now = datetime.now(tz=UTC)
        return KernelRelationClaimResponse(
            id=uuid4(),
            research_space_id=uuid4(),
            source_type="GENE",
            relation_type=request.relation_type,
            target_type="DISEASE",
            source_label=None,
            target_label=None,
            confidence=request.derived_confidence,
            validation_state="unvalidated",
            validation_reason=None,
            persistability="persistable",
            claim_status="unresolved",
            polarity="positive",
            claim_text=request.claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata={},
            triaged_by=None,
            triaged_at=None,
            created_at=now,
            updated_at=now,
        )

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
    document_binary_store: HarnessDocumentBinaryStore | None = None,
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
        document_binary_store=document_binary_store,
    )


class _WorkspaceReadTimeoutArtifactStore(HarnessArtifactStore):
    def get_workspace(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessWorkspaceRecord | None:
        del space_id, run_id
        raise TimeoutError


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


def test_set_progress_observer_uses_empty_workspace_when_hydration_times_out() -> None:
    services = replace(
        _build_execution_services(),
        artifact_store=_WorkspaceReadTimeoutArtifactStore(),
    )
    space_id = uuid4()
    run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find BRCA1 evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    class _ProgressObserver:
        def __init__(self) -> None:
            self.workspace_snapshots: list[dict[str, object]] = []

        def on_progress(
            self,
            *,
            phase: str,
            message: str,
            progress_percent: float,
            completed_steps: int,
            metadata: dict[str, object],
            workspace_snapshot: dict[str, object],
        ) -> None:
            del phase, message, progress_percent, completed_steps, metadata
            self.workspace_snapshots.append(dict(workspace_snapshot))

    observer = _ProgressObserver()

    research_init_runtime._set_progress(
        services=services,
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 1/12 selected documents.",
        progress_percent=0.61,
        completed_steps=3,
        metadata={"document_extraction_completed_count": 1},
        progress_observer=cast(
            "research_init_runtime.ResearchInitProgressObserver",
            observer,
        ),
    )

    assert observer.workspace_snapshots == [{}]


def test_run_marrvel_enrichment_is_retired_and_returns_zero() -> None:
    """Direct MARRVEL enrichment is retired; proposals come from extraction pipeline."""
    created = research_init._run_marrvel_enrichment(
        space_id=uuid4(),
        objective="Investigate MED13 syndrome",
        graph_api_gateway=_StubGraphApiGateway(),
        proposal_store=None,
        run_id=None,
    )
    assert created == 0


@pytest.mark.asyncio
async def test_create_research_init_uses_saved_sources_for_marrvel_only_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Saved Sources",
        description="Persisted source settings",
        settings={
            "sources": {
                "pubmed": False,
                "marrvel": True,
                "pdf": False,
                "text": False,
            },
        },
    )
    run_registry = HarnessRunRegistry()
    proposal_store = HarnessProposalStore()
    artifact_store = HarnessArtifactStore()

    def _unexpected_pubmed_queries(
        objective: str,
        seed_terms: list[str],
    ) -> list[dict[str, str | None]]:
        del objective, seed_terms
        raise AssertionError(
            "PubMed queries should not be built for saved MARRVEL-only spaces",
        )

    monkeypatch.setattr(
        research_init,
        "_build_pubmed_queries",
        _unexpected_pubmed_queries,
    )
    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=_build_execution_services(),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    stored_runs = run_registry.list_runs(space_id=space_record.id)
    stored_proposals = proposal_store.list_proposals(space_id=space_record.id)

    assert response.run.harness_id == "full-ai-orchestrator"
    assert response.run.status == "queued"
    assert response.poll_url == (
        f"/v1/spaces/{space_record.id}/runs/{response.run.id}/progress"
    )
    assert response.proposal_count == 0
    assert response.pubmed_results == []
    assert response.pending_questions == []
    assert response.errors == []
    assert len(stored_runs) == 1
    assert response.run.id == stored_runs[0].id
    assert stored_runs[0].input_payload["planner_mode"] == "guarded"
    assert stored_runs[0].input_payload["guarded_rollout_profile"] == (
        "guarded_source_chase"
    )
    assert stored_runs[0].input_payload["guarded_rollout_profile_source"] == "default"
    saved_sources = stored_runs[0].input_payload["sources"]
    assert saved_sources["pubmed"] is False
    assert saved_sources["marrvel"] is True
    assert saved_sources["pdf"] is False
    assert saved_sources["text"] is False
    assert len(stored_proposals) == 0
    assert (
        artifact_store.get_workspace(
            space_id=space_record.id,
            run_id=response.run.id,
        )
        is not None
    )


@pytest.mark.asyncio
async def test_create_research_init_shadow_mode_routes_to_full_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Shadow Orchestrator",
        description="Request-level orchestrator opt-in",
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            sources={"pubmed": False, "marrvel": True, "pdf": False, "text": False},
            orchestration_mode="full_ai_shadow",
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=_build_execution_services(),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    stored_runs = run_registry.list_runs(space_id=space_record.id)

    assert len(stored_runs) == 1
    assert response.run.harness_id == "full-ai-orchestrator"
    assert response.run.id == stored_runs[0].id
    assert stored_runs[0].input_payload["planner_mode"] == "shadow"
    assert stored_runs[0].input_payload["sources"]["pubmed"] is False
    workspace = artifact_store.get_workspace(
        space_id=space_record.id,
        run_id=response.run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["planner_execution_mode"] == "shadow"


@pytest.mark.asyncio
async def test_create_research_init_saved_guarded_mode_routes_to_full_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Guarded Orchestrator",
        description="Space-level orchestrator opt-in",
        settings={
            "research_orchestration_mode": "full_ai_guarded",
            "full_ai_guarded_rollout_profile": "guarded_chase_only",
            "sources": {
                "pubmed": False,
                "marrvel": True,
                "pdf": False,
                "text": False,
            },
        },
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=_build_execution_services(),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    stored_runs = run_registry.list_runs(space_id=space_record.id)

    assert len(stored_runs) == 1
    assert response.run.harness_id == "full-ai-orchestrator"
    assert stored_runs[0].input_payload["planner_mode"] == "guarded"
    assert stored_runs[0].input_payload["guarded_rollout_profile"] == (
        "guarded_chase_only"
    )
    assert stored_runs[0].input_payload["guarded_rollout_profile_source"] == (
        "space_setting"
    )
    assert stored_runs[0].input_payload["sources"]["pubmed"] is False
    workspace = artifact_store.get_workspace(
        space_id=space_record.id,
        run_id=response.run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["planner_execution_mode"] == "guarded"
    assert workspace.snapshot["guarded_rollout_profile"] == "guarded_chase_only"


@pytest.mark.asyncio
async def test_create_research_init_guarded_profile_request_overrides_space_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Guarded Orchestrator",
        description="Space-level orchestrator opt-in",
        settings={
            "research_orchestration_mode": "full_ai_guarded",
            "full_ai_guarded_rollout_profile": "guarded_chase_only",
        },
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            guarded_rollout_profile="guarded_source_chase",
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=_build_execution_services(),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    stored_runs = run_registry.list_runs(space_id=space_record.id)
    workspace = artifact_store.get_workspace(
        space_id=space_record.id,
        run_id=response.run.id,
    )

    assert len(stored_runs) == 1
    assert stored_runs[0].input_payload["guarded_rollout_profile"] == (
        "guarded_source_chase"
    )
    assert stored_runs[0].input_payload["guarded_rollout_profile_source"] == "request"
    assert workspace is not None
    assert workspace.snapshot["guarded_rollout_profile"] == "guarded_source_chase"


@pytest.mark.asyncio
async def test_create_research_init_request_deterministic_overrides_saved_guarded_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Deterministic Override",
        description="Request-level deterministic opt-out",
        settings={
            "research_orchestration_mode": "full_ai_guarded",
            "sources": {
                "pubmed": False,
                "marrvel": True,
                "pdf": False,
                "text": False,
            },
        },
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            orchestration_mode="deterministic",
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=_build_execution_services(),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    stored_runs = run_registry.list_runs(space_id=space_record.id)

    assert len(stored_runs) == 1
    assert response.run.harness_id == "research-init"
    assert stored_runs[0].harness_id == "research-init"
    assert "planner_mode" not in stored_runs[0].input_payload


@pytest.mark.asyncio
async def test_create_research_init_captures_pubmed_replay_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Replay Bundle",
        description="Persist replay bundle before worker handoff",
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=(),
        selection_errors=("captured in research-init router",),
    )

    async def _fake_prepare_pubmed_replay_bundle(
        *,
        objective: str,
        seed_terms: list[str],
        source_caps: ResearchInitSourceCaps,
    ) -> research_init_runtime.ResearchInitPubMedReplayBundle:
        assert objective == "Investigate MED13 syndrome"
        assert seed_terms == ["MED13"]
        assert source_caps.pubmed_max_results_per_query == 10
        return replay_bundle

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init,
        "prepare_pubmed_replay_bundle",
        _fake_prepare_pubmed_replay_bundle,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            sources={"pubmed": True, "marrvel": False, "pdf": False, "text": False},
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=cast(
            "HarnessExecutionServices",
            type("_StubExecutionServices", (), {"runtime": object()})(),
        ),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    workspace = artifact_store.get_workspace(
        space_id=space_record.id,
        run_id=response.run.id,
    )
    assert workspace is not None
    replay_artifact = artifact_store.get_artifact(
        space_id=space_record.id,
        run_id=response.run.id,
        artifact_key=cast("str", workspace.snapshot["pubmed_replay_bundle_key"]),
    )

    assert replay_artifact is not None
    assert replay_artifact.content["selection_errors"] == [
        "captured in research-init router",
    ]
    assert (
        run_registry.list_runs(space_id=space_record.id)[0].input_payload[
            "source_caps"
        ]["pubmed_max_results_per_query"]
        == 10
    )


@pytest.mark.asyncio
async def test_create_research_init_captures_source_cap_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Source Caps",
        description="Persist source cap overrides before worker handoff",
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    captured_caps: list[ResearchInitSourceCaps] = []
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=(),
        selection_errors=(),
    )

    async def _fake_prepare_pubmed_replay_bundle(
        *,
        objective: str,
        seed_terms: list[str],
        source_caps: ResearchInitSourceCaps,
    ) -> research_init_runtime.ResearchInitPubMedReplayBundle:
        del objective, seed_terms
        captured_caps.append(source_caps)
        return replay_bundle

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init,
        "prepare_pubmed_replay_bundle",
        _fake_prepare_pubmed_replay_bundle,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            source_caps={
                "pubmed_max_results_per_query": 42,
                "pubmed_max_previews_per_query": 9,
                "max_terms_per_source": 3,
                "clinvar_max_results": 7,
            },
            sources={"pubmed": True, "marrvel": False, "pdf": False, "text": False},
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=cast(
            "HarnessExecutionServices",
            type("_StubExecutionServices", (), {"runtime": object()})(),
        ),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    assert captured_caps == [
        ResearchInitSourceCaps(
            pubmed_max_results_per_query=42,
            pubmed_max_previews_per_query=9,
            max_terms_per_source=3,
            clinvar_max_results=7,
        ),
    ]
    stored_run = run_registry.list_runs(space_id=space_record.id)[0]
    assert stored_run.input_payload["source_caps"]["pubmed_max_results_per_query"] == 42
    assert stored_run.input_payload["source_caps"]["drugbank_max_results"] == 20
    workspace = artifact_store.get_workspace(
        space_id=space_record.id,
        run_id=response.run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["source_caps"]["max_terms_per_source"] == 3


@pytest.mark.asyncio
async def test_create_research_init_uses_supplied_pubmed_replay_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Supplied Replay Bundle",
        description="Persist supplied replay bundle before worker handoff",
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    supplied_bundle = {
        "version": 1,
        "query_executions": [
            {
                "query_result": {
                    "query": "MED13",
                    "total_found": 1,
                    "abstracts_ingested": 1,
                },
                "candidates": [
                    {
                        "title": "Shared replay paper",
                        "text": "Shared replay evidence",
                        "queries": ["MED13"],
                        "pmid": "pmid-shared",
                        "doi": None,
                        "pmc_id": None,
                        "journal": "Synthetic Journal",
                    },
                ],
                "errors": [],
            },
        ],
        "selected_candidates": [
            {
                "candidate": {
                    "title": "Shared replay paper",
                    "text": "Shared replay evidence",
                    "queries": ["MED13"],
                    "pmid": "pmid-shared",
                    "doi": None,
                    "pmc_id": None,
                    "journal": "Synthetic Journal",
                },
                "review": {
                    "method": "heuristic",
                    "label": "relevant",
                    "confidence": 0.91,
                    "rationale": "Reuse the supplied bundle.",
                    "agent_run_id": None,
                    "signal_count": 0,
                    "focus_signal_count": 0,
                    "query_specificity": 0,
                },
            },
        ],
        "selection_errors": ["shared replay bundle"],
    }

    async def _fail_prepare_pubmed_replay_bundle(**_kwargs):
        raise AssertionError("prepare_pubmed_replay_bundle should not be called")

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        full_ai_orchestrator_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init,
        "prepare_pubmed_replay_bundle",
        _fail_prepare_pubmed_replay_bundle,
    )

    response = await research_init.create_research_init(
        space_id=UUID(space_record.id),
        request=research_init.ResearchInitRequest(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            sources={"pubmed": True, "marrvel": False, "pdf": False, "text": False},
            pubmed_replay_bundle=supplied_bundle,
        ),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=_StubGraphApiGateway(),
        execution_services=cast(
            "HarnessExecutionServices",
            type("_StubExecutionServices", (), {"runtime": object()})(),
        ),
        current_user=HarnessUser(
            id=owner_id,
            email="owner@example.com",
            username="owner",
            full_name="Owner",
            role=HarnessUserRole.RESEARCHER,
            status=HarnessUserStatus.ACTIVE,
        ),
        identity_gateway=LocalIdentityGateway(research_space_store=space_store),
    )

    workspace = artifact_store.get_workspace(
        space_id=space_record.id,
        run_id=response.run.id,
    )
    assert workspace is not None
    replay_artifact = artifact_store.get_artifact(
        space_id=space_record.id,
        run_id=response.run.id,
        artifact_key=cast("str", workspace.snapshot["pubmed_replay_bundle_key"]),
    )

    assert replay_artifact is not None
    assert replay_artifact.content["selection_errors"] == ["shared replay bundle"]
    assert replay_artifact.content["selected_candidates"][0]["candidate"]["title"] == (
        "Shared replay paper"
    )


@pytest.mark.asyncio
async def test_create_research_init_rejects_invalid_pubmed_replay_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Invalid Replay Bundle",
        description="Reject invalid replay bundle payloads",
    )
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()

    monkeypatch.setattr(research_init, "_require_worker_ready", lambda: None)
    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await research_init.create_research_init(
            space_id=UUID(space_record.id),
            request=research_init.ResearchInitRequest(
                objective="Investigate MED13 syndrome",
                seed_terms=["MED13"],
                sources={"pubmed": True},
                pubmed_replay_bundle={"version": "invalid"},
            ),
            run_registry=run_registry,
            artifact_store=artifact_store,
            graph_api_gateway=_StubGraphApiGateway(),
            execution_services=cast(
                "HarnessExecutionServices",
                type("_StubExecutionServices", (), {"runtime": object()})(),
            ),
            current_user=HarnessUser(
                id=owner_id,
                email="owner@example.com",
                username="owner",
                full_name="Owner",
                role=HarnessUserRole.RESEARCHER,
                status=HarnessUserStatus.ACTIVE,
            ),
            identity_gateway=LocalIdentityGateway(research_space_store=space_store),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid pubmed_replay_bundle payload."
    assert run_registry.list_runs(space_id=space_record.id) == []


def test_require_worker_ready_logs_dead_worker_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(
        research_init_helpers,
        "read_heartbeat",
        lambda *_args, **_kwargs: ProcessHealth(
            status="degraded",
            last_tick="36s ago",
            pid=681,
            detail={
                "failure_reason": "process_not_running",
                "heartbeat_path": "logs/artana-evidence-api-worker-heartbeat.json",
                "heartbeat_age_seconds": 36,
                "process_alive": False,
            },
        ),
    )

    with pytest.raises(HTTPException) as exc_info, caplog.at_level("WARNING"):
        research_init._require_worker_ready()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "Research init worker unavailable. "
        "Last heartbeat: 36s ago. "
        "Worker process is not running."
    )
    assert any(
        record.message == "research-init worker readiness check failed"
        and getattr(record, "heartbeat_status", None) == "degraded"
        and getattr(record, "heartbeat_failure_reason", None) == "process_not_running"
        and getattr(record, "heartbeat_pid", None) == 681
        for record in caplog.records
    )


def test_require_worker_ready_reports_loop_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        research_init_helpers,
        "read_heartbeat",
        lambda *_args, **_kwargs: ProcessHealth(
            status="degraded",
            last_tick="4s ago",
            pid=681,
            detail={
                "failure_reason": "loop_error",
                "error_type": "RuntimeError",
                "error": "Synthetic worker tick failure.",
                "process_alive": True,
            },
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        research_init._require_worker_ready()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "Research init worker unavailable. "
        "Last heartbeat: 4s ago. "
        "Worker loop is erroring."
    )


@pytest.mark.asyncio
async def test_create_research_init_preserves_worker_ready_http_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = uuid4()
    space_store = HarnessResearchSpaceStore()
    space_record = space_store.create_space(
        owner_id=owner_id,
        name="Worker Readiness",
        description="Readiness passthrough",
    )
    monkeypatch.setattr(
        research_init,
        "_require_worker_ready",
        lambda: (_ for _ in ()).throw(
            HTTPException(
                status_code=503,
                detail="Research init worker unavailable. Last heartbeat: 36s ago.",
            ),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await research_init.create_research_init(
            space_id=UUID(space_record.id),
            request=research_init.ResearchInitRequest(
                objective="Investigate MED13 syndrome",
            ),
            run_registry=HarnessRunRegistry(),
            artifact_store=HarnessArtifactStore(),
            graph_api_gateway=_StubGraphApiGateway(),
            execution_services=cast(
                "HarnessExecutionServices",
                type("_StubExecutionServices", (), {"runtime": object()})(),
            ),
            current_user=HarnessUser(
                id=owner_id,
                email="owner@example.com",
                username="owner",
                full_name="Owner",
                role=HarnessUserRole.RESEARCHER,
                status=HarnessUserStatus.ACTIVE,
            ),
            identity_gateway=LocalIdentityGateway(research_space_store=space_store),
        )

    assert exc_info.value.status_code == 503
    assert (
        exc_info.value.detail
        == "Research init worker unavailable. Last heartbeat: 36s ago."
    )


@pytest.mark.asyncio
async def test_execute_research_init_processes_existing_text_documents_without_sweeping_legacy_pubmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    text_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Research note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="text-sha",
        byte_size=12,
        page_count=None,
        text_content="MED13 supports developmental phenotypes.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )
    legacy_pubmed_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Legacy PubMed abstract",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="legacy-sha",
        byte_size=18,
        page_count=None,
        text_content="Legacy ingested PubMed abstract.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="legacy-pubmed-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "pubmed": {"pmid": "12345"},
        },
    )

    captured_bootstrap_source_type: list[str] = []
    captured_marrvel_enabled: list[bool] = []
    bridged_document_ids: list[str] = []

    async def _fake_sync_uploaded_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id
        del pipeline_run_id
        bridged_document_ids.extend(document.id for document in documents)
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=1,
                    entities_created=1,
                    seed_entity_ids=("11111111-1111-1111-1111-111111111111",),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=("11111111-1111-1111-1111-111111111111",),
            errors=(),
        )

    def _unexpected_pubmed_queries(
        objective: str,
        seed_terms: list[str],
    ) -> list[dict[str, str | None]]:
        del objective, seed_terms
        raise AssertionError("PubMed queries should not be built for text-only runs")

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                _build_extraction_draft(
                    document_id=document.id,
                    title=document.title,
                ),
            ),
            [],
        )

    async def _fake_review_document_extraction_drafts(**kwargs: object):
        return tuple(cast("tuple[HarnessProposalDraft, ...]", kwargs["drafts"]))

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        source_type = str(kwargs["source_type"])
        captured_bootstrap_source_type.append(source_type)
        captured_marrvel_enabled.append(bool(kwargs["marrvel_enabled"]))
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        _unexpected_pubmed_queries,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_uploaded_documents_into_shared_observation_ingestion,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    proposals = proposal_store.list_proposals(space_id=space_id)
    updated_text_document = document_store.get_document(
        space_id=space_id,
        document_id=text_document.id,
    )
    updated_legacy_pubmed_document = document_store.get_document(
        space_id=space_id,
        document_id=legacy_pubmed_document.id,
    )
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )

    assert result.proposal_count == 1
    assert captured_bootstrap_source_type == ["text"]
    assert captured_marrvel_enabled == [False]
    assert len(proposals) == 1
    assert proposals[0].run_id == queued_run.id
    assert updated_text_document is not None
    assert updated_text_document.extraction_status == "completed"
    assert updated_text_document.last_extraction_run_id == queued_run.id
    assert updated_text_document.metadata["observation_bridge_status"] == "extracted"
    assert (
        updated_text_document.metadata["observation_bridge_observations_created"] == 1
    )
    assert updated_legacy_pubmed_document is not None
    assert updated_legacy_pubmed_document.extraction_status == "not_started"
    assert bridged_document_ids == [text_document.id]
    assert workspace is not None
    assert workspace.snapshot["source_results"]["text"]["documents_selected"] == 1
    assert workspace.snapshot["source_results"]["text"]["observations_created"] == 1


@pytest.mark.asyncio
async def test_execute_research_init_batches_pubmed_observation_bridge_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    services = _build_execution_services(document_store=document_store)

    for index in range(4):
        document_store.create_document(
            space_id=space_id,
            created_by=uuid4(),
            title=f"Replay PubMed note {index + 1}",
            source_type="pubmed",
            filename=None,
            media_type="text/plain",
            sha256=f"pubmed-bridge-{index}",
            byte_size=64,
            page_count=None,
            text_content="BRCA1 and PARP inhibitor response evidence.",
            raw_storage_key=None,
            enriched_storage_key=None,
            ingestion_run_id="pubmed-ingestion-run",
            last_enrichment_run_id=None,
            enrichment_status="completed",
            extraction_status="not_started",
            metadata={"source": "research-init-pubmed"},
        )

    class _ProgressObserver:
        def __init__(self) -> None:
            self.batch_indices: list[int] = []

        def on_progress(
            self,
            *,
            phase: str,
            message: str,
            progress_percent: float,
            completed_steps: int,
            metadata: dict[str, object],
            workspace_snapshot: dict[str, object],
        ) -> None:
            del message, progress_percent, completed_steps, workspace_snapshot
            if (
                phase == "document_extraction"
                and metadata.get("document_observation_bridge_stage")
                == "pubmed_sync_batch_completed"
            ):
                batch_index = metadata["pubmed_observation_bridge_batch_index"]
                assert isinstance(batch_index, int)
                self.batch_indices.append(
                    batch_index,
                )

    observer = _ProgressObserver()
    bridge_batch_sizes: list[int] = []

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [],
    )

    async def _fake_select_candidates_for_ingestion(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del candidates, objective, seed_terms, errors
        return []

    async def _fake_sync_pubmed_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id, pipeline_run_id
        bridge_batch_sizes.append(len(documents))
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=0,
                    entities_created=0,
                    seed_entity_ids=(),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=(),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_diagnostics(
        text: str,
        *,
        space_context: str,
    ) -> tuple[list[object], DocumentCandidateExtractionDiagnostics]:
        del text, space_context
        return (
            [],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="not_needed",
            ),
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates_for_ingestion,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_pubmed_documents_into_shared_observation_ingestion",
        _fake_sync_pubmed_documents_into_shared_observation_ingestion,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _fake_extract_relation_candidates_with_diagnostics,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate BRCA1",
        seed_terms=["BRCA1"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "uniprot": False,
            "hgnc": False,
        },
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate BRCA1",
        seed_terms=["BRCA1"],
        max_depth=1,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "uniprot": False,
            "hgnc": False,
        },
        execution_services=services,
        existing_run=queued_run,
        progress_observer=observer,
    )

    assert result.run.status == "completed"
    assert bridge_batch_sizes == [3, 1]
    assert observer.batch_indices == [1, 2]


@pytest.mark.asyncio
async def test_execute_research_init_times_out_one_document_extraction_without_stalling_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    text_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Slow extraction note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="slow-text-sha",
        byte_size=24,
        page_count=None,
        text_content="PCSK9 modulates lipid metabolism.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    async def _fake_sync_uploaded_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id, pipeline_run_id
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=0,
                    entities_created=0,
                    seed_entity_ids=(),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=(),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                _build_extraction_draft(
                    document_id=document.id,
                    title=document.title,
                ),
            ),
            [],
        )

    async def _slow_review_document_extraction_drafts(**kwargs: object):
        del kwargs
        await asyncio.sleep(0.05)
        return ()

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _slow_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_uploaded_documents_into_shared_observation_ingestion,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate PCSK9",
        seed_terms=["PCSK9"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        max_depth=1,
        max_hypotheses=3,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate PCSK9",
        seed_terms=["PCSK9"],
        max_depth=1,
        max_hypotheses=3,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    updated_document = document_store.get_document(
        space_id=space_id,
        document_id=text_document.id,
    )
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )

    assert result.run.status == "completed"
    assert result.proposal_count == 0
    assert any(
        "Extraction timed out for 'Slow extraction note'" in error
        for error in result.errors
    )
    assert updated_document is not None
    assert updated_document.extraction_status == "failed"
    assert updated_document.last_extraction_run_id == queued_run.id
    assert workspace is not None
    assert workspace.snapshot["proposal_count"] == 0


@pytest.mark.asyncio
async def test_execute_research_init_emits_incremental_document_extraction_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    for index in range(2):
        document_store.create_document(
            space_id=space_id,
            created_by=uuid4(),
            title=f"Extraction note {index + 1}",
            source_type="text",
            filename=None,
            media_type="text/plain",
            sha256=f"text-sha-{index}",
            byte_size=32,
            page_count=None,
            text_content="PCSK9 modulates lipid metabolism.",
            raw_storage_key=None,
            enriched_storage_key=None,
            ingestion_run_id="text-upload-run",
            last_enrichment_run_id=None,
            enrichment_status="skipped",
            extraction_status="not_started",
            metadata={},
        )

    class _ProgressObserver:
        def __init__(self) -> None:
            self.completed_counts: list[int] = []
            self.last_metadata: dict[str, object] | None = None

        def on_progress(
            self,
            *,
            phase: str,
            message: str,
            progress_percent: float,
            completed_steps: int,
            metadata: dict[str, object],
            workspace_snapshot: dict[str, object],
        ) -> None:
            del message, progress_percent, completed_steps, workspace_snapshot
            if (
                phase == "document_extraction"
                and "document_extraction_completed_count" in metadata
            ):
                completed_count = metadata["document_extraction_completed_count"]
                assert isinstance(completed_count, int)
                self.completed_counts.append(
                    completed_count,
                )
                self.last_metadata = dict(metadata)

    observer = _ProgressObserver()

    async def _fake_sync_uploaded_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id, pipeline_run_id
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=0,
                    entities_created=0,
                    seed_entity_ids=(),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=(),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_diagnostics(
        text: str,
        *,
        space_context: str,
    ) -> tuple[list[dict[str, str]], DocumentCandidateExtractionDiagnostics]:
        del text, space_context
        return (
            [{"candidate": "synthetic"}],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                _build_extraction_draft(
                    document_id=document.id,
                    title=document.title,
                ),
            ),
            [],
        )

    async def _fake_review_document_extraction_drafts(**kwargs: object):
        return tuple(cast("tuple[HarnessProposalDraft, ...]", kwargs["drafts"]))

    def _fake_ground_candidate_claim_drafts(
        *,
        space_id: UUID,
        drafts: tuple[HarnessProposalDraft, ...],
        graph_api_gateway: object,
    ) -> tuple[
        tuple[HarnessProposalDraft, ...],
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
    ]:
        del space_id, graph_api_gateway
        return drafts, ("entity-1",), ("entity-1",), ()

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_uploaded_documents_into_shared_observation_ingestion,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_ground_candidate_claim_drafts",
        _fake_ground_candidate_claim_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _fake_extract_relation_candidates_with_diagnostics,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate PCSK9",
        seed_terms=["PCSK9"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        max_depth=1,
        max_hypotheses=3,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate PCSK9",
        seed_terms=["PCSK9"],
        max_depth=1,
        max_hypotheses=3,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
        progress_observer=observer,
    )

    assert result.run.status == "completed"
    assert observer.completed_counts[:2] == [1, 2]
    assert observer.last_metadata is not None
    assert observer.last_metadata["document_extraction_total_count"] == 2
    assert observer.last_metadata["document_extraction_draft_count"] == 2


@pytest.mark.asyncio
async def test_execute_research_init_times_out_blocking_document_draft_build_without_stalling_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    text_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Blocking extraction note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="blocking-text-sha",
        byte_size=28,
        page_count=None,
        text_content="PCSK9 affects LDL receptor activity.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    async def _fake_sync_uploaded_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id, pipeline_run_id
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=0,
                    entities_created=0,
                    seed_entity_ids=(),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=(),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _blocking_build_document_extraction_drafts(**_kwargs: object):
        time.sleep(0.05)
        return ((), [])

    async def _fake_review_document_extraction_drafts(**_kwargs: object):
        return ()

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _blocking_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_uploaded_documents_into_shared_observation_ingestion,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate PCSK9",
        seed_terms=["PCSK9"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        max_depth=1,
        max_hypotheses=3,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate PCSK9",
        seed_terms=["PCSK9"],
        max_depth=1,
        max_hypotheses=3,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    updated_document = document_store.get_document(
        space_id=space_id,
        document_id=text_document.id,
    )
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )

    assert result.run.status == "completed"
    assert result.proposal_count == 0
    assert any(
        "Extraction timed out for 'Blocking extraction note'" in error
        for error in result.errors
    )
    assert updated_document is not None
    assert updated_document.extraction_status == "failed"
    assert updated_document.last_extraction_run_id == queued_run.id
    assert workspace is not None
    assert workspace.snapshot["proposal_count"] == 0


@pytest.mark.asyncio
async def test_execute_research_init_passes_parent_run_id_and_filters_soft_bootstrap_fallback_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    text_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Research note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="text-note-parent-run",
        byte_size=48,
        page_count=None,
        text_content="MED13 is associated with developmental delay.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-run-parent",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    captured_parent_run_ids: list[str | None] = []

    async def _fake_sync_uploaded_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id, pipeline_run_id
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=0,
                    entities_created=0,
                    seed_entity_ids=(),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=(),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                _build_extraction_draft(
                    document_id=document.id,
                    title=document.title,
                ),
            ),
            [],
        )

    async def _fake_review_document_extraction_drafts(**kwargs: object):
        return tuple(cast("tuple[HarnessProposalDraft, ...]", kwargs["drafts"]))

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        captured_parent_run_ids.append(
            cast("str | None", kwargs.get("parent_run_id")),
        )
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={"linked_proposal_count": 1},
            proposal_records=[],
            pending_questions=[],
            errors=[
                "seed:11111111-1111-1111-1111-111111111111:no_generated_relations:fallback",
                "transport:graph-api-timeout",
            ],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_uploaded_documents_into_shared_observation_ingestion,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    assert captured_parent_run_ids == [queued_run.id]
    assert result.proposal_count == 1
    assert result.errors == ["transport:graph-api-timeout"]
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["bootstrap_summary"]["linked_proposal_count"] == 1
    assert workspace.snapshot["bootstrap_summary"]["proposal_count"] == 0
    assert text_document.id in [
        proposal.document_id or ""
        for proposal in proposal_store.list_proposals(
            space_id=space_id,
        )
    ]


@pytest.mark.asyncio
async def test_execute_research_init_enables_bootstrap_claim_curation_and_surfaces_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    text_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Research note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="text-note-claim-curation",
        byte_size=48,
        page_count=None,
        text_content="MED13 is associated with developmental delay.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-run-claim-curation",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    captured_bootstrap_kwargs: dict[str, object] = {}

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                _build_extraction_draft(
                    document_id=document.id,
                    title=document.title,
                ),
            ),
            [],
        )

    async def _fake_review_document_extraction_drafts(**kwargs: object):
        return tuple(cast("tuple[HarnessProposalDraft, ...]", kwargs["drafts"]))

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        captured_bootstrap_kwargs.update(kwargs)
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={"bootstrap_generated_proposal_count": 1},
            proposal_records=[],
            pending_questions=[],
            errors=[],
            claim_curation=ResearchBootstrapClaimCurationSummary(
                status="paused",
                run_id="claim-curation-run",
                proposal_ids=("proposal-1",),
                proposal_count=1,
                blocked_proposal_count=0,
                pending_approval_count=1,
            ),
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    assert captured_bootstrap_kwargs["approval_store"] is services.approval_store
    assert (
        captured_bootstrap_kwargs["claim_curation_graph_api_gateway_factory"]
        is services.graph_api_gateway_factory
    )
    assert captured_bootstrap_kwargs["auto_queue_claim_curation"] is True
    assert captured_bootstrap_kwargs["claim_curation_proposal_limit"] == 5
    assert result.proposal_count == 2
    assert result.claim_curation == {
        "status": "paused",
        "run_id": "claim-curation-run",
        "proposal_ids": ["proposal-1"],
        "proposal_count": 1,
        "blocked_proposal_count": 0,
        "pending_approval_count": 1,
        "reason": None,
    }
    updated_document = document_store.get_document(
        space_id=space_id,
        document_id=text_document.id,
    )
    assert updated_document is not None
    assert updated_document.extraction_status == "completed"

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["proposal_count"] == 2
    assert workspace.snapshot["claim_curation_run_id"] == "claim-curation-run"
    assert workspace.snapshot["claim_curation"]["pending_approval_count"] == 1


@pytest.mark.asyncio
async def test_execute_research_init_auto_creates_entities_with_improved_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    captured_entity_types: list[tuple[str, str]] = []
    created_entity_ids_by_label: dict[str, str] = {}

    class _CapturingGraphApiGateway(_StubGraphApiGateway):
        def create_entity(
            self,
            *,
            space_id: UUID,
            entity_type: str,
            display_label: object,
        ) -> dict[str, str]:
            del space_id
            normalized_label = str(display_label)
            captured_entity_types.append((normalized_label, entity_type))
            entity_id = created_entity_ids_by_label.get(normalized_label)
            if entity_id is None:
                entity_id = str(uuid4())
                created_entity_ids_by_label[normalized_label] = entity_id
            return {"id": entity_id}

    services = replace(
        _build_execution_services(
            document_store=document_store,
            proposal_store=proposal_store,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
        ),
        graph_api_gateway_factory=_CapturingGraphApiGateway,
    )

    text_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Research note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="text-sha",
        byte_size=12,
        page_count=None,
        text_content="BRCA1/2 status shapes olaparib response.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    def _unexpected_pubmed_queries(
        objective: str,
        seed_terms: list[str],
    ) -> list[dict[str, str | None]]:
        del objective, seed_terms
        raise AssertionError("PubMed queries should not be built for text-only runs")

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="document_extraction",
                    source_key=document.id,
                    title=f"Draft for {document.title}",
                    summary="BRCA1/2 status shapes olaparib response.",
                    confidence=0.9,
                    ranking_score=0.9,
                    reasoning_path={},
                    evidence_bundle=[],
                    payload={
                        "proposed_subject": "unresolved:brca1_2",
                        "proposed_subject_label": "BRCA1/2",
                        "proposed_object": "unresolved:olaparib",
                        "proposed_object_label": "olaparib",
                    },
                    metadata={},
                    document_id=document.id,
                ),
            ),
            [],
        )

    async def _fake_review_document_extraction_drafts(**kwargs: object):
        return tuple(cast("tuple[HarnessProposalDraft, ...]", kwargs["drafts"]))

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        _unexpected_pubmed_queries,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Assess BRCA1/2 response to olaparib",
        seed_terms=["BRCA1/2", "olaparib"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": True,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Assess BRCA1/2 response to olaparib",
        seed_terms=["BRCA1/2", "olaparib"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": False,
            "marrvel": False,
            "clinvar": False,
            "mondo": False,
            "pdf": False,
            "text": True,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    assert result.proposal_count == 1
    assert captured_entity_types == [
        ("BRCA1/2", "GENE"),
        ("olaparib", "DRUG"),
    ]
    stored_proposals = proposal_store.list_proposals(space_id=space_id)
    assert len(stored_proposals) == 1
    grounded_payload = stored_proposals[0].payload
    assert (
        grounded_payload["proposed_subject"] == created_entity_ids_by_label["BRCA1/2"]
    )
    assert (
        grounded_payload["proposed_object"] == created_entity_ids_by_label["olaparib"]
    )
    assert UUID(str(grounded_payload["proposed_subject"]))
    assert UUID(str(grounded_payload["proposed_object"]))
    updated_document = document_store.get_document(
        space_id=space_id,
        document_id=text_document.id,
    )
    assert updated_document is not None
    assert updated_document.extraction_status == "completed"


@pytest.mark.asyncio
async def test_execute_research_init_processes_pdf_documents_when_pdf_source_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    binary_store = HarnessDocumentBinaryStore()
    services = _build_execution_services(
        document_store=document_store,
        proposal_store=proposal_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        document_binary_store=binary_store,
    )

    pdf_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Uploaded PDF",
        source_type="pdf",
        filename="upload.pdf",
        media_type="application/pdf",
        sha256="pdf-sha",
        byte_size=120,
        page_count=None,
        text_content="",
        raw_storage_key="documents/raw/upload.pdf",
        enriched_storage_key=None,
        ingestion_run_id="pdf-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="not_started",
        extraction_status="not_started",
        metadata={},
    )

    captured_bootstrap_source_type: list[str] = []
    enrich_calls: list[str] = []
    bridged_payloads: list[tuple[str, str]] = []

    def _unexpected_pubmed_queries(
        objective: str,
        seed_terms: list[str],
    ) -> list[dict[str, str | None]]:
        del objective, seed_terms
        raise AssertionError("PubMed queries should not be built for pdf-only runs")

    async def _fake_enrich_pdf_document(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        enrich_calls.append(document.id)
        updated = document_store.update_document(
            space_id=space_id,
            document_id=document.id,
            text_content="Extracted PDF text about MED13.",
            last_enrichment_run_id="research-init-enrichment",
            enrichment_status="completed",
        )
        assert updated is not None
        return updated

    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[dict[str, str]]:
        del text, max_relations, space_context
        return [{"candidate": "synthetic"}]

    async def _fake_pre_resolve_entities_with_ai(**_kwargs: object) -> dict[str, str]:
        return {}

    def _fake_build_document_extraction_drafts(**kwargs: object):
        document = cast("HarnessDocumentRecord", kwargs["document"])
        return (
            (
                _build_extraction_draft(
                    document_id=document.id,
                    title=document.title,
                ),
            ),
            [],
        )

    async def _fake_review_document_extraction_drafts(**kwargs: object):
        return tuple(cast("tuple[HarnessProposalDraft, ...]", kwargs["drafts"]))

    async def _fake_sync_uploaded_documents_into_shared_observation_ingestion(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id
        del pipeline_run_id
        bridged_payloads.extend(
            (document.id, document.text_content) for document in documents
        )
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=2,
                    entities_created=1,
                    seed_entity_ids=("22222222-2222-2222-2222-222222222222",),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=("22222222-2222-2222-2222-222222222222",),
            errors=(),
        )

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        captured_bootstrap_source_type.append(str(kwargs["source_type"]))
        snapshot_store = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        )
        state_store = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        )
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = state_store.upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        _unexpected_pubmed_queries,
    )
    monkeypatch.setattr(
        "artana_evidence_api.research_init_runtime._enrich_pdf_document",
        _fake_enrich_pdf_document,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.pre_resolve_entities_with_ai",
        _fake_pre_resolve_entities_with_ai,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.build_document_extraction_drafts",
        _fake_build_document_extraction_drafts,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.review_document_extraction_drafts",
        _fake_review_document_extraction_drafts,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _fake_sync_uploaded_documents_into_shared_observation_ingestion,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": True,
            "text": False,
            "clinvar": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": True,
            "text": False,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    updated_pdf_document = document_store.get_document(
        space_id=space_id,
        document_id=pdf_document.id,
    )

    assert result.proposal_count == 1
    assert enrich_calls == [pdf_document.id]
    assert captured_bootstrap_source_type == ["pdf"]
    assert updated_pdf_document is not None
    assert updated_pdf_document.enrichment_status == "completed"
    assert updated_pdf_document.extraction_status == "completed"
    assert updated_pdf_document.last_extraction_run_id == queued_run.id
    assert updated_pdf_document.metadata["observation_bridge_status"] == "extracted"
    assert updated_pdf_document.metadata["observation_bridge_observations_created"] == 2
    assert bridged_payloads == [(pdf_document.id, "Extracted PDF text about MED13.")]


@pytest.mark.asyncio
async def test_execute_research_init_runs_pubmed_queries_concurrently_preserving_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    services = _build_execution_services()
    current_concurrency = 0
    max_concurrency = 0

    async def _fake_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del owner_id, max_results_per_query, max_previews_per_query
        nonlocal current_concurrency, max_concurrency
        current_concurrency += 1
        max_concurrency = max(max_concurrency, current_concurrency)
        try:
            query = query_params.get("search_term", "") or ""
            await asyncio.sleep(0.05 if query == "slow-query" else 0.01)
            return research_init_runtime._PubMedQueryExecutionResult(
                query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                    query=query,
                    total_found=10 if query == "slow-query" else 20,
                    abstracts_ingested=0,
                ),
                candidates=(),
                errors=(),
            )
        finally:
            current_concurrency -= 1

    async def _fake_select_candidates_for_ingestion(
        _candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del objective, seed_terms, errors
        return []

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [
            {"search_term": "slow-query", "gene_symbol": None},
            {"search_term": "fast-query", "gene_symbol": None},
        ],
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _fake_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates_for_ingestion,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    assert [item.query for item in result.pubmed_results] == [
        "slow-query",
        "fast-query",
    ]
    assert [item.total_found for item in result.pubmed_results] == [10, 20]
    assert max_concurrency > 1


@pytest.mark.asyncio
async def test_prepare_pubmed_replay_bundle_captures_selected_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del owner_id, max_results_per_query, max_previews_per_query
        query = query_params.get("search_term", "") or ""
        candidate = research_init._PubMedCandidate(
            title=f"{query} paper",
            text=f"{query} evidence",
            queries=[query],
            pmid=f"pmid-{query}",
            doi=None,
            pmc_id=None,
            journal="Synthetic Journal",
        )
        return research_init_runtime._PubMedQueryExecutionResult(
            query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                query=query,
                total_found=1,
                abstracts_ingested=1,
            ),
            candidates=(candidate,),
            errors=(),
        )

    async def _fake_select_candidates_for_ingestion(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del objective, seed_terms
        errors.append("synthetic replay selection warning")
        return [
            (
                candidates[0],
                research_init._PubMedCandidateReview(
                    method="heuristic",
                    label="relevant",
                    confidence=0.95,
                    rationale="synthetic replay",
                ),
            ),
        ]

    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [
            {"search_term": "MED13", "gene_symbol": None},
        ],
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _fake_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates_for_ingestion,
    )

    bundle = await research_init_runtime.prepare_pubmed_replay_bundle(
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
    )

    assert len(bundle.query_executions) == 1
    assert bundle.selection_errors == ("synthetic replay selection warning",)
    assert len(bundle.selected_candidates) == 1
    candidate, review = bundle.selected_candidates[0]
    assert isinstance(candidate, research_init._PubMedCandidate)
    assert isinstance(review, research_init._PubMedCandidateReview)
    assert candidate.title == "MED13 paper"
    assert candidate.queries == ["MED13"]
    assert review.confidence == pytest.approx(0.95)


def test_build_pubmed_replay_bundle_with_document_outputs_captures_extractions() -> (
    None
):
    space_id = uuid4()
    run_id = str(uuid4())
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    replay_candidate = research_init._PubMedCandidate(
        title="Replay MED13 paper",
        text="MED13 replay evidence",
        queries=["MED13"],
        pmid="pmid-replay",
        doi=None,
        pmc_id=None,
        journal="Synthetic Journal",
    )
    replay_review = research_init._PubMedCandidateReview(
        method="heuristic",
        label="relevant",
        confidence=0.9,
        rationale="replayed",
    )
    normalized = normalize_text_document(replay_candidate.text)
    replay_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title=replay_candidate.title,
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=sha256_hex(normalized.encode("utf-8")),
        byte_size=len(normalized.encode("utf-8")),
        page_count=None,
        text_content=normalized,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="completed",
        metadata={"source": "research-init-pubmed"},
    )
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key=f"{replay_document.id}:0",
                title="Extracted claim: MED13 ASSOCIATED_WITH syndrome",
                summary="PubMed extraction summary",
                confidence=0.6,
                ranking_score=0.6,
                reasoning_path={"source": "document_extraction"},
                evidence_bundle=[],
                payload={"proposed_subject_label": "MED13"},
                metadata={"source": "document_extraction"},
                document_id=replay_document.id,
                claim_fingerprint="pubmed-fingerprint-1",
            ),
        ),
    )
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=((replay_candidate, replay_review),),
        selection_errors=(),
    )

    enriched_bundle = (
        research_init_runtime.build_pubmed_replay_bundle_with_document_outputs(
            replay_bundle=replay_bundle,
            space_id=space_id,
            run_id=run_id,
            document_store=document_store,
            proposal_store=proposal_store,
        )
    )

    assert len(enriched_bundle.documents) == 1
    assert enriched_bundle.documents[0].source_document_id == replay_document.id
    assert enriched_bundle.documents[0].sha256 == replay_document.sha256
    assert len(enriched_bundle.documents[0].extraction_proposals) == 1
    assert (
        enriched_bundle.documents[0].extraction_proposals[0].claim_fingerprint
        == "pubmed-fingerprint-1"
    )


def test_pubmed_replay_bundle_serialization_round_trips() -> None:
    replay_candidate = research_init._PubMedCandidate(
        title="Replay MED13 paper",
        text="MED13 replay evidence",
        queries=["MED13", "MED13 syndrome"],
        pmid="pmid-replay",
        doi="10.1234/replay",
        pmc_id="PMC123",
        journal="Synthetic Journal",
    )
    replay_review = research_init._PubMedCandidateReview(
        method="llm",
        label="relevant",
        confidence=0.88,
        rationale="Replay candidate still matters.",
        agent_run_id="agent-1",
        signal_count=3,
        focus_signal_count=2,
        query_specificity=1,
    )
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(
            research_init_runtime._PubMedQueryExecutionResult(
                query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                    query="MED13 syndrome",
                    total_found=7,
                    abstracts_ingested=4,
                ),
                candidates=(replay_candidate,),
                errors=("query warning",),
            ),
        ),
        selected_candidates=((replay_candidate, replay_review),),
        selection_errors=("selection warning",),
        documents=(
            research_init_runtime.ResearchInitPubMedReplayDocument(
                source_document_id="pubmed-doc-1",
                sha256="pubmed-doc-sha",
                title="Replay MED13 paper",
                extraction_proposals=(
                    research_init_runtime.ResearchInitStructuredReplayProposal(
                        proposal_type="candidate_claim",
                        source_kind="document_extraction",
                        source_key="pubmed-doc-1:0",
                        title="Extracted claim: MED13 ASSOCIATED_WITH syndrome",
                        summary="PubMed extraction summary",
                        confidence=0.7,
                        ranking_score=0.7,
                        reasoning_path={"source": "document_extraction"},
                        evidence_bundle=[],
                        payload={"proposed_subject_label": "MED13"},
                        metadata={"source": "document_extraction"},
                        source_document_id="pubmed-doc-1",
                        claim_fingerprint="pubmed-doc-fingerprint",
                    ),
                ),
            ),
        ),
    )

    serialized = research_init_runtime.serialize_pubmed_replay_bundle(replay_bundle)
    restored = research_init_runtime.deserialize_pubmed_replay_bundle(serialized)

    assert restored is not None
    assert len(restored.query_executions) == 1
    assert restored.query_executions[0].query_result is not None
    assert restored.query_executions[0].query_result.query == "MED13 syndrome"
    assert restored.query_executions[0].query_result.abstracts_ingested == 4
    assert restored.query_executions[0].errors == ("query warning",)
    restored_candidate, restored_review = restored.selected_candidates[0]
    assert restored_candidate.title == "Replay MED13 paper"
    assert restored_candidate.queries == ["MED13", "MED13 syndrome"]
    assert restored_review.label == "relevant"
    assert restored_review.agent_run_id == "agent-1"
    assert restored.selection_errors == ("selection warning",)
    assert len(restored.documents) == 1
    assert restored.documents[0].source_document_id == "pubmed-doc-1"
    assert restored.documents[0].sha256 == "pubmed-doc-sha"
    assert restored.documents[0].extraction_proposals[0].claim_fingerprint == (
        "pubmed-doc-fingerprint"
    )


def test_pubmed_replay_bundle_artifact_round_trips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = _build_execution_services()
    space_id = uuid4()
    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Artifact replay",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "marrvel": False, "pdf": False, "text": False},
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )
    replay_candidate = research_init._PubMedCandidate(
        title="Artifact replay paper",
        text="Artifact replay evidence",
        queries=["MED13"],
        pmid="pmid-artifact",
        doi=None,
        pmc_id=None,
        journal="Synthetic Journal",
    )
    replay_review = research_init._PubMedCandidateReview(
        method="heuristic",
        label="relevant",
        confidence=0.91,
        rationale="artifact round trip",
    )
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(
            research_init_runtime._PubMedQueryExecutionResult(
                query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                    query="MED13",
                    total_found=3,
                    abstracts_ingested=1,
                ),
                candidates=(replay_candidate,),
                errors=(),
            ),
        ),
        selected_candidates=((replay_candidate, replay_review),),
        selection_errors=("artifact warning",),
    )
    research_init_runtime.store_pubmed_replay_bundle_artifact(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
        replay_bundle=replay_bundle,
    )

    restored = research_init_runtime.load_pubmed_replay_bundle_artifact(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )

    assert restored is not None
    assert restored.selection_errors == ("artifact warning",)
    assert restored.selected_candidates[0][0].title == "Artifact replay paper"
    assert workspace is not None
    assert workspace.snapshot["pubmed_replay_bundle_key"] == (
        "research_init_pubmed_replay_bundle"
    )


def test_build_structured_enrichment_replay_bundle_captures_documents_and_proposals() -> (
    None
):
    space_id = uuid4()
    run_id = str(uuid4())
    child_run_id = str(uuid4())
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    structured_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="DrugBank: PCSK9 inhibitor",
        source_type="drugbank",
        filename=None,
        media_type="application/json",
        sha256="drugbank-sha",
        byte_size=128,
        page_count=None,
        text_content="DrugBank structured payload",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=child_run_id,
        last_enrichment_run_id=child_run_id,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={"source": "drugbank"},
    )
    proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="drugbank_enrichment",
                source_key="drugbank:pcsk9",
                title="DrugBank: PCSK9 inhibitor TARGETS PCSK9",
                summary="DrugBank summary",
                confidence=0.5,
                ranking_score=0.5,
                reasoning_path={"source": "drugbank"},
                evidence_bundle=[],
                payload={"proposed_subject_label": "PCSK9 inhibitor"},
                metadata={"source": "drugbank"},
                document_id=structured_document.id,
                claim_fingerprint="fingerprint-1",
            ),
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="document:drugbank:pcsk9",
                title="DrugBank document says inhibitor lowers PCSK9",
                summary="Document extraction summary",
                confidence=0.6,
                ranking_score=0.6,
                reasoning_path={"source": "document_extraction"},
                evidence_bundle=[],
                payload={"proposed_subject_label": "PCSK9 inhibitor"},
                metadata={"source": "document_extraction"},
                document_id=structured_document.id,
                claim_fingerprint="fingerprint-2",
            ),
        ),
    )

    bundle = research_init_runtime.build_structured_enrichment_replay_bundle(
        space_id=space_id,
        run_id=run_id,
        document_store=document_store,
        proposal_store=proposal_store,
        workspace_snapshot={
            "source_results": {
                "drugbank": {"records_processed": 3},
            },
        },
    )

    assert len(bundle.sources) == 1
    replay_source = bundle.sources[0]
    assert replay_source.source_key == "drugbank"
    assert replay_source.records_processed == 3
    assert len(replay_source.documents) == 1
    assert replay_source.documents[0].source_document_id == structured_document.id
    assert len(replay_source.proposals) == 1
    assert replay_source.proposals[0].source_document_id == structured_document.id
    assert replay_source.proposals[0].claim_fingerprint == "fingerprint-1"
    assert len(replay_source.document_extraction_proposals) == 1
    assert (
        replay_source.document_extraction_proposals[0].source_document_id
        == structured_document.id
    )
    assert (
        replay_source.document_extraction_proposals[0].claim_fingerprint
        == "fingerprint-2"
    )


@pytest.mark.asyncio
async def test_execute_research_init_uses_pubmed_replay_bundle_without_live_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    services = _build_execution_services()

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: (_ for _ in ()).throw(
            AssertionError("pubmed queries should not be rebuilt from replay")
        ),
    )

    async def _unexpected_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del query_params, owner_id, max_results_per_query, max_previews_per_query
        raise AssertionError("live pubmed query should not run from replay")

    async def _unexpected_select_candidates(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del candidates, objective, seed_terms, errors
        raise AssertionError("candidate selection should not rerun from replay")

    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _unexpected_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _unexpected_select_candidates,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    async def _unexpected_extract_relation_candidates_with_diagnostics(
        text: str,
        *,
        space_context: str,
    ) -> tuple[list[object], DocumentCandidateExtractionDiagnostics]:
        del text, space_context
        raise AssertionError(
            "live document extraction should not run for replayed pubmed docs"
        )

    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _unexpected_extract_relation_candidates_with_diagnostics,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init replay",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    replay_candidate = research_init._PubMedCandidate(
        title="Replay MED13 paper",
        text="MED13 replay evidence",
        queries=["MED13"],
        pmid="pmid-replay",
        doi=None,
        pmc_id=None,
        journal="Synthetic Journal",
    )
    replay_review = research_init._PubMedCandidateReview(
        method="heuristic",
        label="relevant",
        confidence=0.99,
        rationale="replayed",
    )
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(
            research_init_runtime._PubMedQueryExecutionResult(
                query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                    query="MED13",
                    total_found=1,
                    abstracts_ingested=1,
                ),
                candidates=(replay_candidate,),
                errors=(),
            ),
        ),
        selected_candidates=((replay_candidate, replay_review),),
        selection_errors=("synthetic replay warning",),
        documents=(
            research_init_runtime.ResearchInitPubMedReplayDocument(
                source_document_id="baseline-pubmed-doc-1",
                sha256=sha256_hex(
                    normalize_text_document(replay_candidate.text).encode("utf-8"),
                ),
                title="Replay MED13 paper",
                extraction_proposals=(
                    research_init_runtime.ResearchInitStructuredReplayProposal(
                        proposal_type="candidate_claim",
                        source_kind="document_extraction",
                        source_key="baseline-pubmed-doc-1:0",
                        title="Extracted claim: MED13 ASSOCIATED_WITH syndrome",
                        summary="PubMed extraction replay summary",
                        confidence=0.7,
                        ranking_score=0.7,
                        reasoning_path={"source": "document_extraction"},
                        evidence_bundle=[],
                        payload={"proposed_subject_label": "MED13"},
                        metadata={"source": "document_extraction"},
                        source_document_id="baseline-pubmed-doc-1",
                        claim_fingerprint="pubmed-replay-fingerprint",
                    ),
                ),
            ),
        ),
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init replay",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=1,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
        pubmed_replay_bundle=replay_bundle,
    )

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    proposals = services.proposal_store.list_proposals(
        space_id=space_id,
        run_id=queued_run.id,
    )
    documents = services.document_store.list_documents(space_id=space_id)

    assert workspace is not None
    source_results = workspace.snapshot["source_results"]
    assert isinstance(source_results, dict)
    assert result.documents_ingested == 1
    assert result.proposal_count == 1
    assert "synthetic replay warning" in result.errors
    assert [record.query for record in result.pubmed_results] == ["MED13"]
    assert source_results["pubmed"]["documents_discovered"] == 1
    assert source_results["pubmed"]["documents_selected"] == 1
    assert source_results["pubmed"]["documents_ingested"] == 1
    assert len(proposals) == 1
    assert proposals[0].claim_fingerprint == "pubmed-replay-fingerprint"
    assert len(documents) == 1
    assert documents[0].metadata["replayed_source_document_id"] == (
        "baseline-pubmed-doc-1"
    )
    assert documents[0].metadata["document_extraction_replayed"] is True
    source_capture = documents[0].metadata["source_capture"]
    assert isinstance(source_capture, dict)
    assert source_capture["source_key"] == "pubmed"
    assert source_capture["capture_stage"] == "source_document"
    assert source_capture["capture_method"] == "research_plan"
    assert source_capture["external_id"] == "pmid-replay"
    assert source_capture["locator"] == "pubmed:pmid-replay"


@pytest.mark.asyncio
async def test_execute_research_init_uses_structured_replay_bundle_without_live_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    services = _build_execution_services()

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    async def _unexpected_run_drugbank_enrichment(**_kwargs: object):
        raise AssertionError("live drugbank enrichment should not run from replay")

    async def _unexpected_extract_relation_candidates_with_diagnostics(
        text: str,
        *,
        space_context: str,
    ) -> tuple[list[object], DocumentCandidateExtractionDiagnostics]:
        del text, space_context
        raise AssertionError(
            "live document extraction should not run for replayed structured docs"
        )

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        ).create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        ).upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        "artana_evidence_api.research_init_source_enrichment.run_drugbank_enrichment",
        _unexpected_run_drugbank_enrichment,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _unexpected_extract_relation_candidates_with_diagnostics,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init structured replay",
        objective="Investigate PCSK9 repurposing",
        seed_terms=["PCSK9"],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
            "drugbank": True,
        },
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    structured_replay_bundle = (
        research_init_runtime.ResearchInitStructuredEnrichmentReplayBundle(
            sources=(
                research_init_runtime.ResearchInitStructuredEnrichmentReplaySource(
                    source_key="drugbank",
                    documents=(
                        research_init_runtime.ResearchInitStructuredReplayDocument(
                            source_document_id="baseline-doc-1",
                            created_by=str(uuid4()),
                            title="DrugBank replay document",
                            source_type="drugbank",
                            filename=None,
                            media_type="application/json",
                            sha256="replay-drugbank-doc",
                            byte_size=64,
                            page_count=None,
                            text_content="DrugBank replay text",
                            raw_storage_key=None,
                            enriched_storage_key=None,
                            enrichment_status="completed",
                            extraction_status="not_started",
                            metadata={"source": "drugbank"},
                        ),
                    ),
                    proposals=(
                        research_init_runtime.ResearchInitStructuredReplayProposal(
                            proposal_type="candidate_claim",
                            source_kind="drugbank_enrichment",
                            source_key="drugbank:pcsk9",
                            title="DrugBank: inhibitor TARGETS PCSK9",
                            summary="DrugBank replay summary",
                            confidence=0.5,
                            ranking_score=0.5,
                            reasoning_path={"source": "drugbank"},
                            evidence_bundle=[],
                            payload={
                                "proposed_subject_label": "PCSK9 inhibitor",
                                "proposed_claim_type": "TARGETS",
                                "proposed_object_label": "PCSK9",
                            },
                            metadata={"source": "drugbank"},
                            source_document_id="baseline-doc-1",
                            claim_fingerprint="drugbank-replay-fingerprint",
                        ),
                    ),
                    document_extraction_proposals=(
                        research_init_runtime.ResearchInitStructuredReplayProposal(
                            proposal_type="candidate_claim",
                            source_kind="document_extraction",
                            source_key="document:drugbank:pcsk9",
                            title="Replay document says inhibitor TARGETS PCSK9",
                            summary="Document extraction replay summary",
                            confidence=0.55,
                            ranking_score=0.55,
                            reasoning_path={"source": "document_extraction"},
                            evidence_bundle=[],
                            payload={
                                "proposed_subject_label": "PCSK9 inhibitor",
                                "proposed_claim_type": "TARGETS",
                                "proposed_object_label": "PCSK9",
                            },
                            metadata={"source": "document_extraction"},
                            source_document_id="baseline-doc-1",
                            claim_fingerprint="drugbank-doc-replay-fingerprint",
                        ),
                    ),
                    records_processed=2,
                ),
            ),
        )
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init structured replay",
        objective="Investigate PCSK9 repurposing",
        seed_terms=["PCSK9"],
        max_depth=1,
        max_hypotheses=5,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
            "drugbank": True,
        },
        execution_services=services,
        existing_run=queued_run,
        structured_enrichment_replay_bundle=structured_replay_bundle,
    )

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    proposals = services.proposal_store.list_proposals(
        space_id=space_id,
        run_id=queued_run.id,
    )
    documents = services.document_store.list_documents(space_id=space_id)

    assert result.proposal_count == 2
    assert workspace is not None
    assert workspace.snapshot["source_results"]["drugbank"]["status"] == "completed"
    assert workspace.snapshot["source_results"]["drugbank"]["records_processed"] == 2
    assert len(proposals) == 2
    assert {proposal.claim_fingerprint for proposal in proposals} == {
        "drugbank-replay-fingerprint",
        "drugbank-doc-replay-fingerprint",
    }
    assert all(proposal.document_id is not None for proposal in proposals)
    assert len(documents) == 1
    assert documents[0].metadata["replayed_source_document_id"] == "baseline-doc-1"
    assert documents[0].metadata["document_extraction_replayed"] is True


@pytest.mark.asyncio
async def test_execute_research_init_loads_pubmed_replay_bundle_from_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    services = _build_execution_services()

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: (_ for _ in ()).throw(
            AssertionError("pubmed queries should not be rebuilt from replay artifact")
        ),
    )

    async def _unexpected_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del query_params, owner_id, max_results_per_query, max_previews_per_query
        raise AssertionError("live pubmed query should not run from replay artifact")

    async def _unexpected_select_candidates(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del candidates, objective, seed_terms, errors
        raise AssertionError(
            "candidate selection should not rerun from replay artifact"
        )

    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _unexpected_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _unexpected_select_candidates,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init replay artifact",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    replay_candidate = research_init._PubMedCandidate(
        title="Artifact replay MED13 paper",
        text="MED13 artifact replay evidence",
        queries=["MED13"],
        pmid="pmid-artifact-replay",
        doi=None,
        pmc_id=None,
        journal="Synthetic Journal",
    )
    replay_review = research_init._PubMedCandidateReview(
        method="heuristic",
        label="relevant",
        confidence=0.97,
        rationale="artifact replayed",
    )
    replay_bundle = research_init_runtime.ResearchInitPubMedReplayBundle(
        query_executions=(
            research_init_runtime._PubMedQueryExecutionResult(
                query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                    query="MED13",
                    total_found=1,
                    abstracts_ingested=1,
                ),
                candidates=(replay_candidate,),
                errors=(),
            ),
        ),
        selected_candidates=((replay_candidate, replay_review),),
        selection_errors=("artifact replay warning",),
    )
    research_init_runtime.store_pubmed_replay_bundle_artifact(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
        replay_bundle=replay_bundle,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init replay artifact",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=1,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    assert result.documents_ingested == 1
    assert "artifact replay warning" in result.errors
    assert [record.query for record in result.pubmed_results] == ["MED13"]


@pytest.mark.asyncio
async def test_execute_research_init_persists_pubmed_results_before_document_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    services = _build_execution_services()

    class _ProgressObserver:
        def __init__(self) -> None:
            self.document_ingestion_snapshot: dict[str, object] | None = None

        def on_progress(
            self,
            *,
            phase: str,
            message: str,
            progress_percent: float,
            completed_steps: int,
            metadata: dict[str, object],
            workspace_snapshot: dict[str, object],
        ) -> None:
            del message, progress_percent, completed_steps, metadata
            if phase == "document_ingestion":
                self.document_ingestion_snapshot = dict(workspace_snapshot)

    observer = _ProgressObserver()

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [{"search_term": "MED13 syndrome"}],
    )

    async def _fake_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del owner_id, max_results_per_query, max_previews_per_query
        candidate = research_init._PubMedCandidate(
            title="MED13 syndrome overview",
            text="MED13 syndrome evidence abstract.",
            queries=[str(query_params.get("search_term", ""))],
            pmid="pmid-1",
            doi=None,
            pmc_id=None,
            journal="Synthetic Journal",
        )
        return research_init_runtime._PubMedQueryExecutionResult(
            query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                query="MED13 syndrome",
                total_found=7,
                abstracts_ingested=1,
            ),
            candidates=(candidate,),
            errors=(),
        )

    async def _fake_select_candidates_for_ingestion(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del candidates, objective, seed_terms, errors
        return []

    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _fake_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates_for_ingestion,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
        },
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=1,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
        },
        execution_services=services,
        existing_run=queued_run,
        progress_observer=observer,
    )

    assert result.pubmed_results == (
        research_init_runtime.ResearchInitPubMedResultRecord(
            query="MED13 syndrome",
            total_found=7,
            abstracts_ingested=1,
        ),
    )
    assert observer.document_ingestion_snapshot is not None
    assert observer.document_ingestion_snapshot["pubmed_results"] == [
        {
            "query": "MED13 syndrome",
            "total_found": 7,
            "abstracts_ingested": 1,
        },
    ]
    source_results = observer.document_ingestion_snapshot["source_results"]
    assert isinstance(source_results, dict)
    assert source_results["pubmed"]["documents_discovered"] == 1
    assert source_results["pubmed"]["documents_selected"] == 0


@pytest.mark.asyncio
async def test_execute_research_init_skips_duplicate_pubmed_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    services = _build_execution_services(document_store=document_store)
    normalized_text = "MED13 associates with cardiomyopathy."
    _existing_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Existing MED13 article",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        byte_size=len(normalized_text.encode("utf-8")),
        page_count=None,
        text_content=normalized_text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="existing-ingestion-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={"source": "existing"},
    )

    async def _fake_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del owner_id, max_results_per_query, max_previews_per_query
        query = query_params.get("search_term", "") or ""
        candidate = research_init._PubMedCandidate(
            title="Existing MED13 article",
            text=normalized_text,
            queries=[query],
            pmid="pmid-123",
            doi=None,
            pmc_id=None,
            journal="Synthetic Journal",
        )
        return research_init_runtime._PubMedQueryExecutionResult(
            query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                query=query,
                total_found=1,
                abstracts_ingested=1,
            ),
            candidates=(candidate,),
            errors=(),
        )

    async def _fake_select_candidates_for_ingestion(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del objective, seed_terms, errors
        candidate = candidates[0]
        return [
            (
                candidate,
                research_init._PubMedCandidateReview(
                    method="heuristic",
                    label="relevant",
                    confidence=0.99,
                    rationale="synthetic",
                ),
            ),
        ]

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [
            {"search_term": "MED13", "gene_symbol": None},
        ],
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _fake_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates_for_ingestion,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    assert result.run.status == "completed"
    assert result.documents_ingested == 0
    assert result.proposal_count == 0
    assert result.errors == []
    assert len(document_store.list_documents(space_id=space_id)) == 1
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    assert (
        workspace.snapshot["source_results"]["pubmed"]["documents_skipped_duplicate"]
        == 1
    )


@pytest.mark.parametrize(
    "last_graph_snapshot_id",
    ["prior-snapshot", None],
)
@pytest.mark.asyncio
async def test_execute_research_init_suppresses_scope_refinement_after_prior_context(
    monkeypatch: pytest.MonkeyPatch,
    last_graph_snapshot_id: str | None,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    research_state_store = HarnessResearchStateStore()
    research_state_store.upsert_state(
        space_id=space_id,
        objective="Investigate MED13 syndrome",
        explored_questions=[
            "Investigate MED13 syndrome",
            "disease mechanisms and pathways",
        ],
        pending_questions=["Which direction should I deepen next?"],
        last_graph_snapshot_id=last_graph_snapshot_id,
    )
    services = _build_execution_services(
        document_store=document_store,
        research_state_store=research_state_store,
    )
    normalized_text = "MED13 associates with cardiomyopathy."
    _existing_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Existing MED13 article",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        byte_size=len(normalized_text.encode("utf-8")),
        page_count=None,
        text_content=normalized_text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="existing-ingestion-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={"source": "existing"},
    )

    async def _fake_execute_pubmed_query(
        *,
        query_params: dict[str, str | None],
        owner_id: UUID,
        max_results_per_query: int,
        max_previews_per_query: int,
    ) -> research_init_runtime._PubMedQueryExecutionResult:
        del owner_id, max_results_per_query, max_previews_per_query
        query = query_params.get("search_term", "") or ""
        candidate = research_init._PubMedCandidate(
            title="Existing MED13 article",
            text=normalized_text,
            queries=[query],
            pmid="pmid-123",
            doi=None,
            pmc_id=None,
            journal="Synthetic Journal",
        )
        return research_init_runtime._PubMedQueryExecutionResult(
            query_result=research_init_runtime.ResearchInitPubMedResultRecord(
                query=query,
                total_found=1,
                abstracts_ingested=1,
            ),
            candidates=(candidate,),
            errors=(),
        )

    async def _fake_select_candidates_for_ingestion(
        candidates: list[object],
        *,
        objective: str,
        seed_terms: list[str],
        errors: list[str],
    ) -> list[tuple[object, object]]:
        del objective, seed_terms, errors
        candidate = candidates[0]
        return [
            (
                candidate,
                research_init._PubMedCandidateReview(
                    method="heuristic",
                    label="relevant",
                    confidence=0.99,
                    rationale="synthetic",
                ),
            ),
        ]

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [
            {"search_term": "MED13", "gene_symbol": None},
        ],
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_execute_pubmed_query",
        _fake_execute_pubmed_query,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_select_candidates_for_ingestion",
        _fake_select_candidates_for_ingestion,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "clinvar": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    state = research_state_store.get_state(space_id=space_id)

    assert result.run.status == "completed"
    assert result.documents_ingested == 0
    assert result.proposal_count == 0
    assert result.pending_questions == []
    assert state is not None
    assert state.pending_questions == []
    assert state.last_graph_snapshot_id == last_graph_snapshot_id
    assert state.metadata["last_research_init_status"] == (
        "completed_without_follow_up_evidence"
    )


@pytest.mark.asyncio
async def test_execute_research_init_syncs_pubmed_observations_for_existing_pubmed_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    services = _build_execution_services(document_store=document_store)
    pubmed_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="COVID-19 host interaction",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="pubmed-sha",
        byte_size=42,
        page_count=None,
        text_content="ACE2 is implicated in SARS-CoV-2 host entry.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="existing-ingestion-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["COVID-19 ACE2"],
            "pubmed": {
                "pmid": "12345",
                "journal": "Synthetic Journal",
            },
        },
    )
    synced_document_ids: list[str] = []

    async def _fake_sync_pubmed_observations(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id
        del pipeline_run_id
        synced_document_ids.extend(document.id for document in documents)
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=2,
                    entities_created=1,
                    seed_entity_ids=("entity-1",),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=("entity-1",),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_diagnostics(
        text: str,
        *,
        space_context: str,
    ) -> tuple[list[dict[str, str]], DocumentCandidateExtractionDiagnostics]:
        del text, space_context
        return [], DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="not_needed",
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [],
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_pubmed_documents_into_shared_observation_ingestion",
        _fake_sync_pubmed_observations,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _fake_extract_relation_candidates_with_diagnostics,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate COVID-19 host mechanisms",
        seed_terms=["COVID-19", "ACE2"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "pdf": False,
            "text": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate COVID-19 host mechanisms",
        seed_terms=["COVID-19", "ACE2"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "pdf": False,
            "text": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    updated_document = document_store.get_document(
        space_id=space_id,
        document_id=pubmed_document.id,
    )
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )

    assert result.run.status == "completed"
    assert result.proposal_count == 0
    assert synced_document_ids == [pubmed_document.id]
    assert updated_document is not None
    assert updated_document.metadata["observation_bridge_status"] == "extracted"
    assert updated_document.metadata["observation_bridge_observations_created"] == 2
    assert workspace is not None
    assert workspace.snapshot["source_results"]["pubmed"]["documents_selected"] == 1
    assert workspace.snapshot["source_results"]["pubmed"]["observations_created"] == 2


@pytest.mark.asyncio
async def test_execute_research_init_keeps_llm_candidate_fallback_diagnostics_out_of_run_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    document_store = HarnessDocumentStore()
    services = _build_execution_services(document_store=document_store)
    pubmed_document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Short abstract",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="pubmed-sha-fallback",
        byte_size=31,
        page_count=None,
        text_content="Expression was measured in cases.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="existing-ingestion-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["MED13 expression"],
            "pubmed": {
                "pmid": "67890",
                "journal": "Synthetic Journal",
            },
        },
    )

    async def _fake_sync_pubmed_observations(
        *,
        space_id: UUID,
        owner_id: UUID,
        documents: list[HarnessDocumentRecord],
        pipeline_run_id: str | None = None,
    ) -> research_init_runtime._ObservationBridgeBatchResult:
        del space_id, owner_id, pipeline_run_id
        return research_init_runtime._ObservationBridgeBatchResult(
            document_results={
                document.id: research_init_runtime._PubMedObservationSyncResult(
                    source_document_id=document.id,
                    status="extracted",
                    observations_created=1,
                    entities_created=0,
                    seed_entity_ids=(),
                    errors=(),
                )
                for document in documents
            },
            seed_entity_ids=(),
            errors=(),
        )

    async def _fake_extract_relation_candidates_with_diagnostics(
        text: str,
        *,
        space_context: str,
    ) -> tuple[list[dict[str, str]], DocumentCandidateExtractionDiagnostics]:
        del text, space_context
        return [], DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="fallback_error",
            llm_candidate_error="LLM candidate extraction timed out",
            fallback_candidate_count=0,
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_build_pubmed_queries",
        lambda _objective, _seed_terms: [],
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_resolve_bootstrap_source_type",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "_sync_pubmed_documents_into_shared_observation_ingestion",
        _fake_sync_pubmed_observations,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_diagnostics",
        _fake_extract_relation_candidates_with_diagnostics,
    )

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 expression evidence",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "marrvel": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "pdf": False,
            "text": False,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    result = await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Research init",
        objective="Investigate MED13 expression evidence",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={
            "pubmed": True,
            "marrvel": False,
            "mondo": False,
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "pdf": False,
            "text": False,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    updated_document = document_store.get_document(
        space_id=space_id,
        document_id=pubmed_document.id,
    )

    assert result.run.status == "completed"
    assert result.errors == []
    assert updated_document is not None
    assert updated_document.extraction_status == "completed"
    assert updated_document.metadata["observation_bridge_status"] == "extracted"


@pytest.mark.asyncio
async def test_sync_pubmed_observation_bridge_uses_combined_postgres_search_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    harness_document = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="Search-path regression paper",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="search-path-sha",
        byte_size=42,
        page_count=None,
        text_content="MED13 regulates mediator complex recruitment.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="search-path-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["MED13 mediator"],
            "pubmed": {"pmid": "77777"},
        },
    )

    class _FakeSession:
        def __init__(self) -> None:
            self.bind = type(
                "_Bind",
                (),
                {"dialect": type("_Dialect", (), {"name": "postgresql"})()},
            )()
            self.executed_statements: list[str] = []

        def execute(self, statement: object, *_args: object, **_kwargs: object) -> None:
            self.executed_statements.append(str(statement))

    class _FakeSourceDocumentRepository:
        def __init__(self, session: object) -> None:
            assert session is fake_session
            self._documents_by_id: dict[UUID, SourceDocument] = {}

        def upsert_many(
            self,
            documents: list[SourceDocument],
        ) -> list[SourceDocument]:
            for document in documents:
                self._documents_by_id[document.id] = document
            return documents

        def list_pending_extraction(
            self,
            *,
            limit: int = 100,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
        ) -> list[SourceDocument]:
            documents = list(self._documents_by_id.values())
            filtered = [
                document
                for document in documents
                if (source_id is None or document.source_id == source_id)
                and (
                    research_space_id is None
                    or document.research_space_id == research_space_id
                )
                and (
                    ingestion_job_id is None
                    or document.ingestion_job_id == ingestion_job_id
                )
                and (
                    source_type is None
                    or document.source_type.value.casefold() == source_type.casefold()
                )
                and document.extraction_status == DocumentExtractionStatus.PENDING
            ]
            return filtered[: max(limit, 1)]

        def upsert(self, document: SourceDocument) -> SourceDocument:
            self._documents_by_id[document.id] = document
            return document

        def get_by_id(self, document_id: UUID) -> SourceDocument | None:
            return self._documents_by_id.get(document_id)

    class _FakeEntityRecognitionService:
        def __init__(self, repository: _FakeSourceDocumentRepository) -> None:
            self._repository = repository

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            assert pipeline_run_id == "search-path-run"
            pending_documents = self._repository.list_pending_extraction(
                limit=limit,
                source_id=source_id,
                research_space_id=research_space_id,
                ingestion_job_id=ingestion_job_id,
                source_type=source_type,
            )
            for source_document in pending_documents:
                self._repository.upsert(
                    source_document.model_copy(
                        update={
                            "extraction_status": DocumentExtractionStatus.EXTRACTED,
                            "metadata": {
                                **source_document.metadata,
                                "entity_recognition_ingestion_observations_created": 1,
                                "entity_recognition_ingestion_entities_created": 1,
                                "entity_recognition_ingestion_errors": [],
                            },
                        },
                    ),
                )

            class _Summary:
                derived_graph_seed_entity_ids = ("seed-1",)
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    def _fake_create_entity_recognition_service(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _FakeEntityRecognitionService:
        assert session is fake_session
        assert isinstance(
            source_document_repository,
            _FakeSourceDocumentRepository,
        )
        assert isinstance(
            pipeline_run_event_repository,
            research_init_observation_bridge._NoOpPipelineRunEventRepository,
        )
        return _FakeEntityRecognitionService(source_document_repository)

    fake_session = _FakeSession()

    monkeypatch.setenv("GRAPH_DB_SCHEMA", "graph_runtime")
    monkeypatch.setenv("ARTANA_EVIDENCE_API_DB_SCHEMA", "artana_evidence_api")
    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(fake_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "build_source_document_repository",
        _FakeSourceDocumentRepository,
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create_entity_recognition_service,
    )

    result = await research_init_runtime._sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[harness_document],
        pipeline_run_id="search-path-run",
    )

    assert result.errors == ()
    assert result.seed_entity_ids == ("seed-1",)
    assert result.document_results[harness_document.id].status == "extracted"
    assert fake_session.executed_statements == [
        'SET search_path TO "graph_runtime", "artana_evidence_api", public',
    ]


def test_observation_bridge_postgres_search_path_keeps_public_last() -> None:
    assert (
        research_init_observation_bridge._observation_bridge_postgres_search_path(
            graph_schema="graph_runtime",
            harness_schema="artana_evidence_api",
        )
        == '"graph_runtime", "artana_evidence_api", public'
    )
    assert (
        research_init_observation_bridge._observation_bridge_postgres_search_path(
            graph_schema="public",
            harness_schema="artana_evidence_api",
        )
        == '"artana_evidence_api", public'
    )
    assert (
        research_init_observation_bridge._observation_bridge_postgres_search_path(
            graph_schema="graph_runtime",
            harness_schema="public",
        )
        == '"graph_runtime", public'
    )


@pytest.mark.asyncio
async def test_sync_pubmed_observation_bridge_persists_source_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy import text as sa_text
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker

    bridge_engine = create_engine("sqlite:///:memory:")
    with bridge_engine.connect() as _conn:
        _conn.execute(
            sa_text(
                "CREATE TABLE source_documents ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  research_space_id VARCHAR(36),"
                "  source_id VARCHAR(36) NOT NULL,"
                "  ingestion_job_id VARCHAR(36),"
                "  external_record_id VARCHAR(255) NOT NULL,"
                "  source_type VARCHAR(32) NOT NULL,"
                "  document_format VARCHAR(64) NOT NULL DEFAULT 'json',"
                "  raw_storage_key VARCHAR(500),"
                "  enriched_storage_key VARCHAR(500),"
                "  content_hash VARCHAR(128),"
                "  content_length_chars INTEGER,"
                "  enrichment_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  enrichment_method VARCHAR(64),"
                "  enrichment_agent_run_id VARCHAR(255),"
                "  extraction_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  extraction_agent_run_id VARCHAR(255),"
                "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
                "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  UNIQUE(source_id, external_record_id)"
                ")",
            ),
        )
        _conn.commit()
    bridge_session = sa_sessionmaker(
        bind=bridge_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )()

    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    harness_document = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="COVID-19 host interaction",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="pubmed-sha",
        byte_size=42,
        page_count=None,
        text_content="ACE2 is implicated in SARS-CoV-2 host entry.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="existing-ingestion-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["COVID-19 ACE2"],
            "pubmed": {
                "pmid": "12345",
                "journal": "Synthetic Journal",
            },
        },
    )

    class _FakeEntityRecognitionService:
        def __init__(
            self,
            repository: SqlAlchemySourceDocumentRepository,
        ) -> None:
            self._repository = repository

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            assert limit == 1
            assert (
                source_id
                == research_init_observation_bridge._research_init_pubmed_source_id(
                    space_id,
                )
            )
            assert research_space_id == space_id
            assert ingestion_job_id is not None
            assert source_type == "pubmed"
            assert pipeline_run_id == "research-init-run"

            pending_documents = self._repository.list_pending_extraction(
                limit=limit,
                source_id=source_id,
                research_space_id=research_space_id,
                ingestion_job_id=ingestion_job_id,
                source_type=source_type,
            )
            assert len(pending_documents) == 1
            source_document = pending_documents[0]
            assert source_document.document_format == DocumentFormat.MEDLINE_XML
            assert source_document.external_record_id == "pubmed:pmid:12345"
            raw_record = source_document.metadata["raw_record"]
            assert raw_record["pubmed_id"] == "12345"
            assert raw_record["source_queries"] == ["COVID-19 ACE2"]

            self._repository.upsert(
                source_document.model_copy(
                    update={
                        "extraction_status": DocumentExtractionStatus.EXTRACTED,
                        "metadata": {
                            **source_document.metadata,
                            "entity_recognition_ingestion_observations_created": 1,
                            "entity_recognition_ingestion_entities_created": 1,
                            "entity_recognition_ingestion_errors": [],
                        },
                    },
                ),
            )

            class _Summary:
                derived_graph_seed_entity_ids = ("seed-1",)
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    def _fake_create_entity_recognition_service(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _FakeEntityRecognitionService:
        assert session is bridge_session
        assert isinstance(
            source_document_repository,
            SqlAlchemySourceDocumentRepository,
        )
        assert isinstance(
            pipeline_run_event_repository,
            research_init_observation_bridge._NoOpPipelineRunEventRepository,
        )
        return _FakeEntityRecognitionService(source_document_repository)

    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(bridge_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create_entity_recognition_service,
    )

    result = await research_init_runtime._sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[harness_document],
        pipeline_run_id="research-init-run",
    )

    assert result.errors == ()
    assert result.seed_entity_ids == ("seed-1",)
    assert result.document_results[harness_document.id].status == "extracted"
    assert result.document_results[harness_document.id].observations_created == 1
    assert result.document_results[harness_document.id].entities_created == 1

    persisted_count = bridge_session.execute(
        sa_text("SELECT count(*) FROM source_documents"),
    ).scalar_one()
    assert persisted_count == 1, "source document should be persisted in the database"


@pytest.mark.asyncio
async def test_sync_pubmed_observation_bridge_caps_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy import text as sa_text
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker

    bridge_engine = create_engine("sqlite:///:memory:")
    with bridge_engine.connect() as _conn:
        _conn.execute(
            sa_text(
                "CREATE TABLE source_documents ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  research_space_id VARCHAR(36),"
                "  source_id VARCHAR(36) NOT NULL,"
                "  ingestion_job_id VARCHAR(36),"
                "  external_record_id VARCHAR(255) NOT NULL,"
                "  source_type VARCHAR(32) NOT NULL,"
                "  document_format VARCHAR(64) NOT NULL DEFAULT 'json',"
                "  raw_storage_key VARCHAR(500),"
                "  enriched_storage_key VARCHAR(500),"
                "  content_hash VARCHAR(128),"
                "  content_length_chars INTEGER,"
                "  enrichment_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  enrichment_method VARCHAR(64),"
                "  enrichment_agent_run_id VARCHAR(255),"
                "  extraction_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  extraction_agent_run_id VARCHAR(255),"
                "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
                "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  UNIQUE(source_id, external_record_id)"
                ")",
            ),
        )
        _conn.commit()
    bridge_session = sa_sessionmaker(
        bind=bridge_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )()

    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    run_registry = HarnessRunRegistry()
    from artana_evidence_api import research_init_source_enrichment

    artifact_store = HarnessArtifactStore()

    parent_run = run_registry.create_run(
        space_id=str(space_id),
        harness_id="research-init",
        title="Bridge timeout caps",
        input_payload={},
        graph_service_status="healthy",
        graph_service_version="test",
    )
    artifact_store.seed_for_run(run=parent_run)

    harness_document = research_init_source_enrichment._create_enrichment_document(
        space_id=space_id,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        title="PubMed doc",
        source_type="pubmed",
        text_content="MED13 drives developmental delay.",
        metadata={
            "source": "research-init-pubmed",
            "pubmed": {"pmid": "11111111", "doi": "10.1/example"},
        },
    )
    assert harness_document is not None

    class _FakeEntityRecognitionService:
        def __init__(self, repository: SqlAlchemySourceDocumentRepository) -> None:
            self._repository = repository
            self._agent_timeout_seconds = 180.0
            self._extraction_stage_timeout_seconds = 300.0

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None,
            ingestion_job_id: UUID | None = None,
            research_space_id: UUID | None = None,
            source_type: str | None = None,
            model_id: str | None = None,
            shadow_mode: bool | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            del (
                limit,
                source_id,
                ingestion_job_id,
                research_space_id,
                source_type,
                model_id,
                shadow_mode,
            )
            stored = self._repository.list_pending_extraction(limit=10)
            assert len(stored) == 1
            document = stored[0]
            updated = document.model_copy(
                update={
                    "extraction_status": DocumentExtractionStatus.EXTRACTED,
                    "metadata": {
                        **document.metadata,
                        "pipeline_run_id": pipeline_run_id,
                        "entity_recognition_ingestion_observations_created": 1,
                        "entity_recognition_ingestion_entities_created": 1,
                    },
                },
            )
            self._repository.upsert(updated)

            class _Summary:
                derived_graph_seed_entity_ids = ("seed-1",)
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    observed_service: _FakeEntityRecognitionService | None = None

    def _fake_create_entity_recognition_service(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _FakeEntityRecognitionService:
        del pipeline_run_event_repository
        assert session is bridge_session
        assert isinstance(
            source_document_repository,
            SqlAlchemySourceDocumentRepository,
        )
        nonlocal observed_service
        observed_service = _FakeEntityRecognitionService(source_document_repository)
        return observed_service

    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(bridge_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create_entity_recognition_service,
    )

    result = await research_init_runtime._sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[harness_document],
        pipeline_run_id="research-init-run",
    )

    assert observed_service is not None
    assert observed_service._agent_timeout_seconds == 90.0
    assert observed_service._extraction_stage_timeout_seconds == 120.0
    assert result.document_results[harness_document.id].status == "extracted"


@pytest.mark.asyncio
async def test_sync_pubmed_observation_bridge_times_out_batch_and_marks_documents_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy import text as sa_text
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker

    bridge_engine = create_engine("sqlite:///:memory:")
    with bridge_engine.connect() as _conn:
        _conn.execute(
            sa_text(
                "CREATE TABLE source_documents ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  research_space_id VARCHAR(36),"
                "  source_id VARCHAR(36) NOT NULL,"
                "  ingestion_job_id VARCHAR(36),"
                "  external_record_id VARCHAR(255) NOT NULL,"
                "  source_type VARCHAR(32) NOT NULL,"
                "  document_format VARCHAR(64) NOT NULL DEFAULT 'json',"
                "  raw_storage_key VARCHAR(500),"
                "  enriched_storage_key VARCHAR(500),"
                "  content_hash VARCHAR(128),"
                "  content_length_chars INTEGER,"
                "  enrichment_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  enrichment_method VARCHAR(64),"
                "  enrichment_agent_run_id VARCHAR(255),"
                "  extraction_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  extraction_agent_run_id VARCHAR(255),"
                "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
                "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  UNIQUE(source_id, external_record_id)"
                ")",
            ),
        )
        _conn.commit()
    bridge_session = sa_sessionmaker(
        bind=bridge_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )()

    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    harness_document = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="Timed out PubMed bridge paper",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="pubmed-timeout-sha",
        byte_size=42,
        page_count=None,
        text_content="MED13 regulates mediator complex recruitment.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="bridge-timeout-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["MED13 mediator"],
            "pubmed": {"pmid": "123123"},
        },
    )

    class _SlowEntityRecognitionService:
        def __init__(
            self,
            repository: SqlAlchemySourceDocumentRepository,
        ) -> None:
            self._repository = repository

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            del (
                limit,
                source_id,
                research_space_id,
                ingestion_job_id,
                source_type,
                pipeline_run_id,
            )
            stored = self._repository.list_pending_extraction(limit=10)
            assert len(stored) == 1
            await asyncio.sleep(0.05)

            class _Summary:
                derived_graph_seed_entity_ids = ()
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    def _fake_create_entity_recognition_service(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _SlowEntityRecognitionService:
        del pipeline_run_event_repository
        assert session is bridge_session
        assert isinstance(
            source_document_repository,
            SqlAlchemySourceDocumentRepository,
        )
        return _SlowEntityRecognitionService(source_document_repository)

    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(bridge_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS",
        0.01,
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create_entity_recognition_service,
    )

    result = await research_init_runtime._sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[harness_document],
        pipeline_run_id="research-init-timeout-run",
    )

    assert result.seed_entity_ids == ()
    assert result.document_results[harness_document.id].status == "failed"
    assert result.document_results[harness_document.id].errors == (
        "Observation bridge batch timed out after 0.0s",
        "observation_bridge_batch_timeout",
    )
    assert result.errors == ("Observation bridge batch timed out after 0.0s",)


@pytest.mark.asyncio
async def test_sync_file_upload_observation_bridge_persists_source_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy import text as sa_text
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker

    bridge_engine = create_engine("sqlite:///:memory:")
    with bridge_engine.connect() as _conn:
        _conn.execute(
            sa_text(
                "CREATE TABLE source_documents ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  research_space_id VARCHAR(36),"
                "  source_id VARCHAR(36) NOT NULL,"
                "  ingestion_job_id VARCHAR(36),"
                "  external_record_id VARCHAR(255) NOT NULL,"
                "  source_type VARCHAR(32) NOT NULL,"
                "  document_format VARCHAR(64) NOT NULL DEFAULT 'json',"
                "  raw_storage_key VARCHAR(500),"
                "  enriched_storage_key VARCHAR(500),"
                "  content_hash VARCHAR(128),"
                "  content_length_chars INTEGER,"
                "  enrichment_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  enrichment_method VARCHAR(64),"
                "  enrichment_agent_run_id VARCHAR(255),"
                "  extraction_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  extraction_agent_run_id VARCHAR(255),"
                "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
                "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  UNIQUE(source_id, external_record_id)"
                ")",
            ),
        )
        _conn.commit()
    bridge_session = sa_sessionmaker(
        bind=bridge_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )()

    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()
    text_document = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="Research note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="text-sha",
        byte_size=12,
        page_count=None,
        text_content="MED13 supports developmental phenotypes.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="text-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )
    pdf_document = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="Uploaded PDF",
        source_type="pdf",
        filename="paper.pdf",
        media_type="application/pdf",
        sha256="pdf-sha",
        byte_size=24,
        page_count=3,
        text_content="PDF full text about MED13.",
        raw_storage_key="raw/pdf",
        enriched_storage_key="enriched/pdf",
        ingestion_run_id="pdf-upload-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    class _FakeEntityRecognitionService:
        def __init__(
            self,
            repository: SqlAlchemySourceDocumentRepository,
        ) -> None:
            self._repository = repository

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            assert limit == 2
            assert (
                source_id
                == research_init_observation_bridge._research_init_upload_source_id(
                    space_id,
                )
            )
            assert research_space_id == space_id
            assert ingestion_job_id is not None
            assert source_type == "file_upload"
            assert pipeline_run_id == "research-init-upload-run"

            pending_documents = self._repository.list_pending_extraction(
                limit=limit,
                source_id=source_id,
                research_space_id=research_space_id,
                ingestion_job_id=ingestion_job_id,
                source_type=source_type,
            )
            assert len(pending_documents) == 2
            pending_by_id = {
                str(document.id): document for document in pending_documents
            }
            assert (
                pending_by_id[text_document.id].document_format == DocumentFormat.TEXT
            )
            assert pending_by_id[pdf_document.id].document_format == DocumentFormat.PDF
            assert (
                pending_by_id[pdf_document.id].metadata["raw_record"][
                    "full_text_source"
                ]
                == "research_init_pdf_enrichment"
            )

            for source_document in pending_documents:
                self._repository.upsert(
                    source_document.model_copy(
                        update={
                            "extraction_status": DocumentExtractionStatus.EXTRACTED,
                            "metadata": {
                                **source_document.metadata,
                                "entity_recognition_ingestion_observations_created": 1,
                                "entity_recognition_ingestion_entities_created": 1,
                                "entity_recognition_ingestion_errors": [],
                            },
                        },
                    ),
                )

            class _Summary:
                derived_graph_seed_entity_ids = ("seed-text", "seed-pdf")
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    def _fake_create_entity_recognition_service(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _FakeEntityRecognitionService:
        assert session is bridge_session
        assert isinstance(
            source_document_repository,
            SqlAlchemySourceDocumentRepository,
        )
        assert isinstance(
            pipeline_run_event_repository,
            research_init_observation_bridge._NoOpPipelineRunEventRepository,
        )
        return _FakeEntityRecognitionService(source_document_repository)

    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(bridge_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create_entity_recognition_service,
    )

    result = await research_init_runtime._sync_file_upload_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[text_document, pdf_document],
        pipeline_run_id="research-init-upload-run",
    )

    assert result.errors == ()
    assert result.seed_entity_ids == ("seed-text", "seed-pdf")
    assert result.document_results[text_document.id].status == "extracted"
    assert result.document_results[pdf_document.id].status == "extracted"
    assert result.document_results[text_document.id].observations_created == 1
    assert result.document_results[pdf_document.id].observations_created == 1

    persisted_count = bridge_session.execute(
        sa_text("SELECT count(*) FROM source_documents"),
    ).scalar_one()
    assert persisted_count == 2, "both source documents should be persisted"


@pytest.mark.asyncio
async def test_observation_bridge_persistence_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a research-init bridge run must leave behind persisted
    source_documents *and* report observations_created > 0 for each document.

    This guards the P0.6 convergence requirement that the bootstrap flow
    materializes graph_runtime.source_documents alongside observations.
    """
    from sqlalchemy import create_engine
    from sqlalchemy import text as sa_text
    from sqlalchemy.orm import sessionmaker as sa_sessionmaker

    bridge_engine = create_engine("sqlite:///:memory:")
    with bridge_engine.connect() as _conn:
        _conn.execute(
            sa_text(
                "CREATE TABLE source_documents ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  research_space_id VARCHAR(36),"
                "  source_id VARCHAR(36) NOT NULL,"
                "  ingestion_job_id VARCHAR(36),"
                "  external_record_id VARCHAR(255) NOT NULL,"
                "  source_type VARCHAR(32) NOT NULL,"
                "  document_format VARCHAR(64) NOT NULL DEFAULT 'json',"
                "  raw_storage_key VARCHAR(500),"
                "  enriched_storage_key VARCHAR(500),"
                "  content_hash VARCHAR(128),"
                "  content_length_chars INTEGER,"
                "  enrichment_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  enrichment_method VARCHAR(64),"
                "  enrichment_agent_run_id VARCHAR(255),"
                "  extraction_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
                "  extraction_agent_run_id VARCHAR(255),"
                "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
                "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "  UNIQUE(source_id, external_record_id)"
                ")",
            ),
        )
        _conn.commit()
    bridge_session = sa_sessionmaker(
        bind=bridge_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )()

    space_id = uuid4()
    owner_id = uuid4()
    document_store = HarnessDocumentStore()

    pubmed_doc = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="Regression PubMed paper",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="reg-pubmed-sha",
        byte_size=50,
        page_count=None,
        text_content="MED13 interacts with the mediator complex in neurons.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="reg-pubmed-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["MED13 mediator"],
            "pubmed": {"pmid": "99999"},
        },
    )
    text_doc = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="Regression text note",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="reg-text-sha",
        byte_size=30,
        page_count=None,
        text_content="CDK8 phosphorylation in neural progenitors.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="reg-text-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={},
    )

    entities_created_per_doc = 2
    observations_created_per_doc = 3

    class _FakeEntityRecognitionService:
        def __init__(self, repository: SqlAlchemySourceDocumentRepository) -> None:
            self._repository = repository

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            pending = self._repository.list_pending_extraction(
                limit=limit,
                source_id=source_id,
                research_space_id=research_space_id,
                ingestion_job_id=ingestion_job_id,
                source_type=source_type,
            )
            for doc in pending:
                self._repository.upsert(
                    doc.model_copy(
                        update={
                            "extraction_status": DocumentExtractionStatus.EXTRACTED,
                            "metadata": {
                                **doc.metadata,
                                "entity_recognition_ingestion_observations_created": observations_created_per_doc,
                                "entity_recognition_ingestion_entities_created": entities_created_per_doc,
                                "entity_recognition_ingestion_errors": [],
                            },
                        },
                    ),
                )

            class _Summary:
                derived_graph_seed_entity_ids = ("reg-seed-1", "reg-seed-2")
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    def _fake_create(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _FakeEntityRecognitionService:
        del pipeline_run_event_repository
        assert session is bridge_session
        assert isinstance(
            source_document_repository,
            SqlAlchemySourceDocumentRepository,
        )
        return _FakeEntityRecognitionService(source_document_repository)

    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(bridge_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create,
    )

    pubmed_result = await research_init_runtime._sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[pubmed_doc],
        pipeline_run_id="reg-run-pubmed",
    )
    upload_result = await research_init_runtime._sync_file_upload_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[text_doc],
        pipeline_run_id="reg-run-upload",
    )

    # --- Core regression assertions ---
    source_document_count = bridge_session.execute(
        sa_text("SELECT count(*) FROM source_documents"),
    ).scalar_one()
    assert source_document_count > 0, "source_documents must be persisted"

    total_observations = sum(
        r.observations_created for r in pubmed_result.document_results.values()
    ) + sum(r.observations_created for r in upload_result.document_results.values())
    assert total_observations > 0, "observations must be reported as created"

    total_entities = sum(
        r.entities_created for r in pubmed_result.document_results.values()
    ) + sum(r.entities_created for r in upload_result.document_results.values())
    assert total_entities > 0, "entities must be reported as created"

    assert source_document_count == 2, "one source_document per input document"
    assert total_observations == observations_created_per_doc * 2
    assert total_entities == entities_created_per_doc * 2


# ── _build_source_results unit tests ──────────────────────────────────────────


def test_build_source_results_mondo_pending_when_enabled() -> None:
    """mondo status is 'pending' when mondo=True in sources."""
    result = research_init_runtime._build_source_results(sources={"mondo": True})
    assert result["mondo"]["status"] == "pending"
    assert result["mondo"]["selected"] is True


def test_build_source_results_mondo_skipped_when_disabled() -> None:
    """mondo status is 'skipped' when mondo=False in sources."""
    result = research_init_runtime._build_source_results(sources={"mondo": False})
    assert result["mondo"]["status"] == "skipped"
    assert result["mondo"]["selected"] is False


def test_build_source_results_mondo_pending_by_default() -> None:
    """mondo defaults to pending (True) when not specified in sources."""
    result = research_init_runtime._build_source_results(sources={})
    assert result["mondo"]["status"] == "pending"
    assert result["mondo"]["selected"] is True


def test_build_source_results_includes_all_expected_source_keys() -> None:
    """_build_source_results returns entries for all known sources."""
    result = research_init_runtime._build_source_results(sources={})
    expected_keys = set(research_plan_source_keys())
    assert set(result.keys()) == expected_keys


def test_build_source_results_includes_registry_metadata() -> None:
    """Research-plan source summaries use the public source registry language."""
    result = research_init_runtime._build_source_results(sources={})

    assert result["pubmed"]["source_key"] == "pubmed"
    assert result["pubmed"]["display_name"] == "PubMed"
    assert SourceCapability.SEARCH.value in result["pubmed"]["capabilities"]
    assert result["pubmed"]["direct_search_enabled"] is True
    assert result["clinvar"]["direct_search_enabled"] is True
    assert result["clinical_trials"]["direct_search_enabled"] is True
    assert result["uniprot"]["direct_search_enabled"] is True
    assert result["alphafold"]["direct_search_enabled"] is True
    assert result["gnomad"]["direct_search_enabled"] is True
    assert result["drugbank"]["direct_search_enabled"] is True
    assert result["mgi"]["direct_search_enabled"] is True
    assert result["zfin"]["direct_search_enabled"] is True
    assert result["orphanet"]["direct_search_enabled"] is True
    assert result["mondo"]["direct_search_enabled"] is False
    assert result["clinvar"]["research_plan_enabled"] is True
    assert "source_result_capture" in result["clinvar"]
    assert "proposal_flow" in result["clinvar"]


def test_build_source_results_uniprot_skipped_by_default() -> None:
    """uniprot defaults to skipped (False) when not specified."""
    result = research_init_runtime._build_source_results(sources={})
    assert result["uniprot"]["status"] == "skipped"
    assert result["uniprot"]["selected"] is False


def test_build_source_results_gnomad_skipped_by_default() -> None:
    """gnomad defaults to skipped (False) when not specified."""
    result = research_init_runtime._build_source_results(sources={})
    assert result["gnomad"]["status"] == "skipped"
    assert result["gnomad"]["selected"] is False


def test_build_source_results_orphanet_skipped_by_default() -> None:
    """orphanet defaults to skipped (False) when not specified."""
    result = research_init_runtime._build_source_results(sources={})
    assert result["orphanet"]["status"] == "skipped"
    assert result["orphanet"]["selected"] is False
    assert result["orphanet"]["records_processed"] == 0


def test_source_result_counters_fall_back_for_registered_search_sources() -> None:
    assert research_init_source_results._source_result_counters("orphanet") == {
        "records_processed": 0,
    }


def test_source_result_counters_reject_unknown_sources() -> None:
    with pytest.raises(ValueError, match="Unknown source key"):
        research_init_source_results._source_result_counters("custom_source")


def test_build_source_results_gnomad_pending_when_enabled() -> None:
    """gnomad status is 'pending' when gnomad=True in sources."""
    result = research_init_runtime._build_source_results(sources={"gnomad": True})
    assert result["gnomad"]["status"] == "pending"
    assert result["gnomad"]["selected"] is True


def test_build_source_results_uniprot_pending_when_enabled() -> None:
    """uniprot status is 'pending' when uniprot=True in sources."""
    result = research_init_runtime._build_source_results(sources={"uniprot": True})
    assert result["uniprot"]["status"] == "pending"
    assert result["uniprot"]["selected"] is True


def test_research_init_result_payload_includes_alias_yield_rollup() -> None:
    """Final run payload surfaces backend-derived alias-yield counts."""
    source_results = research_init_runtime._build_source_results(
        sources={"drugbank": True, "hgnc": True},
    )
    source_results["drugbank"]["alias_candidates_count"] = 5
    source_results["drugbank"]["aliases_persisted"] = 4
    source_results["drugbank"]["aliases_skipped"] = 1
    source_results["drugbank"]["alias_entities_touched"] = 1
    source_results["hgnc"]["alias_candidates_count"] = 3
    source_results["hgnc"]["aliases_persisted"] = 3
    source_results["hgnc"]["aliases_skipped"] = 0
    source_results["hgnc"]["alias_entities_touched"] = 1

    payload = research_init_runtime._research_init_result_payload(
        run_id="run-alias-yield",
        selected_sources={"drugbank": True, "hgnc": True},
        source_results=source_results,
        pubmed_results=[],
        documents_ingested=0,
        proposal_count=0,
        research_state=None,
        pending_questions=[],
        errors=[],
    )

    serialized_sources = payload["source_results"]
    assert isinstance(serialized_sources, dict)
    alias_yield = serialized_sources["alias_yield"]
    assert isinstance(alias_yield, dict)
    totals = alias_yield["totals"]
    sources = alias_yield["sources"]
    assert isinstance(totals, dict)
    assert isinstance(sources, dict)
    assert totals["alias_candidates_count"] == 8
    assert totals["aliases_persisted"] == 7
    assert sources["drugbank"]["aliases_skipped"] == 1


# ── Deferred-source marking unit tests ────────────────────────────────────────


def test_pending_sources_are_marked_deferred_at_end_of_run() -> None:
    """Sources still 'pending' at the end of execute_research_init_run are marked 'deferred'.

    This exercises the loop:
        for pending_source in ("clinvar", "drugbank", "alphafold", "gnomad", ...):
            if source_results.get(pending_source, {}).get("status") == "pending":
                source_results[pending_source]["status"] = "deferred"

    We replicate the loop logic directly so that if the set of sources changes
    in the implementation the test will surface the discrepancy.
    """
    # Simulate source_results as produced by _build_source_results when all
    # non-default-on sources are explicitly enabled.
    source_results = research_init_runtime._build_source_results(
        sources={
            "pubmed": True,
            "marrvel": True,
            "clinvar": True,
            "mondo": True,
            "pdf": True,
            "text": True,
            "drugbank": True,
            "alphafold": True,
            "gnomad": True,
            "uniprot": True,
            "hgnc": True,
            "clinical_trials": True,
            "mgi": True,
            "zfin": True,
            "orphanet": True,
        },
    )

    # All sources start as "pending" when enabled.
    for key in source_results:
        assert source_results[key]["status"] == "pending", (
            f"Expected {key!r} to start as 'pending', got {source_results[key]['status']!r}"
        )

    # Apply the deferred-marking loop exactly as in complete_research_init_run.
    pending_sources = research_init_completion_runtime._pending_deferred_source_keys(
        source_results,
    )
    for pending_source in pending_sources:
        if source_results.get(pending_source, {}).get("status") == "pending":
            source_results[pending_source]["status"] = "deferred"

    # These sources should now be "deferred" since we never ran them above.
    assert source_results["clinvar"]["status"] == "deferred"
    assert source_results["drugbank"]["status"] == "deferred"
    assert source_results["alphafold"]["status"] == "deferred"
    assert source_results["gnomad"]["status"] == "deferred"
    assert source_results["uniprot"]["status"] == "deferred"
    assert source_results["hgnc"]["status"] == "deferred"
    assert source_results["clinical_trials"]["status"] == "deferred"
    assert source_results["mgi"]["status"] == "deferred"
    assert source_results["zfin"]["status"] == "deferred"
    assert source_results["orphanet"]["status"] == "deferred"

    # Sources outside the deferred loop are unaffected.
    assert source_results["pubmed"]["status"] == "pending"
    assert source_results["marrvel"]["status"] == "pending"
    assert source_results["mondo"]["status"] == "pending"
    assert source_results["pdf"]["status"] == "pending"
    assert source_results["text"]["status"] == "pending"


def test_skipped_sources_are_not_changed_to_deferred() -> None:
    """Sources with status='skipped' are NOT changed to 'deferred'."""
    source_results = research_init_runtime._build_source_results(
        sources={
            "clinvar": False,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "orphanet": False,
        },
    )

    # All these are skipped because they are disabled.
    for key in (
        "clinvar",
        "drugbank",
        "alphafold",
        "gnomad",
        "uniprot",
        "hgnc",
        "orphanet",
    ):
        assert source_results[key]["status"] == "skipped"

    # Apply the loop.
    pending_sources = research_init_completion_runtime._pending_deferred_source_keys(
        source_results,
    )
    for pending_source in pending_sources:
        if source_results.get(pending_source, {}).get("status") == "pending":
            source_results[pending_source]["status"] = "deferred"

    # Still skipped — not upgraded to deferred.
    for key in (
        "clinvar",
        "drugbank",
        "alphafold",
        "gnomad",
        "uniprot",
        "hgnc",
        "orphanet",
    ):
        assert source_results[key]["status"] == "skipped"


async def test_run_structured_enrichment_source_times_out_marrvel_and_keeps_run_moving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS", "0.01")

    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = uuid4()
    parent_run = run_registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Structured enrichment timeout test",
        input_payload={"objective": "Investigate BRCA1"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    source_results = research_init_runtime._build_source_results(
        sources={"marrvel": True},
    )
    enrichment_documents: list[HarnessDocumentRecord] = []
    errors: list[str] = []

    async def _slow_marrvel_runner(**_: object) -> object:
        await asyncio.sleep(0.05)
        return object()

    created = await research_init_runtime._run_structured_enrichment_source(
        source_key="marrvel",
        source_label="MARRVEL",
        log_message="Phase 2b: running MARRVEL enrichment for space %s",
        runner=_slow_marrvel_runner,
        space_id=space_id,
        seed_terms=["BRCA1"],
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        proposal_store=proposal_store,
        run_id=parent_run.id,
        objective="Investigate BRCA1",
        source_results=source_results,
        enrichment_documents=enrichment_documents,
        errors=errors,
        source_caps=ResearchInitSourceCaps(),
    )

    assert created == 0
    assert enrichment_documents == []
    assert source_results["marrvel"]["status"] == "failed"
    assert source_results["marrvel"]["failure_reason"] == "timeout"
    assert source_results["marrvel"]["timeout_seconds"] == 0.01
    assert errors == ["MARRVEL enrichment timed out after 0.01s"]


async def test_run_structured_enrichment_source_passes_source_caps_to_runner() -> None:
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = uuid4()
    parent_run = run_registry.create_run(
        space_id=space_id,
        harness_id="research-init",
        title="Structured caps test",
        input_payload={"objective": "Investigate BRCA1"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    expected_caps = ResearchInitSourceCaps(
        max_terms_per_source=2,
        clinvar_max_results=8,
    )
    captured_caps: list[ResearchInitSourceCaps] = []

    async def _runner(**kwargs: object) -> SourceEnrichmentResult:
        captured_caps.append(cast("ResearchInitSourceCaps", kwargs["source_caps"]))
        return SourceEnrichmentResult(source_key="clinvar")

    created = await research_init_runtime._run_structured_enrichment_source(
        source_key="clinvar",
        source_label="ClinVar",
        log_message="Phase 2b: running ClinVar enrichment for space %s",
        runner=_runner,
        space_id=space_id,
        seed_terms=["BRCA1"],
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        proposal_store=proposal_store,
        run_id=parent_run.id,
        objective="Investigate BRCA1",
        source_results=research_init_runtime._build_source_results(
            sources={"clinvar": True},
        ),
        enrichment_documents=[],
        errors=[],
        source_caps=expected_caps,
    )

    assert created == 0
    assert captured_caps == [expected_caps]


@pytest.mark.asyncio
async def test_execute_research_init_marks_pending_sources_as_deferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end verify source status after run.

    Enables clinvar/drugbank/alphafold/uniprot/hgnc.  Clinvar, drugbank, and alphafold
    now execute inline in Phase 2b (structured enrichment) and complete
    successfully (even with empty seed terms).  Uniprot and HGNC have no
    research-init enrichment handler yet, so they remain 'pending' and the
    deferred-marking loop sets them to 'deferred'.
    """
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

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        ).create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        ).upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )

    class _StubOntologyIngestionSummary:
        def __init__(self) -> None:
            self.terms_imported = 0
            self.hierarchy_edges_created = 0
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

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Deferred sources test",
        objective="Test deferred source marking",
        seed_terms=[],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
            "uniprot": True,
            "hgnc": True,
        },
        max_depth=1,
        max_hypotheses=1,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Deferred sources test",
        objective="Test deferred source marking",
        seed_terms=[],
        max_depth=1,
        max_hypotheses=1,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
            "uniprot": True,
            "hgnc": True,
        },
        execution_services=services,
        existing_run=queued_run,
    )

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    run_record = services.run_registry.get_run(space_id=space_id, run_id=queued_run.id)
    assert run_record is not None
    assert run_record.status == "completed"
    source_results = workspace.snapshot["source_results"]

    # Clinvar/drugbank/alphafold now execute in Phase 2b (structured enrichment).
    assert source_results["clinvar"]["status"] == "completed"
    assert source_results["drugbank"]["status"] == "completed"
    assert source_results["alphafold"]["status"] == "completed"
    # Uniprot and HGNC have no enrichment handler yet, so they remain deferred.
    assert source_results["uniprot"]["status"] == "deferred"
    assert source_results["hgnc"]["status"] == "deferred"

    # MONDO now continues in the background after the main run completes.
    assert source_results["mondo"]["status"] == "background"
    assert deferred_mondo_tasks

    await asyncio.gather(*deferred_mondo_tasks)

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    source_results = workspace.snapshot["source_results"]
    assert source_results["mondo"]["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_research_init_honors_guarded_structured_source_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    class _GuardedStructuredSelectionObserver:
        def __init__(self) -> None:
            self.available_source_keys: tuple[str, ...] | None = None
            self.verified_workspace: dict[str, object] | None = None

        def on_progress(
            self,
            *,
            phase: str,
            message: str,
            progress_percent: float,
            completed_steps: int,
            metadata: dict[str, object],
            workspace_snapshot: dict[str, object],
        ) -> None:
            del (
                phase,
                message,
                progress_percent,
                completed_steps,
                metadata,
                workspace_snapshot,
            )

        async def maybe_select_structured_enrichment_sources(
            self,
            *,
            available_source_keys: tuple[str, ...],
            workspace_snapshot: dict[str, object],
        ) -> tuple[str, ...]:
            del workspace_snapshot
            self.available_source_keys = available_source_keys
            return ("drugbank",)

        async def verify_guarded_structured_enrichment(
            self,
            *,
            workspace_snapshot: dict[str, object],
        ) -> bool:
            self.verified_workspace = workspace_snapshot
            return True

    observer = _GuardedStructuredSelectionObserver()

    async def _fake_execute_bootstrap(
        **kwargs: object,
    ) -> ResearchBootstrapExecutionResult:
        run = cast("HarnessRunRecord", kwargs["existing_run"])
        snapshot = cast(
            "HarnessGraphSnapshotStore",
            kwargs["graph_snapshot_store"],
        ).create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=[],
            relation_ids=[],
            graph_document_hash="bootstrap",
            summary={},
            metadata={},
        )
        state = cast(
            "HarnessResearchStateStore",
            kwargs["research_state_store"],
        ).upsert_state(
            space_id=space_id,
            objective=str(kwargs["objective"]),
            pending_questions=[],
        )
        return ResearchBootstrapExecutionResult(
            run=cast("object", run),
            graph_snapshot=snapshot,
            research_state=state,
            research_brief={},
            graph_summary={},
            source_inventory={},
            proposal_records=[],
            pending_questions=[],
            errors=[],
        )

    monkeypatch.setattr(
        research_init_runtime,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        research_init_runtime,
        "execute_research_bootstrap_run",
        _fake_execute_bootstrap,
    )

    class _StubOntologyIngestionSummary:
        def __init__(self) -> None:
            self.terms_imported = 0
            self.hierarchy_edges_created = 0
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

    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Guarded structured selection",
        objective="Test guarded structured source selection",
        seed_terms=[],
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
            "uniprot": False,
            "hgnc": False,
        },
        max_depth=1,
        max_hypotheses=1,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    await research_init_runtime.execute_research_init_run(
        space_id=space_id,
        title="Guarded structured selection",
        objective="Test guarded structured source selection",
        seed_terms=[],
        max_depth=1,
        max_hypotheses=1,
        sources={
            "pubmed": False,
            "marrvel": False,
            "pdf": False,
            "text": False,
            "mondo": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
            "uniprot": False,
            "hgnc": False,
        },
        execution_services=services,
        existing_run=queued_run,
        progress_observer=cast(
            "research_init_runtime.ResearchInitProgressObserver",
            observer,
        ),
    )

    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_run.id,
    )
    assert workspace is not None
    source_results = workspace.snapshot["source_results"]

    assert observer.available_source_keys == ("clinvar", "drugbank", "alphafold")
    assert source_results["drugbank"]["status"] == "completed"
    assert source_results["clinvar"]["status"] == "deferred"
    assert source_results["alphafold"]["status"] == "deferred"
    assert source_results["clinvar"]["deferred_reason"] == "guarded_source_selection"
    assert source_results["alphafold"]["deferred_reason"] == (
        "guarded_source_selection"
    )
    orchestration = source_results["enrichment_orchestration"]
    assert orchestration["execution_mode"] == "guarded_single_source"
    assert orchestration["selected_enrichment_sources"] == ["drugbank"]
    assert orchestration["deferred_enrichment_sources"] == [
        "clinvar",
        "alphafold",
    ]
    assert workspace.snapshot["guarded_structured_enrichment_selection"] == {
        "selected_source_key": "drugbank",
        "selected_source_keys": ["drugbank"],
        "ordered_source_keys": ["drugbank"],
        "deferred_source_keys": ["clinvar", "alphafold"],
    }
    assert observer.verified_workspace is not None
    verified_source_results = cast(
        "dict[str, dict[str, object]]",
        observer.verified_workspace["source_results"],
    )
    assert verified_source_results["drugbank"]["status"] == "completed"
    assert verified_source_results["clinvar"]["status"] == "deferred"
    assert verified_source_results["alphafold"]["status"] == "deferred"
    assert deferred_mondo_tasks

    await asyncio.gather(*deferred_mondo_tasks)


def test_ground_candidate_claim_drafts_tracks_surfaced_entity_ids() -> None:
    space_id = uuid4()
    existing_entity_id = str(uuid4())
    created_entity_id = str(uuid4())

    def _fake_resolve_graph_entity_label(
        *,
        space_id: UUID,
        label: str,
        graph_api_gateway: object,
    ) -> dict[str, str] | None:
        del space_id, graph_api_gateway
        if label == "MED13":
            return {"id": existing_entity_id}
        return None

    class _GraphApiGatewayWithCreation(_StubGraphApiGateway):
        def create_entity(
            self,
            *,
            space_id: UUID,
            entity_type: str,
            display_label: object,
        ) -> dict[str, str]:
            del space_id, entity_type, display_label
            return {"id": created_entity_id}

    original_resolve = research_init_observation_bridge.resolve_graph_entity_label
    research_init_observation_bridge.resolve_graph_entity_label = (
        _fake_resolve_graph_entity_label
    )
    try:
        grounded_drafts, surfaced_entity_ids, created_entity_ids, errors = (
            research_init_runtime._ground_candidate_claim_drafts(
                space_id=space_id,
                drafts=(
                    HarnessProposalDraft(
                        proposal_type="candidate_claim",
                        source_kind="document_extraction",
                        source_key="pubmed",
                        title="Grounded claim",
                        summary="Synthetic claim",
                        confidence=0.8,
                        ranking_score=0.8,
                        reasoning_path={},
                        evidence_bundle=[],
                        payload={
                            "proposed_subject": "unresolved:med13",
                            "proposed_subject_label": "MED13",
                            "proposed_object": "unresolved:cdk8",
                            "proposed_object_label": "CDK8",
                        },
                        metadata={},
                        document_id=str(uuid4()),
                    ),
                ),
                graph_api_gateway=_GraphApiGatewayWithCreation(),
            )
        )
    finally:
        research_init_observation_bridge.resolve_graph_entity_label = original_resolve

    assert errors == ()
    assert surfaced_entity_ids == (existing_entity_id, created_entity_id)
    assert created_entity_ids == (created_entity_id,)
    assert grounded_drafts[0].payload["proposed_subject"] == existing_entity_id
    assert grounded_drafts[0].payload["proposed_object"] == created_entity_id


def test_proposal_payload_entity_ids_extracts_uuid_backed_endpoints() -> None:
    subject_entity_id = str(uuid4())
    object_entity_id = str(uuid4())
    now = datetime.now(tz=UTC)

    proposal_records = [
        HarnessProposalRecord(
            id=str(uuid4()),
            space_id=str(uuid4()),
            run_id=str(uuid4()),
            proposal_type="candidate_claim",
            source_kind="research_bootstrap",
            source_key="pubmed",
            document_id=None,
            title="Bootstrap claim",
            summary="Synthetic bootstrap claim",
            status="pending_review",
            confidence=0.8,
            ranking_score=0.8,
            reasoning_path={},
            evidence_bundle=[],
            payload={
                "proposed_subject": subject_entity_id,
                "proposed_object": "not-a-uuid",
            },
            metadata={},
            decision_reason=None,
            decided_at=None,
            created_at=now,
            updated_at=now,
        ),
        HarnessProposalRecord(
            id=str(uuid4()),
            space_id=str(uuid4()),
            run_id=str(uuid4()),
            proposal_type="candidate_claim",
            source_kind="research_bootstrap",
            source_key="pubmed",
            document_id=None,
            title="Bootstrap claim 2",
            summary="Synthetic bootstrap claim",
            status="pending_review",
            confidence=0.9,
            ranking_score=0.9,
            reasoning_path={},
            evidence_bundle=[],
            payload={
                "proposed_subject": subject_entity_id,
                "proposed_object": object_entity_id,
            },
            metadata={},
            decision_reason=None,
            decided_at=None,
            created_at=now,
            updated_at=now,
        ),
    ]

    assert research_init_runtime._proposal_payload_entity_ids(proposal_records) == (
        subject_entity_id,
        object_entity_id,
    )


def test_ground_replay_candidate_claim_drafts_grounds_labels_in_current_space() -> None:
    space_id = uuid4()
    foreign_subject_id = str(uuid4())
    foreign_object_id = str(uuid4())
    existing_entity_id = str(uuid4())
    created_entity_id = str(uuid4())

    def _fake_resolve_graph_entity_label(
        *,
        space_id: UUID,
        label: str,
        graph_api_gateway: object,
    ) -> dict[str, str] | None:
        del space_id, graph_api_gateway
        if label == "MED13":
            return {"id": existing_entity_id}
        return None

    class _GraphApiGatewayWithCreation(_StubGraphApiGateway):
        def create_entity(
            self,
            *,
            space_id: UUID,
            entity_type: str,
            display_label: object,
        ) -> dict[str, str]:
            del space_id, entity_type, display_label
            return {"id": created_entity_id}

    replay_drafts = (
        HarnessProposalDraft(
            proposal_type="candidate_claim",
            source_kind="document_extraction",
            source_key="pubmed",
            title="Replay claim",
            summary="Synthetic replay claim",
            confidence=0.8,
            ranking_score=0.8,
            reasoning_path={},
            evidence_bundle=[],
            payload={
                "proposed_subject": foreign_subject_id,
                "proposed_subject_label": "MED13",
                "proposed_object": foreign_object_id,
                "proposed_object_label": "CDK8",
            },
            metadata={},
            document_id=None,
        ),
        HarnessProposalDraft(
            proposal_type="candidate_claim",
            source_kind="document_extraction",
            source_key="pubmed",
            title="Replay claim duplicate",
            summary="Synthetic replay claim",
            confidence=0.7,
            ranking_score=0.7,
            reasoning_path={},
            evidence_bundle=[],
            payload={
                "proposed_subject": str(uuid4()),
                "proposed_subject_label": "MED13",
                "proposed_object": str(uuid4()),
                "proposed_object_label": "CDK8",
            },
            metadata={},
            document_id=None,
        ),
    )

    original_resolve = research_init_observation_bridge.resolve_graph_entity_label
    research_init_observation_bridge.resolve_graph_entity_label = (
        _fake_resolve_graph_entity_label
    )
    try:
        grounded_drafts, surfaced_entity_ids, created_entity_ids, errors = (
            research_init_observation_bridge._ground_replay_candidate_claim_drafts(
                space_id=space_id,
                drafts=replay_drafts,
                graph_api_gateway=_GraphApiGatewayWithCreation(),
            )
        )
    finally:
        research_init_observation_bridge.resolve_graph_entity_label = original_resolve

    assert errors == ()
    assert surfaced_entity_ids == (existing_entity_id, created_entity_id)
    assert created_entity_ids == (created_entity_id,)
    assert grounded_drafts[0].payload["proposed_subject"] == existing_entity_id
    assert grounded_drafts[0].payload["proposed_object"] == created_entity_id
    assert grounded_drafts[1].payload["proposed_subject"] == existing_entity_id
    assert grounded_drafts[1].payload["proposed_object"] == created_entity_id


def _build_chase_preparation_for_test() -> _ChaseRoundPreparation:
    candidates = (
        full_ai_orchestrator_runtime.ResearchOrchestratorChaseCandidate(
            entity_id="entity-1",
            display_label="CDK8",
            normalized_label="CDK8",
            candidate_rank=1,
            observed_round=1,
            available_source_keys=["clinvar", "marrvel"],
            evidence_basis="Candidate one.",
            novelty_basis="not_in_previous_seed_terms",
        ),
        full_ai_orchestrator_runtime.ResearchOrchestratorChaseCandidate(
            entity_id="entity-2",
            display_label="MED12",
            normalized_label="MED12",
            candidate_rank=2,
            observed_round=1,
            available_source_keys=["clinvar", "marrvel"],
            evidence_basis="Candidate two.",
            novelty_basis="not_in_previous_seed_terms",
        ),
        full_ai_orchestrator_runtime.ResearchOrchestratorChaseCandidate(
            entity_id="entity-3",
            display_label="MED13L",
            normalized_label="MED13L",
            candidate_rank=3,
            observed_round=1,
            available_source_keys=["clinvar", "marrvel"],
            evidence_basis="Candidate three.",
            novelty_basis="not_in_previous_seed_terms",
        ),
    )
    return _ChaseRoundPreparation(
        candidates=candidates,
        filtered_candidates=(),
        deterministic_selection=research_init_guarded.ResearchOrchestratorChaseSelection(
            selected_entity_ids=["entity-1", "entity-2", "entity-3"],
            selected_labels=["CDK8", "MED12", "MED13L"],
            stop_instead=False,
            stop_reason=None,
            selection_basis="Deterministic chase selection.",
        ),
        errors=[],
    )


def test_prepare_chase_round_stringifies_graph_entity_ids() -> None:
    space_id = uuid4()
    entity_id = uuid4()

    class _GraphApiGatewayWithUuidEntities(_StubGraphApiGateway):
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
            del q, entity_type, ids, offset, limit
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=entity_id,
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE",
                        display_label="CDK8",
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(tz=UTC),
                        updated_at=datetime.now(tz=UTC),
                    ),
                ],
                total=1,
                offset=0,
                limit=20,
            )

    preparation = research_init_runtime._prepare_chase_round(
        space_id=space_id,
        objective="Investigate MED13 syndrome mechanisms.",
        round_number=1,
        created_entity_ids=[str(entity_id)],
        previous_seed_terms={"MED13"},
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "mondo": False,
        },
        graph_api_gateway=_GraphApiGatewayWithUuidEntities(),
    )

    assert preparation.errors == []
    assert len(preparation.candidates) == 1
    assert preparation.filtered_candidates == ()
    assert preparation.candidates[0].entity_id == str(entity_id)
    assert preparation.deterministic_selection.selected_entity_ids == []
    assert preparation.deterministic_selection.stop_instead is True
    assert preparation.deterministic_selection.stop_reason == "threshold_not_met"


def test_prepare_chase_round_filters_low_signal_labels() -> None:
    space_id = uuid4()
    entity_labels = [
        "result 1",
        "Pathogenic variant",
        "Likely benign variant",
        "Uncertain significance",
        "CFIO01_06523",
        "MED13L",
        "CDK8",
        "PARP inhibitor response",
    ]

    class _GraphApiGatewayWithMixedLabels(_StubGraphApiGateway):
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
            del q, entity_type, ids, offset, limit
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=uuid4(),
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE",
                        display_label=label,
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(tz=UTC),
                        updated_at=datetime.now(tz=UTC),
                    )
                    for label in entity_labels
                ],
                total=len(entity_labels),
                offset=0,
                limit=20,
            )

    preparation = research_init_runtime._prepare_chase_round(
        space_id=space_id,
        objective="Investigate MED13 and PARP inhibitor response.",
        round_number=1,
        created_entity_ids=[str(uuid4()) for _ in entity_labels],
        previous_seed_terms={"MED13"},
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "mondo": False,
        },
        graph_api_gateway=_GraphApiGatewayWithMixedLabels(),
    )

    assert [candidate.display_label for candidate in preparation.candidates] == [
        "MED13L",
        "PARP inhibitor response",
        "CDK8",
    ]
    assert [
        candidate.display_label for candidate in preparation.filtered_candidates
    ] == [
        "result 1",
        "Pathogenic variant",
        "Likely benign variant",
        "Uncertain significance",
        "CFIO01_06523",
    ]
    assert [
        candidate.filter_reason for candidate in preparation.filtered_candidates
    ] == [
        "generic_result_label",
        "clinical_significance_bucket",
        "clinical_significance_bucket",
        "clinical_significance_bucket",
        "accession_like_placeholder",
    ]
    assert preparation.deterministic_selection.selected_labels == [
        "MED13L",
        "PARP inhibitor response",
        "CDK8",
    ]
    assert preparation.deterministic_selection.stop_instead is False
    assert "med13" in preparation.candidates[0].evidence_basis.casefold()
    assert "parp" in preparation.candidates[1].evidence_basis.casefold()


def test_prepare_chase_round_prioritizes_objective_relevant_candidates() -> None:
    space_id = uuid4()
    entity_labels = [
        "CDK8",
        "BRCA1 PARP inhibitor result 4",
        "BRCA1 C Terminus domain",
        "PARP inhibitor response",
        "Inherited ovarian cancer (without breast cancer)",
    ]

    class _GraphApiGatewayWithRankableLabels(_StubGraphApiGateway):
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
            del q, entity_type, ids, offset, limit
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=uuid4(),
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE",
                        display_label=label,
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(tz=UTC),
                        updated_at=datetime.now(tz=UTC),
                    )
                    for label in entity_labels
                ],
                total=len(entity_labels),
                offset=0,
                limit=20,
            )

    preparation = research_init_runtime._prepare_chase_round(
        space_id=space_id,
        objective="Investigate BRCA1 and PARP inhibitor response.",
        round_number=1,
        created_entity_ids=[str(uuid4()) for _ in entity_labels],
        previous_seed_terms={"BRCA1", "PARP INHIBITOR"},
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": True,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "mondo": False,
        },
        graph_api_gateway=_GraphApiGatewayWithRankableLabels(),
    )

    assert [candidate.display_label for candidate in preparation.candidates] == [
        "PARP inhibitor response",
        "BRCA1 C Terminus domain",
        "CDK8",
        "Inherited ovarian cancer (without breast cancer)",
    ]
    assert [
        candidate.display_label for candidate in preparation.filtered_candidates
    ] == [
        "BRCA1 PARP inhibitor result 4",
    ]
    assert [
        candidate.filter_reason for candidate in preparation.filtered_candidates
    ] == [
        "generic_result_label",
    ]
    assert (
        preparation.deterministic_selection.selection_basis
        == "The deterministic baseline chases the bounded candidate set in objective-relevance rank order after filtering out prior seed terms."
    )


def test_prepare_chase_round_filters_taxonomic_spillover_for_non_organism_objective() -> (
    None
):
    space_id = uuid4()
    entity_labels = [
        "Colletotrichum fioriniae",
        "Colletotrichum fioriniae PJ7",
        "BRCA1 C Terminus",
        "PARP inhibitor response",
    ]

    class _GraphApiGatewayWithTaxonomicLabels(_StubGraphApiGateway):
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
            del q, entity_type, ids, offset, limit
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=uuid4(),
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE",
                        display_label=label,
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(tz=UTC),
                        updated_at=datetime.now(tz=UTC),
                    )
                    for label in entity_labels
                ],
                total=len(entity_labels),
                offset=0,
                limit=20,
            )

    preparation = research_init_runtime._prepare_chase_round(
        space_id=space_id,
        objective="Investigate BRCA1 and PARP inhibitor response.",
        round_number=1,
        created_entity_ids=[str(uuid4()) for _ in entity_labels],
        previous_seed_terms={"BRCA1", "PARP INHIBITOR"},
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": True,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "mondo": False,
        },
        graph_api_gateway=_GraphApiGatewayWithTaxonomicLabels(),
    )

    assert [candidate.display_label for candidate in preparation.candidates] == [
        "PARP inhibitor response",
        "BRCA1 C Terminus",
    ]
    assert [
        candidate.display_label for candidate in preparation.filtered_candidates
    ] == [
        "Colletotrichum fioriniae",
        "Colletotrichum fioriniae PJ7",
    ]
    assert [
        candidate.filter_reason for candidate in preparation.filtered_candidates
    ] == [
        "taxonomic_spillover",
        "taxonomic_spillover",
    ]
    assert preparation.deterministic_selection.stop_instead is True
    assert preparation.deterministic_selection.stop_reason == "threshold_not_met"


def test_prepare_chase_round_filters_underanchored_fragment_labels() -> None:
    space_id = uuid4()
    entity_labels = [
        "CDK8",
        "C Terminus domain",
        "BRCA1 C Terminus domain",
        "PARP inhibitor response",
    ]

    class _GraphApiGatewayWithFragmentLabels(_StubGraphApiGateway):
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
            del q, entity_type, ids, offset, limit
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=uuid4(),
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE",
                        display_label=label,
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(tz=UTC),
                        updated_at=datetime.now(tz=UTC),
                    )
                    for label in entity_labels
                ],
                total=len(entity_labels),
                offset=0,
                limit=20,
            )

    preparation = research_init_runtime._prepare_chase_round(
        space_id=space_id,
        objective="Investigate BRCA1 and PARP inhibitor response.",
        round_number=1,
        created_entity_ids=[str(uuid4()) for _ in entity_labels],
        previous_seed_terms={"BRCA1", "PARP INHIBITOR"},
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": True,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "mondo": False,
        },
        graph_api_gateway=_GraphApiGatewayWithFragmentLabels(),
    )

    assert [candidate.display_label for candidate in preparation.candidates] == [
        "PARP inhibitor response",
        "BRCA1 C Terminus domain",
        "CDK8",
    ]
    assert [
        candidate.display_label for candidate in preparation.filtered_candidates
    ] == [
        "C Terminus domain",
    ]
    assert [
        candidate.filter_reason for candidate in preparation.filtered_candidates
    ] == [
        "underanchored_fragment_label",
    ]


def test_prepare_chase_round_keeps_taxonomic_candidates_for_organism_objective() -> (
    None
):
    space_id = uuid4()
    entity_labels = [
        "Colletotrichum fioriniae",
        "Colletotrichum fioriniae PJ7",
        "BRCA1 C Terminus",
    ]

    class _GraphApiGatewayWithOrganismLabels(_StubGraphApiGateway):
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
            del q, entity_type, ids, offset, limit
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=uuid4(),
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE",
                        display_label=label,
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(tz=UTC),
                        updated_at=datetime.now(tz=UTC),
                    )
                    for label in entity_labels
                ],
                total=len(entity_labels),
                offset=0,
                limit=20,
            )

    preparation = research_init_runtime._prepare_chase_round(
        space_id=space_id,
        objective="Compare BRCA1 expression across fungal species and strains.",
        round_number=1,
        created_entity_ids=[str(uuid4()) for _ in entity_labels],
        previous_seed_terms={"BRCA1"},
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
            "mondo": False,
        },
        graph_api_gateway=_GraphApiGatewayWithOrganismLabels(),
    )

    assert [candidate.display_label for candidate in preparation.candidates] == [
        "BRCA1 C Terminus",
        "Colletotrichum fioriniae",
        "Colletotrichum fioriniae PJ7",
    ]
    assert preparation.filtered_candidates == ()
    assert preparation.deterministic_selection.selected_labels == [
        "BRCA1 C Terminus",
        "Colletotrichum fioriniae",
        "Colletotrichum fioriniae PJ7",
    ]
    assert preparation.deterministic_selection.stop_instead is False


def test_coerce_guarded_chase_selection_accepts_ordered_subset() -> None:
    preparation = _build_chase_preparation_for_test()

    selection = research_init_guarded.coerce_guarded_chase_selection(
        selection_payload={
            "selected_entity_ids": ["entity-1", "entity-3"],
            "selected_labels": ["CDK8", "MED13L"],
            "stop_instead": False,
            "stop_reason": None,
            "selection_basis": "Keep the strongest and least repetitive chase leads.",
        },
        preparation=preparation,
    )

    assert selection is not None
    assert selection.selected_entity_ids == ["entity-1", "entity-3"]
    assert selection.selected_labels == ["CDK8", "MED13L"]


def test_coerce_guarded_chase_selection_accepts_exact_deterministic_selection() -> None:
    preparation = _build_chase_preparation_for_test()

    selection = research_init_guarded.coerce_guarded_chase_selection(
        selection_payload={
            "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
            "selected_labels": ["CDK8", "MED12", "MED13L"],
            "stop_instead": False,
            "stop_reason": None,
            "selection_basis": (
                "The full deterministic chase set should remain the guarded baseline."
            ),
        },
        preparation=preparation,
    )

    assert selection is not None
    assert selection.selected_entity_ids == ["entity-1", "entity-2", "entity-3"]
    assert selection.selected_labels == ["CDK8", "MED12", "MED13L"]


def test_coerce_guarded_chase_selection_rejects_unknown_entity() -> None:
    preparation = _build_chase_preparation_for_test()

    selection = research_init_guarded.coerce_guarded_chase_selection(
        selection_payload={
            "selected_entity_ids": ["entity-missing"],
            "selected_labels": ["Missing"],
            "stop_instead": False,
            "stop_reason": None,
            "selection_basis": "This should be rejected.",
        },
        preparation=preparation,
    )

    assert selection is None


def test_coerce_guarded_chase_selection_rejects_out_of_order_subset() -> None:
    preparation = _build_chase_preparation_for_test()

    selection = research_init_guarded.coerce_guarded_chase_selection(
        selection_payload={
            "selected_entity_ids": ["entity-3", "entity-1"],
            "selected_labels": ["MED13L", "CDK8"],
            "stop_instead": False,
            "stop_reason": None,
            "selection_basis": "This should be rejected because the order drifted.",
        },
        preparation=preparation,
    )

    assert selection is None


def test_coerce_guarded_chase_selection_accepts_stop_with_reason() -> None:
    preparation = _build_chase_preparation_for_test()

    selection = research_init_guarded.coerce_guarded_chase_selection(
        selection_payload={
            "selected_entity_ids": [],
            "selected_labels": [],
            "stop_instead": True,
            "stop_reason": "low_incremental_value",
            "selection_basis": "The remaining leads are repetitive and weak.",
        },
        preparation=preparation,
    )

    assert selection is not None
    assert selection.stop_instead is True
    assert selection.stop_reason == "low_incremental_value"


@pytest.mark.asyncio
async def test_maybe_select_guarded_chase_round_selection_uses_observer() -> None:
    space_id = uuid4()
    services = _build_execution_services()
    original_transparency = research_init_runtime.ensure_run_transparency_seed
    research_init_runtime.ensure_run_transparency_seed = lambda **_kwargs: None
    queued_run = research_init_runtime.queue_research_init_run(
        space_id=space_id,
        title="Guarded chase selection",
        objective="Test guarded chase selection",
        seed_terms=["MED13"],
        sources={
            "pubmed": False,
            "marrvel": True,
            "pdf": False,
            "text": False,
            "clinvar": True,
            "drugbank": False,
            "alphafold": False,
            "gnomad": False,
            "uniprot": False,
            "hgnc": False,
        },
        max_depth=1,
        max_hypotheses=1,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )
    try:
        services.artifact_store.patch_workspace(
            space_id=space_id,
            run_id=queued_run.id,
            patch={"pending_chase_round": {"round_number": 1}},
        )
        preparation = _build_chase_preparation_for_test()

        class _GuardedChaseObserver:
            def on_progress(
                self,
                *,
                phase: str,
                message: str,
                progress_percent: float,
                completed_steps: int,
                metadata: dict[str, object],
                workspace_snapshot: dict[str, object],
            ) -> None:
                del (
                    phase,
                    message,
                    progress_percent,
                    completed_steps,
                    metadata,
                    workspace_snapshot,
                )

            async def maybe_select_chase_round_selection(
                self,
                *,
                round_number: int,
                chase_candidates: tuple[
                    full_ai_orchestrator_runtime.ResearchOrchestratorChaseCandidate,
                    ...,
                ],
                deterministic_selection: research_init_guarded.ResearchOrchestratorChaseSelection,
                workspace_snapshot: dict[str, object],
            ) -> dict[str, object]:
                assert round_number == 1
                assert [candidate.display_label for candidate in chase_candidates] == [
                    "CDK8",
                    "MED12",
                    "MED13L",
                ]
                assert deterministic_selection.selected_labels == [
                    "CDK8",
                    "MED12",
                    "MED13L",
                ]
                assert workspace_snapshot["pending_chase_round"] == {"round_number": 1}
                return {
                    "selected_entity_ids": ["entity-1", "entity-3"],
                    "selected_labels": ["CDK8", "MED13L"],
                    "stop_instead": False,
                    "stop_reason": None,
                    "selection_basis": (
                        "Keep the strongest bounded chase subset in guarded mode."
                    ),
                }

        selection = (
            await research_init_guarded.maybe_select_guarded_chase_round_selection(
                services=services,
                space_id=space_id,
                run_id=queued_run.id,
                round_number=1,
                preparation=preparation,
                progress_observer=cast(
                    "research_init_runtime.ResearchInitProgressObserver",
                    _GuardedChaseObserver(),
                ),
            )
        )

        assert selection is not None
        assert selection.selected_entity_ids == ["entity-1", "entity-3"]
        assert selection.selected_labels == ["CDK8", "MED13L"]
    finally:
        research_init_runtime.ensure_run_transparency_seed = original_transparency
