"""Unit tests for the service-local ClinVar gateway."""

from __future__ import annotations

from typing import cast

import httpx
import pytest
from artana_evidence_api.clinvar_gateway import ClinVarSourceGateway
from artana_evidence_api.source_enrichment_bridges import (
    ClinVarQueryConfig,
    build_clinvar_gateway,
)


def test_build_clinvar_gateway_returns_service_local_gateway() -> None:
    gateway = build_clinvar_gateway()

    assert isinstance(gateway, ClinVarSourceGateway)


@pytest.mark.asyncio
async def test_clinvar_gateway_fetch_records_normalizes_ncbi_summary() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200,
                json={
                    "esearchresult": {
                        "count": "1",
                        "retstart": "0",
                        "retmax": "5",
                        "idlist": ["123"],
                    },
                },
                request=request,
            )
        if request.url.path.endswith("/esummary.fcgi"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "uids": ["123"],
                        "123": {
                            "uid": "123",
                            "accession": "VCV000012345",
                            "title": "NM_007294.4(BRCA1):c.5266dupC",
                            "obj_type": "single nucleotide variant",
                            "genes": [{"symbol": "BRCA1"}],
                            "variation_set": [
                                {
                                    "variation_name": (
                                        "NM_007294.4(BRCA1):c.5266dupC"
                                    ),
                                },
                            ],
                            "germline_classification": {
                                "description": "Pathogenic",
                                "review_status": (
                                    "criteria provided, multiple submitters"
                                ),
                                "trait_set": [
                                    {
                                        "trait_name": [
                                            "Breast-ovarian cancer, familial 1",
                                        ],
                                    },
                                ],
                            },
                        },
                    },
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    gateway = ClinVarSourceGateway(
        api_key="",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    records = await gateway.fetch_records(
        ClinVarQueryConfig(
            gene_symbol="brca1",
            clinical_significance=["Pathogenic"],
            max_results=5,
        ),
    )

    assert len(records) == 1
    assert records[0]["clinvar_id"] == "123"
    assert records[0]["accession"] == "VCV000012345"
    assert records[0]["title"] == "NM_007294.4(BRCA1):c.5266dupC"
    assert records[0]["clinical_significance"] == "Pathogenic"
    assert records[0]["conditions"] == ["Breast-ovarian cancer, familial 1"]
    assert records[0]["variation_type"] == "single nucleotide variant"

    parsed_data = cast("dict[str, object]", records[0]["parsed_data"])
    assert parsed_data["gene_symbol"] == "BRCA1"
    assert parsed_data["clinical_significance"] == "Pathogenic"
    assert parsed_data["hgvs_notations"] == ["NM_007294.4(BRCA1):c.5266dupC"]
    assert parsed_data["review_status"] == "criteria provided, multiple submitters"

    search_params = captured_requests[0].url.params
    assert search_params["term"] == (
        "BRCA1[gene] AND Pathogenic[clinical_significance]"
    )
    assert search_params["retmax"] == "5"

    summary_params = captured_requests[1].url.params
    assert summary_params["id"] == "123"


@pytest.mark.asyncio
async def test_clinvar_gateway_returns_empty_when_search_has_no_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"esearchresult": {"count": "0", "idlist": []}},
            request=request,
        )

    gateway = ClinVarSourceGateway(
        api_key="",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    records = await gateway.fetch_records(ClinVarQueryConfig(gene_symbol="MED13"))

    assert records == []
