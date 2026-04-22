"""Unit tests for the harness-local PubMed discovery adapter."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from artana_evidence_api import pubmed_discovery
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoveryProvider,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    LocalPubMedDiscoveryService,
    NCBIPubMedGatewaySettings,
    NCBIPubMedSearchGateway,
    RunPubmedSearchRequest,
    build_pubmed_query_preview,
)


@pytest.mark.asyncio
async def test_run_pubmed_search_uses_local_runner_and_maps_payloads() -> None:
    now = datetime.now(UTC)
    captured_owner_id = uuid4()
    captured_request: RunPubmedSearchRequest | None = None

    async def fake_runner(
        owner_id,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        nonlocal captured_request
        assert owner_id == captured_owner_id
        captured_request = request
        return DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview="MED13[Title/Abstract] AND cardiomyopathy",
            parameters=request.parameters,
            total_results=7,
            result_metadata={"article_ids": ["a1", "a2"]},
            created_at=now,
            updated_at=now,
            completed_at=now,
        )

    service = LocalPubMedDiscoveryService(
        runner=fake_runner,
        platform_session_resolver=lambda _owner_id, session_id: session_id,
        harness_session_resolver=lambda _owner_id, session_id: session_id,
    )
    request = RunPubmedSearchRequest(
        session_id=uuid4(),
        parameters=AdvancedQueryParameters(
            gene_symbol="MED13",
            search_term="cardiomyopathy",
            max_results=10,
        ),
    )

    response = await service.run_pubmed_search(
        owner_id=captured_owner_id,
        request=request,
    )

    assert captured_request is not None
    assert captured_request.parameters.gene_symbol == "MED13"
    assert captured_request.parameters.search_term == "cardiomyopathy"
    assert captured_request.parameters.max_results == 10
    assert response.provider == DiscoveryProvider.PUBMED
    assert response.status == DiscoverySearchStatus.COMPLETED
    assert response.total_results == 7
    assert response.result_metadata == {"article_ids": ["a1", "a2"]}


def test_build_pubmed_query_preview_matches_platform_query_builder() -> None:
    preview = build_pubmed_query_preview(
        AdvancedQueryParameters(
            gene_symbol="MED13",
            search_term="mechanism",
            publication_types=["Review"],
            languages=["eng"],
            max_results=25,
        ),
    )

    assert preview == (
        "MED13[Title/Abstract] AND mechanism AND Review[Publication Type] "
        "AND eng[Language]"
    )


@pytest.mark.asyncio
async def test_ncbi_pubmed_gateway_retries_rate_limit_and_succeeds(
    monkeypatch,
) -> None:
    search_attempts = 0
    summary_attempts = 0
    sleep_calls: list[float] = []

    async def fake_sleep(delay_seconds: float) -> None:
        sleep_calls.append(delay_seconds)

    class _NoOpLimiter:
        async def acquire(self) -> None:
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal search_attempts, summary_attempts
        if request.url.path.endswith("/esearch.fcgi"):
            search_attempts += 1
            if search_attempts < 3:
                return httpx.Response(
                    status_code=429,
                    request=request,
                    json={"error": "rate limited"},
                )
            return httpx.Response(
                status_code=200,
                request=request,
                json={
                    "esearchresult": {
                        "count": "2",
                        "idlist": ["111", "222"],
                    },
                },
            )
        if request.url.path.endswith("/esummary.fcgi"):
            summary_attempts += 1
            return httpx.Response(
                status_code=200,
                request=request,
                json={
                    "result": {
                        "uids": ["111", "222"],
                        "111": {"title": "First result"},
                        "222": {"title": "Second result"},
                    },
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    from artana_evidence_api import pubmed_search

    monkeypatch.setattr(pubmed_search.asyncio, "sleep", fake_sleep)
    gateway = NCBIPubMedSearchGateway(
        settings=NCBIPubMedGatewaySettings(timeout_seconds=1.0),
        transport=httpx.MockTransport(handler),
    )
    gateway._rate_limiter = _NoOpLimiter()  # type: ignore[attr-defined]

    payload = await gateway.run_search(
        AdvancedQueryParameters(
            search_term="angiosarcoma",
        ),
    )

    assert search_attempts == 3
    assert summary_attempts == 1
    assert sleep_calls == [1.0, 2.0]
    assert payload.article_ids == ["111", "222"]
    assert payload.total_count == 2


def test_pubmed_search_parameters_reject_blank_queries() -> None:
    with pytest.raises(
        ValueError,
        match="At least one of search_term or gene_symbol is required",
    ):
        AdvancedQueryParameters(
            gene_symbol="  ",
            search_term="",
        )


@pytest.mark.asyncio
async def test_run_pubmed_search_translates_space_id_to_platform_session_id() -> None:
    owner_id = uuid4()
    harness_space_id = uuid4()
    platform_session_id = uuid4()
    captured_request: RunPubmedSearchRequest | None = None

    async def fake_runner(
        run_owner_id,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        nonlocal captured_request
        assert run_owner_id == owner_id
        captured_request = request
        return DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview="MED13",
            parameters=request.parameters,
            total_results=1,
            result_metadata={},
        )

    service = LocalPubMedDiscoveryService(
        runner=fake_runner,
        platform_session_resolver=lambda run_owner_id, space_id: (
            platform_session_id
            if run_owner_id == owner_id and space_id == harness_space_id
            else uuid4()
        ),
        harness_session_resolver=lambda run_owner_id, session_id: (
            harness_space_id
            if run_owner_id == owner_id and session_id == platform_session_id
            else None
        ),
    )

    response = await service.run_pubmed_search(
        owner_id=owner_id,
        request=RunPubmedSearchRequest(
            session_id=harness_space_id,
            parameters=AdvancedQueryParameters(search_term="MED13"),
        ),
    )

    assert captured_request is not None
    assert captured_request.session_id == platform_session_id
    assert response.session_id == harness_space_id


def test_get_search_job_translates_platform_session_id_back_to_space_id(
    monkeypatch,
) -> None:
    owner_id = uuid4()
    job_id = uuid4()
    harness_space_id = uuid4()
    platform_session_id = uuid4()

    @contextmanager
    def _fake_session_local():
        yield object()

    class _StubPlatformService:
        def get_search_job(
            self,
            requested_owner_id,
            requested_job_id,
        ) -> DiscoverySearchJob | None:
            assert requested_owner_id == owner_id
            assert requested_job_id == job_id
            return DiscoverySearchJob(
                id=job_id,
                owner_id=owner_id,
                session_id=platform_session_id,
                provider=DiscoveryProvider.PUBMED,
                status=DiscoverySearchStatus.COMPLETED,
                query_preview="MED13",
                parameters=AdvancedQueryParameters(search_term="MED13"),
                total_results=2,
                result_metadata={},
            )

    monkeypatch.setattr(pubmed_discovery, "SessionLocal", _fake_session_local)
    monkeypatch.setattr(
        pubmed_discovery,
        "set_session_rls_context",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pubmed_discovery,
        "_build_platform_pubmed_discovery_service",
        lambda session: _StubPlatformService(),
    )

    service = LocalPubMedDiscoveryService(
        harness_session_resolver=lambda run_owner_id, session_id: (
            harness_space_id
            if run_owner_id == owner_id and session_id == platform_session_id
            else None
        ),
    )

    response = service.get_search_job(owner_id=owner_id, job_id=job_id)

    assert response is not None
    assert response.session_id == harness_space_id
