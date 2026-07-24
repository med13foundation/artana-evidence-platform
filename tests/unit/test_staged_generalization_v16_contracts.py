"""Focused schema regressions for the bounded V16 scope contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)

REPO = Path(__file__).resolve().parents[2]
V11_UNCERTAINTY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-"
    "generalization-uncertainty-raw.json"
)


def test_v16_schema_accepts_one_scope_link_and_partitive_on_affected_argument() -> None:
    output = V16StagedGeneralizationOutput.model_validate_json(
        json.dumps(_valid_payload())
    )
    argument = output.links[0].arguments[0]

    assert output.participant_scope_links[0].restricted_participant_id == "p1"
    assert output.participant_scope_links[0].restrictor_participant_id == "p2"
    assert argument.partitive_scope is not None
    assert argument.partitive_scope.kind == "MAJORITY"
    assert argument.partitive_scope.antecedent_participant_id == "p1"


def test_v16_schema_rejects_partitive_bound_to_a_different_argument_target() -> None:
    payload = _valid_payload()
    payload["links"][0]["arguments"][0]["partitive_scope"][
        "antecedent_participant_id"
    ] = "p2"

    with pytest.raises(ValidationError, match="partitive antecedent"):
        V16StagedGeneralizationOutput.model_validate_json(json.dumps(payload))


def test_v16_schema_rejects_duplicate_scope_links() -> None:
    payload = _valid_payload()
    scope = payload["participant_scope_links"][0]
    payload["participant_scope_links"].append(dict(scope))

    with pytest.raises(ValidationError, match="scope links must be unique"):
        V16StagedGeneralizationOutput.model_validate_json(json.dumps(payload))


def _valid_payload() -> dict[str, object]:
    value = json.loads(V11_UNCERTAINTY_RAW.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("raw uncertainty fixture is not an object")
    links = value["links"]
    if not isinstance(links, list) or not isinstance(links[0], dict):
        raise TypeError("raw uncertainty links are malformed")
    arguments = links[0]["arguments"]
    if not isinstance(arguments, list) or not isinstance(arguments[0], dict):
        raise TypeError("raw uncertainty arguments are malformed")
    evidence = "RESULTS: A total of 947 variants were detected in the SLC12A3 gene, the majority of which were classified as of uncertain significance."
    arguments[0]["partitive_scope"] = {
        "kind": "MAJORITY",
        "exact_text": "the majority of which",
        "exact_evidence": evidence,
        "antecedent_participant_id": "p1",
        "explanation": "The classification applies to the stated majority subset.",
    }
    value["participant_scope_links"] = [
        {
            "restricted_participant_id": "p1",
            "restrictor_participant_id": "p2",
            "relation_type": "IDENTITY_OR_SCOPE_RESTRICTION",
            "exact_evidence": evidence,
            "explanation": "The named gene restricts the detected variant cohort.",
        }
    ]
    return value
