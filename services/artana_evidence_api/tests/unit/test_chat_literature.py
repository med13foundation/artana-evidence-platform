"""Unit tests for graph-chat literature refresh helpers."""

from __future__ import annotations

from artana_evidence_api.agent_contracts import GraphSearchContract
from artana_evidence_api.chat_literature import (
    build_chat_literature_answer_supplement,
    build_chat_literature_request,
)
from artana_evidence_api.graph_chat_runtime import (
    GraphChatEvidenceItem,
    GraphChatResult,
    GraphChatVerification,
)


def _chat_result() -> GraphChatResult:
    return GraphChatResult(
        answer_text="Preliminary graph answer:\nMED13: synthetic answer.",
        chat_summary="Answered with 1 grounded graph match. Verification: needs_review.",
        evidence_bundle=[
            GraphChatEvidenceItem(
                entity_id="entity-1",
                entity_type="gene",
                display_label="MED13",
                relevance_score=0.72,
                support_summary="Synthetic support summary.",
                explanation="Synthetic explanation.",
            ),
        ],
        warnings=["Synthetic warning."],
        verification=GraphChatVerification(
            status="needs_review",
            reason="Synthetic warning requires review.",
            grounded_match_count=1,
            top_relevance_score=0.72,
            warning_count=1,
            allows_graph_write=False,
        ),
        search=GraphSearchContract(
            decision="generated",
            confidence_score=0.72,
            rationale="Synthetic graph-search result.",
            evidence=[],
            research_space_id="space-1",
            original_query="What does the graph say about MED13?",
            interpreted_intent="What does the graph say about MED13?",
            query_plan_summary="Synthetic plan.",
            total_results=1,
            results=[],
            executed_path="agent",
            warnings=["Synthetic warning."],
            agent_run_id="graph_chat:test-search",
        ),
    )


def test_build_chat_literature_request_uses_gene_symbol_and_objective() -> None:
    request = build_chat_literature_request(
        question="What does the graph say about MED13?",
        objective="Map MED13 mechanism evidence in cardiomyopathy.",
        result=_chat_result(),
    )

    assert request.gene_symbol == "MED13"
    assert request.search_term == "Map mechanism evidence cardiomyopathy"
    assert request.max_results == 5


def test_build_chat_literature_answer_supplement_formats_preview_records() -> None:
    supplement = build_chat_literature_answer_supplement(
        query_preview="MED13[Title/Abstract] AND mechanism",
        preview_records=[
            {"pmid": "pmid-1", "title": "Synthetic PubMed result 1"},
            {"pmid": "pmid-2", "title": "Synthetic PubMed result 2"},
            {"pmid": "pmid-3", "title": "Synthetic PubMed result 3"},
            {"pmid": "pmid-4", "title": "Synthetic PubMed result 4"},
        ],
    )

    assert supplement is not None
    assert "Fresh literature to review:" in supplement
    assert "PubMed query: MED13[Title/Abstract] AND mechanism" in supplement
    assert "- Synthetic PubMed result 1 (pmid-1)" in supplement
    assert "- Synthetic PubMed result 3 (pmid-3)" in supplement
    assert "Synthetic PubMed result 4" not in supplement
