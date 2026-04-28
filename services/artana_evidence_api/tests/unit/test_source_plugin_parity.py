"""Generic parity checks for migrated source plugins."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection_extraction_policy import (
    adapter_extraction_policy_for_source,
    adapter_normalized_extraction_payload,
)
from artana_evidence_api.evidence_selection_source_planning import PlannedSourceIntent
from artana_evidence_api.evidence_selection_source_playbooks import (
    adapter_source_query_playbook,
)
from artana_evidence_api.source_plugins.registry import (
    source_plugin,
    source_plugin_keys,
)
from artana_evidence_api.source_policies import adapter_source_record_policy
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.types.common import JSONObject


@pytest.mark.parametrize("source_key", source_plugin_keys())
def test_plugin_public_metadata_matches_central_registry(source_key: str) -> None:
    plugin = source_plugin(source_key)
    definition = get_source_definition(source_key)

    assert plugin is not None
    assert definition is not None
    assert plugin.source_definition() == definition
    assert plugin.metadata.source_key == definition.source_key
    assert plugin.metadata.display_name == definition.display_name
    assert plugin.metadata.source_family == definition.source_family
    assert plugin.metadata.request_schema_ref == definition.request_schema_ref
    assert plugin.metadata.result_schema_ref == definition.result_schema_ref
    assert plugin.metadata.direct_search_supported is definition.direct_search_enabled


@pytest.mark.parametrize("source_key", source_plugin_keys())
def test_plugin_query_planning_matches_legacy_playbook(source_key: str) -> None:
    plugin = source_plugin(source_key)
    playbook = adapter_source_query_playbook(source_key)
    intent = _planning_intent(source_key)

    assert plugin is not None
    assert playbook is not None
    assert plugin.build_query_payload(intent) == playbook.build_payload(intent)
    assert plugin.supported_objective_intents == playbook.supported_objective_intents
    assert plugin.result_interpretation_hints == playbook.result_interpretation_hints
    assert plugin.non_goals == playbook.non_goals
    assert plugin.handoff_eligible is playbook.handoff_eligible


@pytest.mark.parametrize("source_key", source_plugin_keys())
def test_plugin_record_policy_matches_legacy_policy(source_key: str) -> None:
    plugin = source_plugin(source_key)
    policy = adapter_source_record_policy(source_key)
    record = _record(source_key)

    assert plugin is not None
    assert policy is not None
    assert plugin.source_family == policy.source_family
    assert plugin.handoff_target_kind == policy.handoff_target_kind
    assert plugin.direct_search_supported is policy.direct_search_supported
    assert plugin.request_schema_ref == policy.request_schema_ref
    assert plugin.result_schema_ref == policy.result_schema_ref
    assert plugin.provider_external_id(record) == policy.provider_external_id(record)
    assert plugin.recommends_variant_aware(record) is policy.recommends_variant_aware(record)
    assert plugin.normalize_record(record) == policy.normalize_record(record)


@pytest.mark.parametrize("source_key", source_plugin_keys())
def test_plugin_extraction_policy_matches_legacy_policy(source_key: str) -> None:
    plugin = source_plugin(source_key)
    policy = adapter_extraction_policy_for_source(source_key)
    record = _record(source_key)

    assert plugin is not None
    assert plugin.review_policy.source_key == policy.source_key
    assert plugin.review_policy.proposal_type == policy.proposal_type
    assert plugin.review_policy.review_type == policy.review_type
    assert plugin.review_policy.evidence_role == policy.evidence_role
    assert plugin.review_policy.limitations == policy.limitations
    assert plugin.review_policy.normalized_fields == policy.normalized_fields
    assert plugin.normalized_extraction_payload(record) == (
        adapter_normalized_extraction_payload(source_key=source_key, record=record)
    )


def _planning_intent(source_key: str) -> PlannedSourceIntent:
    intents = {
        "pubmed": PlannedSourceIntent(
            source_key="pubmed",
            gene_symbol="MED13",
            disease="congenital heart disease",
            phenotype="developmental delay",
            evidence_role="literature",
            reason="Find literature.",
        ),
        "marrvel": PlannedSourceIntent(
            source_key="marrvel",
            gene_symbol="MED13",
            variant_hgvs="NC_000017.11:g.6012345A>G",
            evidence_role="variant panel evidence",
            reason="Search MARRVEL panels.",
        ),
        "clinvar": PlannedSourceIntent(
            source_key="clinvar",
            gene_symbol="brca1",
            evidence_role="variant assertion",
            reason="Search ClinVar.",
        ),
        "drugbank": PlannedSourceIntent(
            source_key="drugbank",
            drug_name="imatinib",
            drugbank_id="DB00619",
            evidence_role="drug target context",
            reason="Fetch drug targets.",
        ),
        "alphafold": PlannedSourceIntent(
            source_key="alphafold",
            uniprot_id="P38398",
            evidence_role="structure",
            reason="Fetch structure.",
        ),
        "uniprot": PlannedSourceIntent(
            source_key="uniprot",
            gene_symbol="MED13",
            organism="Homo sapiens",
            evidence_role="protein identity",
            reason="Ground protein identity.",
        ),
        "clinical_trials": PlannedSourceIntent(
            source_key="clinical_trials",
            disease="cystic fibrosis",
            drug_name="ivacaftor",
            evidence_role="trial context",
            reason="Search trials.",
        ),
        "mgi": PlannedSourceIntent(
            source_key="mgi",
            gene_symbol="Med13",
            phenotype="cardiac phenotype",
            evidence_role="mouse model",
            reason="Search mouse model evidence.",
        ),
        "zfin": PlannedSourceIntent(
            source_key="zfin",
            gene_symbol="med13",
            disease="heart development",
            evidence_role="zebrafish model",
            reason="Search zebrafish model evidence.",
        ),
    }
    return intents[source_key]


def _record(source_key: str) -> JSONObject:
    records: dict[str, JSONObject] = {
        "pubmed": {
            "pmid": "12345",
            "title": "MED13 and congenital heart disease",
            "abstract": "A focused abstract.",
            "journal": "Journal of MED13",
            "publication_year": "2025",
        },
        "marrvel": {
            "marrvel_record_id": "search-1:clinvar:0",
            "panel_name": "clinvar",
            "panel_family": "variant",
            "gene_symbol": "MED13",
            "resolved_gene_symbol": "MED13",
            "hgvs_notation": "NC_000017.11:g.6012345A>G",
            "query_mode": "variant_hgvs",
            "query_value": "NC_000017.11:g.6012345A>G",
            "variant_aware_recommended": True,
        },
        "clinvar": {
            "clinvar_id": "123",
            "accession": "VCV000012345",
            "variation_id": 12345,
            "title": "NM_007294.4(BRCA1):c.5266dupC",
            "gene_symbol": "BRCA1",
            "clinical_significance": "Pathogenic",
            "conditions": ["Breast-ovarian cancer, familial 1"],
            "review_status": "criteria provided, multiple submitters",
            "variation_type": "duplication",
            "hgvs": "NM_007294.4:c.5266dupC",
            "source": "clinvar",
        },
        "drugbank": {
            "drugbank_id": "DB00619",
            "name": "Imatinib",
            "target_name": "ABL1",
            "targets": ["ABL1", "KIT"],
            "mechanism_of_action": "Inhibits BCR-ABL.",
            "categories": ["Antineoplastic Agents"],
        },
        "alphafold": {
            "uniprot_id": "P38398",
            "protein_name": "BRCA1 protein",
            "gene_name": "BRCA1",
            "organism": "Homo sapiens",
            "predicted_structure_confidence": 92.4,
            "model_url": "https://alphafold.example/P38398.cif",
            "pdb_url": "https://alphafold.example/P38398.pdb",
            "domains": [{"name": "BRCT"}],
        },
        "uniprot": {
            "uniprot_id": "Q9UHV7",
            "primary_accession": "Q9UHV7",
            "accession": "Q9UHV7",
            "gene_name": "MED13",
            "protein_name": "Mediator complex subunit 13",
            "organism": "Homo sapiens",
            "function": "Component of the mediator complex.",
            "sequence_length": 2174,
            "source": "uniprot",
        },
        "clinical_trials": {
            "nct_id": "NCT01234567",
            "brief_title": "MED13 trial",
            "overall_status": "RECRUITING",
            "phases": ["PHASE1"],
            "conditions": ["Congenital heart disease"],
            "interventions": [{"name": "Observation"}],
            "study_type": "OBSERVATIONAL",
        },
        "mgi": {
            "mgi_id": "MGI:1919711",
            "gene_symbol": "Med13",
            "gene_name": "mediator complex subunit 13",
            "species": "Mus musculus",
            "phenotype_statements": ["abnormal heart morphology"],
            "disease_associations": [{"name": "heart disease", "do_id": "DOID:114"}],
        },
        "zfin": {
            "zfin_id": "ZDB-GENE-040426-1432",
            "gene_symbol": "med13",
            "gene_name": "mediator complex subunit 13",
            "species": "Danio rerio",
            "phenotype_statements": ["abnormal cardiac ventricle morphology"],
            "expression_terms": ["heart"],
        },
    }
    return records[source_key]
