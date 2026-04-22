"""Unit tests for artana-evidence-api pipeline orchestration helpers."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.contracts.graph_search_assessment import (
    GraphSearchGroundingLevel,
    build_graph_search_assessment_from_confidence,
)
from src.domain.entities.user import User, UserRole, UserStatus
from src.infrastructure.platform_graph.artana_evidence_api.pipeline import (
    ArtanaEvidenceApiGraphSearchAdapter,
    build_graph_connection_seed_runner_for_service,
    build_graph_connection_seed_runner_for_user,
    build_graph_search_service_for_service,
    build_graph_search_service_for_user,
)


class _StubArtanaEvidenceApiClient:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.connection_calls: list[dict[str, object]] = []
        self.closed = False

    def search_graph(self, **kwargs: object) -> GraphSearchContract:
        self.search_calls.append(kwargs)
        assessment = build_graph_search_assessment_from_confidence(
            0.9,
            confidence_rationale="Search completed.",
            grounding_level=GraphSearchGroundingLevel.AGGREGATED,
        )
        return GraphSearchContract(
            assessment=assessment,
            rationale="Search completed.",
            evidence=[],
            decision="generated",
            research_space_id=str(kwargs["space_id"]),
            original_query=str(kwargs["question"]),
            interpreted_intent=str(kwargs["question"]),
            query_plan_summary="Plan",
            total_results=1,
            results=[],
            executed_path="agent",
            warnings=[],
            agent_run_id="run-1",
        )

    def discover_entity_connections(self, **kwargs: object):
        self.connection_calls.append(kwargs)

        class _Response:
            decision = "generated"
            proposed_relations = [
                {
                    "source_id": str(kwargs["entity_id"]),
                    "relation_type": "ASSOCIATED_WITH",
                    "target_id": str(uuid4()),
                    "confidence": 0.7,
                    "evidence_summary": "Harness evidence",
                    "supporting_provenance_ids": [],
                    "supporting_document_count": 1,
                    "reasoning": "Harness reasoning",
                },
            ]
            rejected_candidates = []
            agent_run_id = "graph-harness-run-001"

        return _Response()

    def close(self) -> None:
        self.closed = True


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="graph-runner@example.com",
        username="graph-runner",
        full_name="Graph Runner",
        hashed_password="hashed",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )


@pytest.mark.asyncio
async def test_graph_connection_seed_runner_for_user_calls_artana_evidence_api_client() -> (
    None
):
    user = _build_user()
    stub_client = _StubArtanaEvidenceApiClient()
    runner = build_graph_connection_seed_runner_for_user(
        user,
        client_factory=lambda _: stub_client,
    )

    outcome = await runner(
        source_id="source-1",
        research_space_id=str(uuid4()),
        seed_entity_id=str(uuid4()),
        source_type="pubmed",
        model_id="model-1",
        relation_types=["ASSOCIATED_WITH"],
        max_depth=3,
        shadow_mode=False,
        pipeline_run_id="pipeline-run-001",
        fallback_relations=None,
    )

    assert outcome.status == "discovered"
    assert outcome.wrote_to_graph is False
    assert outcome.persisted_relations_count == 0
    assert outcome.proposed_relations_count == 1
    assert stub_client.closed is True
    assert stub_client.connection_calls[0]["source_id"] == "source-1"


@pytest.mark.asyncio
async def test_graph_connection_seed_runner_for_service_calls_artana_evidence_api_client() -> (
    None
):
    stub_client = _StubArtanaEvidenceApiClient()
    runner = build_graph_connection_seed_runner_for_service(
        client_factory=lambda: stub_client,
    )

    outcome = await runner(
        source_id="source-1",
        research_space_id=str(uuid4()),
        seed_entity_id=str(uuid4()),
        source_type="clinvar",
        model_id=None,
        relation_types=None,
        max_depth=2,
        shadow_mode=None,
        pipeline_run_id="run-http-service-001",
        fallback_relations=None,
    )

    assert outcome.run_id == "graph-harness-run-001"
    assert stub_client.closed is True
    assert stub_client.connection_calls[0]["pipeline_run_id"] == "run-http-service-001"


@pytest.mark.asyncio
async def test_graph_search_adapter_calls_artana_evidence_api_client() -> None:
    stub_client = _StubArtanaEvidenceApiClient()
    adapter = ArtanaEvidenceApiGraphSearchAdapter(client_factory=lambda: stub_client)

    contract = await adapter.search(
        question="Find seeds",
        research_space_id=str(uuid4()),
        max_depth=1,
        top_k=5,
        include_evidence_chains=False,
        force_agent=True,
        model_id="model-1",
    )

    assert contract.agent_run_id == "run-1"
    assert stub_client.closed is True
    assert "force_agent" not in stub_client.search_calls[0]
    assert stub_client.search_calls[0]["model_id"] == "model-1"


def test_build_graph_search_service_for_service_returns_adapter() -> None:
    adapter = build_graph_search_service_for_service(
        client_factory=lambda: _StubArtanaEvidenceApiClient(),
    )

    assert isinstance(adapter, ArtanaEvidenceApiGraphSearchAdapter)


@pytest.mark.asyncio
async def test_build_graph_search_service_for_user_uses_user_client_factory() -> None:
    user = _build_user()
    stub_client = _StubArtanaEvidenceApiClient()
    captured_users: list[User] = []
    adapter = build_graph_search_service_for_user(
        user,
        client_factory=lambda resolved_user: (
            captured_users.append(resolved_user) or stub_client
        ),
    )

    contract = await adapter.search(
        question="Infer graph seeds",
        research_space_id=str(uuid4()),
        max_depth=1,
        top_k=5,
        include_evidence_chains=False,
        force_agent=True,
    )

    assert contract.agent_run_id == "run-1"
    assert captured_users == [user]
    assert stub_client.closed is True
