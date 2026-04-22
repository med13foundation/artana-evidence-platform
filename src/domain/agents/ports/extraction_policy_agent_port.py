"""Port interface for extraction relation-policy agent operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_policy_context import (
        ExtractionPolicyContext,
    )
    from src.domain.agents.contracts.extraction_policy import ExtractionPolicyContract


class ExtractionPolicyAgentPort(ABC):
    """Port for proposing relation-policy updates for undefined relation patterns."""

    @abstractmethod
    async def propose(
        self,
        context: ExtractionPolicyContext,
        *,
        model_id: str | None = None,
    ) -> ExtractionPolicyContract:
        """Propose relation-constraint and mapping updates."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["ExtractionPolicyAgentPort"]
