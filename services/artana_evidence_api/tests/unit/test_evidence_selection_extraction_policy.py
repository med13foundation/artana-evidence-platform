"""Unit tests for evidence-selection source extraction policies."""

from __future__ import annotations

from artana_evidence_api.source_adapters import require_source_adapter


def test_extraction_policy_for_known_source_returns_source_specific_contract() -> None:
    adapter = require_source_adapter("uniprot")

    assert adapter.proposal_type == "protein_annotation_candidate"
    assert adapter.review_type == "protein_annotation_review"
    assert "uniprot_id" in adapter.normalized_fields


def test_normalized_extraction_payload_filters_missing_values() -> None:
    payload = require_source_adapter("drugbank").normalized_extraction_payload(
        {
            "drugbank_id": "DB01234",
            "drug_name": "Olaparib",
            "target_name": "",
            "indication": [],
            "mechanism_of_action": None,
        },
    )

    assert payload["fields"] == {
        "drugbank_id": "DB01234",
        "drug_name": "Olaparib",
    }
    assert payload["identifiers"] == {"drugbank_id": "DB01234"}


def test_normalized_extraction_payload_does_not_overmatch_identifier_suffixes() -> None:
    payload = require_source_adapter("uniprot").normalized_extraction_payload(
        {
            "uniprot_id": "Q9UHV7",
            "valid": "not an identifier",
            "hybrid": "not an identifier",
            "id": "local-id",
        },
    )

    assert payload["identifiers"] == {
        "uniprot_id": "Q9UHV7",
        "id": "local-id",
    }
