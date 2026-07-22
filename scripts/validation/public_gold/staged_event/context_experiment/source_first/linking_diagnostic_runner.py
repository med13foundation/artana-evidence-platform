"""Run one bounded Stage 2-only linking diagnostic and blinded review."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    BackgroundExecutionRuntime,
    BackgroundProviderExecution,
    execute_background_provider_call,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.anchors import (
    AnchorResolutionError,
    resolve_anchor,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    CustodyPersistenceError,
    StageCustodyInput,
    StageCustodyPaths,
    persist_stage_custody,
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.diagnostic_replay import (
    DiagnosticInventoryReplay,
    load_diagnostic_inventory,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking import (
    EventLinkingOutput,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking_review import (
    SourceOnlyLinkingReview,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.staged_runner import (
    ProcessingContext,
    canonical_sha256,
    process_linking_execution,
    provider_format,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.source_first.validation import (
        ExposedGraphComparison,
    )

REPO = Path(__file__).resolve().parents[6]
SOURCE = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
    "original-data/devel/PMID-16428936.txt"
)
LINKING_PROMPT = REPO / (
    "docs/validation/prompts/2026-07-22-staged-linking-diagnostic-v1.md"
)
REVIEW_PROMPT = REPO / (
    "docs/validation/prompts/2026-07-22-staged-linking-source-review-v1.md"
)
PREREGISTRATION = REPO / (
    "docs/validation/preregistrations/2026-07-22-staged-linking-diagnostic-v1.json"
)
RESULT = REPO / ("docs/validation/results/2026-07-22-staged-linking-diagnostic-v1.json")
LINKING_ATTEMPT = REPO / (
    "docs/validation/receipts/2026-07-22-staged-linking-v1-attempt.json"
)
REVIEW_ATTEMPT = REPO / (
    "docs/validation/receipts/2026-07-22-staged-linking-v1-review-attempt.json"
)
LINKING_CUSTODY = StageCustodyPaths(
    bundle=REPO / "docs/validation/receipts/2026-07-22-staged-linking-v1-custody.json",
    receipt=REPO / "docs/validation/receipts/2026-07-22-staged-linking-v1.json",
    raw_output=REPO / "docs/validation/results/2026-07-22-staged-linking-v1-raw.json",
)
REVIEW_CUSTODY = StageCustodyPaths(
    bundle=REPO
    / "docs/validation/receipts/2026-07-22-staged-linking-v1-review-custody.json",
    receipt=REPO / "docs/validation/receipts/2026-07-22-staged-linking-v1-review.json",
    raw_output=REPO
    / "docs/validation/results/2026-07-22-staged-linking-v1-review-raw.json",
)
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
SOURCE_SHA256 = "00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab"
SCOPE_START = 0
SCOPE_END = 222
FINDING_START = 0
FINDING_END = 75
MAX_OUTPUT_TOKENS = 32000
MAX_TOTAL_TOKENS = 40000
MAX_LATENCY_SECONDS = 900.0
MAX_COST_USD = 0.35


class LinkingDiagnosticStateError(RuntimeError):
    """The frozen Stage 2 diagnostic cannot execute safely."""


@dataclass(frozen=True, slots=True)
class DiagnosticRuntime:
    linking_call: Callable[
        [str, str, str], BackgroundProviderExecution[EventLinkingOutput]
    ]
    review_call: Callable[
        [str, str, str], BackgroundProviderExecution[SourceOnlyLinkingReview]
    ]
    after_linking_persist: Callable[[], None]
    after_review_persist: Callable[[], None]


def linking_input(source: str, replay: DiagnosticInventoryReplay) -> str:
    inventory = [
        {
            "event_id": item.temporary_event_id,
            "event_type": item.event_type.value,
            "exact_trigger": item.trigger.exact_text,
            "exact_evidence": item.trigger.exact_evidence,
            "structural_position": item.structural_position,
            "explanation": item.explanation,
        }
        for item in replay.inventory
    ]
    return _prompt_input(
        LINKING_PROMPT,
        {
            "packet_id": "staged-linking-diagnostic-v1",
            "permitted_context": source[SCOPE_START:SCOPE_END],
            "highlighted_finding": source[FINDING_START:FINDING_END],
            "frozen_event_inventory": inventory,
        },
    )


def review_input(source: str, output: EventLinkingOutput) -> str:
    return _prompt_input(
        REVIEW_PROMPT,
        {
            "packet_id": "staged-linking-diagnostic-v1-review",
            "permitted_context": source[SCOPE_START:SCOPE_END],
            "highlighted_finding": source[FINDING_START:FINDING_END],
            "candidate_graph": output.model_dump(mode="json"),
        },
    )


def _prompt_input(prompt: Path, packet: dict[str, object]) -> str:
    return (
        prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN DIAGNOSTIC PACKET ---\n"
        + json.dumps(packet, indent=2, sort_keys=True)
        + "\n--- END FROZEN DIAGNOSTIC PACKET ---\n"
    )


def _request(
    *,
    stage: str,
    provider_input_value: str,
    response_format: dict[str, object],
    preregistration_sha256: str,
) -> ProviderRequest:
    return ProviderRequest(
        provider_input=provider_input_value,
        provider_format=response_format,
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
            "artana_experiment": "staged-linking-diagnostic-v1",
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_source_sha256": SOURCE_SHA256,
            "artana_stage": stage,
        },
    )


def _linking_provider_call(
    api_key: str, provider_input_value: str, preregistration_sha256: str
) -> BackgroundProviderExecution[EventLinkingOutput]:
    return execute_background_provider_call(
        api_key=api_key,
        output_model=EventLinkingOutput,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        request=_request(
            stage="PARTICIPANT_EVENT_LINKING",
            provider_input_value=provider_input_value,
            response_format=provider_format(
                EventLinkingOutput,
                description="Link participants and immutable event nodes into one typed graph.",
            ),
            preregistration_sha256=preregistration_sha256,
        ),
        runtime=BackgroundExecutionRuntime(
            on_acknowledged=lambda response_id: acknowledge_attempt(
                LINKING_ATTEMPT, response_id=response_id
            )
        ),
    )


def _review_provider_call(
    api_key: str, provider_input_value: str, preregistration_sha256: str
) -> BackgroundProviderExecution[SourceOnlyLinkingReview]:
    return execute_background_provider_call(
        api_key=api_key,
        output_model=SourceOnlyLinkingReview,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        request=_request(
            stage="SOURCE_ONLY_LINKING_REVIEW",
            provider_input_value=provider_input_value,
            response_format=provider_format(
                SourceOnlyLinkingReview,
                description="Blinded categorical source-only review of one typed graph.",
            ),
            preregistration_sha256=preregistration_sha256,
        ),
        runtime=BackgroundExecutionRuntime(
            on_acknowledged=lambda response_id: acknowledge_attempt(
                REVIEW_ATTEMPT, response_id=response_id
            )
        ),
    )


def execute(runtime: DiagnosticRuntime | None = None) -> str:
    _require_unused_outputs()
    replay = load_diagnostic_inventory()
    frozen = _load_and_verify_preregistration(replay)
    source = SOURCE.read_text(encoding="utf-8")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise LinkingDiagnosticStateError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
    active = runtime or DiagnosticRuntime(
        _linking_provider_call,
        _review_provider_call,
        lambda: None,
        lambda: None,
    )
    linking_provider_input = linking_input(source, replay)
    reserve_attempt(
        LINKING_ATTEMPT,
        stage="PARTICIPANT_EVENT_LINKING",
        provider_input=linking_provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    try:
        linking_execution = active.linking_call(
            api_key, linking_provider_input, preregistration_sha256
        )
    except ProviderExecutionError as exc:
        return _stop_invalid(exc, completed_calls=0)
    try:
        linking_output, comparison, _ = process_linking_execution(
            linking_execution,
            provider_input_value=linking_provider_input,
            inventory=replay.inventory,
            context=ProcessingContext(
                source=source,
                custody_paths=LINKING_CUSTODY,
                after_persist=active.after_linking_persist,
            ),
        )
    except (AnchorResolutionError, ValueError) as exc:
        return _stop_scientific(
            structural_error=str(exc),
            comparison=None,
            review=None,
            provider_calls=1,
        )
    review_provider_input = review_input(source, linking_output)
    if (
        frozen.get("review_prompt_sha256")
        != hashlib.sha256(REVIEW_PROMPT.read_bytes()).hexdigest()
    ):
        raise LinkingDiagnosticStateError("frozen review prompt changed")
    reserve_attempt(
        REVIEW_ATTEMPT,
        stage="SOURCE_ONLY_LINKING_REVIEW",
        provider_input=review_provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    try:
        review_execution = active.review_call(
            api_key, review_provider_input, preregistration_sha256
        )
    except ProviderExecutionError as exc:
        return _stop_invalid(exc, completed_calls=1)
    try:
        review = _persist_and_validate_review(
            review_execution,
            provider_input_value=review_provider_input,
            source=source,
            after_persist=active.after_review_persist,
        )
    except AnchorResolutionError as exc:
        return _stop_scientific(
            structural_error=f"source-only review evidence: {exc}",
            comparison=comparison,
            review=None,
            provider_calls=_consumed_calls(),
        )
    except CustodyPersistenceError as exc:
        return _stop_invalid_state(
            stage="SOURCE_ONLY_REVIEW_CUSTODY",
            root_cause=str(exc),
        )
    decision = (
        "ADVANCE_STAGED_LINKING_DIAGNOSTIC"
        if comparison.exact and review.verdict not in {"CONTRADICTED", "INCOMPLETE"}
        else "STOP_EVENT_LINKING_SCIENTIFIC_FAILURE"
    )
    try:
        provider_cost_usd = _cost(linking_execution.receipt) + _cost(
            review_execution.receipt
        )
    except LinkingDiagnosticStateError as exc:
        return _stop_invalid_state(stage="ACCOUNTING", root_cause=str(exc))
    _write_result(
        {
            "decision": decision,
            "stage1_status": replay.evidence["status"],
            "graph_comparison": asdict(comparison),
            "source_only_review": review.model_dump(mode="json"),
            "provider_calls": _consumed_calls(),
            "provider_cost_usd": provider_cost_usd,
            "qualification_credit": False,
            "trusted_promotion": False,
            "graph_writes": 0,
        }
    )
    return decision


def _persist_and_validate_review(
    execution: BackgroundProviderExecution[SourceOnlyLinkingReview],
    *,
    provider_input_value: str,
    source: str,
    after_persist: Callable[[], None],
) -> SourceOnlyLinkingReview:
    output = execution.extraction
    persist_stage_custody(
        custody_input=StageCustodyInput(
            paths=REVIEW_CUSTODY,
            stage="SOURCE_ONLY_LINKING_REVIEW",
            provider_input=provider_input_value,
            schema_sha256=canonical_sha256(SourceOnlyLinkingReview.model_json_schema()),
        ),
        output=output,
        canonical_payload=execution.canonical_payload,
        receipt=execution.receipt,
    )
    after_persist()
    resolve_anchor(
        source=source,
        scope_start=SCOPE_START,
        scope_end=SCOPE_END,
        exact_text=output.exact_evidence,
        exact_evidence=output.exact_evidence,
    )
    return output


def _load_and_verify_preregistration(
    replay: DiagnosticInventoryReplay,
) -> dict[str, object]:
    loaded: object = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("frozen_state"), dict):
        raise LinkingDiagnosticStateError("malformed preregistration")
    frozen = cast("dict[str, object]", loaded["frozen_state"])
    source = SOURCE.read_text(encoding="utf-8")
    checks = {
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "diagnostic_inventory_sha256": canonical_sha256(replay.evidence),
        "linking_prompt_sha256": hashlib.sha256(
            LINKING_PROMPT.read_bytes()
        ).hexdigest(),
        "review_prompt_sha256": hashlib.sha256(REVIEW_PROMPT.read_bytes()).hexdigest(),
        "linking_schema_sha256": canonical_sha256(
            EventLinkingOutput.model_json_schema()
        ),
        "review_schema_sha256": canonical_sha256(
            SourceOnlyLinkingReview.model_json_schema()
        ),
        "linking_provider_input_sha256": hashlib.sha256(
            linking_input(source, replay).encode()
        ).hexdigest(),
        "linking_provider_format_sha256": canonical_sha256(
            provider_format(
                EventLinkingOutput,
                description="Link participants and immutable event nodes into one typed graph.",
            )
        ),
        "review_provider_format_sha256": canonical_sha256(
            provider_format(
                SourceOnlyLinkingReview,
                description="Blinded categorical source-only review of one typed graph.",
            )
        ),
    }
    for key, value in checks.items():
        if frozen.get(key) != value:
            raise LinkingDiagnosticStateError(f"frozen {key} changed")
    expected_settings = {
        "model": "openai:gpt-5.6-luna",
        "provider_model_id": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "budgets": {
            "global_max_cost_usd": 1.0,
            "global_max_creation_calls": 3,
            "per_call_max_cost_usd": MAX_COST_USD,
            "per_call_max_latency_seconds": MAX_LATENCY_SECONDS,
            "per_call_max_output_tokens": MAX_OUTPUT_TOKENS,
            "per_call_max_total_tokens": MAX_TOTAL_TOKENS,
            "retries": 0,
        },
    }
    for key, expected in expected_settings.items():
        if frozen.get(key) != expected:
            raise LinkingDiagnosticStateError(f"frozen {key} changed")
    rules = loaded.get("rules")
    if rules != {
        "all_outputs_review_only": True,
        "fallbacks": 0,
        "graph_writes": 0,
        "promotion": False,
        "reviewer_may_override_gold_comparison": False,
        "stage1_provider_calls": 0,
        "untouched_sources": False,
    }:
        raise LinkingDiagnosticStateError("frozen safety rules changed")
    code_hashes = frozen.get("code_sha256")
    if not isinstance(code_hashes, dict):
        raise LinkingDiagnosticStateError("frozen code hashes are absent")
    for relative, expected in code_hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise LinkingDiagnosticStateError("malformed code hash")
        if hashlib.sha256((REPO / relative).read_bytes()).hexdigest() != expected:
            raise LinkingDiagnosticStateError(f"frozen code changed: {relative}")
    return frozen


def _require_unused_outputs() -> None:
    paths = (
        RESULT,
        LINKING_ATTEMPT,
        REVIEW_ATTEMPT,
        LINKING_CUSTODY.bundle,
        LINKING_CUSTODY.receipt,
        LINKING_CUSTODY.raw_output,
        REVIEW_CUSTODY.bundle,
        REVIEW_CUSTODY.receipt,
        REVIEW_CUSTODY.raw_output,
    )
    if any(path.exists() for path in paths):
        raise LinkingDiagnosticStateError("Stage 2 Diagnostic V1 already started")


def _stop_invalid(error: ProviderExecutionError, *, completed_calls: int) -> str:
    _write_result(
        {
            "decision": "INVALID_PROVIDER_EXECUTION",
            "failure_stage": error.stage,
            "root_cause": error.root_cause,
            "diagnostics": error.diagnostics,
            "provider_calls": max(completed_calls, _consumed_calls()),
            "qualification_credit": False,
            "trusted_promotion": False,
        }
    )
    return "INVALID_PROVIDER_EXECUTION"


def _stop_invalid_state(*, stage: str, root_cause: str) -> str:
    _write_result(
        {
            "decision": "INVALID_PROVIDER_EXECUTION",
            "failure_stage": stage,
            "root_cause": root_cause,
            "provider_calls": _consumed_calls(),
            "qualification_credit": False,
            "trusted_promotion": False,
        }
    )
    return "INVALID_PROVIDER_EXECUTION"


def _consumed_calls() -> int:
    return sum(
        _attempt_has_response_id(path) for path in (LINKING_ATTEMPT, REVIEW_ATTEMPT)
    )


def _attempt_has_response_id(path: Path) -> bool:
    if not path.exists():
        return False
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    return isinstance(loaded, dict) and isinstance(loaded.get("response_id"), str)


def _stop_scientific(
    *,
    structural_error: str | None,
    comparison: ExposedGraphComparison | None,
    review: SourceOnlyLinkingReview | None,
    provider_calls: int,
) -> str:
    decision = "STOP_EVENT_LINKING_SCIENTIFIC_FAILURE"
    _write_result(
        {
            "decision": decision,
            "structural_error": structural_error,
            "graph_comparison": asdict(comparison) if comparison else None,
            "source_only_review": review.model_dump(mode="json") if review else None,
            "provider_calls": provider_calls,
            "qualification_credit": False,
            "trusted_promotion": False,
        }
    )
    return decision


def _cost(receipt: dict[str, object]) -> float:
    usage = receipt.get("usage")
    value = usage.get("cost_usd") if isinstance(usage, dict) else None
    if not isinstance(value, int | float):
        raise LinkingDiagnosticStateError("verified receipt cost is absent")
    return float(value)


def _write_result(value: object) -> None:
    write_json_atomic(RESULT, value)


if __name__ == "__main__":
    print(execute())
