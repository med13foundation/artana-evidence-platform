"""Explicit run-budget models and helpers for graph-harness workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

_CONTINUOUS_LEARNING_DEFAULT_MAX_TOOL_CALLS: Final[int] = 100
_CONTINUOUS_LEARNING_DEFAULT_MAX_EXTERNAL_QUERIES: Final[int] = 101
_CONTINUOUS_LEARNING_DEFAULT_MAX_NEW_PROPOSALS: Final[int] = 20
_CONTINUOUS_LEARNING_DEFAULT_MAX_RUNTIME_SECONDS: Final[int] = 300
_CONTINUOUS_LEARNING_DEFAULT_MAX_COST_USD: Final[float] = 5.0


class HarnessRunBudget(BaseModel):
    """Hard operational limits for one harness run."""

    model_config = ConfigDict(strict=True)

    max_tool_calls: int = Field(..., ge=1, le=1000)
    max_external_queries: int = Field(..., ge=1, le=1000)
    max_new_proposals: int = Field(..., ge=1, le=100)
    max_runtime_seconds: int = Field(..., ge=1, le=3600)
    max_cost_usd: float = Field(..., ge=0.0, le=1000.0)


class HarnessRunBudgetUsage(BaseModel):
    """Measured budget usage for one harness run."""

    model_config = ConfigDict(strict=True)

    tool_calls: int = Field(default=0, ge=0)
    external_queries: int = Field(default=0, ge=0)
    new_proposals: int = Field(default=0, ge=0)
    runtime_seconds: float = Field(default=0.0, ge=0.0)
    cost_usd: float = Field(default=0.0, ge=0.0)


class HarnessRunBudgetStatus(BaseModel):
    """Budget state emitted into artifacts, workspaces, and API responses."""

    model_config = ConfigDict(strict=True)

    status: Literal["active", "completed", "exhausted"]
    limits: HarnessRunBudget
    usage: HarnessRunBudgetUsage
    exhausted_limit: str | None = None
    message: str | None = None


class HarnessRunBudgetExceededError(Exception):
    """Raised when a run exceeds one enforced budget limit."""

    def __init__(
        self,
        *,
        limit_name: str,
        limit_value: float,
        usage: HarnessRunBudgetUsage,
        message: str,
    ) -> None:
        super().__init__(message)
        self.limit_name = limit_name
        self.limit_value = limit_value
        self.usage = usage


def default_continuous_learning_run_budget() -> HarnessRunBudget:
    """Return the default guardrails for continuous-learning runs."""
    return HarnessRunBudget(
        max_tool_calls=_CONTINUOUS_LEARNING_DEFAULT_MAX_TOOL_CALLS,
        max_external_queries=_CONTINUOUS_LEARNING_DEFAULT_MAX_EXTERNAL_QUERIES,
        max_new_proposals=_CONTINUOUS_LEARNING_DEFAULT_MAX_NEW_PROPOSALS,
        max_runtime_seconds=_CONTINUOUS_LEARNING_DEFAULT_MAX_RUNTIME_SECONDS,
        max_cost_usd=_CONTINUOUS_LEARNING_DEFAULT_MAX_COST_USD,
    )


def resolve_continuous_learning_run_budget(
    run_budget: HarnessRunBudget | None,
) -> HarnessRunBudget:
    """Resolve the effective continuous-learning budget."""
    return (
        run_budget
        if run_budget is not None
        else default_continuous_learning_run_budget()
    )


def budget_to_json(budget: HarnessRunBudget) -> JSONObject:
    """Serialize one budget into a JSON-safe object."""
    return cast("JSONObject", budget.model_dump(mode="json"))


def budget_status_to_json(status: HarnessRunBudgetStatus) -> JSONObject:
    """Serialize one budget status into a JSON-safe object."""
    return cast("JSONObject", status.model_dump(mode="json"))


def budget_from_json(value: object) -> HarnessRunBudget | None:
    """Parse one budget object from a workspace or schedule payload."""
    if not isinstance(value, dict):
        return None
    return HarnessRunBudget.model_validate(value)


__all__ = [
    "HarnessRunBudget",
    "HarnessRunBudgetExceededError",
    "HarnessRunBudgetStatus",
    "HarnessRunBudgetUsage",
    "budget_from_json",
    "budget_status_to_json",
    "budget_to_json",
    "default_continuous_learning_run_budget",
    "resolve_continuous_learning_run_budget",
]
