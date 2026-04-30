"""Budget helpers for continuous-learning runs."""

from __future__ import annotations

from time import monotonic
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.run_budget import (
    HarnessRunBudget,
    HarnessRunBudgetExceededError,
    HarnessRunBudgetStatus,
    HarnessRunBudgetUsage,
    budget_status_to_json,
    budget_to_json,
)
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore


def _elapsed_runtime_seconds(started_at: float) -> float:
    return round(max(monotonic() - started_at, 0.0), 6)


def _build_budget_usage(
    *,
    tool_calls: int,
    external_queries: int,
    new_proposals: int,
    runtime_seconds: float,
    cost_usd: float = 0.0,
) -> HarnessRunBudgetUsage:
    return HarnessRunBudgetUsage(
        tool_calls=tool_calls,
        external_queries=external_queries,
        new_proposals=new_proposals,
        runtime_seconds=runtime_seconds,
        cost_usd=cost_usd,
    )


def _active_budget_status(
    *,
    budget: HarnessRunBudget,
    usage: HarnessRunBudgetUsage,
) -> HarnessRunBudgetStatus:
    return HarnessRunBudgetStatus(
        status="active",
        limits=budget,
        usage=usage,
        exhausted_limit=None,
        message="Run is within budget limits.",
    )


def _completed_budget_status(
    *,
    budget: HarnessRunBudget,
    usage: HarnessRunBudgetUsage,
) -> HarnessRunBudgetStatus:
    return HarnessRunBudgetStatus(
        status="completed",
        limits=budget,
        usage=usage,
        exhausted_limit=None,
        message="Run completed within budget limits.",
    )


def _exhausted_budget_status(
    *,
    budget: HarnessRunBudget,
    exceeded: HarnessRunBudgetExceededError,
) -> HarnessRunBudgetStatus:
    return HarnessRunBudgetStatus(
        status="exhausted",
        limits=budget,
        usage=exceeded.usage,
        exhausted_limit=exceeded.limit_name,
        message=str(exceeded),
    )


def _write_budget_state(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
    budget: HarnessRunBudget,
    budget_status: HarnessRunBudgetStatus,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="run_budget",
        media_type="application/json",
        content={"limits": budget_to_json(budget)},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="budget_status",
        media_type="application/json",
        content=budget_status_to_json(budget_status),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "run_budget": budget_to_json(budget),
            "budget_status": budget_status_to_json(budget_status),
        },
    )


def _ensure_budget_capacity(  # noqa: PLR0913
    *,
    budget: HarnessRunBudget,
    tool_calls: int,
    external_queries: int,
    runtime_seconds: float,
    next_tool_calls: int = 0,
    next_external_queries: int = 0,
) -> None:
    projected_tool_calls = tool_calls + next_tool_calls
    if projected_tool_calls > budget.max_tool_calls:
        usage = _build_budget_usage(
            tool_calls=tool_calls,
            external_queries=external_queries,
            new_proposals=0,
            runtime_seconds=runtime_seconds,
        )
        message = (
            "Run exceeded max_tool_calls budget: "
            f"{projected_tool_calls} > {budget.max_tool_calls}"
        )
        raise HarnessRunBudgetExceededError(
            limit_name="max_tool_calls",
            limit_value=float(budget.max_tool_calls),
            usage=usage,
            message=message,
        )
    projected_external_queries = external_queries + next_external_queries
    if projected_external_queries > budget.max_external_queries:
        usage = _build_budget_usage(
            tool_calls=tool_calls,
            external_queries=external_queries,
            new_proposals=0,
            runtime_seconds=runtime_seconds,
        )
        message = (
            "Run exceeded max_external_queries budget: "
            f"{projected_external_queries} > {budget.max_external_queries}"
        )
        raise HarnessRunBudgetExceededError(
            limit_name="max_external_queries",
            limit_value=float(budget.max_external_queries),
            usage=usage,
            message=message,
        )
    if runtime_seconds > float(budget.max_runtime_seconds):
        usage = _build_budget_usage(
            tool_calls=tool_calls,
            external_queries=external_queries,
            new_proposals=0,
            runtime_seconds=runtime_seconds,
        )
        message = (
            "Run exceeded max_runtime_seconds budget: "
            f"{runtime_seconds:.3f} > {budget.max_runtime_seconds}"
        )
        raise HarnessRunBudgetExceededError(
            limit_name="max_runtime_seconds",
            limit_value=float(budget.max_runtime_seconds),
            usage=usage,
            message=message,
        )


def _budget_failure_http_exception(
    exceeded: HarnessRunBudgetExceededError,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exceeded),
    )


__all__ = [
    "_active_budget_status",
    "_budget_failure_http_exception",
    "_build_budget_usage",
    "_completed_budget_status",
    "_elapsed_runtime_seconds",
    "_ensure_budget_capacity",
    "_exhausted_budget_status",
    "_write_budget_state",
]
