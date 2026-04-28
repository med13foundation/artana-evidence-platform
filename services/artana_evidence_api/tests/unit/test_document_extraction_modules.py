"""Unit coverage for extracted document-extraction helper modules."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from artana_evidence_api.document_context_summary import summarize_document_context
from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
    DocumentProposalReviewDiagnostics,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_diagnostics import (
    candidate_completed,
    candidate_fallback,
    candidate_llm_empty,
    candidate_not_needed,
    proposal_review_completed,
    proposal_review_fallback_error,
    proposal_review_not_needed,
    proposal_review_unavailable,
    runtime_error_candidate_status,
)
from artana_evidence_api.document_extraction_drafts import (
    build_document_extraction_drafts,
)
from artana_evidence_api.document_extraction_entities import (
    build_unresolved_entity_id,
    clean_candidate_label,
    clean_llm_entity_label,
    require_match_display_label,
    require_match_id,
    resolve_exact_entity_label,
    split_compound_entity_label,
)
from artana_evidence_api.document_extraction_prompting import (
    build_llm_extraction_output_schema,
    build_proposal_review_output_schema,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_RELATION_SYNONYMS,
    LLM_VALID_RELATION_TYPES,
)
from artana_evidence_api.document_extraction_review import (
    apply_document_proposal_review,
    build_document_review_context,
    build_fallback_document_review,
    goal_context_summary,
    review_from_draft_metadata,
    shorten_text,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft


class _GraphGateway:
    def __init__(self, labels: dict[str, dict[str, object]] | None = None) -> None:
        self._labels = {} if labels is None else labels

    def list_entities(self, *, space_id, q: str, limit: int):  # noqa: ANN001
        del space_id, limit
        entities = []
        for key, payload in self._labels.items():
            aliases = payload.get("aliases", [])
            if key.casefold() != q.casefold() and q.casefold() not in {
                str(alias).casefold() for alias in aliases
            }:
                continue
            entities.append(
                SimpleNamespace(
                    id=payload["id"],
                    display_label=payload["display_label"],
                    aliases=aliases,
                ),
            )
        return SimpleNamespace(entities=entities)


def _document() -> HarnessDocumentRecord:
    now = datetime.now(UTC)
    return HarnessDocumentRecord(
        id="document-1",
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="MED13 document",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="sha",
        byte_size=1,
        page_count=None,
        text_content="MED13 activates EGFR.",
        text_excerpt="MED13 activates EGFR.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="completed",
        metadata={},
        created_at=now,
        updated_at=now,
    )


def test_diagnostics_builders_normalize_candidate_and_review_status() -> None:
    assert candidate_not_needed() == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="not_needed",
    )
    assert candidate_completed(candidate_count=2) == (
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=2,
        )
    )
    assert candidate_llm_empty(fallback_candidate_count=1).as_metadata() == {
        "llm_candidate_status": "llm_empty",
        "llm_candidate_attempted": True,
        "llm_candidate_failed": False,
        "fallback_candidate_count": 1,
        "llm_candidate_error": "LLM succeeded but returned zero usable candidates",
    }
    assert candidate_fallback(
        status="unavailable",
        error="missing key",
        fallback_candidate_count=3,
    ).llm_candidate_status == "unavailable"
    assert runtime_error_candidate_status("OPENAI_API_KEY not configured") == (
        "unavailable"
    )
    assert runtime_error_candidate_status("boom") == "fallback_error"

    assert proposal_review_not_needed() == DocumentProposalReviewDiagnostics(
        llm_review_status="not_needed",
    )
    assert proposal_review_unavailable("missing").llm_review_status == "unavailable"
    assert proposal_review_fallback_error("timeout").llm_review_status == (
        "fallback_error"
    )
    assert proposal_review_completed() == DocumentProposalReviewDiagnostics(
        llm_review_status="completed",
    )


def test_prompt_schema_builders_validate_structured_outputs() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)
    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "MED13",
                    "relation_type": "ACTIVATES",
                    "object": "EGFR",
                    "sentence": "MED13 activates EGFR.",
                },
            ],
        },
    )
    assert parsed.relations[0].subject == "MED13"

    review_schema = build_proposal_review_output_schema()
    review = review_schema.model_validate(
        {
            "reviews": [
                {
                    "index": 0,
                    "factual_support": "strong",
                    "goal_relevance": "direct",
                    "priority": "prioritize",
                    "rationale": "Directly supported.",
                    "factual_rationale": "The sentence is direct.",
                    "relevance_rationale": "Matches the objective.",
                },
            ],
        },
    )
    assert review.reviews[0].priority == "prioritize"

    with pytest.raises(ValueError):
        extraction_schema.model_validate({"relations": [{"subject": ""}]})


def test_relation_taxonomy_keeps_canonical_types_and_synonyms_together() -> None:
    assert "ASSOCIATED_WITH" in LLM_VALID_RELATION_TYPES
    assert "ACTIVATES" in LLM_VALID_RELATION_TYPES
    assert LLM_RELATION_SYNONYMS["CORRELATED_WITH"] == "ASSOCIATED_WITH"
    assert LLM_RELATION_SYNONYMS["STIMULATES"] == "ACTIVATES"
    assert all(
        canonical_type in LLM_VALID_RELATION_TYPES
        for canonical_type in LLM_RELATION_SYNONYMS.values()
    )


def test_entity_helpers_clean_split_and_resolve_labels() -> None:
    gateway = _GraphGateway(
        {
            "EGFR": {
                "id": uuid4(),
                "display_label": "EGFR",
                "aliases": ["ERBB1"],
            },
            "AKT1": {
                "id": uuid4(),
                "display_label": "AKT1",
                "aliases": [],
            },
        },
    )
    space_id = uuid4()

    assert clean_candidate_label("mutation in MED13 in patients") == "MED13"
    assert clean_llm_entity_label("Inherited pathogenic variants in BRCA1") == "BRCA1"
    assert build_unresolved_entity_id("MED13 gene") == "unresolved:med13_gene"
    assert split_compound_entity_label(
        space_id=space_id,
        label="EGFR and AKT1",
        graph_api_gateway=gateway,
    ) == ("EGFR", "AKT1")
    resolved = resolve_exact_entity_label(
        space_id=space_id,
        label="ERBB1",
        graph_api_gateway=gateway,
    )
    assert resolved is not None
    assert require_match_display_label(resolved) == "EGFR"
    assert require_match_id(resolved) != ""


def test_review_helpers_apply_ranked_metadata_to_drafts() -> None:
    context = build_document_review_context(
        objective="Study MED13 EGFR activation.",
        current_hypotheses=("MED13 activates EGFR", "MED13 activates EGFR"),
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )
    review = build_fallback_document_review(
        candidate=candidate,
        review_context=context,
    )
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="document-1:0",
        title="MED13 activates EGFR",
        summary="MED13 activates EGFR.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[{"relevance": 0.1}],
        payload={},
        metadata={},
        document_id="document-1",
    )

    updated = apply_document_proposal_review(
        draft=draft,
        review=review,
        review_context=context,
    )

    assert "Objective: Study MED13 EGFR activation." in goal_context_summary(context)
    assert shorten_text("a " * 20, max_length=10).endswith("...")
    assert updated.confidence > draft.confidence
    assert updated.metadata["proposal_review"]["method"] == "heuristic_fallback_v1"
    assert review_from_draft_metadata(updated) == review


def test_draft_builder_assembles_reviewed_proposals_from_candidates() -> None:
    gateway = _GraphGateway()
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=gateway,
        review_context=build_document_review_context(
            objective="Study MED13 activates EGFR.",
        ),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].payload["proposed_subject"] == "unresolved:med13"
    assert drafts[0].payload["proposed_object"] == "unresolved:egfr"
    assert drafts[0].metadata["proposal_review"]["goal_relevance"] == "direct"


def test_draft_builder_uses_resolved_entities_and_splits_compound_objects() -> None:
    med13_id = uuid4()
    egfr_id = uuid4()
    akt1_id = uuid4()
    gateway = _GraphGateway(
        {
            "MED13": {
                "id": med13_id,
                "display_label": "MED13",
                "aliases": [],
            },
            "EGFR": {
                "id": egfr_id,
                "display_label": "EGFR",
                "aliases": [],
            },
            "AKT1": {
                "id": akt1_id,
                "display_label": "AKT1",
                "aliases": [],
            },
        },
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR and AKT1",
        sentence="MED13 was associated with EGFR and AKT1.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=gateway,
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 2
    assert [draft.payload["proposed_subject"] for draft in drafts] == [
        str(med13_id),
        str(med13_id),
    ]
    assert {draft.payload["proposed_object"] for draft in drafts} == {
        str(egfr_id),
        str(akt1_id),
    }
    assert all(draft.metadata["object_split_applied"] is True for draft in drafts)


def test_document_context_summary_lists_documents_and_top_proposals() -> None:
    summary = summarize_document_context(
        documents=(_document(),),
        proposals_by_document_id={
            "document-1": [
                {"summary": "First claim."},
                {"summary": "Second claim."},
                {"summary": "Third claim."},
                {"summary": "Ignored fourth claim."},
            ],
        },
    )

    assert summary is not None
    assert "MED13 document [text] (4 staged proposal(s))" in summary
    assert "First claim." in summary
    assert "Ignored fourth claim." not in summary
