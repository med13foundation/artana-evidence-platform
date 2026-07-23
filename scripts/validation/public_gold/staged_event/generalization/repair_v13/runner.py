"""Fail-fast exactly-once execution of the preregistered V13 exposed gate."""

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
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
    failure_classification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
    V13OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    V13Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    evaluate_v13_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.preflight import (
    ordered_cases,
    provider_input,
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider import (
    execute_case,
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
from scripts.validation.public_gold.staged_event.generalization.repair_v13.terminal import (
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
    V13ProviderExecution[V9StagedGeneralizationOutput],
]


class V13ExecutionError(RuntimeError):
    """V13 cannot violate its frozen execution contract."""


@dataclass(frozen=True, slots=True)
class V13Runtime:
    """Injectable runtime limited to one provider creation per case."""

    provider_call: ProviderCall
    after_case_persist: Callable[[], None] = lambda: None


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    paths: V13Paths
    preregistration_sha256: str
    policy: FrozenDualLanePolicy
    contract: V13NestedTwoLaneContract
    active: V13Runtime


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: V13Runtime | None = None,
    *,
    paths: V13Paths = DEFAULT_PATHS,
    remote_gate: bool = True,
) -> str:
    """Run the frozen panel, persisting each call before fail-fast decisions."""

    cases = ordered_cases(paths)
    case_ids = tuple(case.case_id for case in cases)
    _require_unused(paths, case_ids)
    verify(paths, remote_gate=remote_gate)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise V13ExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = _sha256(paths.preregistration)
    policy = verify_v13_frozen_policy(paths.grading, cases=cases)
    contract = load_contract(
        paths.nested_two_lane_contract,
        adjudication_path=paths.nested_adjudication,
        v12_contract_path=paths.v12_drug_two_lane_contract,
    )
    ledger = V13OperationalLedger()
    active = runtime or V13Runtime(_live_call)
    context = _ExecutionContext(
        paths=paths,
        preregistration_sha256=preregistration_sha256,
        policy=policy,
        contract=contract,
        active=active,
    )
    outcomes: list[CaseOutcome] = []
    planned = len(cases)

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
                    reason="V13 cumulative budget exhausted before next call",
                    diagnostics={"next_case_not_called": case.case_id},
                ),
                planned_case_count=planned,
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
                planned_case_count=planned,
            )
        if outcome is None:
            raise V13ExecutionError("case execution returned no outcome")
        outcomes.append(outcome)
        try:
            persist_case_evaluation(
                paths.case(case.case_id).evaluation,
                outcome,
            )
        except Exception as exc:  # noqa: BLE001 - consumed call must be sealed.
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
                planned_case_count=planned,
            )
        try:
            active.after_case_persist()
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
                planned_case_count=planned,
            )
        if ledger.budget_exhausted(global_max_cost_usd=GLOBAL_MAX_COST_USD):
            return persist_operational_budget_terminal(
                paths,
                outcomes=tuple(outcomes),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="OPERATIONAL_BUDGET_STOP",
                    reason=(
                        "V13 cumulative budget reached or exceeded after the "
                        "persisted provider call"
                    ),
                    diagnostics={
                        "stopped_after_persisted_case": case.case_id,
                        "next_case_not_called": _next_case_id(
                            case_ids,
                            case.case_id,
                        ),
                        "scientific_frontier_preserved": (
                            outcome.failure_classification
                        ),
                    },
                ),
                planned_case_count=planned,
            )
        if outcome.failure_classification is not None:
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


def _execute_one_case(
    *,
    case: GeneralizationCase,
    ledger: V13OperationalLedger,
    context: _ExecutionContext,
) -> tuple[CaseOutcome | None, V13OperationalLedger, InvalidTerminal | None]:
    """Execute, account, persist custody, and evaluate one case."""

    case_id = case.case_id
    case_paths = context.paths.case(case_id)
    value = provider_input(case_id, context.paths)
    reserve_attempt(
        case_paths.attempt,
        stage=f"GENERALIZATION_V13_EXPOSED:{case_id}",
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
    except V13ExecutionError as exc:
        error = reject_verified_execution(
            cast("V13ProviderExecution[BaseModel]", execution),
            stage="CASE_IDENTITY_CUSTODY",
            root_cause=str(exc),
            diagnostics={
                "expected_case_id": case_id,
                "observed_case_id": execution.extraction.case_id,
            },
        )
        return _rejected_terminal(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            ledger=ledger,
            error=error,
        )
    try:
        admitted = ledger.record_execution(
            case_id=case_id,
            execution=cast(
                "V13ProviderExecution[BaseModel]",
                execution,
            ),
        )
    except ValueError as exc:
        error = reject_verified_execution(
            cast("V13ProviderExecution[BaseModel]", execution),
            stage="EXACTLY_ONCE_ACCOUNTING",
            root_cause=str(exc),
            diagnostics=_receipt_diagnostics(execution),
        )
        return _rejected_terminal(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            ledger=ledger,
            error=error,
        )
    try:
        custody_record = _persist_custody(
            case_id=case_id,
            case_paths=case_paths,
            provider_input_value=value,
            execution=execution,
        )
    except (V13RejectedCustodyError, V13ExecutionError) as exc:
        error = reject_verified_execution(
            cast("V13ProviderExecution[BaseModel]", execution),
            stage="LOCAL_CUSTODY",
            root_cause=str(exc),
            diagnostics={
                "normal_path_custody_may_be_partial": True,
                "rejected_artifacts_not_overwritten": True,
                "complete_transport_evidence": (
                    execution.transport_evidence().as_json()
                ),
            },
        )
        updated = ledger.record_rejected(
            case_id=case_id,
            error=error,
            custody=None,
        )
        return (
            None,
            updated,
            InvalidTerminal(
                failed_case_id=case_id,
                stage="LOCAL_CUSTODY",
                reason=str(exc),
                diagnostics={
                    **error.diagnostics,
                    "complete_transport_evidence": (
                        execution.transport_evidence().as_json()
                    ),
                },
            ),
        )
    try:
        metrics = evaluate_v13_case(
            case,
            execution.extraction,
            case_policy(context.policy, case_id),
            context.contract,
        )
        failure = failure_classification(metrics)
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
                    "custody": cast(
                        "dict[str, object]",
                        asdict(custody_record),
                    ),
                },
            ),
        )
    return (
        CaseOutcome(
            case_id=case_id,
            response_id=_execution_response_id(execution),
            usage=_execution_usage(execution),
            metrics=metrics,
            failure_classification=failure,
            custody=cast("dict[str, object]", asdict(custody_record)),
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
    reused_response_ids = ledger.reused_response_ids(error.evidence.response_ids)
    custody: V13RejectedCustodyRecord | None = None
    custody_error: str | None = None
    try:
        custody = persist_rejected_custody(
            paths=case_paths,
            stage=f"GENERALIZATION_V13_EXPOSED:{case_id}",
            provider_input=provider_input_value,
            schema_sha256=_canonical_schema_sha256(),
            error=error,
        )
    except V13RejectedCustodyError as exc:
        custody_error = str(exc)
    updated = ledger.record_rejected(
        case_id=case_id,
        error=error,
        custody=custody,
    )
    diagnostics = dict(error.diagnostics)
    diagnostics["rejected_custody"] = custody.as_json() if custody is not None else None
    if custody_error is not None:
        diagnostics["rejected_custody_error"] = custody_error
        diagnostics["complete_transport_evidence"] = error.evidence.as_json()
    if reused_response_ids:
        diagnostics["original_failure_stage"] = error.stage
        diagnostics["original_root_cause"] = error.root_cause
        diagnostics["reused_response_ids"] = list(reused_response_ids)
        return (
            None,
            updated,
            InvalidTerminal(
                failed_case_id=case_id,
                stage="RESPONSE_ID_CUSTODY",
                reason="provider response ID was reused across V13 cases",
                diagnostics=diagnostics,
            ),
        )
    if custody_error is not None:
        diagnostics["original_failure_stage"] = error.stage
        diagnostics["original_root_cause"] = error.root_cause
        return (
            None,
            updated,
            InvalidTerminal(
                failed_case_id=case_id,
                stage="REJECTED_CUSTODY_PERSISTENCE",
                reason=custody_error,
                diagnostics=diagnostics,
            ),
        )
    return (
        None,
        updated,
        InvalidTerminal(
            failed_case_id=case_id,
            stage=error.stage,
            reason=error.root_cause,
            diagnostics=diagnostics,
        ),
    )


def _persist_custody(
    *,
    case_id: str,
    case_paths: CaseExecutionPaths,
    provider_input_value: str,
    execution: V13ProviderExecution[V9StagedGeneralizationOutput],
) -> StageCustodyRecord:
    _require_attempt_custody(
        case_paths.attempt,
        _execution_response_id(execution),
    )
    return persist_admitted_custody(
        custody_input=StageCustodyInput(
            paths=StageCustodyPaths(
                bundle=case_paths.bundle,
                receipt=case_paths.receipt,
                raw_output=case_paths.raw_output,
            ),
            stage=f"GENERALIZATION_V13_EXPOSED:{case_id}",
            provider_input=provider_input_value,
            schema_sha256=_canonical_schema_sha256(),
        ),
        output=execution.extraction,
        canonical_payload=execution.canonical_payload,
        receipt=execution.receipt,
    )


def _require_unused(paths: V13Paths, case_ids: tuple[str, ...]) -> None:
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
        raise V13ExecutionError(f"{EXPERIMENT_ID} already started")


def _require_case_identity(expected: str, observed: str) -> None:
    if observed != expected:
        raise V13ExecutionError("provider output case_id differs from called case")


def _require_attempt_custody(path: Path, response_id: str) -> None:
    loaded = _object(json.loads(path.read_text(encoding="utf-8")))
    if loaded.get("state") != "ACKNOWLEDGED":
        raise V13ExecutionError("attempt response ID was not acknowledged")
    if loaded.get("response_id") != response_id:
        raise V13ExecutionError("attempt response ID differs from receipt")


def _execution_response_id(
    execution: V13ProviderExecution[V9StagedGeneralizationOutput],
) -> str:
    identity = execution.receipt.get("identity")
    if not isinstance(identity, dict) or not isinstance(
        identity.get("response_id"), str
    ):
        raise V13ExecutionError("verified response identity is absent")
    return cast("str", identity["response_id"])


def _execution_usage(
    execution: V13ProviderExecution[V9StagedGeneralizationOutput],
) -> dict[str, object]:
    usage = execution.receipt.get("usage")
    if not isinstance(usage, dict):
        raise V13ExecutionError("verified usage is absent")
    return usage


def _receipt_diagnostics(
    execution: V13ProviderExecution[V9StagedGeneralizationOutput],
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
        raise V13ExecutionError("expected JSON object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _next_case_id(case_ids: tuple[str, ...], current: str) -> str | None:
    index = case_ids.index(current)
    return case_ids[index + 1] if index + 1 < len(case_ids) else None


__all__ = ["V13ExecutionError", "V13Runtime", "execute"]
