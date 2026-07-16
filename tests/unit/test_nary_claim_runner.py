from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.validation.claim_events.runner import (
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
            source_end=20,
            inventory_payload={
                "exact_span": "AKT1 phosphorylation",
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
                    },
                ],
            },
        ),
    )

    assert _nary_events(lineage) == [
        {
            "inventory_id": "inventory-1",
            "source_start": 0,
            "source_end": 20,
            "exact_span": "AKT1 phosphorylation",
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
                    "source_start": 0,
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
