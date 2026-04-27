"""Unit tests for evidence-selection source extraction policies."""

from __future__ import annotations

from artana_evidence_api.evidence_selection_extraction_policy import (
    extraction_policy_for_source,
    normalized_extraction_payload,
)


def test_extraction_policy_for_known_source_returns_source_specific_contract() -> None:
    policy = extraction_policy_for_source("uniprot")

    assert policy.proposal_type == "protein_annotation_candidate"
    assert policy.review_type == "protein_annotation_review"
    assert "uniprot_id" in policy.normalized_fields


def test_extraction_policy_for_unknown_source_fails_loudly() -> None:
    try:
        extraction_policy_for_source("custom_source")
    except KeyError as exc:
        assert "custom_source" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unknown extraction policies should fail loudly")


def test_normalized_extraction_payload_filters_missing_values() -> None:
    payload = normalized_extraction_payload(
        source_key="drugbank",
        record={
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
    payload = normalized_extraction_payload(
        source_key="uniprot",
        record={
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
