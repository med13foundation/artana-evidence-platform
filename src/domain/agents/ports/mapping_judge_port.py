"""Port interface for mapper-judge agent operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.mapping_judge_context import MappingJudgeContext
    from src.domain.agents.contracts.mapping_judge import MappingJudgeContract


class MappingJudgePort(ABC):
    """Port for selecting the best variable candidate for ambiguous mappings."""

    @abstractmethod
    def judge(
        self,
        context: MappingJudgeContext,
        *,
        model_id: str | None = None,
    ) -> MappingJudgeContract:
        """Run one mapping-judge decision for a single field."""

    @abstractmethod
    def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["MappingJudgePort"]
