"""Unit tests for harness PubMed routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.app import create_app
from artana_evidence_api.dependencies import (
    get_direct_source_search_store,
    get_pubmed_discovery_service,
    get_research_space_store,
)
from artana_evidence_api.direct_source_search import InMemoryDirectSourceSearchStore
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoveryProvider,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    PubMedSearchRateLimitError,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-pubmed@example.com"


def _auth_headers(*, user_id: str = _TEST_USER_ID) -> dict[str, str]:
    return {
        "X-TEST-USER-ID": user_id,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": "researcher",
    }


class _StubPubMedDiscoveryService:
    def __init__(self) -> None:
        self.jobs: dict[str, DiscoverySearchJob] = {}

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request,
    ) -> DiscoverySearchJob:
        now = datetime.now(UTC)
        job = DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview=request.parameters.search_term or "MED13",
            parameters=request.parameters,
            total_results=2,
            result_metadata={"preview_records": [{"pmid": "pmid-1"}]},
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        self.jobs[str(job.id)] = job
        return job

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        job = self.jobs.get(str(job_id))
        if job is None or job.owner_id != owner_id:
            return None
        return job

    def close(self) -> None:
        return None


class _FailingPubMedDiscoveryService:
    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request,
    ) -> DiscoverySearchJob:
        del owner_id, request
        raise RuntimeError("Discovery backend unavailable.")

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        del owner_id, job_id
        raise RuntimeError("Discovery backend unavailable.")

    def close(self) -> None:
        return None


class _RateLimitedPubMedDiscoveryService:
    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request,
    ) -> DiscoverySearchJob:
        del owner_id, request
        raise PubMedSearchRateLimitError(
            "PubMed search rate limited by NCBI after repeated attempts",
            retry_after_seconds=7,
        )

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        del owner_id, job_id
        raise RuntimeError("Discovery backend unavailable.")

    def close(self) -> None:
        return None


def _build_client() -> tuple[TestClient, _StubPubMedDiscoveryService, str]:
    app = create_app()
    pubmed_service = _StubPubMedDiscoveryService()
    direct_source_search_store = InMemoryDirectSourceSearchStore()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="PubMed Space",
        description="Owned test space for pubmed routes.",
    )
    app.dependency_overrides[get_pubmed_discovery_service] = lambda: pubmed_service
    app.dependency_overrides[get_direct_source_search_store] = (
        lambda: direct_source_search_store
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    return TestClient(app), pubmed_service, space.id


def test_create_pubmed_search_and_get_job() -> None:
    client, pubmed_service, space_id = _build_client()

    create_response = client.post(
        f"/v1/spaces/{space_id}/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "MED13 cardiomyopathy",
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        },
    )

    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["status"] == "completed"
    assert created_payload["session_id"] == space_id
    assert created_payload["result_metadata"]["preview_records"][0]["pmid"] == "pmid-1"

    job_id = created_payload["id"]
    get_response = client.get(
        f"/v1/spaces/{space_id}/pubmed/searches/{job_id}",
        headers=_auth_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == job_id
    assert str(job_id) in pubmed_service.jobs


def test_create_pubmed_search_through_generic_v2_source_route() -> None:
    client, pubmed_service, space_id = _build_client()

    create_response = client.post(
        f"/v2/spaces/{space_id}/sources/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "MED13 cardiomyopathy",
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        },
    )

    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["status"] == "completed"
    assert created_payload["session_id"] == space_id
    assert created_payload["source_capture"]["source_key"] == "pubmed"
    assert created_payload["source_capture"]["capture_stage"] == "search_result"
    assert created_payload["source_capture"]["capture_method"] == "direct_source_search"
    assert created_payload["source_capture"]["locator"].startswith("pubmed:search:")

    job_id = created_payload["id"]
    get_response = client.get(
        f"/v2/spaces/{space_id}/sources/pubmed/searches/{job_id}",
        headers=_auth_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == job_id
    assert get_response.json()["source_capture"]["search_id"] == job_id
    assert str(job_id) in pubmed_service.jobs


def test_generic_v2_source_search_rejects_research_plan_only_source() -> None:
    client, _, space_id = _build_client()

    response = client.post(
        f"/v2/spaces/{space_id}/sources/text/searches",
        headers=_auth_headers(),
        json={"text": "MED13"},
    )

    assert response.status_code == 501
    assert "direct source search is not enabled yet" in response.json()["detail"]


def test_generic_v2_source_search_rejects_unknown_source() -> None:
    client, _, space_id = _build_client()

    response = client.post(
        f"/v2/spaces/{space_id}/sources/not_a_source/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "MED13"},
    )

    assert response.status_code == 404
    assert "not registered" in response.json()["detail"]


@pytest.mark.parametrize("search_term", ["", "   ", None])
def test_create_pubmed_search_rejects_empty_search_term(
    search_term: str | None,
) -> None:
    client, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "gene_symbol": None,
                "search_term": search_term,
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        },
    )

    assert response.status_code == 422
    assert "At least one of search_term or gene_symbol is required" in response.text


def test_get_pubmed_job_rejects_wrong_owner() -> None:
    client, pubmed_service, space_id = _build_client()
    now = datetime.now(UTC)
    foreign_job = DiscoverySearchJob(
        id=uuid4(),
        owner_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        session_id=UUID(space_id),
        provider=DiscoveryProvider.PUBMED,
        status=DiscoverySearchStatus.COMPLETED,
        query_preview="MED13",
        parameters=AdvancedQueryParameters(search_term="MED13"),
        total_results=1,
        result_metadata={},
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    pubmed_service.jobs[str(foreign_job.id)] = foreign_job

    response = client.get(
        f"/v1/spaces/{space_id}/pubmed/searches/{foreign_job.id}",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_pubmed_search_returns_503_when_service_fails() -> None:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="PubMed Space",
        description="Owned test space for pubmed routes.",
    )
    app.dependency_overrides[get_pubmed_discovery_service] = (
        lambda: _FailingPubMedDiscoveryService()
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    client = TestClient(app)

    response = client.post(
        f"/v1/spaces/{space.id}/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "MED13 cardiomyopathy",
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        },
    )

    assert response.status_code == 503
    assert "discovery backend unavailable" in response.json()["detail"].lower()


def test_create_pubmed_search_returns_429_when_rate_limited() -> None:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="PubMed Space",
        description="Owned test space for pubmed routes.",
    )
    app.dependency_overrides[get_pubmed_discovery_service] = (
        lambda: _RateLimitedPubMedDiscoveryService()
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    client = TestClient(app)

    response = client.post(
        f"/v1/spaces/{space.id}/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "gene_symbol": "MED13",
                "search_term": "MED13 cardiomyopathy",
                "date_from": None,
                "date_to": None,
                "publication_types": [],
                "languages": [],
                "sort_by": "relevance",
                "max_results": 25,
                "additional_terms": None,
            },
        },
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert "rate limited" in response.json()["detail"].lower()


def test_get_pubmed_job_returns_503_when_service_fails() -> None:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="PubMed Space",
        description="Owned test space for pubmed routes.",
    )
    app.dependency_overrides[get_pubmed_discovery_service] = (
        lambda: _FailingPubMedDiscoveryService()
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    client = TestClient(app)

    response = client.get(
        f"/v1/spaces/{space.id}/pubmed/searches/{uuid4()}",
        headers=_auth_headers(),
    )

    assert response.status_code == 503
    assert "discovery backend unavailable" in response.json()["detail"].lower()
