"""Unit tests for the service-local gnomAD gateway."""

from __future__ import annotations

import json

import httpx
import pytest
from artana_evidence_api.direct_sources.gnomad_gateway import (
    GnomADGatewayError,
    GnomADSourceGateway,
)
from artana_evidence_api.source_enrichment_bridges import build_gnomad_gateway


def test_build_gnomad_gateway_returns_service_local_gateway() -> None:
    gateway = build_gnomad_gateway()

    assert isinstance(gateway, GnomADSourceGateway)


def test_gnomad_gateway_fetch_records_normalizes_gene_constraint() -> None:
    captured_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "data": {
                    "gene": {
                        "reference_genome": "GRCh38",
                        "gene_id": "ENSG00000108510",
                        "symbol": "MED13",
                        "name": "mediator complex subunit 13",
                        "chrom": "17",
                        "start": 5982000,
                        "stop": 6052000,
                        "gnomad_constraint": {
                            "pLI": 1,
                            "oe_lof": 0.10,
                            "oe_lof_upper": 0.14,
                            "mis_z": 3.3,
                            "flags": ["ok"],
                        },
                    },
                },
            },
            request=request,
        )

    gateway = GnomADSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(gene_symbol="med13")

    assert result.fetched_records == 1
    assert result.records[0]["record_type"] == "gene_constraint"
    assert result.records[0]["gene_symbol"] == "MED13"
    assert result.records[0]["gene_id"] == "ENSG00000108510"
    assert result.records[0]["pLI"] == 1.0
    assert result.records[0]["oe_lof_upper"] == 0.14
    assert captured_payloads[0]["variables"] == {
        "geneSymbol": "MED13",
        "referenceGenome": "GRCh38",
    }


def test_gnomad_gateway_fetch_records_normalizes_variant_frequency() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "variant": {
                        "variant_id": "17-5982158-C-T",
                        "variantId": "17-5982158-C-T",
                        "reference_genome": "GRCh38",
                        "chrom": "17",
                        "pos": 5982158,
                        "ref": "C",
                        "alt": "T",
                        "rsids": ["rs554720391"],
                        "rsid": "rs554720391",
                        "exome": None,
                        "genome": {
                            "ac": 1,
                            "an": 152332,
                            "af": 0.00000656,
                            "homozygote_count": 0,
                            "hemizygote_count": 0,
                            "filters": [],
                            "populations": [
                                {
                                    "id": "eas",
                                    "ac": 1,
                                    "an": 5186,
                                    "homozygote_count": 0,
                                    "hemizygote_count": 0,
                                },
                            ],
                        },
                        "joint": None,
                        "transcript_consequences": [
                            {
                                "gene_id": "ENSG00000108510",
                                "gene_symbol": "MED13",
                                "transcript_id": "ENST00000397786",
                                "major_consequence": "missense_variant",
                                "consequence_terms": ["missense_variant"],
                                "hgvsc": "c.977C>T",
                                "hgvsp": "p.Thr326Met",
                                "canonical": True,
                            },
                        ],
                    },
                },
            },
            request=request,
        )

    gateway = GnomADSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(variant_id="17-5982158-C-T")

    assert result.fetched_records == 1
    record = result.records[0]
    assert record["record_type"] == "variant_frequency"
    assert record["variant_id"] == "17-5982158-C-T"
    assert record["gene_symbol"] == "MED13"
    assert record["major_consequence"] == "missense_variant"
    assert record["genome"] == {
        "ac": 1,
        "an": 152332,
        "af": 0.00000656,
        "homozygote_count": 0,
        "hemizygote_count": 0,
        "filters": [],
        "populations": [
            {
                "id": "eas",
                "ac": 1,
                "an": 5186,
                "af": 1 / 5186,
                "homozygote_count": 0,
                "hemizygote_count": 0,
            },
        ],
    }


def test_gnomad_gateway_returns_empty_for_not_found_graphql_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errors": [{"message": "Variant not found"}], "data": {"variant": None}},
            request=request,
        )

    gateway = GnomADSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(variant_id="17-1-A-T")

    assert result.records == []
    assert result.fetched_records == 0


def test_gnomad_gateway_raises_for_non_record_not_found_graphql_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "errors": [{"message": "Authorization token not found"}],
                "data": {"variant": None},
            },
            request=request,
        )

    gateway = GnomADSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(GnomADGatewayError, match="Authorization token not found"):
        gateway.fetch_records(variant_id="17-1-A-T")


def test_gnomad_gateway_raises_for_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable", request=request)

    gateway = GnomADSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(GnomADGatewayError, match="gnomAD GraphQL request failed"):
        gateway.fetch_records(gene_symbol="MED13")


def test_gnomad_gateway_preserves_missing_numeric_values_and_zero_af() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "variant": {
                        "variant_id": "17-5982158-C-T",
                        "chrom": "17",
                        "pos": 5982158,
                        "ref": "C",
                        "alt": "T",
                        "genome": {
                            "ac": 0,
                            "an": 100,
                            "af": 0.0,
                            "populations": [{"id": "afr"}],
                        },
                    },
                },
            },
            request=request,
        )

    gateway = GnomADSourceGateway(
        timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = gateway.fetch_records(variant_id="17-5982158-C-T")

    genome = result.records[0]["genome"]
    assert isinstance(genome, dict)
    assert genome["ac"] == 0
    assert genome["an"] == 100
    assert genome["af"] == 0.0
    population = genome["populations"][0]
    assert population["ac"] is None
    assert population["an"] is None
    assert population["af"] is None
