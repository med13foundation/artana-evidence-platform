"""Facade mixin for claim-backed kernel service factories."""

from __future__ import annotations

from src.infrastructure.dependency_injection._kernel_claim_projection_service_factories import (
    KernelClaimProjectionServiceFactoryMixin,
)
from src.infrastructure.dependency_injection._kernel_reasoning_hypothesis_service_factories import (
    KernelReasoningHypothesisServiceFactoryMixin,
)


class KernelClaimServiceFactoryMixin(
    KernelClaimProjectionServiceFactoryMixin,
    KernelReasoningHypothesisServiceFactoryMixin,
):
    """Aggregate claim, reasoning, and hypothesis service factory methods."""


__all__ = ["KernelClaimServiceFactoryMixin"]
