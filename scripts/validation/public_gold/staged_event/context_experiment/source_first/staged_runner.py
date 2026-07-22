"""Run the frozen two-stage Luna nested-event construction experiment."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

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
from scripts.validation.public_gold.staged_event.context_experiment.source_first.anchors import (
    AnchorResolutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.inventory import (
    EventInventoryOutput,
    ResolvedInventoryEvent,
    compare_exposed_inventory,
    resolve_inventory,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking import (
    EventLinkingOutput,
    assemble_graph,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.validation import (
    SourceFirstValidationError,
    compare_exposed_nested_graph,
    validate_structure,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.public_gold.staged_event.context_experiment.source_first.validation import (
        ExposedGraphComparison,
    )

REPO = Path(__file__).resolve().parents[6]
SOURCE = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
INVENTORY_PROMPT = REPO / (
    "docs/validation/prompts/2026-07-22-staged-luna-event-inventory-v2.md"
)
LINKING_PROMPT = REPO / (
    "docs/validation/prompts/2026-07-22-staged-luna-event-linking-v2.md"
)
PREREGISTRATION = REPO / (
    "docs/validation/preregistrations/"
    "2026-07-22-staged-luna-event-construction-v2.json"
)
RESULT = REPO / (
    "docs/validation/results/2026-07-22-staged-luna-event-construction-v2.json"
)
RECEIPT = REPO / (
    "docs/validation/receipts/2026-07-22-staged-luna-event-construction-v2.json"
)
RAW_OUTPUT = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-luna-event-construction-v2-raw.json"
)
SOURCE_SHA256 = "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
PACKET_ID = "staged-primary-nested-v2"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
SCOPE_START = 0
SCOPE_END = 222
FINDING_START = 0
FINDING_END = 75
MAX_OUTPUT_TOKENS = 16000
MAX_TOTAL_TOKENS = 24000
MAX_COST_USD = 0.25
MAX_LATENCY_SECONDS = 900.0

SPECIALIST_HINTS = (
    {
        "generator": "DeepEventMine-GE11",
        "event_type": "Negative_regulation",
        "trigger": "Decrease",
        "arguments": ("Theme:c-Myc",),
        "provenance": "DeepEventMine:e1c56013:GE11:PMID-16428936:E1",
    },
)


class StagedExperimentStateError(RuntimeError):
    """Frozen staged experiment state is missing or changed."""


@dataclass(frozen=True, slots=True)
class StageCall:
    stage: str
    provider_input: str
    output_model: type[BaseModel]
    description: str


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def provider_format(model: type[BaseModel], *, description: str) -> dict[str, object]:
    value = cast("dict[str, object]", type_to_text_format_param(model))
    value["description"] = description
    return value


def source_packet(source: str) -> dict[str, object]:
    return {
        "packet_id": PACKET_ID,
        "permitted_context": source[SCOPE_START:SCOPE_END],
        "highlighted_finding": source[FINDING_START:FINDING_END],
        "optional_specialist_hints": list(SPECIALIST_HINTS),
    }


def inventory_input(source: str) -> str:
    return _input(INVENTORY_PROMPT, source_packet(source))


def linking_input(
    source: str, inventory: tuple[ResolvedInventoryEvent, ...]
) -> str:
    frozen_inventory = [
        {
            "temporary_event_id": item.temporary_event_id,
            "event_type": item.event_type.value,
            "exact_trigger": item.trigger.exact_text,
            "exact_evidence": item.trigger.exact_evidence,
            "resolved_trigger": {
                "start": item.trigger.start,
                "end": item.trigger.end,
            },
            "structural_position": item.structural_position,
            "explanation": item.explanation,
        }
        for item in inventory
    ]
    return _input(
        LINKING_PROMPT,
        {**source_packet(source), "frozen_event_inventory": frozen_inventory},
    )


def _input(prompt: Path, packet: dict[str, object]) -> str:
    return (
        prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN SOURCE PACKET ---\n"
        + json.dumps(packet, indent=2, sort_keys=True)
        + "\n--- END FROZEN SOURCE PACKET ---\n"
    )


def _call(
    *,
    api_key: str,
    call: StageCall,
    preregistration_sha256: str,
) -> BackgroundProviderExecution[BaseModel]:
    return execute_background_provider_call(
        api_key=api_key,
        output_model=call.output_model,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        request=ProviderRequest(
            provider_input=call.provider_input,
            provider_format=provider_format(
                call.output_model, description=call.description
            ),
            provider_model_id=MODEL,
            reasoning_effort=REASONING_EFFORT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            max_total_tokens=MAX_TOTAL_TOKENS,
            max_cost_usd=MAX_COST_USD,
            max_latency_seconds=MAX_LATENCY_SECONDS,
            pricing={
                "input": 0.000001,
                "cached_input": 0.0000001,
                "output": 0.000006,
            },
            metadata={
                "artana_experiment": "staged-luna-event-construction-v2",
                "artana_preregistration_sha256": preregistration_sha256,
                "artana_source_sha256": SOURCE_SHA256,
                "artana_stage": call.stage,
            },
        ),
    )


def execute() -> str:
    """Execute Stage 1 once and Stage 2 only after the frozen inventory gate."""

    _require_unused_outputs()
    frozen = _load_and_verify_preregistration()
    source = SOURCE.read_text(encoding="utf-8")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise StagedExperimentStateError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
    receipts: list[dict[str, object]] = []
    raw_outputs: list[dict[str, object]] = []
    try:
        inventory_execution = _call(
            api_key=api_key,
            call=StageCall(
                stage="EVENT_INVENTORY",
                provider_input=inventory_input(source),
                output_model=EventInventoryOutput,
                description="Source-grounded event inventory without participant linking.",
            ),
            preregistration_sha256=preregistration_sha256,
        )
    except ProviderExecutionError as exc:
        return _stop_invalid(exc, receipts, raw_outputs)
    receipts.append(inventory_execution.receipt)
    inventory_output = EventInventoryOutput.model_validate(
        inventory_execution.extraction.model_dump(mode="json")
    )
    raw_outputs.append(
        {"stage": "EVENT_INVENTORY", "output": inventory_output.model_dump(mode="json")}
    )
    try:
        inventory = resolve_inventory(
            inventory_output,
            source=source,
            scope_start=SCOPE_START,
            scope_end=SCOPE_END,
        )
    except AnchorResolutionError as exc:
        return _stop_scientific_inventory(str(exc), receipts, raw_outputs)
    inventory_gate = compare_exposed_inventory(inventory)
    if not inventory_gate.passed:
        return _stop_scientific_inventory(
            "event inventory differs from exposed public gold",
            receipts,
            raw_outputs,
            inventory_gate=asdict(inventory_gate),
        )
    linking_provider_input = linking_input(source, inventory)
    expected_prefix = frozen.get("linking_input_prefix_sha256")
    if expected_prefix != hashlib.sha256(LINKING_PROMPT.read_bytes()).hexdigest():
        raise StagedExperimentStateError("frozen linking input prefix changed")
    comparison: ExposedGraphComparison | None
    structural_error: str | None
    try:
        linking_execution = _call(
            api_key=api_key,
            call=StageCall(
                stage="PARTICIPANT_EVENT_LINKING",
                provider_input=linking_provider_input,
                output_model=EventLinkingOutput,
                description="Link participants and frozen event nodes into one typed graph.",
            ),
            preregistration_sha256=preregistration_sha256,
        )
    except ProviderExecutionError as exc:
        return _stop_invalid(exc, receipts, raw_outputs)
    receipts.append(linking_execution.receipt)
    linking_output = EventLinkingOutput.model_validate(
        linking_execution.extraction.model_dump(mode="json")
    )
    raw_outputs.append(
        {
            "stage": "PARTICIPANT_EVENT_LINKING",
            "provider_input_sha256": hashlib.sha256(
                linking_provider_input.encode()
            ).hexdigest(),
            "output": linking_output.model_dump(mode="json"),
        }
    )
    try:
        graph = assemble_graph(
            linking_output,
            inventory=inventory,
            source=source,
            scope_start=SCOPE_START,
            scope_end=SCOPE_END,
        )
        validate_structure(
            graph, source=source, scope_start=SCOPE_START, scope_end=SCOPE_END
        )
    except (AnchorResolutionError, SourceFirstValidationError, ValueError) as exc:
        comparison = None
        structural_error = str(exc)
    else:
        comparison = compare_exposed_nested_graph(graph)
        structural_error = None
    decision = (
        "ADVANCE_STAGED_EVENT_CONSTRUCTION"
        if comparison is not None and comparison.exact
        else "STOP_EVENT_LINKING_SCIENTIFIC_FAILURE"
    )
    _write(RECEIPT, {"receipts": receipts})
    _write(RAW_OUTPUT, {"outputs": raw_outputs})
    _write(
        RESULT,
        {
            "decision": decision,
            "inventory_gate": asdict(inventory_gate),
            "structural_error": structural_error,
            "graph_comparison": asdict(comparison) if comparison else None,
            "provider_call_count": len(receipts),
            "trusted_promotion": False,
        },
    )
    return decision


def _require_unused_outputs() -> None:
    if any(path.exists() for path in (RESULT, RECEIPT, RAW_OUTPUT)):
        raise StagedExperimentStateError("staged V2 output already exists")


def _load_and_verify_preregistration() -> dict[str, object]:
    loaded: object = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise StagedExperimentStateError("malformed preregistration")
    preregistration: dict[str, object] = loaded
    frozen = preregistration.get("frozen_state")
    if not isinstance(frozen, dict):
        raise StagedExperimentStateError("malformed frozen state")
    source = SOURCE.read_text(encoding="utf-8")
    checks = {
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "permitted_scope_sha256": hashlib.sha256(
            source[SCOPE_START:SCOPE_END].encode()
        ).hexdigest(),
        "highlighted_finding_sha256": hashlib.sha256(
            source[FINDING_START:FINDING_END].encode()
        ).hexdigest(),
        "inventory_prompt_sha256": hashlib.sha256(INVENTORY_PROMPT.read_bytes()).hexdigest(),
        "linking_prompt_sha256": hashlib.sha256(LINKING_PROMPT.read_bytes()).hexdigest(),
        "inventory_schema_sha256": canonical_sha256(EventInventoryOutput.model_json_schema()),
        "linking_schema_sha256": canonical_sha256(EventLinkingOutput.model_json_schema()),
        "inventory_provider_format_sha256": canonical_sha256(
            provider_format(
                EventInventoryOutput,
                description="Source-grounded event inventory without participant linking.",
            )
        ),
        "linking_provider_format_sha256": canonical_sha256(
            provider_format(
                EventLinkingOutput,
                description="Link participants and frozen event nodes into one typed graph.",
            )
        ),
        "specialist_hint_sha256": canonical_sha256(SPECIALIST_HINTS),
        "inventory_provider_input_sha256": hashlib.sha256(
            inventory_input(source).encode()
        ).hexdigest(),
        "linking_input_prefix_sha256": hashlib.sha256(LINKING_PROMPT.read_bytes()).hexdigest(),
    }
    for name, actual in checks.items():
        if frozen.get(name) != actual:
            raise StagedExperimentStateError(f"frozen {name} changed")
    code_hashes = frozen.get("code_sha256")
    if not isinstance(code_hashes, dict):
        raise StagedExperimentStateError("frozen code hashes are absent")
    for relative, expected in code_hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise StagedExperimentStateError("malformed frozen code hash")
        if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != expected:
            raise StagedExperimentStateError(f"frozen code changed: {relative}")
    return frozen


def _stop_invalid(
    error: ProviderExecutionError,
    receipts: list[dict[str, object]],
    raw_outputs: list[dict[str, object]],
) -> str:
    _write(RECEIPT, {"receipts": receipts, "rejected": error.diagnostics})
    _write(RAW_OUTPUT, {"outputs": raw_outputs})
    _write(
        RESULT,
        {
            "decision": "INVALID_PROVIDER_EXECUTION",
            "failure_stage": error.stage,
            "root_cause": error.root_cause,
            "diagnostics": error.diagnostics,
            "provider_call_count": len(receipts) + 1,
            "trusted_promotion": False,
        },
    )
    return "INVALID_PROVIDER_EXECUTION"


def _stop_scientific_inventory(
    root_cause: str,
    receipts: list[dict[str, object]],
    raw_outputs: list[dict[str, object]],
    *,
    inventory_gate: dict[str, object] | None = None,
) -> str:
    decision = "STOP_EVENT_INVENTORY_SCIENTIFIC_FAILURE"
    _write(RECEIPT, {"receipts": receipts})
    _write(RAW_OUTPUT, {"outputs": raw_outputs})
    _write(
        RESULT,
        {
            "decision": decision,
            "root_cause": root_cause,
            "inventory_gate": inventory_gate,
            "provider_call_count": len(receipts),
            "trusted_promotion": False,
        },
    )
    return decision


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    print(execute())
