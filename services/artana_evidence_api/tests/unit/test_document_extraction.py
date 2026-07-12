"""Unit tests for harness document extraction helpers."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from io import BytesIO
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
    extract_pdf_text,
    extract_relation_candidates,
    extract_relation_candidates_with_diagnostics,
    extract_relation_candidates_with_llm,
    pre_resolve_entities_with_ai,
    review_document_extraction_drafts_with_diagnostics,
)
from artana_evidence_api.document_extraction_prompting import (
    LLM_EXTRACTION_SYSTEM_PROMPT,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    LLM_EXTRACTION_PROMPT_VERSION,
    LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION,
    ModelStepRunner,
    llm_extraction_step_key,
)
from artana_evidence_api.document_extraction_support.strict_relation_discovery import (
    discover_relation_candidates_strict,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
    KernelEntityResponse,
)
from pydantic import ValidationError


def _proposal_review_ref_from_prompt(prompt: str) -> str:
    match = re.search(r"Claim reference: (draft_[0-9a-f]{24})", prompt)
    assert match is not None
    return match.group(1)


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


def _configure_llm_extraction_test_runtime(
    monkeypatch: pytest.MonkeyPatch,
    step_runner: ModelStepRunner,
) -> None:
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
    monkeypatch.setattr(document_extraction, "run_single_step_with_policy", step_runner)


def test_llm_extraction_prompt_covers_rare_disease_gene_variant_associations() -> None:
    assert LLM_EXTRACTION_PROMPT_VERSION == "document_extraction.llm_extraction.v7"
    assert (
        "FBN1 loss-of-function variants ASSOCIATED_WITH Marfan syndrome"
        in LLM_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        "MECP2 pathogenic variants ASSOCIATED_WITH Rett syndrome"
        in LLM_EXTRACTION_SYSTEM_PROMPT
    )
    assert (
        "Do not discard direct gene-variant-to-disease associations"
        in LLM_EXTRACTION_SYSTEM_PROMPT
    )


def test_extract_pdf_text_marks_blank_pdf_as_image_likely() -> None:
    from pypdf import PdfWriter

    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)

    extraction = extract_pdf_text(buffer.getvalue())

    assert extraction.page_count == 1
    assert extraction.text_content == ""
    assert extraction.extraction_outcome == "no_text_image_likely"
    assert extraction.pages_without_text == (1,)


def test_extract_pdf_text_marks_mixed_pages_as_partial_ocr_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakePdfPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class _FakePdfReader:
        def __init__(self, payload: BytesIO) -> None:
            del payload
            self.pages = [
                _FakePdfPage("MED13 associates with cardiomyopathy."),
                _FakePdfPage(""),
                _FakePdfPage("FG syndrome evidence summary."),
            ]

    monkeypatch.setattr("pypdf.PdfReader", _FakePdfReader)

    extraction = extract_pdf_text(b"%PDF-1.4\nsynthetic\n%%EOF\n")

    assert extraction.page_count == 3
    assert extraction.text_content == (
        "MED13 associates with cardiomyopathy.\n\nFG syndrome evidence summary."
    )
    assert extraction.extraction_outcome == "partial_text_ocr_needed"
    assert extraction.pages_without_text == (2,)


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
        "agent_extraction_completed": True,
        "fallback_output_used": False,
        "trusted_evidence_eligible": True,
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
        "agent_extraction_completed": False,
        "fallback_output_used": True,
        "trusted_evidence_eligible": False,
        "fallback_candidate_count": 1,
        "llm_candidate_error": "LLM succeeded but returned zero usable candidates",
    }


@pytest.mark.parametrize(
    "diagnostics",
    [
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="unavailable",
            llm_candidate_error="OPENAI_API_KEY not configured",
            fallback_candidate_count=1,
        ),
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="fallback",
            fallback_candidate_count=1,
        ),
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="fallback_error",
            llm_candidate_error="synthetic llm outage",
            fallback_candidate_count=1,
        ),
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="llm_empty",
            llm_candidate_error="LLM succeeded but returned zero usable candidates",
            fallback_candidate_count=1,
        ),
    ],
)
def test_candidate_extraction_metadata_blocks_fallback_from_trusted_evidence(
    diagnostics: DocumentCandidateExtractionDiagnostics,
) -> None:
    metadata = diagnostics.as_metadata()

    assert metadata["agent_extraction_completed"] is False
    assert metadata["fallback_output_used"] is True
    assert metadata["trusted_evidence_eligible"] is False


def test_candidate_extraction_metadata_marks_agent_completion_as_trusted_eligible() -> (
    None
):
    metadata = DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=1,
    ).as_metadata()

    assert metadata["agent_extraction_completed"] is True
    assert metadata["fallback_output_used"] is False
    assert metadata["trusted_evidence_eligible"] is True


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
async def test_strict_relation_discovery_propagates_unavailable_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _missing_api_key(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        raise RuntimeError("OPENAI_API_KEY not configured")

    def _unexpected_fallback(text: str) -> list[ExtractedRelationCandidate]:
        del text
        raise AssertionError("strict extraction must not call heuristic fallback")

    monkeypatch.setattr(
        "artana_evidence_api.document_extraction_support.strict_relation_discovery."
        "extract_relation_candidates_with_llm",
        _missing_api_key,
    )
    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates",
        _unexpected_fallback,
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY not configured"):
        await discover_relation_candidates_strict(
            "The study found that MED13 was associated with cardiomyopathy.",
        )


@pytest.mark.asyncio
async def test_strict_relation_discovery_reports_empty_agent_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _empty_agent_candidates(
        text: str,
        *,
        max_relations: int = 10,
        space_context: str = "",
    ) -> list[ExtractedRelationCandidate]:
        del text, max_relations, space_context
        return []

    monkeypatch.setattr(
        "artana_evidence_api.document_extraction_support.strict_relation_discovery."
        "extract_relation_candidates_with_llm",
        _empty_agent_candidates,
    )

    candidates, diagnostics = await discover_relation_candidates_strict(
        "No relation is asserted here.",
    )

    assert candidates == []
    assert diagnostics == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="llm_empty",
        llm_candidate_error="LLM succeeded but returned zero usable candidates",
    )
    assert diagnostics.fallback_output_used is False
    assert diagnostics.as_metadata()["fallback_output_used"] is False


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


def test_extract_relation_candidates_suppresses_weak_generic_correlations() -> None:
    candidates = extract_relation_candidates(
        "MET amplification was correlated with resistance in a small exploratory cohort.",
    )

    assert candidates == []


def test_extract_relation_candidates_rejects_bare_fragment_subjects() -> None:
    candidates = extract_relation_candidates(
        "It inhibits CSF-1R. "
        "This activates signaling cascade. "
        "closely interacts with GBM cells. "
        "drug inhibits normal autophagy. "
        "RNA interacts with ultimately reducing tumor volume. "
        "ed causes reduction. "
        "MED13 inhibits CSF-1R. "
        "Wnt activates beta-catenin signaling. "
        "Hh activates Gli1 signaling.",
    )

    assert [
        (candidate.subject_label, candidate.relation_type) for candidate in candidates
    ] == [
        ("MED13", "INHIBITS"),
        ("Wnt", "ACTIVATES"),
        ("Hh", "ACTIVATES"),
    ]


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
        "agent_extraction_completed": False,
        "fallback_output_used": True,
        "trusted_evidence_eligible": False,
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

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
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
async def test_extract_relation_candidates_with_llm_repairs_known_label_curies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "subject_curie": "hgnc:22474",
                        "relation_type": "CAUSES",
                        "object": "developmental delay",
                        "object_curie": "HP:0001263",
                        "sentence": "MED13 causes developmental delay.",
                    },
                    {
                        "subject": "MED13",
                        "subject_curie": "MONDO:0000001",
                        "relation_type": "ACTIVATES",
                        "object": "EGFR",
                        "object_curie": "hgnc:3236",
                        "sentence": "MED13 activates EGFR.",
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

    candidates = await extract_relation_candidates_with_llm(
        "MED13 causes developmental delay. MED13 activates EGFR.",
    )

    assert len(candidates) == 2
    assert candidates[0].subject_curie == "HGNC:22474"
    assert candidates[0].subject_curie_source == "verified_linker"
    assert candidates[0].object_curie == "HP:0001263"
    assert candidates[0].object_curie_source == "verified_linker"
    assert candidates[1].subject_curie == "HGNC:22474"
    assert candidates[1].subject_curie_source == "verified_linker"
    assert candidates[1].object_curie == "HGNC:3236"
    assert candidates[1].object_curie_source == "model"


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_uses_agent_review_only_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        prompts.append(prompt)
        if "WEAK REVIEW-ONLY EXTRACTION PASS" not in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "congenital heart disease",
                        "sentence": (
                            "MED13 may be linked to congenital heart disease "
                            "in a subset of families."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "MED13 may be linked to congenital heart disease in a subset of families.",
    )

    assert len(prompts) == 2
    assert len(candidates) == 1
    assert candidates[0].subject_label == "MED13"
    assert candidates[0].object_label == "congenital heart disease"
    assert candidates[0].review_status == "review_only"
    assert set(candidates[0].review_reason_codes) >= {
        "hedged_language",
        "may_link",
        "weak_review_agent_pass",
        "gene_phenotype_association_requires_variant_state",
    }
    assert candidates[0].trusted_evidence_eligible is False


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_retries_zero_candidate_agent_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompts: list[str] = []
    captured_step_keys: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_prompts.append(str(kwargs["prompt"]))
        captured_step_keys.append(kwargs["step_key"])
        if len(captured_step_keys) <= 2:
            return SimpleNamespace(output={"relations": []})
        if "WEAK REVIEW-ONLY EXTRACTION PASS" in str(kwargs["prompt"]):
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "Larotrectinib",
                        "relation_type": "TREATS",
                        "object": "NTRK fusion solid tumors",
                        "sentence": (
                            "Larotrectinib treats solid tumors harboring "
                            "NTRK gene fusions regardless of tissue origin."
                        ),
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

    text = (
        "Larotrectinib treats solid tumors harboring NTRK gene fusions "
        "regardless of tissue origin."
    )
    candidates = await extract_relation_candidates_with_llm(text)

    assert len(candidates) == 1
    assert candidates[0].subject_label == "Larotrectinib"
    assert candidates[0].relation_type == "TREATS"
    assert candidates[0].object_label == "NTRK fusion solid tumors"
    assert captured_step_keys == [
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION,
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=(
                f"{LLM_EXTRACTION_PROMPT_VERSION}."
                "zero_candidate_retry.v1"
            ),
        ),
    ]
    assert "A prior relation extraction attempt returned zero usable relations" in (
        captured_prompts[2]
    )
    assert "WEAK REVIEW-ONLY EXTRACTION PASS" not in captured_prompts[2]


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_retries_zero_converted_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_step_keys: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_step_keys.append(kwargs["step_key"])
        if len(captured_step_keys) == 1:
            return SimpleNamespace(
                output={
                    "relations": [
                        {
                            "subject": "a",
                            "relation_type": "TREATS",
                            "object": "NTRK fusion solid tumors",
                            "sentence": (
                                "Larotrectinib treats solid tumors harboring "
                                "NTRK gene fusions regardless of tissue origin."
                            ),
                        },
                    ],
                },
            )
        if len(captured_step_keys) == 2 or "WEAK REVIEW-ONLY EXTRACTION PASS" in str(
            kwargs["prompt"],
        ):
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "Larotrectinib",
                        "relation_type": "TREATS",
                        "object": "NTRK fusion solid tumors",
                        "sentence": (
                            "Larotrectinib treats solid tumors harboring "
                            "NTRK gene fusions regardless of tissue origin."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "Larotrectinib treats solid tumors harboring NTRK gene fusions "
        "regardless of tissue origin.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "Larotrectinib"
    assert candidates[0].relation_type == "TREATS"
    assert candidates[0].object_label == "NTRK fusion solid tumors"
    assert len(captured_step_keys) == 3


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_retries_zero_causes_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_step_keys: list[str] = []
    text = "SMN1 loss causes spinal muscular atrophy."

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_step_keys.append(kwargs["step_key"])
        if len(captured_step_keys) <= 2:
            return SimpleNamespace(output={"relations": []})
        if "WEAK REVIEW-ONLY EXTRACTION PASS" in str(kwargs["prompt"]):
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "SMN1 loss",
                        "relation_type": "CAUSES",
                        "object": "spinal muscular atrophy",
                        "sentence": text,
                    },
                ],
            },
        )

    _configure_llm_extraction_test_runtime(
        monkeypatch,
        _fake_run_single_step_with_policy,
    )

    candidates = await extract_relation_candidates_with_llm(text)

    assert len(candidates) == 1
    assert candidates[0].subject_label == "SMN1 loss"
    assert candidates[0].relation_type == "CAUSES"
    assert candidates[0].object_label == "spinal muscular atrophy"
    assert captured_step_keys == [
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION,
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=(
                f"{LLM_EXTRACTION_PROMPT_VERSION}."
                "zero_candidate_retry.v1"
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_retries_schema_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompts: list[str] = []
    captured_step_keys: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_prompts.append(str(kwargs["prompt"]))
        captured_step_keys.append(kwargs["step_key"])
        if len(captured_step_keys) == 1:
            kwargs["output_schema"].model_validate(
                {
                    "relations": [
                        {
                            "subject": "MSI-high status",
                            "relation_type": "BIOMARKER_FOR",
                            "proposed_relation_type": "PREDICTS_RESPONSE_TO",
                            "object": "immune checkpoint inhibitor response",
                            "sentence": (
                                "MSI-high status is a biomarker for immune "
                                "checkpoint inhibitor response."
                            ),
                        },
                    ],
                },
            )
        if "WEAK REVIEW-ONLY EXTRACTION PASS" in str(kwargs["prompt"]):
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MSI-high status",
                        "relation_type": "BIOMARKER_FOR",
                        "object": "immune checkpoint inhibitor response",
                        "sentence": (
                            "MSI-high status is a biomarker for immune "
                            "checkpoint inhibitor response."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "MSI-high status is a biomarker for immune checkpoint inhibitor response.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MSI-high status"
    assert candidates[0].relation_type == "BIOMARKER_FOR"
    assert candidates[0].object_label == "immune checkpoint inhibitor response"
    assert len(captured_step_keys) == 2
    assert captured_step_keys[1] == llm_extraction_step_key(
        text=(
            "MSI-high status is a biomarker for immune checkpoint inhibitor "
            "response."
        ),
        max_relations=10,
        model_id="openai:gpt-5.4-mini",
        prompt_version=f"{LLM_EXTRACTION_PROMPT_VERSION}.schema_retry.v1",
    )
    assert "failed schema validation" in captured_prompts[1]
    assert "Do not set proposed_relation_type" in captured_prompts[1]


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_chains_schema_retry_to_zero_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_step_keys: list[str] = []
    text = "MSI-high status is a biomarker for immune checkpoint inhibitor response."

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        captured_step_keys.append(kwargs["step_key"])
        if len(captured_step_keys) == 1:
            kwargs["output_schema"].model_validate(
                {
                    "relations": [
                        {
                            "subject": "MSI-high status",
                            "relation_type": "BIOMARKER_FOR",
                            "proposed_relation_type": "PREDICTS_RESPONSE_TO",
                            "object": "immune checkpoint inhibitor response",
                            "sentence": text,
                        },
                    ],
                },
            )
        if "ZERO-CANDIDATE RETRY" in prompt and (
            "WEAK REVIEW-ONLY EXTRACTION PASS" not in prompt
        ):
            return SimpleNamespace(
                output={
                    "relations": [
                        {
                            "subject": "MSI-high status",
                            "relation_type": "BIOMARKER_FOR",
                            "object": "immune checkpoint inhibitor response",
                            "sentence": text,
                        },
                    ],
                },
            )
        if "SCHEMA REPAIR RETRY" in prompt and (
            "WEAK REVIEW-ONLY EXTRACTION PASS" not in prompt
        ):
            return SimpleNamespace(
                output={
                    "relations": [
                        {
                            "subject": "a",
                            "relation_type": "BIOMARKER_FOR",
                            "object": "immune checkpoint inhibitor response",
                            "sentence": text,
                        },
                    ],
                },
            )
        return SimpleNamespace(output={"relations": []})

    _configure_llm_extraction_test_runtime(
        monkeypatch,
        _fake_run_single_step_with_policy,
    )

    candidates = await extract_relation_candidates_with_llm(text)

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MSI-high status"
    assert candidates[0].relation_type == "BIOMARKER_FOR"
    assert candidates[0].object_label == "immune checkpoint inhibitor response"
    assert captured_step_keys == [
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=f"{LLM_EXTRACTION_PROMPT_VERSION}.schema_retry.v1",
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION,
        ),
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
            prompt_version=(
                f"{LLM_EXTRACTION_PROMPT_VERSION}."
                "zero_candidate_retry.v1"
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_skips_weak_pass_after_usable_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_step_keys: list[str] = []
    text = (
        "BRCA1 truncating variants are associated with hereditary breast and "
        "ovarian cancer."
    )

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        captured_step_keys.append(kwargs["step_key"])
        if len(captured_step_keys) == 1:
            return SimpleNamespace(
                output={
                    "relations": [
                        {
                            "subject": "BRCA1 truncating variants",
                            "relation_type": "ASSOCIATED_WITH",
                            "object": "hereditary breast and ovarian cancer",
                            "sentence": text,
                        },
                    ],
                },
            )
        raise AssertionError("weak review pass must not run after a usable primary result")

    _configure_llm_extraction_test_runtime(
        monkeypatch,
        _fake_run_single_step_with_policy,
    )

    candidates = await extract_relation_candidates_with_llm(text)

    assert len(candidates) == 1
    assert candidates[0].subject_label == "BRCA1 truncating variants"
    assert candidates[0].relation_type == "ASSOCIATED_WITH"
    assert candidates[0].object_label == "hereditary breast and ovarian cancer"
    assert captured_step_keys == [
        llm_extraction_step_key(
            text=text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
        ),
    ]


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_propagates_invalid_schema_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "MSI-high status is a biomarker for immune checkpoint inhibitor response."

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        kwargs["output_schema"].model_validate(
            {
                "relations": [
                    {
                        "subject": "MSI-high status",
                        "relation_type": "BIOMARKER_FOR",
                        "proposed_relation_type": "PREDICTS_RESPONSE_TO",
                        "object": "immune checkpoint inhibitor response",
                        "sentence": text,
                    },
                ],
            },
        )

    _configure_llm_extraction_test_runtime(
        monkeypatch,
        _fake_run_single_step_with_policy,
    )

    with pytest.raises(ValidationError):
        await extract_relation_candidates_with_llm(text)


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_propagates_runtime_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        raise RuntimeError("model transport failed")

    _configure_llm_extraction_test_runtime(
        monkeypatch,
        _fake_run_single_step_with_policy,
    )

    with pytest.raises(RuntimeError, match="model transport failed"):
        await extract_relation_candidates_with_llm(
            "MSI-high status is a biomarker for immune checkpoint inhibitor response.",
        )


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_filters_pathway_target_sibling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        if "WEAK REVIEW-ONLY EXTRACTION PASS" in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "Vemurafenib",
                        "relation_type": "TARGETS",
                        "object": "BRAF V600E",
                        "sentence": (
                            "Vemurafenib targets BRAF V600E and inhibits "
                            "MAPK signaling."
                        ),
                    },
                    {
                        "subject": "Vemurafenib",
                        "relation_type": "INHIBITS",
                        "object": "MAPK signaling",
                        "sentence": (
                            "Vemurafenib targets BRAF V600E and inhibits "
                            "MAPK signaling."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "Vemurafenib targets BRAF V600E and inhibits MAPK signaling.",
    )

    assert len(candidates) == 1
    assert candidates[0].relation_type == "TARGETS"
    assert candidates[0].trusted_evidence_eligible is True


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_drops_invalid_weak_pass_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        prompts.append(prompt)
        if "WEAK REVIEW-ONLY EXTRACTION PASS" not in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "CASES",
                        "object": "congenital heart disease",
                        "sentence": (
                            "MED13 may be linked to congenital heart disease "
                            "in a subset of families."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "MED13 may be linked to congenital heart disease in a subset of families.",
    )

    assert len(prompts) == 4
    assert "ZERO-CANDIDATE RETRY" in prompts[2]
    assert "ZERO-CANDIDATE RETRY" in prompts[3]
    assert candidates == []


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_drops_invalid_primary_pass_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        prompts.append(prompt)
        if "WEAK REVIEW-ONLY EXTRACTION PASS" in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "CASES",
                        "object": "congenital heart disease",
                        "sentence": "MED13 cases included congenital heart disease.",
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
    monkeypatch.setattr(
        document_extraction,
        "_graph_ai_preflight_service",
        lambda: (_ for _ in ()).throw(RuntimeError("resolver unavailable")),
    )

    candidates = await extract_relation_candidates_with_llm(
        "MED13 cases included congenital heart disease.",
    )

    assert len(prompts) == 4
    assert "ZERO-CANDIDATE RETRY" in prompts[2]
    assert "ZERO-CANDIDATE RETRY" in prompts[3]
    assert candidates == []


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_does_not_downgrade_strong_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        if "WEAK REVIEW-ONLY EXTRACTION PASS" not in str(kwargs["prompt"]):
            return SimpleNamespace(
                output={
                    "relations": [
                        {
                            "subject": "BRCA1",
                            "relation_type": "ACTIVATES",
                            "object": "EGFR",
                            "sentence": "BRCA1 activates EGFR.",
                        },
                    ],
                },
            )
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "BRCA1",
                        "relation_type": "ACTIVATES",
                        "object": "EGFR",
                        "sentence": "BRCA1 activates EGFR.",
                        "review_status": "review_only",
                        "review_reason_codes": ["weak_review_only"],
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

    candidates = await extract_relation_candidates_with_llm("BRCA1 activates EGFR.")

    assert len(candidates) == 1
    assert candidates[0].review_status == "candidate"
    assert candidates[0].review_reason_codes == ()
    assert candidates[0].trusted_evidence_eligible is True


@pytest.mark.asyncio
async def test_weak_pass_does_not_poison_strong_claim_in_mixed_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentence = (
        "BRCA1 activates EGFR, while MED13 may be linked to congenital heart "
        "disease."
    )

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "BRCA1",
                        "relation_type": "ACTIVATES",
                        "object": "EGFR",
                        "sentence": sentence,
                        "review_status": (
                            "review_only"
                            if "WEAK REVIEW-ONLY EXTRACTION PASS"
                            in str(kwargs["prompt"])
                            else "candidate"
                        ),
                        "review_reason_codes": (
                            ["weak_review_only"]
                            if "WEAK REVIEW-ONLY EXTRACTION PASS"
                            in str(kwargs["prompt"])
                            else []
                        ),
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

    candidates = await extract_relation_candidates_with_llm(sentence)

    assert len(candidates) == 1
    assert candidates[0].review_status == "candidate"
    assert candidates[0].review_reason_codes == ()
    assert candidates[0].trusted_evidence_eligible is True


@pytest.mark.asyncio
async def test_weak_pass_drops_structured_relation_type_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        prompts.append(prompt)
        if "WEAK REVIEW-ONLY EXTRACTION PASS" not in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "PROPOSE_NEW_RELATION_TYPE",
                        "proposed_relation_type": "WEAKLY_LINKED_TO",
                        "new_relation_type_rationale": (
                            "Hedged association should stay out of relation "
                            "governance from the weak pass."
                        ),
                        "object": "congenital heart disease",
                        "sentence": (
                            "MED13 may be linked to congenital heart disease."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "MED13 may be linked to congenital heart disease.",
    )

    assert len(prompts) == 4
    assert "ZERO-CANDIDATE RETRY" in prompts[2]
    assert "ZERO-CANDIDATE RETRY" in prompts[3]
    assert candidates == []


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_keeps_structured_new_type_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "BRCA1 loss",
                        "relation_type": "PROPOSE_NEW_RELATION_TYPE",
                        "proposed_relation_type": "REDUCES_TOXICITY_OF",
                        "new_relation_type_rationale": (
                            "Toxicity-specific treatment effect needs governance."
                        ),
                        "object": "cisplatin",
                        "sentence": "BRCA1 loss reduces cisplatin toxicity.",
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

    candidates = await extract_relation_candidates_with_llm(
        "BRCA1 loss reduces cisplatin toxicity.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "BRCA1 loss"
    assert candidates[0].relation_type == "PROPOSE_NEW_RELATION_TYPE"
    assert candidates[0].proposed_relation_type == "REDUCES_TOXICITY_OF"
    assert candidates[0].new_relation_type_rationale == (
        "Toxicity-specific treatment effect needs governance."
    )
    assert candidates[0].object_label == "cisplatin"
    assert candidates[0].relation_governance_status == "requires_relation_review"
    assert candidates[0].trusted_evidence_eligible is False


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_filters_review_required_raw_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api.relation_type_resolver import (
        RelationTypeAction,
        RelationTypeDecision,
    )

    class _PermissiveExtractionSchema:
        @classmethod
        def model_validate(cls, payload):
            return SimpleNamespace(
                relations=[
                    SimpleNamespace(
                        subject=relation["subject"],
                        relation_type=relation["relation_type"],
                        object=relation["object"],
                        sentence=relation["sentence"],
                    )
                    for relation in payload["relations"]
                ],
            )

    class _ReviewRequiredPreflight:
        async def resolve_relation_type(self, **kwargs):
            assert kwargs["relation_type"] == "PROTECTS_AGAINST"
            return RelationTypeDecision(
                action=RelationTypeAction.REQUIRES_REVIEW,
                canonical_type="PROTECTS_AGAINST",
                reasoning="Governed review required before use.",
            )

    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MET amplification",
                        "relation_type": "PROTECTS_AGAINST",
                        "object": "erlotinib",
                        "sentence": "MET amplification protects against erlotinib.",
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
        "build_llm_extraction_output_schema",
        lambda _max_relations: _PermissiveExtractionSchema,
    )
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )
    monkeypatch.setattr(
        document_extraction,
        "_graph_ai_preflight_service",
        _ReviewRequiredPreflight,
    )

    candidates = await extract_relation_candidates_with_llm(
        "MET amplification protects against erlotinib.",
    )

    assert candidates == []


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_prunes_redundant_generic_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "EGFR",
                        "sentence": "MED13 activates EGFR and is associated with EGFR.",
                    },
                    {
                        "subject": "MED13",
                        "relation_type": "ACTIVATES",
                        "object": "EGFR",
                        "sentence": "MED13 activates EGFR and is associated with EGFR.",
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

    candidates = await extract_relation_candidates_with_llm(
        "MED13 activates EGFR and is associated with EGFR.",
    )

    assert len(candidates) == 1
    assert candidates[0].relation_type == "ACTIVATES"
    assert candidates[0].subject_label == "MED13"
    assert candidates[0].object_label == "EGFR"


@pytest.mark.asyncio
async def test_discover_relation_candidates_reports_llm_pruned_generic_siblings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ASSOCIATED_WITH",
            object_label="EGFR",
            sentence="MED13 activates EGFR and is associated with EGFR.",
        ),
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ACTIVATES",
            object_label="EGFR",
            sentence="MED13 activates EGFR and is associated with EGFR.",
        ),
    ]

    async def _fake_extract_relation_candidates_with_llm(*_args, **_kwargs):
        return llm_candidates

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _fake_extract_relation_candidates_with_llm,
    )

    candidates, diagnostics = await discover_relation_candidates(
        "MED13 activates EGFR and is associated with EGFR.",
    )

    assert len(candidates) == 1
    assert candidates[0].relation_type == "ACTIVATES"
    assert diagnostics.llm_candidate_status == "completed"
    assert diagnostics.llm_candidate_count == 1
    assert diagnostics.pruned_generic_relation_count == 1
    assert diagnostics.as_metadata()["pruned_generic_relation_count"] == 1


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_keeps_weak_generic_review_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **_kwargs):
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MET amplification",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "resistance",
                        "sentence": (
                            "MET amplification was correlated with resistance "
                            "in a small exploratory cohort."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "MET amplification was correlated with resistance in a small exploratory cohort.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MET amplification"
    assert candidates[0].relation_type == "ASSOCIATED_WITH"
    assert candidates[0].object_label == "resistance"
    assert candidates[0].review_status == "review_only"
    assert candidates[0].trusted_evidence_eligible is False


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_repairs_weak_met_resistance_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = str(kwargs["prompt"])
        if "WEAK REVIEW-ONLY EXTRACTION PASS" not in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MET amplification",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "EGFR inhibition",
                        "sentence": (
                            "MET amplification was correlated with resistance "
                            "to EGFR inhibition in a small exploratory cohort."
                        ),
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

    candidates = await extract_relation_candidates_with_llm(
        "MET amplification was correlated with resistance to EGFR inhibition "
        "in a small exploratory cohort.",
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MET amplification"
    assert candidates[0].relation_type == "ASSOCIATED_WITH"
    assert candidates[0].object_label == "resistance to EGFR inhibition"
    assert candidates[0].review_status == "review_only"
    assert "correlated_only" in candidates[0].review_reason_codes
    assert candidates[0].trusted_evidence_eligible is False


def test_llm_extraction_step_key_uses_full_text_beyond_prefix() -> None:
    shared_prefix = "Background sentence. " * 250
    first_text = f"{shared_prefix} BRCA1 activates EGFR."
    second_text = f"{shared_prefix} MED13 regulates cardiomyopathy."

    assert first_text[:4000] == second_text[:4000]
    assert llm_extraction_step_key(
        text=first_text,
        max_relations=10,
        model_id="openai/gpt-5.4-mini",
    ) != llm_extraction_step_key(
        text=second_text,
        max_relations=10,
        model_id="openai/gpt-5.4-mini",
    )


@pytest.mark.asyncio
async def test_extract_relation_candidates_with_llm_reads_beyond_first_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_prompts: list[str] = []

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        prompt = kwargs["prompt"]
        captured_prompts.append(prompt)
        if "MED13 causes developmental delay." not in prompt:
            return SimpleNamespace(output={"relations": []})
        return SimpleNamespace(
            output={
                "relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "CAUSES",
                        "object": "developmental delay",
                        "sentence": "MED13 causes developmental delay.",
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

    long_text = (
        ("Background sentence without extractable relations. " * 120)
        + "MED13 causes developmental delay."
    )

    candidates, diagnostics = await extract_relation_candidates_with_diagnostics(
        long_text,
    )

    assert len(candidates) == 1
    assert candidates[0].subject_label == "MED13"
    assert candidates[0].relation_type == "CAUSES"
    assert diagnostics.llm_candidate_status == "completed"
    assert diagnostics.llm_extraction_chunk_count >= 2
    assert diagnostics.as_metadata()["llm_extraction_chunk_count"] >= 2
    assert len(captured_prompts) >= 2


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
        llm_extraction_step_key(
            text=first_text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
        ),
        llm_extraction_step_key(
            text=first_text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
        ),
        llm_extraction_step_key(
            text=second_text,
            max_relations=10,
            model_id="openai:gpt-5.4-mini",
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

    async def _fake_run_single_step_with_policy(*_args, **kwargs):
        return SimpleNamespace(
            output={
                "reviews": [
                    {
                        "draft_ref": _proposal_review_ref_from_prompt(kwargs["prompt"]),
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
                timeout_seconds=30.0,
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
                        "draft_ref": _proposal_review_ref_from_prompt(kwargs["prompt"]),
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
                timeout_seconds=30.0,
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
                timeout_seconds=0.001,
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
async def test_pre_resolve_entities_with_ai_skips_ambiguous_gene_family_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_labels: list[str] = []
    ai_labels: list[str] = []

    def _fake_exact_match(*, space_id, label: str, graph_api_gateway):
        del space_id, graph_api_gateway
        exact_labels.append(label)

    async def _fake_resolve_entity_with_ai(
        *,
        space_id,
        label: str,
        graph_api_gateway,
        space_context: str = "",
    ) -> dict[str, str] | None:
        del space_id, graph_api_gateway, space_context
        ai_labels.append(label)
        return {
            "id": f"resolved:{label}",
            "display_label": f"{label} resolved",
        }

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
                subject_label="MED13 or MED13L",
                relation_type="ASSOCIATED_WITH",
                object_label="developmental disorder",
                sentence="MED13 or MED13L was associated with developmental disorder.",
            ),
        ],
        graph_api_gateway=_EmptyGraphApiGateway(),
        space_context="Investigate MED13 family disorder evidence.",
    )

    assert exact_labels == ["developmental disorder"]
    assert ai_labels == ["developmental disorder"]
    assert resolved == {
        "developmental disorder": {
            "id": "resolved:developmental disorder",
            "display_label": "developmental disorder resolved",
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
