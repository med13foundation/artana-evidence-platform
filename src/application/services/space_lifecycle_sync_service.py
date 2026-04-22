"""Application service for reconciling platform tenant state into graph."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.ports.space_lifecycle_sync_port import SpaceLifecycleSyncPort
from src.domain.repositories.research_space_repository import ResearchSpaceRepository


@dataclass(frozen=True)
class SpaceLifecycleSyncSummary:
    """Summary of one tenant lifecycle sync run."""

    total_spaces: int
    synced_space_ids: tuple[UUID, ...]
    statuses: tuple[str, ...]
    batch_size: int


class SpaceLifecycleSyncService:
    """Reconcile platform-owned space state into the graph control plane."""

    def __init__(
        self,
        research_space_repository: ResearchSpaceRepository,
        space_lifecycle_sync: SpaceLifecycleSyncPort,
    ) -> None:
        self._space_repository = research_space_repository
        self._space_lifecycle_sync = space_lifecycle_sync

    def sync_space(self, space_id: UUID) -> ResearchSpace:
        """Sync one space snapshot into graph."""
        space = self._space_repository.find_by_id(space_id)
        if space is None:
            msg = f"Research space {space_id} not found"
            raise ValueError(msg)

        self._space_lifecycle_sync.sync_space(space)
        return space

    def sync_spaces(
        self,
        *,
        space_id: UUID | None = None,
        statuses: tuple[SpaceStatus, ...] = (
            SpaceStatus.ACTIVE,
            SpaceStatus.INACTIVE,
            SpaceStatus.ARCHIVED,
            SpaceStatus.SUSPENDED,
        ),
        batch_size: int = 100,
    ) -> SpaceLifecycleSyncSummary:
        """Sync one or many spaces into graph."""
        effective_batch_size = max(1, int(batch_size))

        if space_id is not None:
            space = self.sync_space(space_id)
            return SpaceLifecycleSyncSummary(
                total_spaces=1,
                synced_space_ids=(space.id,),
                statuses=(space.status.value,),
                batch_size=effective_batch_size,
            )

        synced_space_ids: list[UUID] = []
        for status in statuses:
            offset = 0
            while True:
                spaces = self._space_repository.find_by_status(
                    status,
                    skip=offset,
                    limit=effective_batch_size,
                )
                if not spaces:
                    break
                for space in spaces:
                    self._space_lifecycle_sync.sync_space(space)
                    synced_space_ids.append(space.id)
                if len(spaces) < effective_batch_size:
                    break
                offset += effective_batch_size

        return SpaceLifecycleSyncSummary(
            total_spaces=len(synced_space_ids),
            synced_space_ids=tuple(synced_space_ids),
            statuses=tuple(status.value for status in statuses),
            batch_size=effective_batch_size,
        )


__all__ = ["SpaceLifecycleSyncService", "SpaceLifecycleSyncSummary"]
