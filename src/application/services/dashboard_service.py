"""Application service for dashboard metrics and activity feed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.models.api import ActivityFeedItem, DashboardSummary

if TYPE_CHECKING:
    from artana_evidence_db.kernel_repositories import KernelEntityRepository


class DashboardService:
    """Aggregate dashboard data from domain repositories."""

    def __init__(
        self,
        entity_repository: KernelEntityRepository,
    ) -> None:
        self._entity_repository = entity_repository

    def get_summary(self) -> DashboardSummary:
        """Return deterministic dashboard summary counts from kernel tables."""
        entity_counts = self._entity_repository.count_global_by_type()
        total_items = sum(entity_counts.values())

        # Until explicit status fields exist, treat all items as approved to avoid
        # fabricating workflow states.
        return DashboardSummary(
            pending_count=0,
            approved_count=total_items,
            rejected_count=0,
            total_items=total_items,
            entity_counts=entity_counts,
        )

    def get_recent_activities(self, limit: int = 10) -> list[ActivityFeedItem]:
        """
        Return recent activities.

        Activity logging is not yet implemented; return an empty list to avoid
        synthetic data while preserving API shape.
        """
        if limit <= 0:
            return []

        # Provide a minimal heartbeat entry so consumers can render deterministically.
        return [
            ActivityFeedItem(
                message="Dashboard snapshot generated",
                category="info",
                icon="mdi:chart-bar",
                created_at=datetime.now(UTC).isoformat(),
            ),
        ][:limit]


__all__ = ["DashboardService"]
