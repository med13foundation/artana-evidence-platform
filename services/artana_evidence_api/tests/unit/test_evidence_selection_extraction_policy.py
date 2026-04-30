"""Unit tests for evidence-selection source extraction policies."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection_extraction_policy import (
    adapter_extraction_policy_for_source,
    adapter_normalized_extraction_payload,
    adapter_proposal_summary,
    adapter_review_item_summary,
)
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


def test_plugin_policy_facade_returns_source_policy() -> None:
    policy = adapter_extraction_policy_for_source("drugbank")

    assert policy.source_key == "drugbank"
    assert policy.proposal_type == "drug_target_context_candidate"
    assert policy.review_type == "drug_target_context_review"
    assert "drugbank_id" in policy.normalized_fields


def test_plugin_policy_facade_builds_payload_and_summaries() -> None:
    payload = adapter_normalized_extraction_payload(
        source_key="clinical_trials",
        record={
            "nct_id": "NCT00000001",
            "title": "MED13L observational trial",
            "status": "",
        },
    )

    assert payload["identifiers"] == {"nct_id": "NCT00000001"}
    assert "MED13L" in adapter_proposal_summary(
        source_key="clinical_trials",
        selection_reason="MED13L trial match",
    )
    assert "MED13L" in adapter_review_item_summary(
        source_key="clinical_trials",
        selection_reason="MED13L trial match",
    )


def test_policy_facade_rejects_unknown_source() -> None:
    with pytest.raises(KeyError, match="missing-source"):
        adapter_extraction_policy_for_source("missing-source")


def test_payload_facade_rejects_unknown_source() -> None:
    with pytest.raises(KeyError, match="missing-source"):
        adapter_normalized_extraction_payload(source_key="missing-source", record={})


def test_proposal_summary_facade_rejects_unknown_source() -> None:
    with pytest.raises(KeyError, match="missing-source"):
        adapter_proposal_summary(source_key="missing-source", selection_reason="x")


def test_review_summary_facade_rejects_unknown_source() -> None:
    with pytest.raises(KeyError, match="missing-source"):
        adapter_review_item_summary(source_key="missing-source", selection_reason="x")
