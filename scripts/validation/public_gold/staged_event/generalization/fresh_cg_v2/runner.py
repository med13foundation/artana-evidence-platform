"""Fail-fast, exactly-once execution of the preregistered Fresh-CG V2 cases."""

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
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.evaluation import (
    FreshCaseMetrics,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_input import (
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    FreshCGTwoLaneReference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.accounting import (
    OperationalLedger,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.preflight import (
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.provider import (
    execute_case,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.selection import (
    load_v2_selection,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.terminal import (
    InvalidTerminal,
    persist_case_evaluation,
    persist_invalid_terminal,
    persist_operational_stop,
    persist_scientific_terminal,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    OccurrenceBindingError,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

ProviderCall = Callable[
    [str, str, str, str, CaseArtifactPaths],
    BackgroundProviderExecution[FreshCGProviderOutput],
]


class FreshCGV2ExecutionError(RuntimeError):
    """Execution cannot continue without violating preregistered custody."""


@dataclass(frozen=True, slots=True)
class FreshCGV2Runtime:
    provider_call: ProviderCall
    after_persist: Callable[[], None] = lambda: None


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseArtifactPaths,
) -> BackgroundProviderExecution[FreshCGProviderOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: FreshCGV2Runtime | None = None,
    *,
    paths: ExperimentPaths = DEFAULT_PATHS,
) -> str:
    """Persist each call and evaluation before deciding whether to continue."""

    selection = load_v2_selection(paths.selection)
    _require_unused(paths, tuple(case.case_id for case in selection.cases))
    verify(paths, remote_gate=True, offline_regression=True)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise FreshCGV2ExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(
        paths.preregistration.read_bytes()
    ).hexdigest()
    reference = FreshCGTwoLaneReference.model_validate_json(
        paths.reference.read_text(encoding="utf-8")
    )
    references = {case.case_id: case for case in reference.cases}
    active = runtime or FreshCGV2Runtime(_live_call)
    metrics: list[FreshCaseMetrics] = []
    ledger = OperationalLedger()
    planned = len(selection.cases)

    for case in selection.cases:
        if len(ledger.records) >= GLOBAL_MAX_CALLS or ledger.budget_exhausted(
            global_max_cost_usd=GLOBAL_MAX_COST_USD
        ):
            return persist_operational_stop(
                paths,
                metrics=tuple(metrics),
                ledger=ledger,
                next_case_id=case.case_id,
                planned_case_count=planned,
            )
        case_paths = paths.case(case.case_id)
        value = provider_input(
            case,
            scientific_prompt_path=paths.scientific_prompt,
            binding_prompt_path=paths.binding_prompt,
        )
        reserve_attempt(
            case_paths.attempt,
            stage=f"FRESH_CG_V2:{case.case_id}",
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
            response_id = _attempt_response_id(case_paths.attempt)
            ledger = ledger.record_rejected(
                case_id=case.case_id,
                response_id=response_id,
                diagnostics=exc.diagnostics,
            )
            return persist_invalid_terminal(
                paths,
                metrics=tuple(metrics),
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
                    stage=f"FRESH_CG_V2:{case.case_id}",
                    provider_input=value,
                    schema_sha256=_canonical_schema_sha256(),
                ),
                output=execution.extraction,
                canonical_payload=execution.canonical_payload,
                receipt=execution.receipt,
            )
            active.after_persist()
        except CustodyPersistenceError as exc:
            return persist_invalid_terminal(
                paths,
                metrics=tuple(metrics),
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
            case_metrics = evaluate_case(
                case,
                references[case.case_id],
                execution.extraction,
            )
        except OccurrenceBindingError as exc:
            return persist_invalid_terminal(
                paths,
                metrics=tuple(metrics),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="OCCURRENCE_BINDING",
                    reason=str(exc),
                    diagnostics={},
                ),
                planned_case_count=planned,
            )
        except Exception as exc:  # noqa: BLE001 - evaluator defects fail closed.
            return persist_invalid_terminal(
                paths,
                metrics=tuple(metrics),
                ledger=ledger,
                failure=InvalidTerminal(
                    failed_case_id=case.case_id,
                    stage="EVALUATOR_DEFECT",
                    reason=f"{type(exc).__name__}: {exc}",
                    diagnostics={},
                ),
                planned_case_count=planned,
            )
        metrics.append(case_metrics)
        persist_case_evaluation(
            case_paths.evaluation,
            metrics=case_metrics,
            response_id=_execution_response_id(execution),
            usage=_execution_usage(execution),
        )
        if not case_metrics.passed:
            return persist_scientific_terminal(
                paths,
                metrics=tuple(metrics),
                ledger=ledger,
                planned_case_count=planned,
            )

    return persist_scientific_terminal(
        paths,
        metrics=tuple(metrics),
        ledger=ledger,
        planned_case_count=planned,
    )


def _require_unused(paths: ExperimentPaths, case_ids: tuple[str, ...]) -> None:
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
        raise FreshCGV2ExecutionError(f"{EXPERIMENT_ID} already started")


def _attempt_response_id(path: Path) -> str | None:
    if not path.exists():
        return None
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    value = loaded.get("response_id")
    return value if isinstance(value, str) else None


def _execution_response_id(
    execution: BackgroundProviderExecution[FreshCGProviderOutput],
) -> str:
    identity = execution.receipt.get("identity")
    if not isinstance(identity, dict) or not isinstance(
        identity.get("response_id"), str
    ):
        raise FreshCGV2ExecutionError("verified response identity is absent")
    return cast("str", identity["response_id"])


def _execution_usage(
    execution: BackgroundProviderExecution[FreshCGProviderOutput],
) -> dict[str, object]:
    usage = execution.receipt.get("usage")
    if not isinstance(usage, dict):
        raise FreshCGV2ExecutionError("verified usage is absent")
    return usage


def _canonical_schema_sha256() -> str:
    raw = json.dumps(
        FreshCGProviderOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = ["FreshCGV2ExecutionError", "FreshCGV2Runtime", "execute"]
