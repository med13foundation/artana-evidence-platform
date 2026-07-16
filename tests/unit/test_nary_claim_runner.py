from __future__ import annotations

from types import SimpleNamespace

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
)

from scripts.validation.claim_events.runner import (
    _attempt_output_schema_sha256,
    _nary_events,
    _require_attempt_model,
    _require_model,
)
from scripts.validation.claim_frames.provider_receipts import (
    canonical_provider_model_id,
)


def test_nary_adapter_preserves_agent_event_semantics() -> None:
    lineage = (
        SimpleNamespace(
            inventory_id="inventory-1",
            source_start=0,
            source_end=31,
            item=ClaimInventoryItem.model_validate(
                {
                    "exact_span": "AKT1 phosphorylation in B cells",
                    "relation_cue_span": "phosphorylation",
                    "source_locator": "normalized_extraction_text",
                    "event_type": "PHOSPHORYLATION",
                    "polarity": "SUPPORT",
                    "epistemic_status": "ASSERTED",
                    "inventory_rationale": "explicit source event",
                    "arguments": [
                        {
                            "role": "GENE_OR_PROTEIN",
                            "event_role": "THEME",
                            "exact_span": "AKT1",
                            "role_rationale": "phosphorylated theme",
                        },
                        {
                            "role": "POPULATION",
                            "event_role": "CONTEXT",
                            "exact_span": "B cells",
                            "role_rationale": "cell population context",
                        },
                    ],
                }
            ),
        ),
    )

    assert _nary_events(lineage) == [
        {
            "inventory_id": "inventory-1",
            "source_start": 0,
            "source_end": 31,
            "exact_span": "AKT1 phosphorylation in B cells",
            "trigger_span": "phosphorylation",
            "trigger_source_start": 5,
            "relation_cue_span": "phosphorylation",
            "source_locator": "normalized_extraction_text",
            "event_type": "PHOSPHORYLATION",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "AKT1",
                    "role_rationale": "phosphorylated theme",
                    "source_start": 0,
                },
                {
                    "role": "POPULATION",
                    "event_role": "CONTEXT",
                    "exact_span": "B cells",
                    "role_rationale": "cell population context",
                    "source_start": 24,
                },
            ],
            "inventory_rationale": "explicit source event",
        },
    ]


def test_runner_rejects_unregistered_or_substituted_models() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        _require_model("openai:gpt-5")
    with pytest.raises(RuntimeError, match="differs"):
        _require_attempt_model("openai/gpt-5.6-luna", "openai:gpt-5.6-sol")

    _require_attempt_model("openai/gpt-5.6-sol", "openai:gpt-5.6-sol")
    assert canonical_provider_model_id("openai:gpt-5.6-sol") == "gpt-5.6-sol"


def test_zero_candidate_retry_uses_inventory_pass_schema() -> None:
    primary = _attempt_output_schema_sha256(
        {
            "attempt_role": "claim_inventory",
            "pass_role": "claim_inventory",
        },
    )

    assert (
        _attempt_output_schema_sha256(
            {
                "attempt_role": "zero_candidate_retry",
                "pass_role": "claim_inventory",
            },
        )
        == primary
    )
