"""
Port interface for entity recognition agent operations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.entity_recognition_context import (
        EntityRecognitionContext,
    )
    from src.domain.agents.contracts.entity_recognition import (
        EntityRecognitionContract,
    )


class EntityRecognitionPort(ABC):
    """Port for entity-recognition agent execution."""

    @abstractmethod
    async def recognize(
        self,
        context: EntityRecognitionContext,
        *,
        model_id: str | None = None,
    ) -> EntityRecognitionContract:
        """Recognize entities/fields from a source document context."""

    @abstractmethod
    async def close(self) -> None:
        """Release runtime resources used by the adapter."""


__all__ = ["EntityRecognitionPort"]
