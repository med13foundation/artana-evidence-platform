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


def test_dictionary_verifies_known_alias_without_model_curie() -> None:
    link = normalize_entity_curie(
        None,
        label="BRCA1 loss",
        source="model",
    )

    assert link.status == "linked"
    assert link.curie == "HGNC:1100"
    assert link.source == "verified_linker"
    assert link.entity_type == "GENE"


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
