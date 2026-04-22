"""Platform-to-graph tenant lifecycle sync helpers."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal, TypeGuard

from src.domain.entities.research_space import ResearchSpace
from src.domain.entities.research_space_membership import ResearchSpaceMembership
from src.type_definitions.common import ResearchSpaceSettings

from .runtime import build_graph_service_client_for_service

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .client import GraphServiceClient, GraphSpaceSyncMembershipPayload


def _is_research_space_settings(value: object) -> TypeGuard[ResearchSpaceSettings]:
    return isinstance(value, dict)


def _membership_role_for_sync(
    membership: ResearchSpaceMembership,
) -> Literal["owner", "admin", "curator", "researcher", "viewer"]:
    role_value = membership.role.value
    if role_value == "owner":
        return "owner"
    if role_value == "admin":
        return "admin"
    if role_value == "curator":
        return "curator"
    if role_value == "researcher":
        return "researcher"
    return "viewer"


def _serialize_memberships(
    memberships: Sequence[ResearchSpaceMembership],
) -> list[GraphSpaceSyncMembershipPayload]:
    from .client import GraphSpaceSyncMembershipPayload as MembershipPayload

    return [
        MembershipPayload(
            user_id=membership.user_id,
            role=_membership_role_for_sync(membership),
            invited_by=membership.invited_by,
            invited_at=membership.invited_at,
            joined_at=membership.joined_at,
            is_active=membership.is_active,
        )
        for membership in memberships
    ]


def _space_sync_fingerprint(
    *,
    space: ResearchSpace,
    memberships: Sequence[ResearchSpaceMembership],
) -> str:
    normalized_memberships = sorted(
        [
            {
                "user_id": str(membership.user_id),
                "role": membership.role.value,
                "invited_by": (
                    str(membership.invited_by)
                    if membership.invited_by is not None
                    else None
                ),
                "invited_at": (
                    membership.invited_at.isoformat()
                    if membership.invited_at is not None
                    else None
                ),
                "joined_at": (
                    membership.joined_at.isoformat()
                    if membership.joined_at is not None
                    else None
                ),
                "is_active": membership.is_active,
            }
            for membership in memberships
        ],
        key=lambda membership: (membership["user_id"], membership["role"]),
    )
    payload = {
        "space": {
            "id": str(space.id),
            "slug": space.slug,
            "name": space.name,
            "description": space.description,
            "owner_id": str(space.owner_id),
            "status": space.status.value,
            "settings": space.settings,
            "updated_at": space.updated_at.isoformat(),
        },
        "memberships": normalized_memberships,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()


def sync_platform_space_to_graph(
    *,
    space: ResearchSpace,
    memberships: Sequence[ResearchSpaceMembership],
    client: GraphServiceClient | None = None,
) -> None:
    """Push one platform space snapshot into the standalone graph service."""
    membership_payloads = _serialize_memberships(memberships)
    graph_client = client or build_graph_service_client_for_service(
        graph_service_capabilities=("space_sync",),
    )
    settings = (
        space.settings
        if _is_research_space_settings(space.settings)
        else ResearchSpaceSettings()
    )
    try:
        graph_client.sync_space(
            space_id=space.id,
            slug=space.slug,
            name=space.name,
            description=space.description,
            owner_id=space.owner_id,
            status=space.status.value,
            settings=settings,
            sync_source="platform_control_plane",
            sync_fingerprint=_space_sync_fingerprint(
                space=space,
                memberships=memberships,
            ),
            source_updated_at=space.updated_at,
            memberships=membership_payloads,
        )
    finally:
        if client is None:
            graph_client.close()


__all__ = ["sync_platform_space_to_graph"]
