"""Fail-fast exactly-once execution of the V11 exposed/public gate."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    CustodyPersistenceError,
    StageCustodyInput,
    StageCustodyPaths,
    persist_stage_custody,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_acceptance import (
    compare_with_v9,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.acceptance import (
    V11AcceptanceInput,
    evaluate_acceptance,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.accounting import (
    V11OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    V11ExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.preflight import (
    ordered_cases,
    provider_input,
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.provider import (
    execute_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.terminal import (
    CaseOutcome,
    InvalidTerminal,
    persist_case_evaluation,
    persist_invalid_terminal,
    persist_scientific_terminal,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

ProviderCall = Callable[
    [str, str, str, str, CaseExecutionPaths],
    BackgroundProviderExecution[V9StagedGeneralizationOutput],
]


class V11ExecutionError(RuntimeError):
    """V11 cannot start without violating its frozen contract."""


@dataclass(frozen=True, slots=True)
class V11Runtime:
    provider_call: ProviderCall
    after_case_persist: Callable[[], None] = lambda: None


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: V11Runtime | None = None,
    *,
    paths: V11ExecutionPaths = DEFAULT_PATHS,
    remote_gate: bool = True,
) -> str:
    """Persist custody, telemetry, and evaluation before every decision."""

    cases = ordered_cases()
    _require_unused(paths, tuple(case.case_id for case in cases))
    verify(paths, remote_gate=remote_gate)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise V11ExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(
        paths.preregistration.read_bytes()
    ).hexdigest()
    policy = verify_frozen_policy(paths.grading)
    v9_metrics = _baseline_metrics(paths.v9_result)
    v10_metrics = _baseline_metrics(paths.v10_result)
    active = runtime or V11Runtime(_live_call)
    outcomes: list[CaseOutcome] = []
    ledger = V11OperationalLedger()
    planned = len(cases)

    for case in cases:
        if len(ledger.records) >= GLOBAL_MAX_CALLS or ledger.budget_exhausted(
            global_max_cost_usd=GLOBAL_MAX_COST_USD
        ):
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="OPERATIONAL_BUDGET_STOP",
                    reason="cumulative V11 exposed budget exhausted before next call",
                    diagnostics={"next_case_not_called": case.case_id},
                ),
                planned_case_count=planned,
            )
        case_paths = paths.case(case.case_id)
        value = provider_input(paths, case.case_id)
        reserve_attempt(
            case_paths.attempt,
            stage=f"GENERALIZATION_V11_EXPOSED:{case.case_id}",
            provider_input=value,
            preregistration_sha256=preregistration_sha256,
        )
        try:
            execution = active.provider_call(
                api_key,
                case.case_id,
                value,
                preregistration_sha256,
                case_paths,
            )
        except ProviderExecutionError as exc:
            ledger = ledger.record_rejected(
                case_id=case.case_id,
                response_id=_attempt_response_id(case_paths.attempt),
                diagnostics=exc.diagnostics,
            )
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage=exc.stage,
                    reason=exc.root_cause,
                    diagnostics=exc.diagnostics,
                ),
                planned_case_count=planned,
            )
        ledger = ledger.record_execution(
            case_id=case.case_id,
            execution=cast("BackgroundProviderExecution[BaseModel]", execution),
        )
        try:
            persist_stage_custody(
                custody_input=StageCustodyInput(
                    paths=StageCustodyPaths(
                        bundle=case_paths.bundle,
                        receipt=case_paths.receipt,
                        raw_output=case_paths.raw_output,
                    ),
                    stage=f"GENERALIZATION_V11_EXPOSED:{case.case_id}",
                    provider_input=value,
                    schema_sha256=_canonical_schema_sha256(),
                ),
                output=execution.extraction,
                canonical_payload=execution.canonical_payload,
                receipt=execution.receipt,
            )
        except CustodyPersistenceError as exc:
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="LOCAL_CUSTODY",
                    reason=str(exc),
                    diagnostics={},
                ),
                planned_case_count=planned,
            )
        try:
            _require_case_identity(case.case_id, execution.extraction.case_id)
            metrics = evaluate_case(
                case,
                execution.extraction,
                case_policy(policy, case.case_id),
            )
            v9_baseline = v9_metrics.get(case.case_id)
            v10_baseline = v10_metrics.get(case.case_id)
            v9_comparison = compare_with_v9(metrics, v9_baseline)
            v10_comparison = compare_with_v9(metrics, v10_baseline)
            acceptance = evaluate_acceptance(
                V11AcceptanceInput(
                    case=case,
                    output=execution.extraction,
                    metrics=metrics,
                    v9_comparison=v9_comparison,
                    v10_comparison=v10_comparison,
                    v9_baseline_passed=(
                        cast("bool", v9_baseline["passed"])
                        if v9_baseline is not None
                        else None
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001 - evaluator defects fail closed.
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="EVALUATOR_DEFECT",
                    reason=f"{type(exc).__name__}: {exc}",
                    diagnostics={},
                ),
                planned_case_count=planned,
            )
        outcome = CaseOutcome(
            case_id=case.case_id,
            response_id=_execution_response_id(execution),
            usage=_execution_usage(execution),
            metrics=metrics,
            v9_comparison=v9_comparison,
            v10_comparison=v10_comparison,
            acceptance=acceptance,
            gene_or_protein_occurrences=tuple(
                participant.exact_text
                for participant in execution.extraction.participants
                if participant.entity_type == "GENE_OR_PROTEIN"
            ),
        )
        outcomes.append(outcome)
        persist_case_evaluation(case_paths.evaluation, outcome)
        active.after_case_persist()
        if not acceptance.passed:
            return persist_scientific_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                planned_case_count=planned,
                grading_policy_sha256=policy_sha256(policy),
            )

    return persist_scientific_terminal(
        paths,
        outcomes=tuple(outcomes),
        ledger=ledger,
        planned_case_count=planned,
        grading_policy_sha256=policy_sha256(policy),
    )


def _require_unused(
    paths: V11ExecutionPaths,
    case_ids: tuple[str, ...],
) -> None:
    candidates = [paths.result, paths.report]
    for case_id in case_ids:
        item = paths.case(case_id)
        candidates.extend(
            (
                item.attempt,
                item.bundle,
                item.receipt,
                item.raw_output,
                item.evaluation,
            )
        )
    if any(path.exists() for path in candidates):
        raise V11ExecutionError(f"{EXPERIMENT_ID} already started")


def _require_case_identity(expected: str, observed: str) -> None:
    if observed != expected:
        raise ValueError("provider output case_id differs from called case")


def _baseline_metrics(path: Path) -> dict[str, dict[str, object]]:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("cases"), list):
        raise V11ExecutionError("baseline metrics are malformed")
    result: dict[str, dict[str, object]] = {}
    for value in cast("list[object]", loaded["cases"]):
        if not isinstance(value, dict) or not isinstance(value.get("case_id"), str):
            raise V11ExecutionError("baseline case metrics are malformed")
        result[cast("str", value["case_id"])] = value
    return result


def _attempt_response_id(path: Path) -> str | None:
    if not path.exists():
        return None
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    response_id = loaded.get("response_id")
    return response_id if isinstance(response_id, str) else None


def _execution_response_id(
    execution: BackgroundProviderExecution[V9StagedGeneralizationOutput],
) -> str:
    identity = execution.receipt.get("identity")
    if not isinstance(identity, dict) or not isinstance(
        identity.get("response_id"), str
    ):
        raise V11ExecutionError("verified response identity is absent")
    return cast("str", identity["response_id"])


def _execution_usage(
    execution: BackgroundProviderExecution[V9StagedGeneralizationOutput],
) -> dict[str, object]:
    usage = execution.receipt.get("usage")
    if not isinstance(usage, dict):
        raise V11ExecutionError("verified usage is absent")
    return usage


def _canonical_schema_sha256() -> str:
    raw = json.dumps(
        V9StagedGeneralizationOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = ["V11ExecutionError", "V11Runtime", "execute"]
