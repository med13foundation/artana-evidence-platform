"""
Helpers for assembling storage overview responses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.type_definitions.storage import (
    StorageConfigurationModel,
    StorageConfigurationStats,
    StorageHealthStatus,
    StorageOverviewResponse,
    StorageOverviewTotals,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from src.domain.entities.storage_configuration import StorageConfiguration
    from src.domain.repositories.storage_repository import StorageOperationRepository


def build_storage_overview(
    configurations: Iterable[StorageConfiguration],
    operation_repository: StorageOperationRepository,
    serializer: Callable[[StorageConfiguration], StorageConfigurationModel],
) -> StorageOverviewResponse:
    """Aggregate usage and health details for admin surfaces."""

    stats: list[StorageConfigurationStats] = []
    total_files = 0
    total_size = 0
    error_rates: list[float] = []
    enabled = 0
    healthy = degraded = offline = 0

    config_list = list(configurations)
    for configuration in config_list:
        usage = operation_repository.get_usage_metrics(configuration.id)
        health_snapshot = operation_repository.get_health_snapshot(configuration.id)
        stats.append(
            StorageConfigurationStats(
                configuration=serializer(configuration),
                usage=usage,
                health=health_snapshot.as_report() if health_snapshot else None,
            ),
        )
        if configuration.enabled:
            enabled += 1
        if usage:
            total_files += usage.total_files
            total_size += usage.total_size_bytes
            if usage.error_rate is not None:
                error_rates.append(usage.error_rate)
        if health_snapshot:
            match health_snapshot.status:
                case StorageHealthStatus.HEALTHY:
                    healthy += 1
                case StorageHealthStatus.DEGRADED:
                    degraded += 1
                case StorageHealthStatus.OFFLINE:
                    offline += 1

    disabled = len(config_list) - enabled
    avg_error = sum(error_rates) / len(error_rates) if error_rates else None

    totals = StorageOverviewTotals(
        total_configurations=len(config_list),
        enabled_configurations=enabled,
        disabled_configurations=disabled,
        healthy_configurations=healthy,
        degraded_configurations=degraded,
        offline_configurations=offline,
        total_files=total_files,
        total_size_bytes=total_size,
        average_error_rate=avg_error,
    )

    return StorageOverviewResponse(
        generated_at=datetime.now(UTC),
        totals=totals,
        configurations=stats,
    )


__all__ = ["build_storage_overview"]
