"""Fail-fast exactly-once execution of the preregistered V12 exposed gate."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.provider_receipt_boundary.foreground import (
    ForegroundProviderExecution,
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
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.acceptance import (
    failure_classification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.accounting import (
    V12OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    V12Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
    evaluate_v12_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.preflight import (
    ordered_cases,
    provider_input,
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.provider import (
    execute_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.terminal import (
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
    ForegroundProviderExecution[V9StagedGeneralizationOutput],
]


class V12ExecutionError(RuntimeError):
    """V12 cannot violate its frozen execution contract."""


@dataclass(frozen=True, slots=True)
class V12Runtime:
    provider_call: ProviderCall
    after_case_persist: Callable[[], None] = lambda: None


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: V12Runtime | None = None,
    *,
    paths: V12Paths = DEFAULT_PATHS,
    remote_gate: bool = True,
) -> str:
    cases = ordered_cases()
    case_ids = tuple(case.case_id for case in cases)
    _require_unused(paths, case_ids)
    verify(paths, remote_gate=remote_gate)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise V12ExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = _sha256(paths.preregistration)
    policy = verify_frozen_policy(paths.grading)
    contract = load_contract(
        paths.two_lane_contract,
        adjudication_path=paths.adjudication,
    )
    ledger = V12OperationalLedger()
    active = runtime or V12Runtime(_live_call)
    outcomes: list[CaseOutcome] = []
    planned = len(cases)

    for case in cases:
        if ledger.stop_before_next_call(
            global_max_calls=GLOBAL_MAX_CALLS,
            global_max_cost_usd=GLOBAL_MAX_COST_USD,
        ):
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="OPERATIONAL_BUDGET_STOP",
                    reason="V12 cumulative budget exhausted before next call",
                    diagnostics={"next_case_not_called": case.case_id},
                ),
                planned_case_count=planned,
            )
        case_paths = paths.case(case.case_id)
        value = provider_input(case.case_id, paths)
        reserve_attempt(
            case_paths.attempt,
            stage=f"GENERALIZATION_V12_EXPOSED:{case.case_id}",
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
        try:
            ledger = ledger.record_execution(
                case_id=case.case_id,
                execution=cast(
                    "ForegroundProviderExecution[BaseModel]",
                    execution,
                ),
            )
        except ValueError as exc:
            diagnostics = _receipt_diagnostics(execution)
            ledger = ledger.record_rejected(
                case_id=case.case_id,
                response_id=_execution_response_id(execution),
                diagnostics=diagnostics,
            )
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="EXACTLY_ONCE_ACCOUNTING",
                    reason=str(exc),
                    diagnostics=diagnostics,
                ),
                planned_case_count=planned,
            )
        try:
            _require_attempt_custody(
                case_paths.attempt,
                _execution_response_id(execution),
            )
            persist_stage_custody(
                custody_input=StageCustodyInput(
                    paths=StageCustodyPaths(
                        bundle=case_paths.bundle,
                        receipt=case_paths.receipt,
                        raw_output=case_paths.raw_output,
                    ),
                    stage=f"GENERALIZATION_V12_EXPOSED:{case.case_id}",
                    provider_input=value,
                    schema_sha256=_canonical_schema_sha256(),
                ),
                output=execution.extraction,
                canonical_payload=execution.canonical_payload,
                receipt=execution.receipt,
            )
        except (CustodyPersistenceError, V12ExecutionError) as exc:
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
            metrics = evaluate_v12_case(
                case,
                execution.extraction,
                case_policy(policy, case.case_id),
                contract,
            )
            failure = failure_classification(metrics)
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
            failure_classification=failure,
        )
        outcomes.append(outcome)
        persist_case_evaluation(case_paths.evaluation, outcome)
        try:
            active.after_case_persist()
        except Exception as exc:  # noqa: BLE001 - injected crash seals invalid.
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="POST_CASE_PERSISTENCE_HOOK",
                    reason=f"{type(exc).__name__}: {exc}",
                    diagnostics={},
                ),
                planned_case_count=planned,
            )
        if failure is not None:
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


def _require_unused(paths: V12Paths, case_ids: tuple[str, ...]) -> None:
    candidates = [
        paths.result,
        paths.report,
        paths.next_fresh_preregistration,
    ]
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
        raise V12ExecutionError(f"{EXPERIMENT_ID} already started")


def _require_case_identity(expected: str, observed: str) -> None:
    if observed != expected:
        raise V12ExecutionError("provider output case_id differs from called case")


def _require_attempt_custody(path: Path, response_id: str) -> None:
    loaded = _object(json.loads(path.read_text(encoding="utf-8")))
    if loaded.get("state") != "ACKNOWLEDGED":
        raise V12ExecutionError("attempt response ID was not acknowledged")
    if loaded.get("response_id") != response_id:
        raise V12ExecutionError("attempt response ID differs from receipt")


def _attempt_response_id(path: Path) -> str | None:
    if not path.exists():
        return None
    response_id = _object(
        json.loads(path.read_text(encoding="utf-8"))
    ).get("response_id")
    return response_id if isinstance(response_id, str) else None


def _execution_response_id(
    execution: ForegroundProviderExecution[V9StagedGeneralizationOutput],
) -> str:
    identity = execution.receipt.get("identity")
    if not isinstance(identity, dict) or not isinstance(
        identity.get("response_id"), str
    ):
        raise V12ExecutionError("verified response identity is absent")
    return cast("str", identity["response_id"])


def _execution_usage(
    execution: ForegroundProviderExecution[V9StagedGeneralizationOutput],
) -> dict[str, object]:
    usage = execution.receipt.get("usage")
    if not isinstance(usage, dict):
        raise V12ExecutionError("verified usage is absent")
    return usage


def _receipt_diagnostics(
    execution: ForegroundProviderExecution[V9StagedGeneralizationOutput],
) -> dict[str, object]:
    receipt = execution.receipt
    diagnostics: dict[str, object] = {
        "provider_retries": receipt.get("provider_retries"),
        "duplicate_creation_calls": receipt.get("duplicate_creation_calls"),
    }
    usage = receipt.get("usage")
    if isinstance(usage, dict):
        diagnostics["observed_usage"] = usage
    return diagnostics


def _canonical_schema_sha256() -> str:
    raw = json.dumps(
        V9StagedGeneralizationOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V12ExecutionError("expected JSON object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["V12ExecutionError", "V12Runtime", "execute"]
