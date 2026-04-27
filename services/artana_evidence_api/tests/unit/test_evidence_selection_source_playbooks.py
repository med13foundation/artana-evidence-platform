"""Tests for evidence-selection source query playbooks."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection_source_planning import (
    ModelEvidenceSelectionSourcePlanContract,
    ModelSourcePlanningError,
    PlannedSourceIntent,
    adapt_model_source_plan,
)
from artana_evidence_api.evidence_selection_source_playbooks import (
    source_query_playbook,
    source_query_playbooks,
)
from artana_evidence_api.source_registry import direct_search_source_keys


def test_every_direct_search_source_has_query_playbook() -> None:
    playbook_keys = {playbook.source_key for playbook in source_query_playbooks()}

    assert playbook_keys == set(direct_search_source_keys())
    for playbook in source_query_playbooks():
        assert playbook.supported_objective_intents
        assert playbook.result_interpretation_hints
        assert playbook.non_goals
        assert playbook.handoff_eligible is True


@pytest.mark.parametrize(
    ("source_key", "intent", "expected_payload"),
    [
        (
            "pubmed",
            PlannedSourceIntent(
                source_key="pubmed",
                gene_symbol="MED13",
                query="congenital heart disease",
                evidence_role="literature",
                reason="Search literature.",
            ),
            {
                "parameters": {
                    "gene_symbol": "MED13",
                    "search_term": "congenital heart disease",
                },
            },
        ),
        (
            "marrvel",
            PlannedSourceIntent(
                source_key="marrvel",
                variant_hgvs="NM_005121.3:c.1A>G",
                evidence_role="variant database",
                reason="Search MARRVEL.",
            ),
            {
                "variant_hgvs": "NM_005121.3:c.1A>G",
                "panels": ["omim", "clinvar", "gnomad", "geno2mp", "expression"],
            },
        ),
        (
            "clinvar",
            PlannedSourceIntent(
                source_key="clinvar",
                gene_symbol="BRCA1",
                evidence_role="variant clinical assertions",
                reason="Search ClinVar.",
            ),
            {"gene_symbol": "BRCA1"},
        ),
        (
            "clinical_trials",
            PlannedSourceIntent(
                source_key="clinical_trials",
                disease="cystic fibrosis",
                drug_name="ivacaftor",
                evidence_role="trial context",
                reason="Search trials.",
            ),
            {"query": "cystic fibrosis ivacaftor"},
        ),
        (
            "uniprot",
            PlannedSourceIntent(
                source_key="uniprot",
                uniprot_id="P13569",
                evidence_role="protein identity",
                reason="Fetch UniProt.",
            ),
            {"uniprot_id": "P13569"},
        ),
        (
            "alphafold",
            PlannedSourceIntent(
                source_key="alphafold",
                uniprot_id="P13569",
                evidence_role="structure",
                reason="Fetch AlphaFold.",
            ),
            {"uniprot_id": "P13569"},
        ),
        (
            "drugbank",
            PlannedSourceIntent(
                source_key="drugbank",
                drugbank_id="DB08820",
                evidence_role="drug context",
                reason="Fetch DrugBank.",
            ),
            {"drugbank_id": "DB08820"},
        ),
        (
            "mgi",
            PlannedSourceIntent(
                source_key="mgi",
                gene_symbol="Cftr",
                phenotype="cystic fibrosis",
                evidence_role="mouse phenotype",
                reason="Search MGI.",
            ),
            {"query": "Cftr cystic fibrosis"},
        ),
        (
            "zfin",
            PlannedSourceIntent(
                source_key="zfin",
                gene_symbol="cftr",
                phenotype="ion transport",
                evidence_role="zebrafish phenotype",
                reason="Search ZFIN.",
            ),
            {"query": "cftr ion transport"},
        ),
    ],
)
def test_source_query_playbooks_emit_valid_payloads(
    source_key: str,
    intent: PlannedSourceIntent,
    expected_payload: dict[str, object],
) -> None:
    playbook = source_query_playbook(source_key)

    assert playbook is not None
    assert playbook.build_payload(intent) == expected_payload


@pytest.mark.parametrize(
    ("intent", "message"),
    [
        (
            PlannedSourceIntent(
                source_key="clinvar",
                query="BRCA1",
                evidence_role="variant",
                reason="Missing gene symbol.",
            ),
            "gene_symbol",
        ),
        (
            PlannedSourceIntent(
                source_key="alphafold",
                gene_symbol="CFTR",
                evidence_role="structure",
                reason="Missing accession.",
            ),
            "uniprot_id",
        ),
        (
            PlannedSourceIntent(
                source_key="drugbank",
                gene_symbol="CFTR",
                evidence_role="drug",
                reason="Missing drug query.",
            ),
            "drug_name",
        ),
    ],
)
def test_source_query_playbooks_reject_missing_required_fields(
    intent: PlannedSourceIntent,
    message: str,
) -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="Invalid playbook input.",
        planned_searches=[intent],
    )

    with pytest.raises(ModelSourcePlanningError, match=message):
        adapt_model_source_plan(
            contract=contract,
            requested_sources=(intent.source_key,),
            max_records_per_search=3,
            max_planned_searches=5,
        )


def test_marrvel_playbook_accepts_explicit_panels_and_taxon() -> None:
    playbook = source_query_playbook("marrvel")
    intent = PlannedSourceIntent(
        source_key="marrvel",
        gene_symbol="med13",
        taxon_id=7955,
        panels=["clinvar", "omim"],
        evidence_role="model organism",
        reason="Search a non-human MARRVEL slice.",
    )

    assert playbook is not None
    assert playbook.build_payload(intent) == {
        "gene_symbol": "med13",
        "taxon_id": 7955,
        "panels": ["clinvar", "omim"],
    }
