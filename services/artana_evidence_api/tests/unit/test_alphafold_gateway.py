"""Unit tests for the service-local AlphaFold gateway."""

from __future__ import annotations

import httpx
from artana_evidence_api.alphafold_gateway import AlphaFoldSourceGateway
from artana_evidence_api.source_enrichment_bridges import build_alphafold_gateway


def test_build_alphafold_gateway_returns_service_local_gateway() -> None:
    gateway = build_alphafold_gateway()

    assert isinstance(gateway, AlphaFoldSourceGateway)


def test_alphafold_gateway_fetch_records_normalizes_prediction() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "entryId": "AF-P04637-F1",
                    "uniprotAccession": "P04637",
                    "uniprotDescription": "Tumor protein p53",
                    "organismScientificName": "Homo sapiens",
                    "gene": "TP53",
                    "cifUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637.cif",
                    "pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637.pdb",
                    "globalMetricValue": 87.5,
                    "domains": [
                        {
                            "name": "P53 DNA-binding",
                            "start": 94,
                            "end": 292,
                            "confidence": 91.2,
                        },
                    ],
                },
            ],
            request=request,
        )

    gateway = AlphaFoldSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(uniprot_id="P04637", max_results=10)

    assert result.fetched_records == 1
    assert len(result.records) == 1
    assert result.records[0]["uniprot_id"] == "P04637"
    assert result.records[0]["protein_name"] == "Tumor protein p53"
    assert result.records[0]["organism"] == "Homo sapiens"
    assert result.records[0]["gene_name"] == "TP53"
    assert result.records[0]["predicted_structure_confidence"] == 87.5
    assert result.records[0]["model_url"].endswith("AF-P04637.cif")
    assert result.records[0]["pdb_url"].endswith("AF-P04637.pdb")
    assert result.records[0]["domains"] == [
        {
            "name": "P53 DNA-binding",
            "domain_name": "P53 DNA-binding",
            "start": 94,
            "end": 292,
            "confidence": 91.2,
        },
    ]
    assert captured_requests[0].url.path.endswith("/prediction/P04637")


def test_alphafold_gateway_returns_empty_for_missing_uniprot_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected AlphaFold request: {request.url}")

    gateway = AlphaFoldSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(uniprot_id="")

    assert result.records == []
    assert result.fetched_records == 0


def test_alphafold_gateway_returns_empty_for_invalid_accession_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, request=request)

    gateway = AlphaFoldSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(uniprot_id="NOTAREAL")

    assert result.records == []
    assert result.fetched_records == 0
