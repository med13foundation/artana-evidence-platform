"""Run the frozen source-first Luna event-construction experiment."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    BackgroundProviderExecution,
    execute_background_provider_call,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first_contracts import (
    CompleteEventOutput,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first_validation import (
    SourceFirstValidationError,
    compare_to_exposed_gold_root,
    validate_structure,
)
from scripts.validation.public_gold.staged_event.context_experiment.specialist_replay import (
    parse_standoff,
)

REPO = Path(__file__).resolve().parents[5]
SOURCE = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
GOLD_A1 = SOURCE.with_suffix(".a1")
GOLD_A2 = SOURCE.with_suffix(".a2")
PROMPT = REPO / (
    "docs/validation/prompts/"
    "2026-07-22-source-first-luna-event-construction-v1.md"
)
PREREGISTRATION = REPO / (
    "docs/validation/preregistrations/"
    "2026-07-22-source-first-luna-event-construction-v1.json"
)
RESULT = REPO / (
    "docs/validation/results/"
    "2026-07-22-source-first-luna-event-construction-v1.json"
)
RECEIPT = REPO / (
    "docs/validation/receipts/"
    "2026-07-22-source-first-luna-event-construction-v1.json"
)
SOURCE_SHA256 = "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MINIMUM_CORRECTED_EVENTS = 2


@dataclass(frozen=True)
class Case:
    packet_id: str
    scope_start: int
    scope_end: int
    finding_start: int
    finding_end: int
    gold_root_id: str
    previously_incorrect: bool
    specialist_hints: tuple[dict[str, object], ...]


CASES = (
    Case(
        packet_id="source-first-primary-nested-v1",
        scope_start=0,
        scope_end=222,
        finding_start=0,
        finding_end=75,
        gold_root_id="E2",
        previously_incorrect=True,
        specialist_hints=(
            {
                "generator": "DeepEventMine-GE11",
                "event_type": "Negative_regulation",
                "trigger": {"start": 0, "end": 8, "text": "Decrease"},
                "arguments": [
                    {
                        "role": "Theme",
                        "target_kind": "PARTICIPANT",
                        "start": 12,
                        "end": 17,
                        "text": "c-Myc",
                        "generator_entity_type": "Protein",
                    }
                ],
                "provenance": "DeepEventMine:e1c56013:GE11:PMID-16428936:E1",
            },
        ),
    ),
    Case(
        packet_id="source-first-sensitivity-v1",
        scope_start=352,
        scope_end=854,
        finding_start=578,
        finding_end=678,
        gold_root_id="E15",
        previously_incorrect=True,
        specialist_hints=(),
    ),
    Case(
        packet_id="source-first-conclusion-v1",
        scope_start=1040,
        scope_end=1443,
        finding_start=1119,
        finding_end=1269,
        gold_root_id="E25",
        previously_incorrect=True,
        specialist_hints=(
            {
                "generator": "DeepEventMine-GE11",
                "event_type": "Gene_expression",
                "trigger": {"start": 1156, "end": 1166, "text": "expression"},
                "arguments": [
                    {
                        "role": "Theme",
                        "target_kind": "PARTICIPANT",
                        "start": 1150,
                        "end": 1155,
                        "text": "c-Myc",
                        "generator_entity_type": "Protein",
                    }
                ],
                "provenance": "DeepEventMine:e1c56013:GE11:PMID-16428936:E4",
            },
            {
                "generator": "DeepEventMine-GE11",
                "event_type": "Negative_regulation",
                "trigger": {"start": 1138, "end": 1146, "text": "decrease"},
                "arguments": [
                    {
                        "role": "Theme",
                        "target_kind": "EVENT",
                        "target_hint": "the expression proposal",
                    }
                ],
                "provenance": "DeepEventMine:e1c56013:GE11:PMID-16428936:E7",
            },
        ),
    ),
    Case(
        packet_id="source-first-simple-control-v1",
        scope_start=0,
        scope_end=222,
        finding_start=0,
        finding_end=26,
        gold_root_id="E1",
        previously_incorrect=False,
        specialist_hints=(
            {
                "generator": "DeepEventMine-GE11",
                "event_type": "Negative_regulation",
                "trigger": {"start": 0, "end": 8, "text": "Decrease"},
                "arguments": [
                    {
                        "role": "Theme",
                        "target_kind": "PARTICIPANT",
                        "start": 12,
                        "end": 17,
                        "text": "c-Myc",
                        "generator_entity_type": "Protein",
                    }
                ],
                "provenance": "DeepEventMine:e1c56013:GE11:PMID-16428936:E1",
            },
        ),
    ),
)


class SourceFirstStateError(RuntimeError):
    """The frozen source-first execution cannot proceed safely."""


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def provider_format() -> dict[str, object]:
    value = cast("dict[str, object]", type_to_text_format_param(CompleteEventOutput))
    value["description"] = "Source-first typed scientific event graph."
    return value


def packet(case: Case, source: str) -> dict[str, object]:
    return {
        "packet_id": case.packet_id,
        "permitted_context": {
            "start": case.scope_start,
            "end": case.scope_end,
            "text": source[case.scope_start : case.scope_end],
        },
        "highlighted_finding": {
            "start": case.finding_start,
            "end": case.finding_end,
            "text": source[case.finding_start : case.finding_end],
        },
        "optional_specialist_hints": list(case.specialist_hints),
    }


def provider_input(case: Case, source: str) -> str:
    return (
        PROMPT.read_text(encoding="utf-8")
        + "\n\n--- FROZEN SOURCE PACKET ---\n"
        + json.dumps(packet(case, source), indent=2, sort_keys=True)
        + "\n--- END FROZEN SOURCE PACKET ---\n"
    )


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _call(
    case: Case, source: str, api_key: str, prereg_hash: str
) -> BackgroundProviderExecution[CompleteEventOutput]:
    return execute_background_provider_call(
        api_key=api_key,
        output_model=CompleteEventOutput,
        transport_budgets=BackgroundExecutionBudgets(
            acknowledgement_timeout_seconds=30,
            polling_interval_seconds=5,
            max_polling_seconds=900,
        ),
        request=ProviderRequest(
            provider_input=provider_input(case, source),
            provider_format=provider_format(),
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
                "artana_experiment": "source-first-luna-event-construction-v1",
                "artana_preregistration_sha256": prereg_hash,
                "artana_source_sha256": SOURCE_SHA256,
                "artana_packet_id": case.packet_id,
            },
        ),
    )


def execute() -> str:  # noqa: C901, PLR0912, PLR0915
    if RESULT.exists() or RECEIPT.exists():
        raise SourceFirstStateError("source-first one-shot result already exists")
    preregistration = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    frozen = preregistration["frozen_state"]
    if not isinstance(frozen, dict):
        raise SourceFirstStateError("malformed frozen state")
    source = SOURCE.read_text(encoding="utf-8")
    if hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise SourceFirstStateError("frozen source changed")
    expected_hashes = {
        "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
        "schema_sha256": canonical_sha256(CompleteEventOutput.model_json_schema()),
        "provider_format_sha256": canonical_sha256(provider_format()),
        "specialist_hint_sha256": canonical_sha256(
            {case.packet_id: case.specialist_hints for case in CASES}
        ),
    }
    for name, actual in expected_hashes.items():
        if frozen.get(name) != actual:
            raise SourceFirstStateError(f"frozen {name} changed")
    code_hashes = frozen.get("code_sha256")
    if not isinstance(code_hashes, dict):
        raise SourceFirstStateError("frozen code hashes are absent")
    for relative, expected in code_hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise SourceFirstStateError("malformed frozen code hash")
        if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != expected:
            raise SourceFirstStateError(f"frozen code changed: {relative}")
    expected_inputs = frozen.get("provider_input_sha256")
    actual_inputs = {
        case.packet_id: hashlib.sha256(provider_input(case, source).encode()).hexdigest()
        for case in CASES
    }
    if expected_inputs != actual_inputs:
        raise SourceFirstStateError("frozen provider inputs changed")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SourceFirstStateError("OPENAI_API_KEY is absent")
    gold = parse_standoff(
        GOLD_A1.read_text(encoding="utf-8")
        + "\n"
        + GOLD_A2.read_text(encoding="utf-8")
    )
    prereg_hash = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
    case_results: list[dict[str, object]] = []
    receipts: list[dict[str, object]] = []
    for index, case in enumerate(CASES):
        try:
            execution = _call(case, source, api_key, prereg_hash)
        except ProviderExecutionError as exc:
            _write(
                RESULT,
                {
                    "decision": "INVALID_PROVIDER_EXECUTION",
                    "failed_packet": case.packet_id,
                    "failure_stage": exc.stage,
                    "root_cause": exc.root_cause,
                    "diagnostics": exc.diagnostics,
                    "completed_cases": case_results,
                },
            )
            _write(RECEIPT, {"receipts": receipts})
            return "INVALID_PROVIDER_EXECUTION"
        receipts.append(execution.receipt)
        output = execution.extraction
        structural_error: str | None
        try:
            validate_structure(
                output,
                source=source,
                scope_start=case.scope_start,
                scope_end=case.scope_end,
            )
        except SourceFirstValidationError as exc:
            comparison = None
            structural_error = str(exc)
        else:
            comparison = compare_to_exposed_gold_root(
                output, gold=gold, gold_root_id=case.gold_root_id
            )
            structural_error = None
        passed = comparison is not None and comparison.exact
        case_results.append(
            {
                "packet_id": case.packet_id,
                "output": output.model_dump(mode="json"),
                "structural_error": structural_error,
                "comparison": asdict(comparison) if comparison else None,
                "passed": passed,
                "receipt_status": execution.receipt.get("status"),
                "usage": execution.receipt.get("usage"),
            }
        )
        if index == 0 and not passed:
            decision = "STOP_SOURCE_FIRST_LUNA_SCIENTIFIC_FAILURE"
            _write(RECEIPT, {"receipts": receipts})
            _write(
                RESULT,
                {
                    "decision": decision,
                    "cases": case_results,
                    "provider_call_count": len(receipts),
                    "trusted_promotion": False,
                },
            )
            return decision
    corrected = sum(
        bool(item["passed"])
        for item, case in zip(case_results, CASES, strict=True)
        if case.previously_incorrect
    )
    control_passed = bool(case_results[-1]["passed"])
    decision = (
        "ADVANCE_SOURCE_FIRST_EVENT_CONSTRUCTION"
        if corrected >= MINIMUM_CORRECTED_EVENTS and control_passed
        else "STOP_SOURCE_FIRST_LUNA_SCIENTIFIC_FAILURE"
    )
    _write(RECEIPT, {"receipts": receipts})
    _write(
        RESULT,
        {
            "decision": decision,
            "cases": case_results,
            "corrected_previously_incorrect": corrected,
            "control_passed": control_passed,
            "provider_call_count": len(receipts),
            "trusted_promotion": False,
        },
    )
    return decision


if __name__ == "__main__":
    print(execute())
