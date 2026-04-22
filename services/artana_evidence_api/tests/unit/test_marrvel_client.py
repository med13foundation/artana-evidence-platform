"""Unit tests for the service-local MARRVEL API client."""

from __future__ import annotations

import logging

import httpx
import pytest
from artana_evidence_api.marrvel_client import (
    MARRVEL_API_BASE_URL,
    MARRVEL_API_FALLBACK_BASE_URL,
    MarrvelClient,
)


def test_marrvel_api_urls_default_to_documented_endpoints() -> None:
    assert MARRVEL_API_BASE_URL == "https://api.marrvel.org/data"
    assert MARRVEL_API_FALLBACK_BASE_URL == "http://api.marrvel.org/data"


@pytest.mark.asyncio
async def test_marrvel_client_retries_tls_hostname_mismatch_over_http(
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

    assert gene_info == {"symbol": "BRCA1", "entrezId": 672}
    assert omim_records == [{"phenotype": "Breast cancer"}]
    assert primary_calls == 1
    assert fallback_calls == 2
    warning_records = [
        record
        for record in caplog.records
        if record.message
        == "MARRVEL HTTPS endpoint failed TLS validation; switching to HTTP fallback"
    ]
    assert len(warning_records) == 1
    warning_record = warning_records[0]
    assert warning_record.marrvel_base_url == "https://api.marrvel.org/data"
    assert warning_record.marrvel_fallback_base_url == "http://api.marrvel.org/data"
    assert warning_record.exception_type == "ConnectError"


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
