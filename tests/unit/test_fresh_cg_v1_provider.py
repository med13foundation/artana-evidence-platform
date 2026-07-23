"""Provider-boundary regressions for the fresh-CG occurrence experiment."""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_input import (
    agent_case,
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.selection import (
    load_frozen_selection,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)

V9_SCHEMA_SHA256 = "02594c4ce1cb089e1b23da0495269a8b457f68b3e57396f345a2258a94eb57c1"
V9_PROMPT_SHA256 = "4ce450b6a79fdb0cb99c48a69eae1390beef21dcf0094099503c03bdb4dd9234"


def _wrapper_payload(*, scientific_case_id: str, binding_case_id: str) -> dict[str, object]:
    evidence = "Drug activates GENE."
    return {
        "schema_version": "artana.staged_generalization.fresh_cg_provider.v1",
        "scientific_output": {
            "case_id": scientific_case_id,
            "inventory": [
                {
                    "event_id": "event-1",
                    "event_type": "POSITIVE_REGULATION",
                    "trigger_text": "activates",
                    "exact_evidence": evidence,
                    "explanation": "The source explicitly states activation.",
                }
            ],
            "participants": [
                {
                    "participant_id": "participant-1",
                    "entity_type": "GENE_OR_PROTEIN",
                    "exact_text": "GENE",
                    "exact_evidence": evidence,
                    "explanation": "GENE is the affected entity.",
                }
            ],
            "links": [
                {
                    "event_id": "event-1",
                    "arguments": [
                        {
                            "role": "AFFECTED_ENTITY",
                            "target_kind": "PARTICIPANT",
                            "target_id": "participant-1",
                            "explanation": "The activation applies to GENE.",
                        }
                    ],
                }
            ],
            "semantic_axes": [
                {
                    "event_id": "event-1",
                    "direction": "INCREASED",
                    "comparison": "NOT_APPLICABLE",
                    "polarity": "AFFIRMED",
                    "uncertainty": "ASSERTED",
                    "statistical_observations": [
                        {"observation_type": "NONE", "exact_text": None}
                    ],
                    "author_interpretation": "NOT_CLAIMED",
                    "evidence_items": ["activates"],
                    "explanation": "The source makes an asserted positive-regulation claim.",
                }
            ],
            "root_event_id": "event-1",
            "completeness": "COMPLETE",
            "structure_explanation": "One atomic event is complete.",
        },
        "occurrence_bindings": {
            "schema_version": "artana.staged_generalization.occurrence_bindings.v2",
            "case_id": binding_case_id,
            "event_mentions": [
                {
                    "node_id": "event-1",
                    "identity": {
                        "evidence_span": {"start": 0, "end": 20},
                        "mention_span": {"start": 5, "end": 14},
                    },
                }
            ],
            "participant_mentions": [
                {
                    "node_id": "participant-1",
                    "identity": {
                        "evidence_span": {"start": 0, "end": 20},
                        "mention_span": {"start": 15, "end": 19},
                    },
                }
            ],
            "semantic_evidence": [
                {
                    "event_id": "event-1",
                    "evidence_item_spans": [{"start": 5, "end": 14}],
                    "statistical_observation_spans": [None],
                }
            ],
        },
    }


def test_provider_contract_reuses_v9_schema_without_mutation() -> None:
    schema_bytes = json.dumps(
        V9StagedGeneralizationOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert hashlib.sha256(schema_bytes).hexdigest() == V9_SCHEMA_SHA256
    assert hashlib.sha256(DEFAULT_PATHS.scientific_prompt.read_bytes()).hexdigest() == (
        V9_PROMPT_SHA256
    )
    assert (
        FreshCGProviderOutput.model_fields["scientific_output"].annotation
        is V9StagedGeneralizationOutput
    )


def test_provider_packet_excludes_references_labels_and_cg_roles() -> None:
    selection = load_frozen_selection(DEFAULT_PATHS.selection)
    case = selection.cases[0]

    packet = agent_case(case)
    value = provider_input(
        case,
        scientific_prompt_path=DEFAULT_PATHS.scientific_prompt,
        binding_prompt_path=DEFAULT_PATHS.binding_prompt,
    )

    assert set(packet) == {
        "case_id",
        "source_id",
        "source_sha256",
        "context_start",
        "context_end",
        "local_context",
        "focus_passage",
    }
    for forbidden in (
        "source_event_type",
        "artana_event_type",
        "source_entity_type",
        "artana_entity_type",
        "source_role",
        "direct_cg_reference_sha256",
        "reviewer_id",
        "expected",
        "benchmark_projection",
    ):
        assert forbidden not in value


def test_provider_contract_rejects_case_identity_mismatch() -> None:
    with pytest.raises(ValidationError, match="case IDs differ"):
        FreshCGProviderOutput.model_validate_json(
            json.dumps(
                _wrapper_payload(
                    scientific_case_id="fresh-case-a",
                    binding_case_id="fresh-case-b",
                )
            )
        )


def test_provider_contract_accepts_matching_case_identity() -> None:
    output = FreshCGProviderOutput.model_validate_json(
        json.dumps(
            _wrapper_payload(
                scientific_case_id="fresh-case-a",
                binding_case_id="fresh-case-a",
            )
        )
    )

    assert output.scientific_output.case_id == "fresh-case-a"
    assert output.occurrence_bindings.case_id == "fresh-case-a"
