"""
Storage metrics recording protocol.

Provides a Clean Architecture boundary so application services can emit
observability events without depending on a concrete monitoring stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.type_definitions.storage import StorageMetricEvent


class StorageMetricsRecorder(Protocol):
    """Records structured storage metric events."""

    def record_event(self, event: StorageMetricEvent) -> None:
        """Persist the metric event."""


class NoOpStorageMetricsRecorder:
    """Fallback metrics recorder used when observability is not configured."""

    def record_event(self, event: StorageMetricEvent) -> None:
        del event


__all__ = [
    "NoOpStorageMetricsRecorder",
    "StorageMetricsRecorder",
]
