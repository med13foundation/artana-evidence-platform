"""Unit tests for the artana-evidence-api HTTP client."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx

from src.infrastructure.platform_graph.artana_evidence_api.client import (
    ArtanaEvidenceApiClient,
    ArtanaEvidenceApiClientConfig,
)


def test_artana_evidence_api_client_executes_graph_search() -> None:
    space_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/spaces/{space_id}/agents/graph-search/runs"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {
            "question": "MED13",
            "model_id": "model-1",
            "max_depth": 2,
            "top_k": 5,
            "curation_statuses": ["ACCEPTED"],
            "include_evidence_chains": True,
        }
        return httpx.Response(
            status_code=201,
            json={
                "run": {
                    "id": "run-1",
                    "harness_id": "graph-search",
                    "status": "completed",
                },
                "result": {
                    "confidence_score": 0.87,
                    "rationale": "Harness graph search completed with ranked results.",
                    "evidence": [],
                    "decision": "generated",
                    "research_space_id": str(space_id),
                    "original_query": "MED13",
                    "interpreted_intent": "MED13",
                    "query_plan_summary": "Harness plan",
                    "total_results": 1,
                    "results": [],
                    "executed_path": "agent",
                    "warnings": [],
                    "agent_run_id": "run-1",
                },
            },
        )

    http_client = httpx.Client(
        base_url="https://graph-harness.test",
        transport=httpx.MockTransport(handler),
    )
    client = ArtanaEvidenceApiClient(
        ArtanaEvidenceApiClientConfig(base_url="https://graph-harness.test"),
        client=http_client,
    )

    response = client.search_graph(
        space_id=space_id,
        question="MED13",
        model_id="model-1",
        top_k=5,
        curation_statuses=["ACCEPTED"],
    )

    assert response.executed_path == "agent"
    assert response.agent_run_id == "run-1"
    http_client.close()


def test_artana_evidence_api_client_executes_graph_connection_run() -> None:
    space_id = uuid4()
    entity_id = uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            f"/v1/spaces/{space_id}/agents/graph-connections/runs"
        )
        payload = json.loads(request.content.decode("utf-8"))
        assert payload == {
            "seed_entity_ids": [str(entity_id)],
            "source_type": "pubmed",
            "source_id": "source-1",
            "model_id": "model-1",
            "relation_types": ["ASSOCIATED_WITH"],
            "max_depth": 3,
            "shadow_mode": False,
            "pipeline_run_id": "pipeline-run-1",
        }
        return httpx.Response(
            status_code=201,
            json={
                "run": {
                    "id": "run-2",
                    "harness_id": "graph-connections",
                    "status": "completed",
                },
                "outcomes": [
                    {
                        "decision": "generated",
                        "confidence_score": 0.81,
                        "rationale": "Harness graph connection completed.",
                        "evidence": [],
                        "source_type": "pubmed",
                        "research_space_id": str(space_id),
                        "seed_entity_id": str(entity_id),
                        "proposed_relations": [
                            {
                                "source_id": str(entity_id),
                                "relation_type": "ASSOCIATED_WITH",
                                "target_id": "target-1",
                                "assessment": {
                                    "support_band": "SUPPORTED",
                                    "grounding_level": "GRAPH_INFERENCE",
                                    "mapping_status": "NOT_APPLICABLE",
                                    "speculation_level": "NOT_APPLICABLE",
                                    "confidence_rationale": "Supported graph candidate",
                                },
                                "confidence": 0.8,
                                "evidence_summary": "Evidence summary",
                                "supporting_provenance_ids": [],
                                "supporting_document_count": 1,
                                "reasoning": "Reasoning",
                            },
                        ],
                        "rejected_candidates": [],
                        "shadow_mode": False,
                        "agent_run_id": "run-2",
                    },
                ],
            },
        )

    http_client = httpx.Client(
        base_url="https://graph-harness.test",
        transport=httpx.MockTransport(handler),
    )
    client = ArtanaEvidenceApiClient(
        ArtanaEvidenceApiClientConfig(base_url="https://graph-harness.test"),
        client=http_client,
    )

    response = client.discover_entity_connections(
        space_id=space_id,
        entity_id=entity_id,
        source_type="pubmed",
        source_id="source-1",
        model_id="model-1",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=3,
        shadow_mode=False,
        pipeline_run_id="pipeline-run-1",
    )

    assert response.seed_entity_id == str(entity_id)
    assert response.agent_run_id == "run-2"
    assert len(response.proposed_relations) == 1
    http_client.close()
