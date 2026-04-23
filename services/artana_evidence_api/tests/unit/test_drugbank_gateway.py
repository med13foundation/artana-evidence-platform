"""Unit tests for the service-local DrugBank gateway."""

from __future__ import annotations

import httpx
from artana_evidence_api.drugbank_gateway import DrugBankSourceGateway
from artana_evidence_api.source_enrichment_bridges import build_drugbank_gateway


def test_build_drugbank_gateway_returns_service_local_gateway() -> None:
    gateway = build_drugbank_gateway()

    assert isinstance(gateway, DrugBankSourceGateway)


def test_drugbank_gateway_returns_empty_without_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected DrugBank request: {request.url}")

    gateway = DrugBankSourceGateway(
        api_key="",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(drug_name="imatinib", max_results=5)

    assert result.records == []
    assert result.fetched_records == 0


def test_drugbank_gateway_search_normalizes_drug_records() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        assert request.headers["authorization"] == "Bearer test-drugbank-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "drugbank_id": "DB00619",
                        "name": "Imatinib",
                        "generic_name": "imatinib",
                        "description": "A tyrosine kinase inhibitor.",
                        "synonyms": [{"name": "Gleevec"}, "STI-571"],
                        "categories": [{"name": "Antineoplastic Agents"}],
                        "targets": [
                            {"gene_name": "ABL1"},
                            {"name": "KIT"},
                        ],
                        "mechanism_of_action": "Inhibits BCR-ABL.",
                        "drug_interactions": [{"name": "Warfarin"}],
                    },
                ],
            },
            request=request,
        )

    gateway = DrugBankSourceGateway(
        api_key="test-drugbank-key",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(drug_name="imatinib", max_results=5)

    assert result.fetched_records == 1
    assert len(result.records) == 1
    assert result.records[0]["drugbank_id"] == "DB00619"
    assert result.records[0]["name"] == "Imatinib"
    assert result.records[0]["synonyms"] == ["Gleevec", "STI-571"]
    assert result.records[0]["categories"] == ["Antineoplastic Agents"]
    assert result.records[0]["targets"] == ["ABL1", "KIT"]
    assert result.records[0]["mechanism_of_action"] == "Inhibits BCR-ABL."
    assert result.records[0]["drug_interactions"] == ["Warfarin"]

    request = captured_requests[0]
    assert request.url.path.endswith("/drugs")
    assert request.url.params["q"] == "imatinib"
    assert request.url.params["per_page"] == "5"


def test_drugbank_gateway_fetches_drug_targets_by_id() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "gene_name": "ABL1",
                    "protein_name": "Tyrosine-protein kinase ABL1",
                    "organism": "Homo sapiens",
                    "actions": [{"name": "inhibitor"}],
                    "known_action": "yes",
                },
            ],
            request=request,
        )

    gateway = DrugBankSourceGateway(
        api_key="test-drugbank-key",
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(drugbank_id="DB00619")

    assert result.fetched_records == 1
    assert result.records[0]["gene_name"] == "ABL1"
    assert result.records[0]["protein_name"] == "Tyrosine-protein kinase ABL1"
    assert result.records[0]["actions"] == ["inhibitor"]
    assert result.records[0]["known_action"] == "yes"
    assert captured_requests[0].url.path.endswith("/drugs/DB00619/targets")
