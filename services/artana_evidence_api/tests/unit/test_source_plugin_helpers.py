"""Tests for shared source plugin helper behavior."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from artana_evidence_api.source_plugins._helpers import (
    assert_intent_source_key,
    assert_search_source_key,
    compact_json_object,
    identifier_fields,
    json_value_field,
    normalized_extraction_payload,
    required_text,
    string_field,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourcePluginPlanningError,
    SourceReviewPolicy,
)
from artana_evidence_api.types.common import JSONObject


def test_compact_json_object_drops_empty_values() -> None:
    assert compact_json_object(
        {
            "name": "BRCA1",
            "missing": None,
            "empty_text": "",
            "empty_list": [],
            "empty_object": {},
            "zero": 0,
            "false": False,
        },
    ) == {"name": "BRCA1", "zero": 0, "false": False}


def test_string_field_returns_first_non_empty_string_like_value() -> None:
    record: JSONObject = {"empty": " ", "number": 123, "name": " BRCA1 "}

    assert string_field(record, "empty", "name") == "BRCA1"
    assert string_field(record, "empty", "number") == "123"
    assert string_field(record, "missing") is None


def test_json_value_field_returns_first_non_empty_json_value() -> None:
    record: JSONObject = {
        "empty": [],
        "confidence": 92.4,
        "domains": [{"name": "BRCT"}],
    }

    assert json_value_field(record, "empty", "confidence") == 92.4
    assert json_value_field(record, "domains") == [{"name": "BRCT"}]
    assert json_value_field(record, "missing") is None


def test_identifier_fields_uses_stable_identifier_suffixes() -> None:
    assert identifier_fields(
        {
            "id": "internal",
            "uniprot_id": "P38398",
            "accession": "P38398",
            "title": "BRCA1",
        },
    ) == {
        "id": "internal",
        "uniprot_id": "P38398",
        "accession": "P38398",
    }


def test_normalized_extraction_payload_uses_review_policy_fields() -> None:
    policy = SourceReviewPolicy(
        source_key="alphafold",
        proposal_type="structure_context_candidate",
        review_type="structure_context_review",
        evidence_role="protein structure context candidate",
        limitations=("Predicted structure is indirect biological context.",),
        normalized_fields=("uniprot_id", "model_url"),
    )

    assert normalized_extraction_payload(
        source_key="alphafold",
        review_policy=policy,
        record={
            "uniprot_id": "P38398",
            "model_url": "https://alphafold.example/P38398.cif",
            "ignored": "value",
        },
    ) == {
        "source_key": "alphafold",
        "evidence_role": "protein structure context candidate",
        "identifiers": {"uniprot_id": "P38398"},
        "fields": {
            "uniprot_id": "P38398",
            "model_url": "https://alphafold.example/P38398.cif",
        },
        "limitations": ["Predicted structure is indirect biological context."],
        "raw_record_preserved": True,
    }


def test_required_text_and_source_key_assertions_fail_closed() -> None:
    assert required_text(" P38398 ", source_key="alphafold", field_name="uniprot_id") == (
        "P38398"
    )
    with pytest.raises(SourcePluginPlanningError, match="uniprot_id"):
        required_text(None, source_key="alphafold", field_name="uniprot_id")
    with pytest.raises(SourcePluginPlanningError, match="cannot plan"):
        assert_intent_source_key(_Intent(source_key="uniprot"), source_key="alphafold")
    with pytest.raises(EvidenceSelectionSourceSearchError, match="canonical"):
        assert_search_source_key(
            _Search(source_key="alpha-fold", query_payload={"uniprot_id": "P38398"}),
            source_key="alphafold",
            display_name="AlphaFold",
        )


@dataclass(frozen=True, slots=True)
class _Intent:
    source_key: str
    query: str | None = None
    gene_symbol: str | None = None
    variant_hgvs: str | None = None
    protein_variant: str | None = None
    uniprot_id: str | None = None
    drug_name: str | None = None
    drugbank_id: str | None = None
    disease: str | None = None
    phenotype: str | None = None
    organism: str | None = None
    taxon_id: int | None = None
    panels: list[str] | None = None


@dataclass(frozen=True, slots=True)
class _Search:
    source_key: str
    query_payload: JSONObject
    max_records: int | None = None
    timeout_seconds: float | None = None
