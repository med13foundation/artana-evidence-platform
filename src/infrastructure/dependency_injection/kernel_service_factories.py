"""Combined kernel service factory mixin."""

from __future__ import annotations

from src.infrastructure.dependency_injection._kernel_claim_service_factories import (
    KernelClaimServiceFactoryMixin,
)
from src.infrastructure.dependency_injection._kernel_core_service_factories import (
    KernelCoreServiceFactoryMixin,
)


class KernelServiceFactoryMixin(
    KernelCoreServiceFactoryMixin,
    KernelClaimServiceFactoryMixin,
):
    """Aggregate kernel-related service factory methods."""


__all__ = ["KernelServiceFactoryMixin"]
