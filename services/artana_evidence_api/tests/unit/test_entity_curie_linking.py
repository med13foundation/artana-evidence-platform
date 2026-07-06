"""Unit coverage for extracted-entity CURIE verification."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.entity_curie_linking import (
    normalize_entity_curie,
)


def test_model_curie_hint_is_verified_when_label_matches_dictionary() -> None:
    link = normalize_entity_curie(
        "HGNC:22474",
        label="MED13",
        source="model",
    )

    assert link.status == "linked"
    assert link.curie == "HGNC:22474"
    assert link.source == "verified_linker"
    assert link.entity_type == "GENE"
    assert link.identifiers == {"hgnc_id": "HGNC:22474"}
    assert link.to_metadata()["trusted_identifier"] is True


def test_model_curie_hint_does_not_override_dictionary_id() -> None:
    link = normalize_entity_curie(
        "MONDO:0007254",
        label="MED13",
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "linked"
    assert link.curie == "HGNC:22474"
    assert link.source == "verified_linker"
    assert metadata["trusted_identifier"] is True
    assert metadata["model_hint_curie"] == "MONDO:0007254"
    assert metadata["model_hint_status"] == "replaced"


def test_gene_state_alias_without_exact_state_identifier_requires_review() -> None:
    link = normalize_entity_curie(
        None,
        label="BRCA1 loss",
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.curie is None
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False


def test_clinvar_variant_curie_can_be_verified() -> None:
    link = normalize_entity_curie(
        "ClinVar:EGFR_T790M",
        label="EGFR T790M",
        source="model",
    )

    assert link.status == "linked"
    assert link.curie == "ClinVar:EGFR_T790M"
    assert link.source == "verified_linker"
    assert link.entity_type == "VARIANT"
    assert link.identifiers == {"clinvar_id": "ClinVar:EGFR_T790M"}


@pytest.mark.parametrize(
    ("raw_curie", "label", "expected_curie", "expected_identifier"),
    [
        (
            "CHEBI:45783",
            "Alectinib",
            "DRUGBANK:DB11363",
            {"drugbank_id": "DRUGBANK:DB11363"},
        ),
        (
            "MESH:D050177",
            "Fabry disease",
            "MONDO:0010526",
            {"mondo_id": "MONDO:0010526"},
        ),
        (
            "MONDO:0019005",
            "familial hypercholesterolemia",
            "MONDO:0005439",
            {"mondo_id": "MONDO:0005439"},
        ),
        (
            "GO:0014065",
            "PI3K-AKT signaling",
            "GO:0043491",
            {"go_id": "GO:0043491"},
        ),
        (
            None,
            "KRAS G12D",
            "ClinVar:KRAS_G12D",
            {"clinvar_id": "ClinVar:KRAS_G12D"},
        ),
        (
            None,
            "MSI-high status",
            "NCIT:C36493",
            {"ncit_id": "NCIT:C36493"},
        ),
        (
            "MONDO:0100342",
            "NTRK fusion solid tumors",
            "MONDO:0700215",
            {"mondo_id": "MONDO:0700215"},
        ),
    ],
)
def test_v3_curated_endpoint_records_verify_or_replace_model_hints(
    raw_curie: str | None,
    label: str,
    expected_curie: str,
    expected_identifier: dict[str, str],
) -> None:
    link = normalize_entity_curie(
        raw_curie,
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "linked"
    assert link.curie == expected_curie
    assert link.source == "verified_linker"
    assert link.identifiers == expected_identifier
    assert metadata["trusted_identifier"] is True
    if raw_curie is not None:
        assert metadata["model_hint_status"] == "replaced"


@pytest.mark.parametrize(
        (
            "raw_curie",
            "label",
            "expected_curie",
            "expected_identifier",
        "expected_hint_status",
    ),
    [
        (
            "MONDO:0005360",
            "familial adenomatous polyposis",
            "NCIT:C3339",
            {"ncit_id": "NCIT:C3339"},
            "replaced",
        ),
        (
            "MONDO:0014998",
            "hereditary breast and ovarian cancer syndrome",
            "MONDO:0003582",
            {"mondo_id": "MONDO:0003582"},
            "replaced",
        ),
        (
            None,
            "Marfan syndrome",
            "MONDO:0007947",
            {"mondo_id": "MONDO:0007947"},
            None,
        ),
        (
            "MONDO:0009828",
            "phenylketonuria",
            "MONDO:0009861",
            {"mondo_id": "MONDO:0009861"},
            "replaced",
        ),
        (
            "MONDO:0016880",
            "Rett syndrome",
            "MONDO:0010726",
            {"mondo_id": "MONDO:0010726"},
            "replaced",
        ),
    ],
)
def test_repeated_v3_high_value_records_verify_or_replace_model_hints(
    raw_curie: str | None,
    label: str,
    expected_curie: str,
    expected_identifier: dict[str, str],
    expected_hint_status: str | None,
) -> None:
    link = normalize_entity_curie(
        raw_curie,
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "linked"
    assert link.curie == expected_curie
    assert link.source == "verified_linker"
    assert link.identifiers == expected_identifier
    assert metadata["trusted_identifier"] is True
    if expected_hint_status is None:
        assert "model_hint_status" not in metadata
    else:
        assert metadata["model_hint_status"] == expected_hint_status


@pytest.mark.parametrize(
    ("raw_curie", "label", "expected_reason_code"),
    [
        (
            "MONDO:0005233",
            "ALK fusion-positive lung cancer",
            "molecular_subtype_requires_structured_grounding",
        ),
        (
            "MONDO:0005061",
            "EGFR exon 19 deletion lung adenocarcinoma",
            "molecular_subtype_requires_structured_grounding",
        ),
        ("NCIT:C157484", "immune checkpoint inhibitor response", "composite_treatment_response_label"),
        ("HGNC:583", "APC pathogenic variants", "gene_state_requires_structured_grounding"),
        ("HGNC:391", "AKT activation", "gene_state_requires_structured_grounding"),
        ("HGNC:1100", "BRCA1 truncating variants", "gene_state_requires_structured_grounding"),
        ("HGNC:3603", "FBN1 loss-of-function variants", "gene_state_requires_structured_grounding"),
        ("HGNC:4296", "GLA variants", "gene_state_requires_structured_grounding"),
        ("HGNC:3430", "HER2 amplification", "gene_state_requires_structured_grounding"),
        ("HGNC:6192", "JAK2 signaling", "gene_state_requires_structured_grounding"),
        ("HGNC:6547", "LDLR loss-of-function variants", "gene_state_requires_structured_grounding"),
        ("HGNC:6990", "MECP2 pathogenic variants", "gene_state_requires_structured_grounding"),
        ("HGNC:7029", "MET amplification", "gene_state_requires_structured_grounding"),
        ("HGNC:8582", "PAH pathogenic variants", "gene_state_requires_structured_grounding"),
        ("HGNC:17635", "PD-L1 expression", "gene_state_requires_structured_grounding"),
        ("HGNC:9588", "PTEN loss", "gene_state_requires_structured_grounding"),
        ("HGNC:11998", "TP53 loss", "gene_state_requires_structured_grounding"),
    ],
)
def test_non_exact_endpoint_labels_do_not_trust_model_hints(
    raw_curie: str,
    label: str,
    expected_reason_code: str,
) -> None:
    link = normalize_entity_curie(
        raw_curie,
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.curie is None
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False
    assert metadata["grounding_reason_code"] == expected_reason_code


@pytest.mark.parametrize(
    ("raw_curie", "label", "expected_curie"),
    [
        ("GO:0000165", "MAPK signaling", "GO:0000165"),
        (
            "GO:0000724",
            "homologous recombination DNA repair",
            "GO:0000724",
        ),
        ("GO:0003279", "cardiac septal development", "GO:0003279"),
    ],
)
def test_biological_process_model_hints_require_verified_grounding(
    raw_curie: str,
    label: str,
    expected_curie: str,
) -> None:
    link = normalize_entity_curie(
        raw_curie,
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "linked"
    assert link.curie == expected_curie
    assert link.source == "verified_linker"
    assert link.entity_type == "BIOLOGICAL_PROCESS"
    assert link.identifiers == {"go_id": expected_curie}
    assert metadata["trusted_identifier"] is True
    assert metadata["model_hint_curie"] == expected_curie
    assert metadata["model_hint_status"] == "matched"


@pytest.mark.parametrize(
    "label",
    [
        "aggressive tumor growth",
        "response to pembrolizumab",
    ],
)
def test_composite_or_broad_labels_abstain_for_review_without_model_hint(
    label: str,
) -> None:
    link = normalize_entity_curie(
        None,
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False


def test_composite_response_does_not_trust_drug_anchor_model_hint() -> None:
    link = normalize_entity_curie(
        "DrugBank:DB09037",
        label="response to pembrolizumab",
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.curie is None
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False
    assert metadata["model_hint_curie"] == "DRUGBANK:DB09037"


def test_verified_linker_source_does_not_bypass_review_only_grounding() -> None:
    link = normalize_entity_curie(
        "DrugBank:DB09037",
        label="response to pembrolizumab",
        source="verified_linker",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.curie is None
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False
    assert metadata["model_hint_curie"] == "DRUGBANK:DB09037"


@pytest.mark.parametrize(
    "label",
    [
        "resistance to gefitinib",
        "gefitinib resistance",
    ],
)
def test_composite_resistance_label_does_not_trust_drug_anchor_hint(
    label: str,
) -> None:
    link = normalize_entity_curie(
        "DrugBank:DB00317",
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.curie is None
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False
    assert metadata["trusted_identifier_allowed"] is False
    assert metadata["grounding_reason_code"] == "generic_resistance_label"
    assert metadata["model_hint_curie"] == "DRUGBANK:DB00317"


def test_unknown_verified_linker_source_is_downgraded_to_untrusted_hint() -> None:
    link = normalize_entity_curie(
        "GO:1234567",
        label="unreviewed pathway label",
        source="verified_linker",
    )

    metadata = link.to_metadata()
    assert link.status == "linked"
    assert link.curie == "GO:1234567"
    assert link.source == "model"
    assert metadata["trusted_identifier"] is False


def test_broad_erk_phosphorylation_grounding_requires_review() -> None:
    link = normalize_entity_curie(
        "GO:0018108",
        label="ERK phosphorylation",
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False
    assert metadata["model_hint_curie"] == "GO:0018108"


@pytest.mark.parametrize(
    ("label", "expected_reason"),
    [
        ("aggressive tumor growth", "composite_event_label"),
        ("ERK phosphorylation", "broad_process_label"),
        ("response to pembrolizumab", "composite_treatment_response_label"),
        ("HRD score", "biomarker_score_label"),
        ("platinum sensitivity", "drug_response_phenotype_label"),
        ("inflammatory signaling", "broad_process_label"),
        ("reduced survival", "prognosis_outcome_label"),
        ("resistance", "generic_resistance_label"),
    ],
)
def test_review_only_grounding_metadata_explains_policy_decision(
    label: str,
    expected_reason: str,
) -> None:
    link = normalize_entity_curie(
        "GO:0002526",
        label=label,
        source="model",
    )

    metadata = link.to_metadata()
    assert link.status == "abstained"
    assert link.curie is None
    assert link.source == "none"
    assert link.reason == "grounding_requires_review"
    assert metadata["trusted_identifier"] is False
    assert metadata["trusted_identifier_allowed"] is False
    assert metadata["grounding_curation_status"] == (
        "review_only_for_relation_feasibility_v2"
    )
    assert metadata["grounding_reason_code"] == expected_reason
    assert metadata["model_hint_curie"] == "GO:0002526"
