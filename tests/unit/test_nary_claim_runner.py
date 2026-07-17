from __future__ import annotations

import hashlib

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
    bind_claim_inventory,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    ClaimInventoryRepairFailedError,
    build_claim_inventory_prompt,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSchemaError,
)

from scripts.validation.claim_events.operational import CaseExecutionOutcome
from scripts.validation.claim_events.runner import (
    _attempt_output_schema_sha256,
    _execution_outcome,
    _inventory_execution_state,
    _nary_events,
    _require_attempt_model,
    _require_model,
    _terminal_error_category,
)
from scripts.validation.claim_frames.provider_receipts import (
    canonical_provider_model_id,
)


def test_nary_adapter_preserves_agent_event_semantics() -> None:
    text = "AKT1 phosphorylation in B cells"
    lineage = bind_claim_inventory(
        (
            ClaimInventoryItem.model_validate(
                {
                    "exact_span": text,
                    "relation_cue_span": "phosphorylation",
                    "source_locator": "normalized_extraction_text",
                    "claim_kind": "SCIENTIFIC_FINDING",
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
                },
            ),
        ),
        source_text=text,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        chunk_index=0,
    )

    assert _nary_events(lineage) == [
        {
            "inventory_id": lineage[0].inventory_id,
            "source_start": 0,
            "source_end": 31,
            "exact_span": "AKT1 phosphorylation in B cells",
            "trigger_span": "phosphorylation",
            "trigger_source_start": 5,
            "trigger_source_mention": {
                "exact_span": "phosphorylation",
                "source_start": 5,
                "source_end": 20,
            },
            "relation_cue_span": "phosphorylation",
            "relation_cue_anchor": None,
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "PHOSPHORYLATION",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "AKT1",
                    "mention_anchors": [],
                    "role_rationale": "phosphorylated theme",
                    "source_start": 0,
                    "source_mentions": [
                        {"exact_span": "AKT1", "source_start": 0, "source_end": 4}
                    ],
                },
                {
                    "role": "POPULATION",
                    "event_role": "CONTEXT",
                    "exact_span": "B cells",
                    "mention_anchors": [],
                    "role_rationale": "cell population context",
                    "source_start": 24,
                    "source_mentions": [
                        {
                            "exact_span": "B cells",
                            "source_start": 24,
                            "source_end": 31,
                        }
                    ],
                },
            ],
            "inventory_rationale": "explicit source event",
        },
    ]


def test_nary_adapter_derives_every_repeated_mention_offset() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    item = ClaimInventoryItem.model_validate(
        {
            "exact_span": text,
            "relation_cue_span": "suggests",
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "REGULATION",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source states one regulation event.",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "WT1",
                    "mention_anchors": [
                        {
                            "mention_span": "WT1",
                            "left_context": "",
                            "right_context": " in fibroblasts",
                        },
                        {
                            "mention_span": "WT1",
                            "left_context": " and ",
                            "right_context": " in lymphocytes",
                        },
                    ],
                    "role_rationale": "Both mentions denote the same participant.",
                },
                {
                    "role": "BIOLOGICAL_PROCESS",
                    "event_role": "THEME",
                    "exact_span": "regulation",
                    "role_rationale": "The source names the regulated process.",
                },
            ],
        },
    )
    source_start = 200

    event = _nary_events(
        bind_claim_inventory(
            (item,),
            source_text=text,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            chunk_index=0,
            source_start_offset=source_start,
        ),
    )[0]

    repeated_argument = event["arguments"][0]
    assert repeated_argument["source_start"] == source_start + text.index("WT1")
    assert [
        mention["source_start"] for mention in repeated_argument["source_mentions"]
    ] == [
        source_start + text.index("WT1"),
        source_start + text.rindex("WT1"),
    ]
    assert event["trigger_source_start"] == source_start + text.index("suggests")


def test_nary_adapter_keeps_legacy_offset_on_canonical_span() -> None:
    text = "It remained elevated after WT1 increased regulation."
    item = ClaimInventoryItem.model_validate(
        {
            "exact_span": text,
            "relation_cue_span": "increased",
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "INCREASE",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source states one increase event.",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "AGENT",
                    "exact_span": "WT1",
                    "mention_anchors": [
                        {
                            "mention_span": "It",
                            "left_context": "",
                            "right_context": " remained elevated",
                        },
                        {
                            "mention_span": "WT1",
                            "left_context": "remained elevated after ",
                            "right_context": " increased",
                        },
                    ],
                    "role_rationale": "The pronoun and WT1 identify one participant.",
                },
                {
                    "role": "BIOLOGICAL_PROCESS",
                    "event_role": "EFFECT",
                    "exact_span": "regulation",
                    "role_rationale": "Regulation is the affected process.",
                },
            ],
        },
    )

    event = _nary_events(
        bind_claim_inventory(
            (item,),
            source_text=text,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            chunk_index=0,
        ),
    )[0]
    argument = event["arguments"][0]

    assert argument["source_mentions"][0]["exact_span"] == "It"
    assert argument["source_start"] == text.index("WT1")
    assert (
        text[argument["source_start"] : argument["source_start"] + len("WT1")] == "WT1"
    )


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


def test_runner_categorizes_bound_empty_and_unbindable_results() -> None:
    assert (
        _execution_outcome(
            events=[{"event_type": "BINDING"}],
            terminal_failure=False,
            semantic_incomplete=False,
        )
        is CaseExecutionOutcome.BOUND_OUTPUT
    )
    assert (
        _execution_outcome(
            events=[],
            terminal_failure=False,
            semantic_incomplete=False,
        )
        is CaseExecutionOutcome.NO_OUTPUT
    )
    assert (
        _execution_outcome(
            events=[],
            terminal_failure=True,
            semantic_incomplete=False,
        )
        is CaseExecutionOutcome.UNBINDABLE_OUTPUT
    )


def test_runner_blocks_scoring_until_inventory_is_semantically_complete() -> None:
    executable, routing_status = _inventory_execution_state(
        inventory_available=True,
        semantic_inventory_complete=False,
        terminal_error=None,
    )

    assert executable is False
    assert routing_status == "semantic_incomplete"
    assert (
        _execution_outcome(
            events=[],
            terminal_failure=False,
            semantic_incomplete=not executable,
        )
        is CaseExecutionOutcome.SEMANTICALLY_INCOMPLETE
    )


def test_runner_routes_complete_inventory_and_terminal_failure_separately() -> None:
    assert _inventory_execution_state(
        inventory_available=True,
        semantic_inventory_complete=True,
        terminal_error=None,
    ) == (True, "complete")
    assert _inventory_execution_state(
        inventory_available=False,
        semantic_inventory_complete=False,
        terminal_error=RuntimeError("model failed"),
    ) == (False, "unbound")


def test_runner_reports_underlying_audited_repair_error_category() -> None:
    error = ClaimInventoryRepairFailedError(
        cause=StructuredModelSchemaError("invalid repair"),
        rejection_events=(),
    )

    assert _terminal_error_category(error) == "StructuredModelSchemaError"


def test_schema_retry_prompt_is_canonically_reconstructable() -> None:
    chunk = build_relation_extraction_text_chunks("WT1 increased expression.")[0]
    base = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=1,
        document_fingerprint="a" * 64,
    )
    retry = build_claim_inventory_prompt(
        chunk=chunk,
        total_chunks=1,
        document_fingerprint="a" * 64,
        schema_retry=True,
    )

    assert retry.startswith(base)
    assert "SCHEMA AND SOURCE-BINDING RETRY" in retry
