"""
Infrastructure utilities for storage metric emission.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.services.storage_metrics import StorageMetricsRecorder

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject
    from src.type_definitions.storage import StorageMetricEvent


class StructuredLoggingStorageMetricsRecorder(StorageMetricsRecorder):
    """
    Emits storage metric events via structured logging.

    This lightweight implementation can feed downstream log-based dashboards
    until a metrics exporter (Prometheus, OpenTelemetry, etc.) is wired in.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or logging.getLogger("artana.storage.metrics")

    def record_event(self, event: StorageMetricEvent) -> None:
        payload: JSONObject = event.model_dump()
        self._logger.info("storage.metric", extra={"storage_metric": payload})


def build_storage_metrics_recorder() -> StorageMetricsRecorder:
    """Provide the default recorder for dependency injection wiring."""

    return StructuredLoggingStorageMetricsRecorder()


__all__ = [
    "StructuredLoggingStorageMetricsRecorder",
    "build_storage_metrics_recorder",
]
