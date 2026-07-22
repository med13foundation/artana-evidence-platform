"""Run the first fail-fast specialist-assisted Luna micro-canary exactly once."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    execute_background_provider_call,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)
from scripts.validation.public_gold.staged_event.context_experiment.specialist_luna_contracts import (
    SpecialistLunaOutput,
)

REPO = Path(__file__).resolve().parents[5]
PREREGISTRATION = REPO / (
    "docs/validation/preregistrations/"
    "2026-07-22-specialist-luna-micro-canary-v1.json"
)
RESULT = REPO / (
    "docs/validation/results/2026-07-22-specialist-luna-micro-canary-v1.json"
)
RECEIPT = REPO / (
    "docs/validation/receipts/2026-07-22-specialist-luna-micro-canary-v1.json"
)
PROMPT = REPO / (
    "docs/validation/prompts/2026-07-22-specialist-luna-micro-canary-v1.md"
)
SOURCE = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
PACKET_ID = "packet-central-nested-v1"
EVENT_SCOPE_END = 222
SOURCE_SHA256 = "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"


class CanaryStateError(RuntimeError):
    """The frozen canary cannot execute safely."""


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def provider_format() -> dict[str, object]:
    value = cast("dict[str, object]", type_to_text_format_param(SpecialistLunaOutput))
    value["description"] = "Categorical source-only specialist proposal adjudication."
    return value


def candidate_packet(source: str) -> dict[str, object]:
    return {
        "packet_id": PACKET_ID,
        "event_local_scope": {
            "start": 0,
            "end": EVENT_SCOPE_END,
            "text": source[0:EVENT_SCOPE_END],
        },
        "atomic_event": {
            "start": 0,
            "end": 75,
            "text": source[0:75],
        },
        "specialist_proposals": [
            {
                "proposal_id": "deepeventmine-E1",
                "generator": "DeepEventMine-GE11",
                "generator_event_type": "Negative_regulation",
                "trigger": {"start": 0, "end": 8, "text": source[0:8]},
                "arguments": [
                    {
                        "role": "Theme",
                        "target_kind": "PARTICIPANT",
                        "start": 12,
                        "end": 17,
                        "text": source[12:17],
                        "generator_entity_type": "Protein",
                    }
                ],
                "provenance": (
                    "DeepEventMine:e1c56013:GE11:PMID-16428936:E1"
                ),
            }
        ],
    }


def build_provider_input(source: str) -> str:
    return (
        PROMPT.read_text(encoding="utf-8")
        + "\n\n--- FROZEN SOURCE PACKET ---\n"
        + json.dumps(candidate_packet(source), indent=2, sort_keys=True)
        + "\n--- END FROZEN SOURCE PACKET ---\n"
    )


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def execute() -> str:
    if RESULT.exists() or RECEIPT.exists():
        raise CanaryStateError("one-shot Luna canary already has terminal artifacts")
    preregistration = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise CanaryStateError("frozen source changed")
    provider_input = build_provider_input(source)
    frozen = preregistration["frozen_state"]
    if not isinstance(frozen, dict):
        raise CanaryStateError("malformed frozen state")
    if frozen.get("candidate_sha256") != canonical_sha256(candidate_packet(source)):
        raise CanaryStateError("candidate packet changed")
    if frozen.get("provider_input_sha256") != hashlib.sha256(
        provider_input.encode()
    ).hexdigest():
        raise CanaryStateError("provider input changed")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise CanaryStateError("OPENAI_API_KEY is absent")
    response_format = provider_format()
    try:
        execution = execute_background_provider_call(
            api_key=api_key,
            output_model=SpecialistLunaOutput,
            transport_budgets=BackgroundExecutionBudgets(
                acknowledgement_timeout_seconds=30,
                polling_interval_seconds=5,
                max_polling_seconds=900,
            ),
            request=ProviderRequest(
                provider_input=provider_input,
                provider_format=response_format,
                provider_model_id=MODEL,
                reasoning_effort=REASONING_EFFORT,
                max_output_tokens=8000,
                max_total_tokens=20000,
                max_cost_usd=1.0,
                max_latency_seconds=900,
                pricing={
                    "input": 0.000001,
                    "cached_input": 0.0000001,
                    "output": 0.000006,
                },
                metadata={
                    "artana_experiment": "specialist-luna-micro-canary-v1",
                    "artana_source_sha256": SOURCE_SHA256,
                    "artana_packet_id": PACKET_ID,
                },
            ),
        )
    except ProviderExecutionError as exc:
        _write(
            RESULT,
            {
                "decision": "INVALID_PROVIDER_EXECUTION",
                "failure_stage": exc.stage,
                "root_cause": exc.root_cause,
                "diagnostics": exc.diagnostics,
            },
        )
        return "INVALID_PROVIDER_EXECUTION"
    output = execution.extraction
    decisions = {item.proposal_id: item for item in output.proposal_decisions}
    expected_ids = {"deepeventmine-E1"}
    valid_ids = set(decisions) == expected_ids
    spans_valid = all(
        source[item.evidence_start : item.evidence_end] == item.exact_evidence
        and 0 <= item.evidence_start < item.evidence_end <= EVENT_SCOPE_END
        for item in output.proposal_decisions
    )
    nested_structure_correct = output.structure_assessment == "COMPLETE"
    decision = (
        "PENDING_NEXT_CANARY"
        if valid_ids and spans_valid and nested_structure_correct
        else "STOP_LUNA_SCIENTIFIC_FAILURE"
    )
    _write(RECEIPT, execution.receipt)
    _write(
        RESULT,
        {
            "decision": decision,
            "packet_id": PACKET_ID,
            "output": output.model_dump(mode="json"),
            "proposal_ids_valid": valid_ids,
            "evidence_spans_valid": spans_valid,
            "nested_structure_correct": nested_structure_correct,
            "receipt_sha256": canonical_sha256(execution.receipt),
            "trusted_promotion": False,
        },
    )
    return decision


if __name__ == "__main__":
    print(execute())
