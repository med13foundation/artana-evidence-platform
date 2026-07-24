"""Fail-fast, exactly-once execution of the frozen V16 exposed gate."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyInput,
    StageCustodyPaths,
    StageCustodyRecord,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
    V13OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ProviderExecution,
    V13ProviderExecutionError,
    reject_verified_execution,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.rejected_custody import (
    V13RejectedCustodyError,
    V13RejectedCustodyRecord,
    persist_admitted_custody,
    persist_rejected_custody,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    V16Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.evaluation import (
    evaluate_v16_case,
    failure_classification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.preflight import (
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.prompt import (
    ordered_cases,
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.provider import (
    execute_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.terminal import (
    CaseOutcome,
    InvalidTerminal,
    persist_case_evaluation,
    persist_invalid_terminal,
    persist_operational_budget_terminal,
    persist_scientific_terminal,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        FrozenDualLanePolicy,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
        V13NestedTwoLaneContract,
    )

ProviderCall = Callable[
    [str, str, str, str, CaseExecutionPaths],
    V13ProviderExecution[V16StagedGeneralizationOutput],
]


class V16ExecutionError(RuntimeError):
    """V16 cannot violate its frozen execution contract."""


@dataclass(frozen=True, slots=True)
class V16Runtime:
    """Injectable exactly-once provider boundary for deterministic tests."""

    provider_call: ProviderCall
    after_case_persist: Callable[[], None] = lambda: None


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    paths: V16Paths
    preregistration_sha256: str
    policy: FrozenDualLanePolicy
    contract: V13NestedTwoLaneContract
    active: V16Runtime


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: V16Runtime | None = None,
    *,
    paths: V16Paths = DEFAULT_PATHS,
    remote_gate: bool = True,
) -> str:
    """Run exposed cases serially and seal custody before every stop decision."""

    cases = ordered_cases(paths)
    case_ids = tuple(case.case_id for case in cases)
    _require_unused(paths, case_ids)
    verify(paths, remote_gate=remote_gate)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise V16ExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = _sha256(paths.preregistration)
    policy = verify_v13_frozen_policy(paths.v15.v14.v13.grading, cases=cases)
    contract = load_contract(
        paths.v15.v14.v13.nested_two_lane_contract,
        adjudication_path=paths.v15.v14.v13.nested_adjudication,
        v12_contract_path=paths.v15.v14.v13.v12_drug_two_lane_contract,
    )
    context = _ExecutionContext(
        paths=paths,
        preregistration_sha256=preregistration_sha256,
        policy=policy,
        contract=contract,
        active=runtime or V16Runtime(_live_call),
    )
    ledger = V13OperationalLedger()
    outcomes: list[CaseOutcome] = []

    for case in cases:
        if ledger.stop_before_next_call(
            global_max_calls=GLOBAL_MAX_CALLS,
            global_max_cost_usd=GLOBAL_MAX_COST_USD,
        ):
            return persist_operational_budget_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="OPERATIONAL_BUDGET_STOP",
                    reason="V16 cumulative budget exhausted before next call",
                    diagnostics={"next_case_not_called": case.case_id},
                ),
                planned_case_count=len(cases),
            )
        outcome, ledger, invalid = _execute_one_case(
            case=case,
            ledger=ledger,
            context=context,
        )
        if invalid is not None:
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=invalid,
                planned_case_count=len(cases),
            )
        if outcome is None:
            raise V16ExecutionError("case execution returned no outcome")
        outcomes.append(outcome)
        try:
            persist_case_evaluation(paths.case(case.case_id).evaluation, outcome)
        except Exception as exc:  # noqa: BLE001 - a consumed call must be sealed.
            return persist_invalid_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="CASE_EVALUATION_PERSISTENCE",
                    reason=f"{type(exc).__name__}: {exc}",
                    diagnostics={
                        "provider_call_and_custody_preserved": True,
                        "case_outcome": outcome.as_json(),
                    },
                ),
                planned_case_count=len(cases),
            )
        try:
            context.active.after_case_persist()
        except Exception as exc:  # noqa: BLE001 - injected crash fails closed.
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
                planned_case_count=len(cases),
            )
        if ledger.budget_exhausted(global_max_cost_usd=GLOBAL_MAX_COST_USD):
            return persist_operational_budget_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="OPERATIONAL_BUDGET_STOP",
                    reason="V16 cumulative budget reached after persisted call",
                    diagnostics={
                        "stopped_after_persisted_case": case.case_id,
                        "next_case_not_called": _next_case_id(case_ids, case.case_id),
                    },
                ),
                planned_case_count=len(cases),
            )
        if outcome.failure_classification is not None:
            return persist_scientific_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                planned_case_count=len(cases),
                grading_policy_sha256=policy_sha256(policy),
            )

    return persist_scientific_terminal(
        paths,
        outcomes=tuple(outcomes),
        ledger=ledger,
        planned_case_count=len(cases),
        grading_policy_sha256=policy_sha256(policy),
    )


def _execute_one_case(
    *,
    case: GeneralizationCase,
    ledger: V13OperationalLedger,
    context: _ExecutionContext,
) -> tuple[CaseOutcome | None, V13OperationalLedger, InvalidTerminal | None]:
    case_id = case.case_id
    case_paths = context.paths.case(case_id)
    value = provider_input(case_id, context.paths)
    reserve_attempt(
        case_paths.attempt,
        stage=f"GENERALIZATION_V16_EXPOSED:{case_id}",
        provider_input=value,
        preregistration_sha256=context.preregistration_sha256,
    )
    try:
        execution = context.active.provider_call(
            os.environ["OPENAI_API_KEY"],
            case_id,
            value,
            context.preregistration_sha256,
            case_paths,
        )
    except V13ProviderExecutionError as exc:
        return _rejected_terminal(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            ledger=ledger,
            error=exc,
        )
    try:
        _require_case_identity(case_id, execution.extraction.case_id)
    except V16ExecutionError as exc:
        return _rejected_terminal(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            ledger=ledger,
            error=reject_verified_execution(
                cast("V13ProviderExecution[BaseModel]", execution),
                stage="CASE_IDENTITY_CUSTODY",
                root_cause=str(exc),
                diagnostics={
                    "expected_case_id": case_id,
                    "observed_case_id": execution.extraction.case_id,
                },
            ),
        )
    try:
        admitted = ledger.record_execution(
            case_id=case_id,
            execution=cast("V13ProviderExecution[BaseModel]", execution),
        )
    except ValueError as exc:
        return _rejected_terminal(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            ledger=ledger,
            error=reject_verified_execution(
                cast("V13ProviderExecution[BaseModel]", execution),
                stage="EXACTLY_ONCE_ACCOUNTING",
                root_cause=str(exc),
                diagnostics=_receipt_diagnostics(execution),
            ),
        )
    try:
        custody = _persist_custody(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            execution=execution,
        )
    except (V13RejectedCustodyError, V16ExecutionError) as exc:
        error = reject_verified_execution(
            cast("V13ProviderExecution[BaseModel]", execution),
            stage="LOCAL_CUSTODY",
            root_cause=str(exc),
            diagnostics={
                "normal_path_custody_may_be_partial": True,
                "complete_transport_evidence": execution.transport_evidence().as_json(),
            },
        )
        updated = ledger.record_rejected(case_id=case_id, error=error, custody=None)
        return (
            None,
            updated,
            InvalidTerminal(
                failed_case_id=case_id,
                stage="LOCAL_CUSTODY",
                reason=str(exc),
                diagnostics=error.diagnostics,
            ),
        )
    try:
        evaluation = evaluate_v16_case(
            case,
            execution.extraction,
            case_policy(context.policy, case_id),
            context.contract,
            v14_consensus_path=context.paths.v15.v14.consensus,
        )
        failure = failure_classification(evaluation)
    except Exception as exc:  # noqa: BLE001 - evaluator defects fail closed.
        return (
            None,
            admitted,
            InvalidTerminal(
                failed_case_id=case_id,
                stage="EVALUATOR_DEFECT",
                reason=f"{type(exc).__name__}: {exc}",
                diagnostics={
                    "provider_call_and_custody_preserved": True,
                    "custody": cast("dict[str, object]", asdict(custody)),
                },
            ),
        )
    return (
        CaseOutcome(
            case_id=case_id,
            response_id=_execution_response_id(execution),
            usage=_execution_usage(execution),
            evaluation=evaluation,
            failure_classification=failure,
            custody=cast("dict[str, object]", asdict(custody)),
        ),
        admitted,
        None,
    )


def _rejected_terminal(
    *,
    case_id: str,
    case_paths: CaseExecutionPaths,
    provider_input_value: str,
    ledger: V13OperationalLedger,
    error: V13ProviderExecutionError,
) -> tuple[None, V13OperationalLedger, InvalidTerminal]:
    reused = ledger.reused_response_ids(error.evidence.response_ids)
    custody: V13RejectedCustodyRecord | None = None
    custody_error: str | None = None
    try:
        custody = persist_rejected_custody(
            paths=case_paths,
            stage=f"GENERALIZATION_V16_EXPOSED:{case_id}",
            provider_input=provider_input_value,
            schema_sha256=_canonical_schema_sha256(),
            error=error,
        )
    except V13RejectedCustodyError as exc:
        custody_error = str(exc)
    updated = ledger.record_rejected(case_id=case_id, error=error, custody=custody)
    diagnostics = dict(error.diagnostics)
    diagnostics["rejected_custody"] = custody.as_json() if custody is not None else None
    if reused:
        diagnostics["reused_response_ids"] = list(reused)
        stage = "RESPONSE_ID_CUSTODY"
        reason = "provider response ID was reused across V16 cases"
    elif custody_error is not None:
        diagnostics["complete_transport_evidence"] = error.evidence.as_json()
        stage = "REJECTED_CUSTODY_PERSISTENCE"
        reason = custody_error
    else:
        stage = error.stage
        reason = error.root_cause
    return (
        None,
        updated,
        InvalidTerminal(
            failed_case_id=case_id,
            stage=stage,
            reason=reason,
            diagnostics=diagnostics,
        ),
    )


def _persist_custody(
    *,
    case_id: str,
    case_paths: CaseExecutionPaths,
    provider_input_value: str,
    execution: V13ProviderExecution[V16StagedGeneralizationOutput],
) -> StageCustodyRecord:
    _require_attempt_custody(case_paths.attempt, _execution_response_id(execution))
    return persist_admitted_custody(
        custody_input=StageCustodyInput(
            paths=StageCustodyPaths(
                bundle=case_paths.bundle,
                receipt=case_paths.receipt,
                raw_output=case_paths.raw_output,
            ),
            stage=f"GENERALIZATION_V16_EXPOSED:{case_id}",
            provider_input=provider_input_value,
            schema_sha256=_canonical_schema_sha256(),
        ),
        output=execution.extraction,
        canonical_payload=execution.canonical_payload,
        receipt=execution.receipt,
    )


def _require_unused(paths: V16Paths, case_ids: tuple[str, ...]) -> None:
    candidates = [paths.result, paths.report]
    for case_id in case_ids:
        item = paths.case(case_id)
        candidates.extend(
            (item.attempt, item.bundle, item.receipt, item.raw_output, item.evaluation)
        )
    if any(path.exists() for path in candidates):
        raise V16ExecutionError(f"{EXPERIMENT_ID} already started")


def _require_case_identity(expected: str, observed: str) -> None:
    if observed != expected:
        raise V16ExecutionError("provider output case_id differs from called case")


def _require_attempt_custody(path: Path, response_id: str) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V16ExecutionError("attempt receipt is not an object")
    if value.get("state") != "ACKNOWLEDGED":
        raise V16ExecutionError("attempt response ID was not acknowledged")
    if value.get("response_id") != response_id:
        raise V16ExecutionError("attempt response ID differs from receipt")


def _execution_response_id(
    execution: V13ProviderExecution[V16StagedGeneralizationOutput],
) -> str:
    identity = execution.receipt.get("identity")
    if not isinstance(identity, dict) or not isinstance(
        identity.get("response_id"), str
    ):
        raise V16ExecutionError("verified response identity is absent")
    return cast("str", identity["response_id"])


def _execution_usage(
    execution: V13ProviderExecution[V16StagedGeneralizationOutput],
) -> dict[str, object]:
    usage = execution.receipt.get("usage")
    if not isinstance(usage, dict):
        raise V16ExecutionError("verified usage is absent")
    return usage


def _receipt_diagnostics(
    execution: V13ProviderExecution[V16StagedGeneralizationOutput],
) -> dict[str, object]:
    return {
        "provider_retries": execution.receipt.get("provider_retries"),
        "duplicate_creation_calls": execution.receipt.get("duplicate_creation_calls"),
        "observed_usage": execution.receipt.get("usage"),
    }


def _canonical_schema_sha256() -> str:
    raw = json.dumps(
        V16StagedGeneralizationOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _next_case_id(case_ids: tuple[str, ...], current: str) -> str | None:
    index = case_ids.index(current)
    return case_ids[index + 1] if index + 1 < len(case_ids) else None


__all__ = ["V16ExecutionError", "V16Runtime", "execute"]
