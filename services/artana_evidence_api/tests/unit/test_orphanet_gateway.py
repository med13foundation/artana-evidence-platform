"""Unit tests for the Orphanet ORPHAcodes gateway."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from artana_evidence_api.direct_sources.orphanet_gateway import (
    OrphanetGatewayError,
    OrphanetSourceGateway,
)


@pytest.mark.asyncio
async def test_orphanet_gateway_search_normalizes_summaries() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.raw_path.decode())
        if request.url.path == "/EN/ClinicalEntity/ApproximateName/Marfan syndrome":
            return httpx.Response(
                200,
                json=[
                    {
                        "ORPHAcode": 558,
                        "Preferred term": "Marfan syndrome",
                        "Date": "2020-06-29T11:48:08Z",
                    },
                ],
            )
        if request.url.path == "/EN/ClinicalEntity/orphacode/558":
            return httpx.Response(
                200,
                json={
                    "ORPHAcode": 558,
                    "Preferred term": "Marfan syndrome",
                    "Synonym": ["MFS", "Marfan disease"],
                    "Definition": "A connective tissue disorder.",
                    "Typology": "Disease",
                    "Status": "Active",
                    "ClassificationLevel": "Disorder",
                    "OrphanetUrl": "https://www.orpha.net/consor/cgi-bin/OC_Exp.php?lng=en&Expert=558",
                    "Preferential parent": {
                        "ORPHAcode": 98023,
                        "Preferred term": "Rare systemic or rheumatologic disease",
                    },
                    "Date": "2020-06-29T11:48:08Z",
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    gateway = OrphanetSourceGateway(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.fetch_records_async(
        query=" Marfan   syndrome ", max_results=5
    )

    assert requests == [
        "/EN/ClinicalEntity/ApproximateName/Marfan%20syndrome",
        "/EN/ClinicalEntity/orphacode/558",
    ]
    assert result.fetched_records == 1
    assert result.records == [
        {
            "orpha_code": "558",
            "orphanet_id": "ORPHA:558",
            "preferred_term": "Marfan syndrome",
            "name": "Marfan syndrome",
            "synonyms": ["MFS", "Marfan disease"],
            "definition": "A connective tissue disorder.",
            "typology": "Disease",
            "status": "Active",
            "classification_level": "Disorder",
            "orphanet_url": "https://www.orpha.net/consor/cgi-bin/OC_Exp.php?lng=en&Expert=558",
            "date": "2020-06-29T11:48:08Z",
            "matched_query": "Marfan syndrome",
            "preferential_parent": {
                "orpha_code": "98023",
                "orphanet_id": "ORPHA:98023",
                "preferred_term": "Rare systemic or rheumatologic disease",
            },
            "source": "orphanet",
        },
    ]


@pytest.mark.asyncio
async def test_orphanet_gateway_search_summaries_are_concurrent_and_partial() -> None:
    active_summary_requests = 0
    max_active_summary_requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_summary_requests, max_active_summary_requests
        if "/ApproximateName/" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    {"ORPHAcode": 111, "Preferred term": "First candidate"},
                    {"ORPHAcode": 222, "Preferred term": "Second candidate"},
                    {"ORPHAcode": 333, "Preferred term": "Third candidate"},
                ],
            )

        active_summary_requests += 1
        max_active_summary_requests = max(
            max_active_summary_requests,
            active_summary_requests,
        )
        await asyncio.sleep(0.01)
        active_summary_requests -= 1

        if request.url.path.endswith("/orphacode/222"):
            return httpx.Response(503, json={"detail": "temporarily unavailable"})
        orphacode = request.url.path.rsplit("/", maxsplit=1)[-1]
        return httpx.Response(
            200,
            json={
                "ORPHAcode": int(orphacode),
                "Preferred term": f"Summary {orphacode}",
                "Definition": f"Summary detail for {orphacode}",
            },
        )

    gateway = OrphanetSourceGateway(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.fetch_records_async(query="rare disease", max_results=3)

    assert max_active_summary_requests > 1
    assert result.fetched_records == 3
    assert [record["preferred_term"] for record in result.records] == [
        "Summary 111",
        "Second candidate",
        "Summary 333",
    ]


@pytest.mark.asyncio
async def test_orphanet_gateway_fetches_exact_orphacode() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["apiKey"] == "test-api-key"
        assert request.url.path == "/EN/ClinicalEntity/orphacode/558"
        return httpx.Response(
            200,
            json={"ORPHAcode": 558, "Preferred term": "Marfan syndrome"},
        )

    gateway = OrphanetSourceGateway(
        api_key="test-api-key",
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.fetch_records_async(orphacode=558)

    assert result.fetched_records == 1
    assert result.records[0]["orphanet_id"] == "ORPHA:558"
    assert result.records[0]["preferred_term"] == "Marfan syndrome"


@pytest.mark.asyncio
async def test_orphanet_gateway_returns_empty_without_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request to {request.url}")

    gateway = OrphanetSourceGateway(api_key="", transport=httpx.MockTransport(handler))

    result = await gateway.fetch_records_async(query="Marfan syndrome")

    assert result.records == []
    assert result.fetched_records == 0


@pytest.mark.asyncio
async def test_orphanet_gateway_returns_empty_for_malformed_payload() -> None:
    gateway = OrphanetSourceGateway(
        api_key="test-api-key",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    result = await gateway.fetch_records_async(query="Marfan syndrome")

    assert result.records == []
    assert result.fetched_records == 0


@pytest.mark.asyncio
async def test_orphanet_gateway_raises_configured_request_errors() -> None:
    gateway = OrphanetSourceGateway(
        api_key="test-api-key",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(401, json={"detail": "unauthorized"}),
        ),
    )

    with pytest.raises(OrphanetGatewayError, match="ORPHAcodes API request failed"):
        await gateway.fetch_records_async(query="Marfan syndrome")
