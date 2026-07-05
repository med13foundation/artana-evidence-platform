"""Unit coverage for extracted-entity CURIE verification."""

from __future__ import annotations

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
