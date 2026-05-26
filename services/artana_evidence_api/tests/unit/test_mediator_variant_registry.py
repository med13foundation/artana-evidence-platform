"""Mediator variant-registry builder tests."""

from __future__ import annotations

import pytest
from artana_evidence_api.research_init.mediator_variant_registry import (
    MODEL_SCORE_COLUMNS,
    MediatorVariantRegistryConfig,
    build_registry_rows,
    fetch_registry_rows,
    normalize_gene_symbols,
    registry_rows_to_csv,
)
from artana_evidence_api.source_enrichment_bridges import ClinVarQueryConfig


def test_normalize_gene_symbols_dedupes_configurable_gene_sets() -> None:
    assert normalize_gene_symbols((" med23 ", "MED6", "med23", "")) == (
        "MED23",
        "MED6",
    )


def test_build_registry_rows_adds_node_and_model_score_columns() -> None:
    config = MediatorVariantRegistryConfig(
        genes=("MED23", "MED25"),
        node_by_gene={"MED23": "cardiac-septal"},
    )

    rows = build_registry_rows(
        config=config,
        records_by_gene={
            "MED23": [
                {
                    "clinvar_id": "123",
                    "variation_id": "123",
                    "accession": "VCV000000123",
                    "title": "NM_004830.4(MED23):c.2150G>A",
                    "gene_symbol": "MED23",
                    "clinical_significance": "Pathogenic",
                    "conditions": ["Atrial septal defect"],
                    "review_status": "criteria provided",
                    "variation_type": "single nucleotide variant",
                    "parsed_data": {
                        "hgvs_notations": ["NM_004830.4(MED23):c.2150G>A"],
                    },
                },
            ],
        },
    )

    assert [row.to_csv_record() for row in rows] == [
        {
            "node": "cardiac-septal",
            "gene_symbol": "MED23",
            "clinvar_id": "123",
            "variation_id": "123",
            "accession": "VCV000000123",
            "title": "NM_004830.4(MED23):c.2150G>A",
            "hgvs": "NM_004830.4(MED23):c.2150G>A",
            "clinical_significance": "Pathogenic",
            "review_status": "criteria provided",
            "variation_type": "single nucleotide variant",
            "conditions": "Atrial septal defect",
            "alphamissense_score": "",
            "revel_score": "",
            "cadd_phred": "",
            "spliceai_delta_score": "",
        },
    ]
    assert tuple(MODEL_SCORE_COLUMNS) == (
        "alphamissense_score",
        "revel_score",
        "cadd_phred",
        "spliceai_delta_score",
    )


def test_registry_rows_to_csv_uses_stable_column_order() -> None:
    config = MediatorVariantRegistryConfig(genes=("MED23",))
    rows = build_registry_rows(
        config=config,
        records_by_gene={
            "MED23": [
                {
                    "clinvar_id": "123",
                    "title": "NM_004830.4(MED23):c.2150G>A",
                    "gene_symbol": "MED23",
                },
            ],
        },
    )

    csv_payload = registry_rows_to_csv(rows)

    assert csv_payload.splitlines()[0] == (
        "node,gene_symbol,clinvar_id,variation_id,accession,title,hgvs,"
        "clinical_significance,review_status,variation_type,conditions,"
        "alphamissense_score,revel_score,cadd_phred,spliceai_delta_score"
    )
    assert "MED23" in csv_payload


@pytest.mark.asyncio
async def test_fetch_registry_rows_queries_configured_genes_with_clinvar_gateway() -> (
    None
):
    gateway = _FakeClinVarGateway()
    config = MediatorVariantRegistryConfig(
        genes=("MED23", "MED25"),
        node_by_gene={"MED23": "cardiac-septal", "MED25": "cardiac-septal"},
    )

    rows = await fetch_registry_rows(
        config=config,
        gateway=gateway,
        max_results_per_gene=7,
    )

    assert gateway.configs == [
        ClinVarQueryConfig(gene_symbol="MED23", max_results=7),
        ClinVarQueryConfig(gene_symbol="MED25", max_results=7),
    ]
    assert [(row.gene_symbol, row.node) for row in rows] == [
        ("MED23", "cardiac-septal"),
        ("MED25", "cardiac-septal"),
    ]


class _FakeClinVarGateway:
    def __init__(self) -> None:
        self.configs: list[ClinVarQueryConfig] = []

    async def fetch_records(
        self,
        config: ClinVarQueryConfig,
    ) -> list[dict[str, object]]:
        self.configs.append(config)
        return [
            {
                "clinvar_id": f"{config.gene_symbol}-1",
                "title": f"NM_000000.0({config.gene_symbol}):c.1A>G",
                "gene_symbol": config.gene_symbol,
            },
        ]
