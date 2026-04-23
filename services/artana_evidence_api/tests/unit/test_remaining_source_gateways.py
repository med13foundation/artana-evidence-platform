"""Unit tests for remaining service-local structured-source gateways."""

from __future__ import annotations

import httpx
import pytest
from artana_evidence_api.alliance_gene_gateways import (
    MGISourceGateway,
    ZFINSourceGateway,
)
from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsSourceGateway
from artana_evidence_api.source_enrichment_bridges import (
    build_clinicaltrials_gateway,
    build_mgi_gateway,
    build_uniprot_gateway,
    build_zfin_gateway,
)
from artana_evidence_api.uniprot_gateway import UniProtSourceGateway


def test_build_remaining_gateway_factories_return_service_local_gateways() -> None:
    assert isinstance(build_uniprot_gateway(), UniProtSourceGateway)
    assert isinstance(build_clinicaltrials_gateway(), ClinicalTrialsSourceGateway)
    assert isinstance(build_mgi_gateway(), MGISourceGateway)
    assert isinstance(build_zfin_gateway(), ZFINSourceGateway)


def test_uniprot_gateway_search_normalizes_uniprot_records() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "primaryAccession": "Q9UHV7",
                        "genes": [{"geneName": {"value": "MED13"}}],
                        "proteinDescription": {
                            "recommendedName": {
                                "fullName": {"value": "Mediator complex subunit 13"},
                            },
                        },
                        "organism": {"scientificName": "Homo sapiens"},
                        "sequence": {"length": 2174},
                    },
                ],
            },
            request=request,
        )

    gateway = UniProtSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(query="MED13", max_results=1)

    assert result.fetched_records == 1
    assert result.records[0]["uniprot_id"] == "Q9UHV7"
    assert result.records[0]["gene_name"] == "MED13"
    assert result.records[0]["protein_name"] == "Mediator complex subunit 13"
    assert result.records[0]["organism"] == "Homo sapiens"
    assert result.records[0]["sequence_length"] == 2174
    assert captured_requests[0].url.path.endswith("/uniprotkb/search")
    assert captured_requests[0].url.params["size"] == "1"


@pytest.mark.asyncio
async def test_clinicaltrials_gateway_normalizes_v2_studies() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json={
                "totalCount": 1,
                "nextPageToken": "next-token",
                "studies": [
                    {
                        "protocolSection": {
                            "identificationModule": {
                                "nctId": "NCT00000001",
                                "briefTitle": "BRCA1 inhibitor trial",
                            },
                            "statusModule": {"overallStatus": "RECRUITING"},
                            "conditionsModule": {"conditions": ["Breast cancer"]},
                            "armsInterventionsModule": {
                                "interventions": [
                                    {"name": "Olaparib", "type": "DRUG"},
                                ],
                            },
                            "designModule": {
                                "phases": ["PHASE2"],
                                "studyType": "INTERVENTIONAL",
                            },
                            "descriptionModule": {
                                "briefSummary": "Testing PARP inhibition.",
                            },
                        },
                    },
                ],
            },
            request=request,
        )

    gateway = ClinicalTrialsSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.fetch_records_async(query="BRCA1", max_results=5)

    assert result.fetched_records == 1
    assert result.next_page_token == "next-token"
    assert result.records[0]["nct_id"] == "NCT00000001"
    assert result.records[0]["conditions"] == ["Breast cancer"]
    assert result.records[0]["interventions"] == [
        {"name": "Olaparib", "type": "DRUG"},
    ]
    assert captured_requests[0].url.path.endswith("/studies")
    assert captured_requests[0].url.params["query.term"] == "BRCA1"
    assert captured_requests[0].url.params["pageSize"] == "5"


@pytest.mark.asyncio
async def test_mgi_gateway_normalizes_mouse_gene_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "primaryKey": "1919711",
                        "symbol": "Brca1",
                        "name": "breast cancer 1",
                        "species": "Mus musculus",
                        "phenotypeStatements": [
                            {"name": "abnormal mammary gland development"},
                        ],
                        "diseaseAssociations": [
                            {"name": "breast cancer", "id": "DOID:1612"},
                        ],
                    },
                ],
            },
            request=request,
        )

    gateway = MGISourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.fetch_records_async(query="BRCA1", max_results=5)

    assert result.fetched_records == 1
    assert result.records[0]["mgi_id"] == "MGI:1919711"
    assert result.records[0]["gene_symbol"] == "Brca1"
    assert result.records[0]["phenotype_statements"] == [
        "abnormal mammary gland development",
    ]
    assert result.records[0]["disease_associations"] == [
        {"name": "breast cancer", "do_id": "DOID:1612"},
    ]


@pytest.mark.asyncio
async def test_zfin_gateway_normalizes_zebrafish_gene_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "primaryKey": "ZDB-GENE-040426-1432",
                        "symbol": "brca1",
                        "name": "BRCA1 DNA repair associated",
                        "species": "Danio rerio",
                        "phenotypes": ["abnormal fin morphology"],
                        "expressionTerms": [{"name": "brain"}],
                    },
                ],
            },
            request=request,
        )

    gateway = ZFINSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.fetch_records_async(query="BRCA1", max_results=5)

    assert result.fetched_records == 1
    assert result.records[0]["zfin_id"] == "ZDB-GENE-040426-1432"
    assert result.records[0]["gene_symbol"] == "brca1"
    assert result.records[0]["phenotype_statements"] == ["abnormal fin morphology"]
    assert result.records[0]["expression_terms"] == ["brain"]
