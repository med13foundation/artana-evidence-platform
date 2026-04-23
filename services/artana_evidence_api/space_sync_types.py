"""Service-local types used to synchronize harness spaces into the graph API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.models.research_space import (
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
    SpaceStatusEnum,
)
from artana_evidence_api.types.common import ResearchSpaceSettings


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def _require_uuid(value: UUID | str | None, *, field_name: str) -> UUID:
    normalized_value = _as_uuid(value)
    if normalized_value is None:
        msg = f"{field_name} is required for graph space sync"
        raise ValueError(msg)
    return normalized_value


def _normalize_settings(value: object) -> ResearchSpaceSettings:
    if not isinstance(value, dict):
        return {}
    return cast("ResearchSpaceSettings", dict(value))


@dataclass(frozen=True, slots=True)
class GraphSyncSpace:
    """Minimal space snapshot pushed into the standalone graph service."""

    id: UUID
    slug: str
    name: str
    description: str
    owner_id: UUID
    status: SpaceStatusEnum
    settings: ResearchSpaceSettings
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class GraphSyncMembership:
    """Minimal membership snapshot pushed into the standalone graph service."""

    id: UUID
    space_id: UUID
    user_id: UUID
    role: MembershipRoleEnum
    invited_by: UUID | None
    invited_at: datetime | None
    joined_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SpaceMembershipSnapshotStore(Protocol):
    """Read the latest membership snapshot for one harness space."""

    def find_by_space(
        self,
        space_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[GraphSyncMembership]:
        """Return active memberships for one space."""


class SpaceLifecycleSyncPort(Protocol):
    """Push the latest tenant snapshot into the graph service."""

    def sync_space(self, space: GraphSyncSpace) -> None:
        """Synchronize one harness space into the graph service."""


def graph_sync_space_from_model(model: ResearchSpaceModel) -> GraphSyncSpace:
    """Convert one ORM research-space row into the graph sync payload type."""
    return GraphSyncSpace(
        id=_require_uuid(model.id, field_name="research_space.id"),
        slug=str(model.slug),
        name=str(model.name),
        description=str(model.description),
        owner_id=_require_uuid(model.owner_id, field_name="research_space.owner_id"),
        status=(
            model.status
            if isinstance(model.status, SpaceStatusEnum)
            else SpaceStatusEnum(str(model.status))
        ),
        settings=_normalize_settings(model.settings),
        updated_at=model.updated_at,
    )


def graph_sync_membership_from_model(
    model: ResearchSpaceMembershipModel,
) -> GraphSyncMembership:
    """Convert one ORM membership row into the graph sync payload type."""
    return GraphSyncMembership(
        id=_require_uuid(model.id, field_name="research_space_membership.id"),
        space_id=_require_uuid(
            model.space_id,
            field_name="research_space_membership.space_id",
        ),
        user_id=_require_uuid(
            model.user_id,
            field_name="research_space_membership.user_id",
        ),
        role=(
            model.role
            if isinstance(model.role, MembershipRoleEnum)
            else MembershipRoleEnum(str(model.role))
        ),
        invited_by=_as_uuid(model.invited_by),
        invited_at=model.invited_at,
        joined_at=model.joined_at,
        is_active=bool(model.is_active),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


__all__ = [
    "GraphSyncMembership",
    "GraphSyncSpace",
    "SpaceLifecycleSyncPort",
    "SpaceMembershipSnapshotStore",
    "graph_sync_membership_from_model",
    "graph_sync_space_from_model",
]
