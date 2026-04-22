"""Unit tests for graph-chat verification and answer synthesis."""

from __future__ import annotations

import asyncio

from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphSearchContract,
    GraphSearchGroundingLevel,
    GraphSearchResultEntry,
    build_graph_search_assessment_from_confidence,
)
from artana_evidence_api.graph_chat_runtime import (
    HarnessGraphChatRequest,
    HarnessGraphChatRunner,
)
from artana_evidence_api.graph_search_runtime import HarnessGraphSearchResult


class _StubGraphSearchRunner:
    def __init__(self, result: GraphSearchContract) -> None:
        self._result = result

    async def run(self, request: object) -> HarnessGraphSearchResult:
        del request
        return HarnessGraphSearchResult(
            contract=self._result,
            agent_run_id=self._result.agent_run_id,
            active_skill_names=("graph_harness.graph_grounding",),
        )


def _graph_chat_request(
    *,
    pending_review_proposal_count: int = 0,
) -> HarnessGraphChatRequest:
    return HarnessGraphChatRequest(
        question="What does MED13 do?",
        research_space_id="space-1",
        model_id=None,
        max_depth=2,
        top_k=10,
        include_evidence_chains=True,
        objective="Map MED13 mechanism evidence.",
        current_hypotheses=("MED13 regulates a transcriptional program.",),
        pending_questions=("What evidence should we review next?",),
        graph_snapshot_summary={"claim_count": 1},
        pending_review_proposal_count=pending_review_proposal_count,
    )


def _graph_search_result(
    *,
    relevance_score: float,
    warnings: list[str],
    matching_relation_ids: list[str],
) -> GraphSearchContract:
    assessment = build_graph_search_assessment_from_confidence(
        relevance_score,
        confidence_rationale="Synthetic graph-search result.",
        grounding_level=GraphSearchGroundingLevel.AGGREGATED,
    )
    return GraphSearchContract(
        decision="generated",
        assessment=assessment,
        rationale="Synthetic graph-search result.",
        evidence=[
            EvidenceItem(
                source_type="db",
                locator="entity:med13",
                excerpt="Synthetic MED13 evidence",
                relevance=relevance_score,
            ),
        ],
        research_space_id="space-1",
        original_query="What does MED13 do?",
        interpreted_intent="What does MED13 do?",
        query_plan_summary="Synthetic query plan.",
        total_results=1,
        results=[
            GraphSearchResultEntry(
                entity_id="entity-1",
                entity_type="gene",
                display_label="MED13",
                relevance_score=relevance_score,
                assessment=assessment,
                matching_observation_ids=["obs-1"],
                matching_relation_ids=matching_relation_ids,
                evidence_chain=[],
                explanation="Synthetic explanation.",
                support_summary="Synthetic support summary.",
            ),
        ],
        executed_path="agent",
        warnings=warnings,
        agent_run_id="graph_chat:test-search",
    )


def test_graph_chat_runner_marks_grounded_answers_verified() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            _graph_search_result(
                relevance_score=0.91,
                warnings=[],
                matching_relation_ids=["rel-1"],
            ),
        ),
    )

    result = asyncio.run(runner.run(_graph_chat_request()))

    assert result.verification.status == "verified"
    assert result.verification.allows_graph_write is True
    assert result.graph_write_candidates == []
    assert result.fresh_literature is None
    assert result.answer_text.startswith("Grounded graph answer:")
    assert result.search.assessment is not None
    assert result.search.assessment.support_band == "STRONG"
    assert result.search.results[0].assessment is not None
    assert result.search.results[0].assessment.support_band == "STRONG"
    assert result.warnings == []


def test_graph_chat_runner_marks_warning_backed_answers_needs_review() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            _graph_search_result(
                relevance_score=0.78,
                warnings=["Synthetic graph-search warning."],
                matching_relation_ids=["rel-1"],
            ),
        ),
    )

    result = asyncio.run(runner.run(_graph_chat_request()))

    assert result.verification.status == "needs_review"
    assert result.verification.allows_graph_write is False
    assert result.graph_write_candidates == []
    assert result.fresh_literature is None
    assert result.answer_text.startswith("Preliminary graph answer:")
    assert any(
        warning.startswith("Grounded-answer verification:")
        for warning in result.warnings
    )


def test_graph_chat_runner_marks_empty_results_unverified() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            GraphSearchContract(
                decision="generated",
                assessment=build_graph_search_assessment_from_confidence(
                    0.22,
                    confidence_rationale="Synthetic empty graph-search result.",
                    grounding_level=GraphSearchGroundingLevel.NONE,
                ),
                rationale="Synthetic empty graph-search result.",
                evidence=[],
                research_space_id="space-1",
                original_query="What does MED13 do?",
                interpreted_intent="What does MED13 do?",
                query_plan_summary="Synthetic query plan.",
                total_results=0,
                results=[],
                executed_path="agent",
                warnings=[],
                agent_run_id="graph_chat:test-search-empty",
            ),
        ),
    )

    result = asyncio.run(runner.run(_graph_chat_request()))

    assert result.verification.status == "unverified"
    assert result.verification.allows_graph_write is False
    assert result.graph_write_candidates == []
    assert result.fresh_literature is None
    assert result.answer_text.startswith("I did not find grounded graph results")


def test_graph_chat_runner_surfaces_pending_review_guidance_when_empty() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            GraphSearchContract(
                decision="generated",
                assessment=build_graph_search_assessment_from_confidence(
                    0.22,
                    confidence_rationale="Synthetic empty graph-search result.",
                    grounding_level=GraphSearchGroundingLevel.NONE,
                ),
                rationale="Synthetic empty graph-search result.",
                evidence=[],
                research_space_id="space-1",
                original_query="What does MED13 do?",
                interpreted_intent="What does MED13 do?",
                query_plan_summary="Synthetic query plan.",
                total_results=0,
                results=[],
                executed_path="agent",
                warnings=[],
                agent_run_id="graph_chat:test-search-empty",
            ),
        ),
    )
    result = asyncio.run(
        runner.run(_graph_chat_request(pending_review_proposal_count=1)),
    )

    assert "1 pending-review proposal waiting in the review queue" in result.answer_text
    assert "Promoting it will add claims to the graph" in result.answer_text
    assert any(
        warning.startswith(
            "There is 1 pending-review proposal waiting in the review queue"
        )
        for warning in result.warnings
    )


def test_graph_chat_runner_uses_plural_guidance_for_multiple_pending_reviews() -> None:
    runner = HarnessGraphChatRunner(
        graph_search_runner=_StubGraphSearchRunner(
            GraphSearchContract(
                decision="generated",
                assessment=build_graph_search_assessment_from_confidence(
                    0.22,
                    confidence_rationale="Synthetic empty graph-search result.",
                    grounding_level=GraphSearchGroundingLevel.NONE,
                ),
                rationale="Synthetic empty graph-search result.",
                evidence=[],
                research_space_id="space-1",
                original_query="What does MED13 do?",
                interpreted_intent="What does MED13 do?",
                query_plan_summary="Synthetic query plan.",
                total_results=0,
                results=[],
                executed_path="agent",
                warnings=[],
                agent_run_id="graph_chat:test-search-empty",
            ),
        ),
    )

    result = asyncio.run(
        runner.run(_graph_chat_request(pending_review_proposal_count=4)),
    )

    assert (
        "4 pending-review proposals waiting in the review queue"
        in result.answer_text
    )
    assert "Promoting them will add claims to the graph" in result.answer_text
