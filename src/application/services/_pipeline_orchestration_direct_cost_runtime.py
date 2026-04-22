"""Direct-cost tracking mixin for pipeline execution runtime."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol

from src.domain.services.direct_cost_tracking import (
    DirectCostUsage,
    activate_cost_usage_recorder,
)
from src.type_definitions.data_sources import PipelineRunCostMetadata

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ._pipeline_orchestration_execution_models import PipelineExecutionState


class _PipelineExecutionCostRuntimeHolder(Protocol):
    _state: PipelineExecutionState


class PipelineExecutionDirectCostRuntimeMixin:
    """Provide direct-cost accumulation helpers for pipeline runtime objects."""

    @contextmanager
    def track_direct_costs(
        self: _PipelineExecutionCostRuntimeHolder,
        *,
        default_stage: str,
    ) -> Iterator[None]:
        def _record(usage: DirectCostUsage) -> None:
            resolved_stage = usage.stage or default_stage
            self._state.direct_stage_costs_usd[resolved_stage] = round(
                self._state.direct_stage_costs_usd.get(resolved_stage, 0.0)
                + usage.cost_usd,
                8,
            )

        with activate_cost_usage_recorder(_record):
            yield

    def build_direct_cost_summary(
        self: _PipelineExecutionCostRuntimeHolder,
    ) -> PipelineRunCostMetadata:
        stage_costs = {
            str(stage): round(max(cost, 0.0), 8)
            for stage, cost in self._state.direct_stage_costs_usd.items()
            if cost > 0.0
        }
        return PipelineRunCostMetadata(
            total_cost_usd=round(sum(stage_costs.values()), 8),
            stage_costs_usd=stage_costs,
        )


__all__ = ["PipelineExecutionDirectCostRuntimeMixin"]
