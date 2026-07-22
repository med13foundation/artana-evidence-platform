"""Execute one preregistered dual-role adjudication on the exposed panel."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, cast

from pydantic import BaseModel

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
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.contracts import (
    BenchmarkRoleReview,
    DualRoleTieBreakReview,
    SourceRoleReview,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.evaluation import (
    RoleEvaluationError,
    evaluate_reviews,
    validate_tiebreak,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.panel import (
    PanelCase,
    build_execution_panel,
    build_panel,
    execution_panel_json,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.policy import (
    policy_summary_for_agent,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyInput,
    StageCustodyPaths,
    persist_stage_custody,
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.staged_runner import (
    canonical_sha256,
    provider_format,
)

REPO = Path(__file__).resolve().parents[6]
PANEL = (
    REPO / "docs/validation/fixtures/2026-07-22-role-alignment-exposed-panel-v2.json"
)
SOURCE_PROMPT = (
    REPO / "docs/validation/prompts/2026-07-22-role-alignment-source-review-v1.md"
)
BENCHMARK_PROMPT = (
    REPO / "docs/validation/prompts/2026-07-22-role-alignment-benchmark-review-v1.md"
)
TIEBREAK_PROMPT = (
    REPO / "docs/validation/prompts/2026-07-22-role-alignment-tiebreak-v1.md"
)
PREREGISTRATION = (
    REPO / "docs/validation/preregistrations/2026-07-22-role-alignment-v2.json"
)
RESULT = REPO / "docs/validation/results/2026-07-22-role-alignment-v2.json"
INVALID_V1_RESULT = REPO / "docs/validation/results/2026-07-22-role-alignment-v1.json"
RESEARCH = REPO / "docs/validation/research/2026-07-22-bionlp-cg-role-policy.md"
PRIOR_RESULT = (
    REPO / "docs/validation/results/2026-07-22-staged-linking-diagnostic-v1.json"
)
PRIOR_ADDENDUM = (
    REPO / "docs/validation/results/2026-07-22-staged-linking-v1-role-addendum.json"
)
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 16000
MAX_TOTAL_TOKENS = 20000
MAX_LATENCY_SECONDS = 900.0
MAX_COST_USD = 0.25
GLOBAL_MAX_CALLS = 4
GLOBAL_MAX_COST_USD = 1.0
PRIOR_CONSUMED_CALLS = 1
PRIOR_CONSUMED_COST_USD = 0.427536

_OutputT = TypeVar("_OutputT", bound=BaseModel)


class RoleAlignmentStateError(RuntimeError):
    """The frozen role-alignment diagnostic cannot execute safely."""


@dataclass(frozen=True, slots=True)
class StagePaths:
    attempt: Path
    custody: StageCustodyPaths


@dataclass(frozen=True, slots=True)
class ProviderStage:
    stage: str
    paths: StagePaths
    description: str


@dataclass(frozen=True, slots=True)
class RoleAlignmentRuntime:
    source_call: Callable[
        [str, str, str], BackgroundProviderExecution[SourceRoleReview]
    ]
    benchmark_call: Callable[
        [str, str, str], BackgroundProviderExecution[BenchmarkRoleReview]
    ]
    tiebreak_call: Callable[
        [str, str, str], BackgroundProviderExecution[DualRoleTieBreakReview]
    ]
    after_persist: Callable[[], None]


SOURCE_PATHS = StagePaths(
    attempt=REPO
    / "docs/validation/receipts/2026-07-22-role-alignment-v2-source-attempt.json",
    custody=StageCustodyPaths(
        bundle=REPO
        / "docs/validation/receipts/2026-07-22-role-alignment-v2-source-custody.json",
        receipt=REPO
        / "docs/validation/receipts/2026-07-22-role-alignment-v2-source.json",
        raw_output=REPO
        / "docs/validation/results/2026-07-22-role-alignment-v2-source-raw.json",
    ),
)
BENCHMARK_PATHS = StagePaths(
    attempt=REPO
    / "docs/validation/receipts/2026-07-22-role-alignment-v2-benchmark-attempt.json",
    custody=StageCustodyPaths(
        bundle=REPO
        / "docs/validation/receipts/2026-07-22-role-alignment-v2-benchmark-custody.json",
        receipt=REPO
        / "docs/validation/receipts/2026-07-22-role-alignment-v2-benchmark.json",
        raw_output=REPO
        / "docs/validation/results/2026-07-22-role-alignment-v2-benchmark-raw.json",
    ),
)
TIEBREAK_PATHS = StagePaths(
    attempt=REPO
    / "docs/validation/receipts/2026-07-22-role-alignment-v2-tiebreak-attempt.json",
    custody=StageCustodyPaths(
        bundle=REPO
        / "docs/validation/receipts/2026-07-22-role-alignment-v2-tiebreak-custody.json",
        receipt=REPO
        / "docs/validation/receipts/2026-07-22-role-alignment-v2-tiebreak.json",
        raw_output=REPO
        / "docs/validation/results/2026-07-22-role-alignment-v2-tiebreak-raw.json",
    ),
)


def agent_cases(cases: tuple[PanelCase, ...]) -> list[dict[str, object]]:
    return [
        {
            "case_id": case.case_id,
            "source_scope": case.exact_scope,
            "event": {"event_type": case.event_type, "trigger_text": case.trigger_text},
            "participant": {
                "entity_type": case.participant_type,
                "exact_text": case.participant_text,
            },
        }
        for case in cases
    ]


def source_input(cases: tuple[PanelCase, ...]) -> str:
    return _prompt_packet(SOURCE_PROMPT, {"cases": agent_cases(cases)})


def benchmark_input(cases: tuple[PanelCase, ...]) -> str:
    return _prompt_packet(
        BENCHMARK_PROMPT,
        {"policy": policy_summary_for_agent(), "cases": agent_cases(cases)},
    )


def tiebreak_input(cases: tuple[PanelCase, ...]) -> str:
    return _prompt_packet(
        TIEBREAK_PROMPT,
        {"policy": policy_summary_for_agent(), "cases": agent_cases(cases)},
    )


def _prompt_packet(prompt: Path, packet: dict[str, object]) -> str:
    return (
        prompt.read_text(encoding="utf-8")
        + "\n\n--- FROZEN ROLE PACKET ---\n"
        + json.dumps(packet, indent=2, sort_keys=True)
        + "\n--- END FROZEN ROLE PACKET ---\n"
    )


def _provider_call(
    *,
    api_key: str,
    provider_input_value: str,
    preregistration_sha256: str,
    output_model: type[_OutputT],
    stage: ProviderStage,
) -> BackgroundProviderExecution[_OutputT]:
    request = ProviderRequest(
        provider_input=provider_input_value,
        provider_format=provider_format(output_model, description=stage.description),
        provider_model_id=MODEL,
        reasoning_effort=REASONING_EFFORT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        max_total_tokens=MAX_TOTAL_TOKENS,
        max_cost_usd=MAX_COST_USD,
        max_latency_seconds=MAX_LATENCY_SECONDS,
        pricing={"input": 0.000001, "cached_input": 0.0000001, "output": 0.000006},
        metadata={
            "artana_experiment": "role-alignment-v2",
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_stage": stage.stage,
        },
    )
    return execute_background_provider_call(
        api_key=api_key,
        output_model=output_model,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        request=request,
        runtime=BackgroundExecutionRuntime(
            on_acknowledged=lambda response_id: acknowledge_attempt(
                stage.paths.attempt, response_id=response_id
            )
        ),
    )


def _live_runtime() -> RoleAlignmentRuntime:
    return RoleAlignmentRuntime(
        source_call=lambda key, value, prereg: _provider_call(
            api_key=key,
            provider_input_value=value,
            preregistration_sha256=prereg,
            output_model=SourceRoleReview,
            stage=ProviderStage(
                "SOURCE_ROLE_REVIEW",
                SOURCE_PATHS,
                "Blinded categorical source-semantic role review.",
            ),
        ),
        benchmark_call=lambda key, value, prereg: _provider_call(
            api_key=key,
            provider_input_value=value,
            preregistration_sha256=prereg,
            output_model=BenchmarkRoleReview,
            stage=ProviderStage(
                "BENCHMARK_ROLE_REVIEW",
                BENCHMARK_PATHS,
                "Blinded categorical BioNLP CG benchmark-role review.",
            ),
        ),
        tiebreak_call=lambda key, value, prereg: _provider_call(
            api_key=key,
            provider_input_value=value,
            preregistration_sha256=prereg,
            output_model=DualRoleTieBreakReview,
            stage=ProviderStage(
                "DUAL_ROLE_TIEBREAK",
                TIEBREAK_PATHS,
                "Blinded dual-role tie-break for disputed cases only.",
            ),
        ),
        after_persist=lambda: None,
    )


def execute(runtime: RoleAlignmentRuntime | None = None) -> str:
    _require_unused_outputs()
    cases = build_execution_panel()
    corpus_cases = build_panel()
    _verify_panel_file()
    _verify_preregistration(cases)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RoleAlignmentStateError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(PREREGISTRATION.read_bytes()).hexdigest()
    active = runtime or _live_runtime()
    executions: list[BackgroundProviderExecution[BaseModel]] = []

    if not _prospective_budget_allows(executions):
        return _operational_blocker("global budget prevents source review", executions)
    source_value = source_input(cases)
    reserve_attempt(
        SOURCE_PATHS.attempt,
        stage="SOURCE_ROLE_REVIEW",
        provider_input=source_value,
        preregistration_sha256=preregistration_sha256,
    )
    try:
        source_execution = active.source_call(
            api_key, source_value, preregistration_sha256
        )
    except ProviderExecutionError as exc:
        return _invalid(exc, executions=executions, failed_paths=SOURCE_PATHS)
    _persist(
        source_execution,
        source_value,
        SourceRoleReview,
        SOURCE_PATHS,
        active.after_persist,
    )
    executions.append(cast("BackgroundProviderExecution[BaseModel]", source_execution))

    if not _prospective_budget_allows(executions):
        return _operational_blocker(
            "global budget prevents benchmark review", executions
        )
    benchmark_value = benchmark_input(cases)
    reserve_attempt(
        BENCHMARK_PATHS.attempt,
        stage="BENCHMARK_ROLE_REVIEW",
        provider_input=benchmark_value,
        preregistration_sha256=preregistration_sha256,
    )
    try:
        benchmark_execution = active.benchmark_call(
            api_key, benchmark_value, preregistration_sha256
        )
    except ProviderExecutionError as exc:
        return _invalid(exc, executions=executions, failed_paths=BENCHMARK_PATHS)
    _persist(
        benchmark_execution,
        benchmark_value,
        BenchmarkRoleReview,
        BENCHMARK_PATHS,
        active.after_persist,
    )
    executions.append(
        cast("BackgroundProviderExecution[BaseModel]", benchmark_execution)
    )

    try:
        metrics = evaluate_reviews(
            cases=cases,
            source_review=source_execution.extraction,
            benchmark_review=benchmark_execution.extraction,
            corpus_cases=corpus_cases,
        )
    except (RoleEvaluationError, ValueError) as exc:
        return _unreliable(str(exc), executions)

    disputed_ids = {
        cast("str", item["case_id"])
        for item in cast("list[dict[str, object]]", metrics["details"])
        if item["cross_view_compatible"] is False
    }
    if disputed_ids:
        if not _prospective_budget_allows(executions):
            return _operational_blocker(
                "global budget prevents blinded tie-break", executions
            )
        disputed_cases = tuple(case for case in cases if case.case_id in disputed_ids)
        tie_value = tiebreak_input(disputed_cases)
        reserve_attempt(
            TIEBREAK_PATHS.attempt,
            stage="DUAL_ROLE_TIEBREAK",
            provider_input=tie_value,
            preregistration_sha256=preregistration_sha256,
        )
        try:
            tie_execution = active.tiebreak_call(
                api_key, tie_value, preregistration_sha256
            )
        except ProviderExecutionError as exc:
            return _invalid(exc, executions=executions, failed_paths=TIEBREAK_PATHS)
        _persist(
            tie_execution,
            tie_value,
            DualRoleTieBreakReview,
            TIEBREAK_PATHS,
            active.after_persist,
        )
        executions.append(cast("BackgroundProviderExecution[BaseModel]", tie_execution))
        try:
            tie_metrics = validate_tiebreak(
                cases=disputed_cases,
                tie_break=tie_execution.extraction,
                disputed_case_ids=disputed_ids,
            )
            metrics["tie_break"] = tie_metrics
            if tie_metrics["third_blinded_unresolved_case_ids"]:
                metrics["decision"] = "STOP_ROLE_ADJUDICATION_UNRELIABLE"
        except (RoleEvaluationError, ValueError) as exc:
            return _unreliable(str(exc), executions)

    metrics.update(_accounting(executions))
    metrics.update(
        {
            "same_model_family_independent_calls": True,
            "model_independent_review": False,
            "qualification_credit": False,
            "trusted_promotion": False,
            "graph_writes": 0,
        }
    )
    write_json_atomic(RESULT, metrics)
    return cast("str", metrics["decision"])


def _persist(
    execution: BackgroundProviderExecution[_OutputT],
    provider_input_value: str,
    output_model: type[_OutputT],
    paths: StagePaths,
    after_persist: Callable[[], None],
) -> None:
    persist_stage_custody(
        custody_input=StageCustodyInput(
            paths=paths.custody,
            stage=output_model.__name__,
            provider_input=provider_input_value,
            schema_sha256=canonical_sha256(output_model.model_json_schema()),
        ),
        output=execution.extraction,
        canonical_payload=execution.canonical_payload,
        receipt=execution.receipt,
    )
    after_persist()


def _verify_panel_file() -> None:
    loaded = json.loads(PANEL.read_text(encoding="utf-8"))
    generated = execution_panel_json()
    if loaded != generated:
        raise RoleAlignmentStateError(
            "frozen role panel differs from deterministic build"
        )


def _verify_preregistration(cases: tuple[PanelCase, ...]) -> None:
    loaded = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    frozen = loaded.get("frozen_state")
    if not isinstance(frozen, dict):
        raise RoleAlignmentStateError("malformed preregistration")
    checks = {
        "panel_sha256": _file_hash(PANEL),
        "source_prompt_sha256": _file_hash(SOURCE_PROMPT),
        "benchmark_prompt_sha256": _file_hash(BENCHMARK_PROMPT),
        "tiebreak_prompt_sha256": _file_hash(TIEBREAK_PROMPT),
        "source_schema_sha256": canonical_sha256(SourceRoleReview.model_json_schema()),
        "benchmark_schema_sha256": canonical_sha256(
            BenchmarkRoleReview.model_json_schema()
        ),
        "tiebreak_schema_sha256": canonical_sha256(
            DualRoleTieBreakReview.model_json_schema()
        ),
        "source_input_sha256": hashlib.sha256(source_input(cases).encode()).hexdigest(),
        "benchmark_input_sha256": hashlib.sha256(
            benchmark_input(cases).encode()
        ).hexdigest(),
        "research_sha256": _file_hash(RESEARCH),
        "prior_result_sha256": _file_hash(PRIOR_RESULT),
        "prior_addendum_sha256": _file_hash(PRIOR_ADDENDUM),
        "invalid_v1_result_sha256": _file_hash(INVALID_V1_RESULT),
        "source_sha256_by_document": {
            case.document_id: case.source_sha256 for case in cases
        },
        "model": "openai:gpt-5.6-luna",
        "reasoning_effort": REASONING_EFFORT,
        "budgets": {
            "global_max_creation_calls": 4,
            "global_max_cost_usd": 1.0,
            "per_call_max_output_tokens": MAX_OUTPUT_TOKENS,
            "per_call_max_total_tokens": MAX_TOTAL_TOKENS,
            "per_call_max_latency_seconds": MAX_LATENCY_SECONDS,
            "per_call_max_cost_usd": MAX_COST_USD,
            "retries": 0,
        },
    }
    for key, value in checks.items():
        if frozen.get(key) != value:
            raise RoleAlignmentStateError(f"frozen {key} changed")
    code_hashes = frozen.get("code_sha256")
    if not isinstance(code_hashes, dict):
        raise RoleAlignmentStateError("frozen code hashes are absent")
    for relative, expected in code_hashes.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise RoleAlignmentStateError("malformed code hash")
        if _file_hash(REPO / relative) != expected:
            raise RoleAlignmentStateError(f"frozen code changed: {relative}")


def _require_unused_outputs() -> None:
    paths = [RESULT]
    for stage in (SOURCE_PATHS, BENCHMARK_PATHS, TIEBREAK_PATHS):
        paths.extend(
            [
                stage.attempt,
                stage.custody.bundle,
                stage.custody.receipt,
                stage.custody.raw_output,
            ]
        )
    if any(path.exists() for path in paths):
        raise RoleAlignmentStateError("Role Alignment V1 already started")


def _accounting(
    executions: list[BackgroundProviderExecution[BaseModel]],
) -> dict[str, object]:
    usage = [item.receipt.get("usage") for item in executions]
    if any(not isinstance(item, dict) for item in usage):
        raise RoleAlignmentStateError("verified usage is absent")
    typed = cast("list[dict[str, object]]", usage)
    return {
        "provider_calls": len(executions),
        "input_tokens": sum(cast("int", item["input_tokens"]) for item in typed),
        "output_tokens": sum(cast("int", item["output_tokens"]) for item in typed),
        "total_tokens": sum(cast("int", item["total_tokens"]) for item in typed),
        "latency_seconds": sum(
            cast("float", item["latency_seconds"]) for item in typed
        ),
        "cost_usd": sum(cast("float", item["cost_usd"]) for item in typed),
        "response_ids": [
            cast("dict[str, object]", item.receipt["identity"])["response_id"]
            for item in executions
        ],
    }


def _prospective_budget_allows(
    executions: list[BackgroundProviderExecution[BaseModel]],
) -> bool:
    if PRIOR_CONSUMED_CALLS + len(executions) + 1 > GLOBAL_MAX_CALLS:
        return False
    observed_cost = 0.0
    for execution in executions:
        usage = execution.receipt.get("usage")
        if not isinstance(usage, dict) or not isinstance(
            usage.get("cost_usd"), int | float
        ):
            return False
        observed_cost += float(usage["cost_usd"])
    return PRIOR_CONSUMED_COST_USD + observed_cost + MAX_COST_USD <= GLOBAL_MAX_COST_USD


def _operational_blocker(
    reason: str, executions: list[BackgroundProviderExecution[BaseModel]]
) -> str:
    result = {
        "decision": "STOP_OPERATIONAL_BLOCKER",
        "root_cause": reason,
        **_accounting(executions),
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(RESULT, result)
    return "STOP_OPERATIONAL_BLOCKER"


def _unreliable(
    reason: str, executions: list[BackgroundProviderExecution[BaseModel]]
) -> str:
    result = {
        "decision": "STOP_ROLE_ADJUDICATION_UNRELIABLE",
        "root_cause": reason,
        **_accounting(executions),
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(RESULT, result)
    return "STOP_ROLE_ADJUDICATION_UNRELIABLE"


def _invalid(
    error: ProviderExecutionError,
    *,
    executions: list[BackgroundProviderExecution[BaseModel]],
    failed_paths: StagePaths,
) -> str:
    acknowledged_response_id = _attempt_response_id(failed_paths.attempt)
    accounting = _accounting(executions)
    response_ids = cast("list[object]", accounting["response_ids"])
    if acknowledged_response_id is not None:
        response_ids.append(acknowledged_response_id)
    accounting["provider_calls"] = len(executions) + int(
        acknowledged_response_id is not None
    )
    accounting["response_ids"] = response_ids
    accounting["failed_call_usage_verified"] = False
    write_json_atomic(
        RESULT,
        {
            "decision": "INVALID_PROVIDER_EXECUTION",
            "failure_stage": error.stage,
            "root_cause": error.root_cause,
            "diagnostics": error.diagnostics,
            **accounting,
            "qualification_credit": False,
            "trusted_promotion": False,
        },
    )
    return "INVALID_PROVIDER_EXECUTION"


def _attempt_response_id(path: Path) -> str | None:
    if not path.exists():
        return None
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    response_id = loaded.get("response_id")
    return response_id if isinstance(response_id, str) else None


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    print(execute())
