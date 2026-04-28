"""Unit tests for harness document extraction helpers."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from artana_evidence_api import (
    document_extraction,
    runtime_support,
)
from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.document_extraction import (
    DocumentCandidateExtractionDiagnostics,
    DocumentProposalReviewDiagnostics,
    ExtractedRelationCandidate,
    build_document_extraction_drafts,
    build_document_review_context,
    discover_relation_candidates,
    extract_relation_candidates,
    extract_relation_candidates_with_diagnostics,
    extract_relation_candidates_with_llm,
    pre_resolve_entities_with_ai,
    review_document_extraction_drafts_with_diagnostics,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
    KernelEntityResponse,
)


class _EmptyGraphApiGateway:
    def __init__(self) -> None:
        self.query = self

    def list_entities(
        self,
        *,
        space_id,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)


class _CatalogGraphApiGateway:
    def __init__(self, *, entities: list[KernelEntityResponse]) -> None:
        self._entities = entities
        self.query = self

    def list_entities(
        self,
        *,
        space_id,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del entity_type, ids, offset, limit
        matching_entities = self._entities
        if isinstance(q, str) and q.strip() != "":
            normalized_query = q.strip().casefold()
            matching_entities = [
                entity
                for entity in self._entities
                if normalized_query in (entity.display_label or "").casefold()
                or any(normalized_query in alias.casefold() for alias in entity.aliases)
            ]
        return KernelEntityListResponse(
            entities=matching_entities,
            total=len(matching_entities),
            offset=0,
            limit=50,
        )


def _build_graph_entity(
    *,
    space_id: UUID,
    entity_id: str,
    entity_type: str,
    display_label: str,
    aliases: list[str],
) -> KernelEntityResponse:
    now = datetime.now(UTC)
    return KernelEntityResponse(
        id=UUID(entity_id),
        research_space_id=space_id,
        entity_type=entity_type,
        display_label=display_label,
        aliases=aliases,
        metadata={},
        created_at=now,
        updated_at=now,
    )


class _FakeKernelStore:
    def __init__(self) -> None:
        self.closed = False
        self.kernel: _FakeKernel | None = None

    async def close(self) -> None:
        self.closed = True


class _FakeKernel:
    def __init__(self, *, store, model_port, **kwargs) -> None:
        del kwargs
        self.store = store
        self.model_port = model_port
        self.closed = False
        store.kernel = self

    async def close(self) -> None:
        self.closed = True


class _FakeSingleStepClient:
    def __init__(self, *, kernel) -> None:
        self.kernel = kernel


@pytest.mark.asyncio
async def test_discover_relation_candidates_prefers_llm_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="cardiomyopathy",
        sentence="The study found that MED13 was associated with cardiomyopathy.",
    )

    async def _fake_llm_candidates(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        return [llm_candidate]

    def _unexpected_regex_candidates(text: str) -> list[ExtractedRelationCandidate]:
        del text
        raise AssertionError("regex fallback should not run when LLM succeeds")

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _fake_llm_candidates,
    )
    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates",
        _unexpected_regex_candidates,
    )
    candidates, diagnostics = await discover_relation_candidates(
        "The study found that MED13 was associated with cardiomyopathy.",
    )
    assert candidates == [llm_candidate]
    assert diagnostics == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=1,
    )
    assert diagnostics.as_metadata() == {
        "llm_candidate_status": "completed",
        "llm_candidate_attempted": True,
        "llm_candidate_failed": False,
        "llm_candidate_count": 1,
    }


@pytest.mark.asyncio
async def test_discover_relation_candidates_falls_back_to_regex_with_llm_empty_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heuristic_candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="cardiomyopathy",
        sentence="The study found that MED13 was associated with cardiomyopathy.",
    )

    async def _empty_llm_candidates(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        return []

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _empty_llm_candidates,
    )
    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates",
        lambda text: [heuristic_candidate],
    )
    candidates, diagnostics = await discover_relation_candidates(
        "The study found that MED13 was associated with cardiomyopathy.",
    )
    assert candidates == [heuristic_candidate]
    assert diagnostics == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="llm_empty",
        llm_candidate_error="LLM succeeded but returned zero usable candidates",
        fallback_candidate_count=1,
    )
    assert diagnostics.as_metadata() == {
        "llm_candidate_status": "llm_empty",
        "llm_candidate_attempted": True,
        "llm_candidate_failed": False,
        "fallback_candidate_count": 1,
        "llm_candidate_error": "LLM succeeded but returned zero usable candidates",
    }


@pytest.mark.asyncio
async def test_discover_relation_candidates_marks_unavailable_on_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heuristic_candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="cardiomyopathy",
        sentence="The study found that MED13 was associated with cardiomyopathy.",
    )

    async def _missing_api_key(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        raise RuntimeError("OPENAI_API_KEY not configured")

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _missing_api_key,
    )
    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates",
        lambda text: [heuristic_candidate],
    )
    candidates, diagnostics = await discover_relation_candidates(
        "The study found that MED13 was associated with cardiomyopathy.",
    )
    assert candidates == [heuristic_candidate]
    assert diagnostics == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="unavailable",
        llm_candidate_error="OPENAI_API_KEY not configured",
        fallback_candidate_count=1,
    )


@pytest.mark.asyncio
async def test_discover_relation_candidates_runtime_error_event_loop_is_fallback_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heuristic_candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="cardiomyopathy",
        sentence="The study found that MED13 was associated with cardiomyopathy.",
    )

    async def _event_loop_closed(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _event_loop_closed,
    )
    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates",
        lambda text: [heuristic_candidate],
    )

    candidates, diagnostics = await discover_relation_candidates(
        "The study found that MED13 was associated with cardiomyopathy.",
    )

    assert candidates == [heuristic_candidate]
    assert diagnostics == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="fallback_error",
        llm_candidate_error="Event loop is closed",
        fallback_candidate_count=1,
    )


def test_extract_relation_candidates_matches_narrative_scientific_text() -> None:
    candidates = extract_relation_candidates(
        "The study found that MED13 was associated with cardiomyopathy in mice.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MED13"
    assert candidates[0].relation_type == "ASSOCIATED_WITH"
    assert candidates[0].object_label == "cardiomyopathy"


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_diagnostics_falls_back_to_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        raise RuntimeError("synthetic llm outage")

    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )

    candidates, diagnostics = await extract_relation_candidates_with_diagnostics(
        "The study found that MED13 was associated with cardiomyopathy in mice.",
        space_context="Investigate MED13 links to cardiomyopathy.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MED13"
    assert diagnostics.as_metadata() == {
        "llm_candidate_status": "fallback_error",
        "llm_candidate_attempted": True,
        "llm_candidate_failed": True,
        "fallback_candidate_count": 1,
        "llm_candidate_error": "synthetic llm outage",
    }


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_diagnostics_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _slow_extract_relation_candidates_with_llm(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str,
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        await asyncio.sleep(0.01)
        return []

    monkeypatch.setattr(
        document_extraction,
        "_LLM_CANDIDATE_EXTRACTION_TIMEOUT_SECONDS",
        0.001,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction.extract_relation_candidates_with_llm",
        _slow_extract_relation_candidates_with_llm,
    )

    candidates, diagnostics = await extract_relation_candidates_with_diagnostics(
        "The study found that MED13 was associated with cardiomyopathy in mice.",
        space_context="Investigate MED13 links to cardiomyopathy.",
    )

    assert len(candidates) == 1
    assert diagnostics == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="fallback_error",
        llm_candidate_error="LLM candidate extraction timed out",
        fallback_candidate_count=1,
    )


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_uses_fresh_store_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "BRCA1",
                        "relation_type": "activates",
                        "object": "EGFR",
                        "sentence": "BRCA1 activates EGFR.",
                    },
                ],
            },
        )

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    first = await extract_relation_candidates_with_llm("BRCA1 activates EGFR.")
    second = await extract_relation_candidates_with_llm("BRCA1 activates EGFR.")

    assert len(first) == 1
    assert first[0].subject_label == "BRCA1"
    assert len(second) == 1
    assert len(created_stores) == 2
    assert created_stores[0] is not created_stores[1]
    assert all(store.closed for store in created_stores)
    for store in created_stores:
        assert store.kernel is not None
        assert store.kernel.closed


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_scopes_step_key_to_document_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_step_keys: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_step_keys.append(kwargs["step_key"])
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "BRCA1",
                        "relation_type": "activates",
                        "object": "EGFR",
                        "sentence": "BRCA1 activates EGFR.",
                    },
                ],
            },
        )

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr(
        runtime_support,
        "create_artana_postgres_store",
        lambda: _FakeKernelStore(),
    )
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    first_text = "BRCA1 activates EGFR."
    second_text = "MED13 regulates cardiomyopathy."
    await extract_relation_candidates_with_llm(first_text)
    await extract_relation_candidates_with_llm(first_text)
    await extract_relation_candidates_with_llm(second_text)

    assert captured_step_keys == [
        document_extraction._llm_extraction_step_key(
            text=first_text,
            max_relations=10,
        ),
        document_extraction._llm_extraction_step_key(
            text=first_text,
            max_relations=10,
        ),
        document_extraction._llm_extraction_step_key(
            text=second_text,
            max_relations=10,
        ),
    ]
    assert captured_step_keys[0] == captured_step_keys[1]
    assert captured_step_keys[0] != captured_step_keys[2]


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_closes_store_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic llm outage")

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(document_extraction, "run_single_step_with_policy", _boom)

    with pytest.raises(RuntimeError, match="synthetic llm outage"):
        await extract_relation_candidates_with_llm("BRCA1 activates EGFR.")

    assert len(created_stores) == 1
    assert created_stores[0].closed is True
    assert created_stores[0].kernel is not None
    assert created_stores[0].kernel.closed is True


@pytest.mark.asyncio
async def test_review_document_extraction_drafts_with_diagnostics_closes_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(
            output={
                "reviews": [
                    {
                        "index": 0,
                        "factual_support": "moderate",
                        "goal_relevance": "direct",
                        "priority": "prioritize",
                        "rationale": "Looks good.",
                        "factual_rationale": "Supported by the candidate.",
                        "relevance_rationale": "Directly relevant to the objective.",
                    },
                ],
            },
        )

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    now = datetime.now(UTC)
    document = HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Narrative MED13 evidence",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=42,
        page_count=None,
        text_content="MED13 activates EGFR.",
        text_excerpt="MED13 activates EGFR.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )
    draft = HarnessProposalDraft(
        proposal_type="relation",
        source_kind="text",
        source_key=f"{document.id}:0",
        title="MED13 activates EGFR",
        summary="MED13 activates EGFR.",
        confidence=0.8,
        ranking_score=0.9,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": "unresolved:med13",
            "proposed_object": "unresolved:egfr",
            "proposed_claim_type": "ACTIVATES",
        },
        metadata={},
        document_id=document.id,
    )

    reviewed_drafts, diagnostics = (
        await review_document_extraction_drafts_with_diagnostics(
            document=document,
            candidates=[candidate],
            drafts=(draft,),
            review_context=build_document_review_context(
                objective="Study MED13 signaling.",
            ),
        )
    )

    assert diagnostics == DocumentProposalReviewDiagnostics(
        llm_review_status="completed",
    )
    assert reviewed_drafts[0].metadata["proposal_review"]["method"] == "llm_judge_v1"
    assert len(created_stores) == 1
    assert created_stores[0].closed is True
    assert created_stores[0].kernel is not None
    assert created_stores[0].kernel.closed is True


@pytest.mark.asyncio
async def test_review_document_extraction_drafts_scopes_step_key_to_review_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_step_keys: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_step_keys.append(kwargs["step_key"])
        return SimpleNamespace(
            output={
                "reviews": [
                    {
                        "index": 0,
                        "factual_support": "moderate",
                        "goal_relevance": "direct",
                        "priority": "prioritize",
                        "rationale": "Looks good.",
                        "factual_rationale": "Supported by the candidate.",
                        "relevance_rationale": "Directly relevant to the objective.",
                    },
                ],
            },
        )

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr(
        runtime_support,
        "create_artana_postgres_store",
        lambda: _FakeKernelStore(),
    )
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    now = datetime.now(UTC)
    document = HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Narrative MED13 evidence",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=42,
        page_count=None,
        text_content="MED13 activates EGFR.",
        text_excerpt="MED13 activates EGFR.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )
    draft = HarnessProposalDraft(
        proposal_type="relation",
        source_kind="text",
        source_key=f"{document.id}:0",
        title="MED13 activates EGFR",
        summary="MED13 activates EGFR.",
        confidence=0.8,
        ranking_score=0.9,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": "unresolved:med13",
            "proposed_object": "unresolved:egfr",
            "proposed_claim_type": "ACTIVATES",
        },
        metadata={},
        document_id=document.id,
    )
    direct_context = build_document_review_context(
        objective="Study MED13 signaling.",
    )
    supporting_context = build_document_review_context(
        objective="Study EGFR signaling.",
    )

    await review_document_extraction_drafts_with_diagnostics(
        document=document,
        candidates=[candidate],
        drafts=(draft,),
        review_context=direct_context,
    )
    await review_document_extraction_drafts_with_diagnostics(
        document=document,
        candidates=[candidate],
        drafts=(draft,),
        review_context=direct_context,
    )
    await review_document_extraction_drafts_with_diagnostics(
        document=document,
        candidates=[candidate],
        drafts=(draft,),
        review_context=supporting_context,
    )

    assert len(captured_step_keys) == 3
    assert all(
        step_key.startswith("document_extraction.proposal_review.v1.")
        for step_key in captured_step_keys
    )
    assert captured_step_keys[0] == captured_step_keys[1]
    assert captured_step_keys[0] != captured_step_keys[2]


@pytest.mark.asyncio
async def test_review_document_extraction_drafts_with_diagnostics_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeKernelStore] = []

    def _create_store() -> _FakeKernelStore:
        store = _FakeKernelStore()
        created_stores.append(store)
        return store

    async def _slow_run_single_step_with_policy(*_args, **_kwargs):
        await asyncio.sleep(0.01)
        return SimpleNamespace(output={"reviews": []})

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(
        document_extraction,
        "_LLM_PROPOSAL_REVIEW_TIMEOUT_SECONDS",
        0.001,
    )
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _slow_run_single_step_with_policy,
    )

    now = datetime.now(UTC)
    document = HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Narrative MED13 evidence",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=42,
        page_count=None,
        text_content="MED13 activates EGFR.",
        text_excerpt="MED13 activates EGFR.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )
    draft = HarnessProposalDraft(
        proposal_type="relation",
        source_kind="text",
        source_key=f"{document.id}:0",
        title="MED13 activates EGFR",
        summary="MED13 activates EGFR.",
        confidence=0.8,
        ranking_score=0.9,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": "unresolved:med13",
            "proposed_object": "unresolved:egfr",
            "proposed_claim_type": "ACTIVATES",
        },
        metadata={},
        document_id=document.id,
    )

    reviewed_drafts, diagnostics = (
        await review_document_extraction_drafts_with_diagnostics(
            document=document,
            candidates=[candidate],
            drafts=(draft,),
            review_context=build_document_review_context(
                objective="Study MED13 signaling.",
            ),
        )
    )

    assert diagnostics == DocumentProposalReviewDiagnostics(
        llm_review_status="fallback_error",
        llm_review_error="LLM proposal review timed out",
    )
    assert reviewed_drafts[0].metadata["proposal_review"]["method"] == (
        "heuristic_fallback_v1"
    )
    assert len(created_stores) == 1
    assert created_stores[0].closed is True
    assert created_stores[0].kernel is not None
    assert created_stores[0].kernel.closed is True


@pytest.mark.asyncio
async def test_pre_resolve_entities_with_ai_caps_ai_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_labels: list[str] = []

    def _fake_exact_match(*, space_id, label: str, graph_api_gateway):
        del space_id, graph_api_gateway
        if label == "BRCA1":
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "display_label": "BRCA1",
            }
        return None

    async def _fake_resolve_entity_with_ai(
        *,
        space_id,
        label: str,
        graph_api_gateway,
        space_context: str = "",
    ) -> dict[str, str] | None:
        del space_id, graph_api_gateway, space_context
        seen_labels.append(label)
        return {
            "id": f"resolved:{label}",
            "display_label": f"{label} resolved",
        }

    monkeypatch.setattr(
        document_extraction,
        "_MAX_AI_ENTITY_PRE_RESOLUTION_LABELS",
        2,
    )
    monkeypatch.setattr(
        document_extraction,
        "resolve_exact_entity_label",
        _fake_exact_match,
    )
    monkeypatch.setattr(
        document_extraction,
        "_resolve_entity_label_with_ai",
        _fake_resolve_entity_with_ai,
    )

    resolved = await pre_resolve_entities_with_ai(
        space_id=uuid4(),
        candidates=[
            ExtractedRelationCandidate(
                subject_label="BRCA1",
                relation_type="ASSOCIATED_WITH",
                object_label="EGFR",
                sentence="BRCA1 was associated with EGFR.",
            ),
            ExtractedRelationCandidate(
                subject_label="AKT1",
                relation_type="ASSOCIATED_WITH",
                object_label="TP53",
                sentence="AKT1 was associated with TP53.",
            ),
        ],
        graph_api_gateway=_EmptyGraphApiGateway(),
        space_context="Investigate BRCA1 signaling.",
    )

    assert seen_labels == ["EGFR", "AKT1"]
    assert resolved == {
        "brca1": {
            "id": "11111111-1111-1111-1111-111111111111",
            "display_label": "BRCA1",
        },
        "egfr": {
            "id": "resolved:EGFR",
            "display_label": "EGFR resolved",
        },
        "akt1": {
            "id": "resolved:AKT1",
            "display_label": "AKT1 resolved",
        },
    }


@pytest.mark.asyncio
async def test_pre_resolve_entities_with_ai_times_out_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _never_exact_match(*, space_id, label: str, graph_api_gateway):
        del space_id, label, graph_api_gateway

    async def _slow_resolve_entity_with_ai(
        *,
        space_id,
        label: str,
        graph_api_gateway,
        space_context: str = "",
    ) -> dict[str, str] | None:
        del space_id, label, graph_api_gateway, space_context
        await asyncio.sleep(0.01)
        return {
            "id": "should-not-complete",
            "display_label": "Should not complete",
        }

    monkeypatch.setattr(
        document_extraction,
        "_AI_ENTITY_PRE_RESOLUTION_TIMEOUT_SECONDS",
        0.001,
    )
    monkeypatch.setattr(
        document_extraction,
        "resolve_exact_entity_label",
        _never_exact_match,
    )
    monkeypatch.setattr(
        document_extraction,
        "_resolve_entity_label_with_ai",
        _slow_resolve_entity_with_ai,
    )

    with caplog.at_level(logging.DEBUG, logger=document_extraction.__name__):
        resolved = await pre_resolve_entities_with_ai(
            space_id=uuid4(),
            candidates=[
                ExtractedRelationCandidate(
                    subject_label="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object_label="cardiomyopathy",
                    sentence="MED13 was associated with cardiomyopathy.",
                ),
            ],
            graph_api_gateway=_EmptyGraphApiGateway(),
            space_context="Investigate MED13 cardiomyopathy evidence.",
        )

    assert resolved == {}
    assert any(
        record.levelno == logging.DEBUG
        and record.getMessage().startswith("AI entity resolution timed out for '")
        for record in caplog.records
    )


def test_build_document_extraction_drafts_keeps_candidates_on_empty_graph() -> None:
    now = datetime.now(UTC)
    document = HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Narrative MED13 evidence",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=42,
        page_count=None,
        text_content="The study found that MED13 was associated with cardiomyopathy.",
        text_excerpt="The study found that MED13 was associated with cardiomyopathy.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ASSOCIATED_WITH",
            object_label="cardiomyopathy",
            sentence="The study found that MED13 was associated with cardiomyopathy.",
        ),
    ]

    drafts, skipped_candidates = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_EmptyGraphApiGateway(),
        review_context=build_document_review_context(
            objective="Investigate MED13 links to cardiomyopathy.",
        ),
    )

    assert skipped_candidates == []
    assert len(drafts) == 1
    assert drafts[0].payload["proposed_subject"] == "unresolved:med13"
    assert drafts[0].payload["proposed_subject_label"] == "MED13"
    assert drafts[0].payload["proposed_object"] == "unresolved:cardiomyopathy"
    assert drafts[0].payload["proposed_object_label"] == "cardiomyopathy"
    assert drafts[0].metadata["subject_resolved"] is False
    assert drafts[0].metadata["object_resolved"] is False
    assert drafts[0].metadata["proposal_review"]["goal_relevance"] in {
        "direct",
        "supporting",
    }
    assert drafts[0].metadata["proposal_review"]["priority"] in {
        "prioritize",
        "review",
    }
    assert drafts[0].claim_fingerprint == compute_claim_fingerprint(
        "MED13",
        "ASSOCIATED_WITH",
        "cardiomyopathy",
    )


def test_build_document_extraction_drafts_splits_compound_object_labels() -> None:
    now = datetime.now(UTC)
    space_id = uuid4()
    document = HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(space_id),
        created_by=str(uuid4()),
        title="Narrative MED13 syndrome evidence",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=42,
        page_count=None,
        text_content=(
            "MED13 causes FG syndrome (Opitz-Kaveggia), "
            "Lujan-Fryns syndrome, and Ohdo syndrome."
        ),
        text_excerpt=(
            "MED13 causes FG syndrome (Opitz-Kaveggia), "
            "Lujan-Fryns syndrome, and Ohdo syndrome."
        ),
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="CAUSES",
            object_label=(
                "FG syndrome (Opitz-Kaveggia), "
                "Lujan-Fryns syndrome, and Ohdo syndrome"
            ),
            sentence=(
                "MED13 causes FG syndrome (Opitz-Kaveggia), "
                "Lujan-Fryns syndrome, and Ohdo syndrome."
            ),
        ),
    ]
    graph_api_gateway = _CatalogGraphApiGateway(
        entities=[
            _build_graph_entity(
                space_id=space_id,
                entity_id="11111111-1111-1111-1111-111111111111",
                entity_type="GENE",
                display_label="MED13",
                aliases=[],
            ),
            _build_graph_entity(
                space_id=space_id,
                entity_id="22222222-2222-2222-2222-222222222222",
                entity_type="DISEASE",
                display_label="FG Syndrome Type 1",
                aliases=["FG syndrome", "Opitz-Kaveggia"],
            ),
            _build_graph_entity(
                space_id=space_id,
                entity_id="33333333-3333-3333-3333-333333333333",
                entity_type="DISEASE",
                display_label="Lujan-Fryns syndrome",
                aliases=[],
            ),
            _build_graph_entity(
                space_id=space_id,
                entity_id="44444444-4444-4444-4444-444444444444",
                entity_type="DISEASE",
                display_label="Ohdo syndrome MKBT",
                aliases=["Ohdo syndrome"],
            ),
        ],
    )

    drafts, skipped_candidates = build_document_extraction_drafts(
        space_id=space_id,
        document=document,
        candidates=candidates,
        graph_api_gateway=graph_api_gateway,
    )

    assert skipped_candidates == []
    assert len(drafts) == 3
    assert [draft.source_key for draft in drafts] == [
        f"{document.id}:0:0",
        f"{document.id}:0:1",
        f"{document.id}:0:2",
    ]
    assert [draft.payload["proposed_object_label"] for draft in drafts] == [
        "FG syndrome",
        "Lujan-Fryns syndrome",
        "Ohdo syndrome",
    ]
    assert [draft.metadata["resolved_object_label"] for draft in drafts] == [
        "FG Syndrome Type 1",
        "Lujan-Fryns syndrome",
        "Ohdo syndrome MKBT",
    ]
    assert all(draft.metadata["object_split_applied"] is True for draft in drafts)
    assert drafts[0].claim_fingerprint == compute_claim_fingerprint(
        "MED13",
        "CAUSES",
        "FG Syndrome Type 1",
    )


def test_build_document_extraction_drafts_keeps_single_entity_names_with_and() -> None:
    now = datetime.now(UTC)
    document = HarnessDocumentRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="Narrative growth factor evidence",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="abc123",
        byte_size=42,
        page_count=None,
        text_content="MED13 regulates growth and differentiation factor 5.",
        text_excerpt="MED13 regulates growth and differentiation factor 5.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="not_started",
        metadata={},
        created_at=now,
        updated_at=now,
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="REGULATES",
            object_label="growth and differentiation factor 5",
            sentence="MED13 regulates growth and differentiation factor 5.",
        ),
    ]

    drafts, skipped_candidates = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_EmptyGraphApiGateway(),
    )

    assert skipped_candidates == []
    assert len(drafts) == 1
    assert drafts[0].payload["proposed_object_label"] == (
        "growth and differentiation factor 5"
    )
    assert drafts[0].metadata["object_split_applied"] is False
