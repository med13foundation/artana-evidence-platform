"""Unit coverage for the local verified entity grounding dictionary."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    REVIEW_ONLY_ENTITY_RECORDS,
    relation_match_label_for_label,
    review_only_record_for_label,
    verified_record_for_label,
)


def test_verified_dictionary_resolves_process_aliases() -> None:
    record = verified_record_for_label("MAPK pathway")

    assert record is not None
    assert record.label == "MAPK signaling"
    assert record.curie == "GO:0000165"


def test_verified_dictionary_resolves_cardiac_septum_alias() -> None:
    record = verified_record_for_label("cardiac septum development")

    assert record is not None
    assert record.label == "cardiac septal development"
    assert record.curie == "GO:0003279"


@pytest.mark.parametrize(
    ("label", "expected_label", "expected_curie"),
    [
        ("Alectinib", "Alectinib", "DrugBank:DB11363"),
        ("Fabry disease", "Fabry disease", "MONDO:0010526"),
        (
            "familial hypercholesterolemia",
            "familial hypercholesterolemia",
            "MONDO:0005439",
        ),
        ("KRAS G12D", "KRAS G12D", "ClinVar:KRAS_G12D"),
        ("Larotrectinib", "Larotrectinib", "DrugBank:DB14723"),
        ("MSI-high status", "MSI-high status", "NCIT:C36493"),
        ("NTRK fusion solid tumors", "NTRK fusion positive cancer", "MONDO:0700215"),
        (
            "NTRK gene fusion solid tumors",
            "NTRK fusion positive cancer",
            "MONDO:0700215",
        ),
        ("PI3K-AKT signaling", "PI3K-AKT signaling", "GO:0043491"),
        ("Vemurafenib", "Vemurafenib", "DrugBank:DB08881"),
    ],
)
def test_verified_dictionary_resolves_v3_trusted_endpoint_gaps(
    label: str,
    expected_label: str,
    expected_curie: str,
) -> None:
    record = verified_record_for_label(label)

    assert record is not None
    assert record.label == expected_label
    assert record.curie == expected_curie
    assert review_only_record_for_label(label) is None


@pytest.mark.parametrize(
    ("label", "expected_label", "expected_curie"),
    [
        (
            "familial adenomatous polyposis",
            "familial adenomatous polyposis",
            "NCIT:C3339",
        ),
        (
            "hereditary breast and ovarian cancer syndrome",
            "hereditary breast ovarian cancer syndrome",
            "MONDO:0003582",
        ),
        ("Marfan syndrome", "Marfan syndrome", "MONDO:0007947"),
        ("phenylketonuria", "phenylketonuria", "MONDO:0009861"),
        ("Rett syndrome", "Rett syndrome", "MONDO:0010726"),
    ],
)
def test_verified_dictionary_resolves_repeated_v3_high_value_endpoint_gaps(
    label: str,
    expected_label: str,
    expected_curie: str,
) -> None:
    record = verified_record_for_label(label)

    assert record is not None
    assert record.label == expected_label
    assert record.curie == expected_curie
    assert review_only_record_for_label(label) is None


@pytest.mark.parametrize(
    ("label", "expected_reason"),
    [
        ("ALK fusion-positive lung cancer", "molecular_subtype_requires_structured_grounding"),
        (
            "EGFR exon 19 deletion lung adenocarcinoma",
            "molecular_subtype_requires_structured_grounding",
        ),
        ("immune checkpoint inhibitor response", "composite_treatment_response_label"),
        ("APC pathogenic variants", "gene_state_requires_structured_grounding"),
        ("AKT activation", "gene_state_requires_structured_grounding"),
        ("BRCA1 loss", "gene_state_requires_structured_grounding"),
        ("BRCA1 truncating variants", "gene_state_requires_structured_grounding"),
        ("FBN1 loss-of-function variants", "gene_state_requires_structured_grounding"),
        ("GLA variants", "gene_state_requires_structured_grounding"),
        ("HER2 amplification", "gene_state_requires_structured_grounding"),
        ("JAK2 signaling", "gene_state_requires_structured_grounding"),
        ("LDLR loss-of-function variants", "gene_state_requires_structured_grounding"),
        ("MECP2 pathogenic variants", "gene_state_requires_structured_grounding"),
        ("MET amplification", "gene_state_requires_structured_grounding"),
        ("PAH pathogenic variants", "gene_state_requires_structured_grounding"),
        ("PD-L1 expression", "gene_state_requires_structured_grounding"),
        ("PTEN loss", "gene_state_requires_structured_grounding"),
        ("TP53 loss", "gene_state_requires_structured_grounding"),
    ],
)
def test_non_exact_v3_endpoint_labels_are_review_only(
    label: str,
    expected_reason: str,
) -> None:
    record = review_only_record_for_label(label)

    assert record is not None
    assert record.reason_code == expected_reason
    assert verified_record_for_label(label) is None


@pytest.mark.parametrize(
    ("label", "bad_curie"),
    [
        ("immune checkpoint inhibitor response", "NCIT:C157484"),
        ("MSI-high status", "NCIT:C150719"),
        ("familial adenomatous polyposis", "MONDO:0008840"),
        ("NTRK fusion solid tumors", "MONDO:0100342"),
        ("hereditary breast and ovarian cancer syndrome", "MONDO:0011450"),
        ("familial hypercholesterolemia", "MONDO:0007750"),
        ("ALK fusion-positive lung cancer", "MONDO:0005233"),
        ("EGFR exon 19 deletion lung adenocarcinoma", "MONDO:0005061"),
    ],
)
def test_known_non_exact_or_wrong_v3_curie_values_are_not_verified(
    label: str,
    bad_curie: str,
) -> None:
    record = verified_record_for_label(label)

    assert record is None or record.curie != bad_curie


def test_review_only_dictionary_blocks_composite_response_grounding() -> None:
    record = review_only_record_for_label("response to pembrolizumab")

    assert record is not None
    assert record.reason == "grounding_requires_review"
    assert verified_record_for_label("response to pembrolizumab") is None


def test_review_only_dictionary_blocks_overbroad_process_grounding() -> None:
    record = review_only_record_for_label("ERK tyrosine phosphorylation")

    assert record is not None
    assert record.label == "ERK phosphorylation"
    assert verified_record_for_label("ERK phosphorylation") is None


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
def test_review_only_dictionary_has_explicit_decisions_for_pr24_endpoint_gaps(
    label: str,
    expected_reason: str,
) -> None:
    record = review_only_record_for_label(label)

    assert record is not None
    assert record.curation_status == "review_only_for_relation_feasibility_v2"
    assert record.reason_code == expected_reason
    assert record.trusted_identifier_allowed is False
    assert verified_record_for_label(label) is None


@pytest.mark.parametrize(
    "label",
    [
        "resistance to gefitinib",
        "gefitinib resistance",
    ],
)
def test_composite_resistance_labels_are_review_only(label: str) -> None:
    record = review_only_record_for_label(label)

    assert record is not None
    assert record.label == "resistance"
    assert record.reason_code == "generic_resistance_label"
    assert verified_record_for_label(label) is None


def test_review_only_labels_and_aliases_never_resolve_as_verified() -> None:
    labels = (
        label
        for record in REVIEW_ONLY_ENTITY_RECORDS
        for label in (record.label, *record.aliases)
    )

    for label in labels:
        assert verified_record_for_label(label) is None


def test_relation_match_aliases_do_not_reuse_identity_aliases() -> None:
    assert (
        relation_match_label_for_label("homologous recombination")
        == "homologous recombination DNA repair"
    )
    assert relation_match_label_for_label("BRCA1 loss") is None


def test_relation_match_aliases_include_live_ntrk_surface_variant() -> None:
    assert (
        relation_match_label_for_label("NTRK gene fusion solid tumors")
        == "NTRK fusion positive cancer"
    )
    assert (
        relation_match_label_for_label("NTRK fusion solid tumors")
        == "NTRK fusion positive cancer"
    )
