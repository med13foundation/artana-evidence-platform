from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import httpx

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from artana_api import ArtanaClient

DEFAULT_SPACE_ID = "11111111-1111-1111-1111-111111111111"
ALT_SPACE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
RUN_ID = "22222222-2222-2222-2222-222222222222"
ENTITY_ID = "33333333-3333-3333-3333-333333333333"


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    default_space_id: str | None = DEFAULT_SPACE_ID,
    api_key: str | None = "artana_test_key",
    access_token: str | None = "test_bearer_token",
    openai_api_key: str | None = "openai_test_key",
    default_headers: dict[str, str] | None = None,
) -> ArtanaClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://artana.test",
        transport=transport,
    )
    return ArtanaClient(
        base_url="https://artana.test",
        api_key=api_key,
        access_token=access_token,
        openai_api_key=openai_api_key,
        default_space_id=default_space_id,
        default_headers=default_headers,
        client=http_client,
    )


def run_payload(
    *,
    run_id: str = RUN_ID,
    space_id: str = DEFAULT_SPACE_ID,
    harness_id: str,
    title: str,
    status: str = "completed",
    input_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": run_id,
        "space_id": space_id,
        "harness_id": harness_id,
        "title": title,
        "status": status,
        "input_payload": {} if input_payload is None else input_payload,
        "graph_service_status": "ok",
        "graph_service_version": "2026.03.20",
        "created_at": "2026-03-20T10:00:00Z",
        "updated_at": "2026-03-20T10:00:01Z",
    }


def graph_search_response() -> dict[str, object]:
    return {
        "run": run_payload(
            harness_id="graph-search",
            title="Graph Search Agent Run",
            input_payload={"question": "What is known about MED13?"},
        ),
        "result": {
            "decision": "generated",
            "research_space_id": DEFAULT_SPACE_ID,
            "original_query": "What is known about MED13?",
            "interpreted_intent": "Find MED13-related graph evidence",
            "query_plan_summary": "Query entities, relations, and evidence",
            "total_results": 1,
            "results": [
                {
                    "entity_id": ENTITY_ID,
                    "entity_type": "GENE",
                    "display_label": "MED13",
                    "relevance_score": 0.99,
                    "matching_observation_ids": [],
                    "matching_relation_ids": [],
                    "evidence_chain": [],
                    "explanation": "MED13 is directly present in the graph.",
                    "support_summary": "1 strongly matching entity found.",
                },
            ],
            "executed_path": "agent",
            "warnings": [],
            "agent_run_id": "graph-search-run-1",
            "confidence_score": 0.98,
            "rationale": "Direct entity match",
            "evidence": [],
        },
    }


def graph_connection_response() -> dict[str, object]:
    return {
        "run": run_payload(
            harness_id="graph-connections",
            title="Graph Connection Agent Run",
            input_payload={"seed_entity_ids": [ENTITY_ID]},
        ),
        "outcomes": [
            {
                "decision": "generated",
                "source_type": "pubmed",
                "research_space_id": DEFAULT_SPACE_ID,
                "seed_entity_id": ENTITY_ID,
                "proposed_relations": [
                    {
                        "source_id": ENTITY_ID,
                        "relation_type": "ASSOCIATED_WITH",
                        "target_id": "44444444-4444-4444-4444-444444444444",
                        "assessment": {
                            "support_band": "STRONG",
                            "grounding_level": "GRAPH_INFERENCE",
                            "mapping_status": "NOT_APPLICABLE",
                            "speculation_level": "NOT_APPLICABLE",
                            "confidence_rationale": "Supported by multiple literature signals.",
                        },
                        "confidence": 0.88,
                        "evidence_summary": "Supported by multiple literature signals.",
                        "evidence_tier": "COMPUTATIONAL",
                        "supporting_provenance_ids": [
                            "55555555-5555-5555-5555-555555555555",
                        ],
                        "supporting_document_count": 3,
                        "reasoning": "Observed across multiple supporting sources.",
                    },
                ],
                "rejected_candidates": [],
                "shadow_mode": True,
                "agent_run_id": "graph-connection-run-1",
                "confidence_score": 0.91,
                "rationale": "Strong evidence-backed relation candidate",
                "evidence": [],
            },
        ],
    }


def onboarding_start_response() -> dict[str, object]:
    return {
        "run": run_payload(
            harness_id="research-onboarding",
            title="MED13 Onboarding",
            input_payload={"research_title": "MED13"},
        ),
        "research_state": {
            "space_id": DEFAULT_SPACE_ID,
            "objective": "Understand MED13 disease mechanisms",
            "current_hypotheses": [],
            "explored_questions": [],
            "pending_questions": ["Which phenotype focus matters most?"],
            "last_graph_snapshot_id": None,
            "active_schedules": [],
            "confidence_model": {},
            "budget_policy": {},
            "metadata": {},
            "created_at": "2026-03-20T10:00:00Z",
            "updated_at": "2026-03-20T10:00:01Z",
        },
        "intake_artifact": {"research_title": "MED13"},
        "assistant_message": {
            "message_type": "clarification_request",
            "title": "A few details to lock in",
            "summary": "Need one more detail before planning.",
            "sections": [{"heading": "Scope", "body": "This will shape the search."}],
            "questions": [
                {
                    "id": "q-1",
                    "prompt": "What phenotype focus matters most?",
                    "helper_text": None,
                },
            ],
            "suggested_actions": [
                {
                    "id": "reply",
                    "label": "Answer question",
                    "action_type": "reply",
                },
            ],
            "artifacts": [],
            "state_patch": {
                "thread_status": "your_turn",
                "onboarding_status": "awaiting_researcher_reply",
                "pending_question_count": 1,
                "objective": "Understand MED13 disease mechanisms",
                "explored_questions": [],
                "pending_questions": ["Which phenotype focus matters most?"],
                "current_hypotheses": [],
            },
            "agent_run_id": "onboarding-run-1",
            "warnings": [],
            "confidence_score": 0.92,
            "rationale": "Need user clarification before planning",
            "evidence": [],
        },
    }


def artifact_payload(
    *,
    key: str = "graph_search_result",
    content: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "key": key,
        "media_type": "application/json",
        "content": {} if content is None else content,
        "created_at": "2026-03-20T10:00:00Z",
        "updated_at": "2026-03-20T10:00:01Z",
    }


__all__ = [
    "ALT_SPACE_ID",
    "DEFAULT_SPACE_ID",
    "ENTITY_ID",
    "RUN_ID",
    "artifact_payload",
    "graph_connection_response",
    "graph_search_response",
    "make_client",
    "onboarding_start_response",
    "run_payload",
]
