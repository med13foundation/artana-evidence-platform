"""
Logging implementation of storage metrics recorder.

Emits structured logs for storage operations to support observability
without external dependencies.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.domain.services.storage_metrics import StorageMetricsRecorder

if TYPE_CHECKING:
    from src.type_definitions.storage import StorageMetricEvent

logger = logging.getLogger("artana.metrics.storage")


class LoggingStorageMetricsRecorder(StorageMetricsRecorder):
    """Records storage metric events to the application log."""

    def record_event(self, event: StorageMetricEvent) -> None:
        """Log the metric event as structured JSON."""
        payload = {
            "event_id": str(event.event_id),
            "metric_type": "storage_operation",
            "configuration_id": (
                str(event.configuration_id) if event.configuration_id else None
            ),
            "provider": event.provider.value,
            "operation": event.event_type.value,
            "status": event.status.value,
            "duration_ms": event.duration_ms,
            "metadata": event.metadata,
            "timestamp": event.emitted_at.isoformat(),
        }
        logger.info(json.dumps(payload))


__all__ = ["LoggingStorageMetricsRecorder"]
