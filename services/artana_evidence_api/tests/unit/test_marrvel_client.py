"""Unit tests for the service-local MARRVEL API client."""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

import httpx
import pytest
from artana_evidence_api.marrvel_client import (
    MARRVEL_API_BASE_URL,
    MARRVEL_API_FALLBACK_BASE_URL,
    MarrvelClient,
)
from artana_evidence_api.marrvel_discovery import (
    MarrvelDiscoveryService,
    _gather_panels,
)


def test_marrvel_api_urls_default_to_documented_endpoints() -> None:
    assert MARRVEL_API_BASE_URL == "https://api.marrvel.org/data"
    assert MARRVEL_API_FALLBACK_BASE_URL is None


@pytest.mark.asyncio
async def test_marrvel_client_does_not_fallback_for_tls_hostname_mismatch(
    caplog: pytest.LogCaptureFixture,
) -> None:
    primary_calls = 0
    fallback_calls = 0

    def _primary_handler(request: httpx.Request) -> httpx.Response:
        nonlocal primary_calls
        primary_calls += 1
        raise httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
            "Hostname mismatch, certificate is not valid for 'api.marrvel.org'. "
            "(_ssl.c:1032)",
            request=request,
        )

    def _fallback_handler(request: httpx.Request) -> httpx.Response:
        nonlocal fallback_calls
        fallback_calls += 1
        if "gene/taxonId/9606/symbol/BRCA1" in str(request.url):
            return httpx.Response(
                200,
                json={"symbol": "BRCA1", "entrezId": 672},
                request=request,
            )
        return httpx.Response(
            200,
            json=[{"phenotype": "Breast cancer"}],
            request=request,
        )

    async with MarrvelClient(
        base_url="https://api.marrvel.org/data",
        fallback_base_url="http://api.marrvel.org/data",
        transport=httpx.MockTransport(_primary_handler),
        fallback_transport=httpx.MockTransport(_fallback_handler),
    ) as client:
        with caplog.at_level(
            logging.WARNING,
            logger="artana_evidence_api.marrvel_client",
        ):
            gene_info = await client.fetch_gene_info(9606, "BRCA1")
            omim_records = await client.fetch_omim_data("BRCA1")

    assert gene_info is None
    assert omim_records == []
    assert primary_calls == 2
    assert fallback_calls == 0
    assert any(
        record.message.startswith("Failed to fetch gene info for BRCA1:")
        and "CERTIFICATE_VERIFY_FAILED" in record.message
        for record in caplog.records
    )
    assert not any(
        record.message
        == "MARRVEL HTTPS endpoint failed TLS validation; switching to HTTP fallback"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_marrvel_client_does_not_fallback_for_generic_connection_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    primary_calls = 0
    fallback_calls = 0

    def _primary_handler(request: httpx.Request) -> httpx.Response:
        nonlocal primary_calls
        primary_calls += 1
        raise httpx.ConnectError("connection reset by peer", request=request)

    def _fallback_handler(request: httpx.Request) -> httpx.Response:
        nonlocal fallback_calls
        fallback_calls += 1
        return httpx.Response(200, json={"symbol": "BRCA1"}, request=request)

    async with MarrvelClient(
        base_url="https://api.marrvel.org/data",
        fallback_base_url="http://api.marrvel.org/data",
        transport=httpx.MockTransport(_primary_handler),
        fallback_transport=httpx.MockTransport(_fallback_handler),
    ) as client:
        with caplog.at_level(
            logging.WARNING,
            logger="artana_evidence_api.marrvel_client",
        ):
            gene_info = await client.fetch_gene_info(9606, "BRCA1")

    assert gene_info is None
    assert primary_calls == 1
    assert fallback_calls == 0
    assert any(
        record.message
        == "Failed to fetch gene info for BRCA1: connection reset by peer"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_marrvel_client_logs_optional_dbnsfp_panel_failures_at_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        if "dbnsfp/variant/BRCA1" in str(request.url):
            return httpx.Response(
                500,
                json={"message": "Server error occured"},
                request=request,
            )
        return httpx.Response(404, request=request)

    async with MarrvelClient(
        base_url="https://api.marrvel.org/data",
        fallback_base_url=None,
        transport=httpx.MockTransport(_handler),
    ) as client:
        with caplog.at_level(
            logging.DEBUG,
            logger="artana_evidence_api.marrvel_client",
        ):
            records = await client.fetch_dbnsfp_data("BRCA1")

    assert records == []
    matching_records = [
        record
        for record in caplog.records
        if record.name == "artana_evidence_api.marrvel_client"
        and record.getMessage().startswith("Failed to fetch dbNSFP data for BRCA1:")
    ]
    assert matching_records
    assert matching_records[-1].levelno == logging.DEBUG


@pytest.mark.asyncio
async def test_marrvel_discovery_records_panel_errors_for_partial_results() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "gene/taxonId/9606/symbol/MED13" in url:
            return httpx.Response(
                200,
                json={"symbol": "MED13", "entrezGeneId": 9969},
                request=request,
            )
        if "omim/gene/symbol/MED13" in url:
            return httpx.Response(
                200,
                json=[{"phenotypes": [{"phenotype": "{MED13 syndrome}"}]}],
                request=request,
            )
        if "clinvar/gene/entrezId/9969" in url:
            return httpx.Response(500, json={"message": "panel down"}, request=request)
        return httpx.Response(404, request=request)

    service = MarrvelDiscoveryService(
        client_factory=lambda: MarrvelClient(
            base_url="https://api.marrvel.org/data",
            fallback_base_url=None,
            transport=httpx.MockTransport(_handler),
        ),
    )

    result = await service.search(
        owner_id=uuid4(),
        space_id=uuid4(),
        gene_symbol="MED13",
        panels=["omim", "clinvar"],
    )

    assert result.status == "partial"
    assert result.panel_counts == {"omim": 1}
    assert "clinvar" not in result.panels
    assert "500 Internal Server Error" in result.panel_errors["clinvar"]


@pytest.mark.asyncio
async def test_marrvel_discovery_gather_panels_excludes_base_exceptions() -> None:
    async def _cancelled_panel() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await _gather_panels(
            {"clinvar": asyncio.create_task(_cancelled_panel())},
        )
