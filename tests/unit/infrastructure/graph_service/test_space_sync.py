from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)
from src.infrastructure.platform_graph.graph_service.space_sync import (
    sync_platform_space_to_graph,
)


class _RecordingGraphClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def sync_space(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


class _ManagedRecordingGraphClient(_RecordingGraphClient):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_sync_platform_space_to_graph_pushes_full_membership_snapshot() -> None:
    space_id = uuid4()
    owner_id = uuid4()
    invited_user_id = uuid4()
    joined_user_id = uuid4()
    now = datetime.now(UTC)
    memberships = [
        ResearchSpaceMembership(
            id=uuid4(),
            space_id=space_id,
            user_id=invited_user_id,
            role=MembershipRole.RESEARCHER,
            invited_by=owner_id,
            invited_at=now,
            joined_at=None,
            is_active=False,
        ),
        ResearchSpaceMembership(
            id=uuid4(),
            space_id=space_id,
            user_id=joined_user_id,
            role=MembershipRole.CURATOR,
            invited_by=owner_id,
            invited_at=now,
            joined_at=now,
            is_active=True,
        ),
    ]
    space = ResearchSpace(
        id=space_id,
        slug="graph-sync-space",
        name="Graph Sync Space",
        description="Graph sync test",
        owner_id=owner_id,
        status=SpaceStatus.ACTIVE,
        settings={"review_threshold": 0.67},
        tags=[],
    )

    client = _RecordingGraphClient()
    sync_platform_space_to_graph(
        space=space,
        memberships=memberships,
        client=client,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["space_id"] == space_id
    assert call["slug"] == "graph-sync-space"
    assert call["owner_id"] == owner_id
    assert call["status"] == "active"
    assert call["sync_source"] == "platform_control_plane"
    assert call["source_updated_at"] == space.updated_at
    assert isinstance(call["sync_fingerprint"], str)
    assert len(call["sync_fingerprint"]) == 64
    membership_payloads = call["memberships"]
    assert isinstance(membership_payloads, list)
    normalized_memberships = sorted(
        [
            {
                **membership.model_dump(),
                "invited_at": membership.invited_at.replace(tzinfo=UTC),
                "joined_at": (
                    membership.joined_at.replace(tzinfo=UTC)
                    if membership.joined_at is not None
                    else None
                ),
            }
            for membership in membership_payloads
        ],
        key=lambda membership: str(membership["user_id"]),
    )
    assert normalized_memberships == sorted(
        [
            {
                "user_id": invited_user_id,
                "role": "researcher",
                "invited_by": owner_id,
                "invited_at": now,
                "joined_at": None,
                "is_active": False,
            },
            {
                "user_id": joined_user_id,
                "role": "curator",
                "invited_by": owner_id,
                "invited_at": now,
                "joined_at": now,
                "is_active": True,
            },
        ],
        key=lambda membership: str(membership["user_id"]),
    )


def test_sync_platform_space_to_graph_requests_space_sync_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space_id = uuid4()
    owner_id = uuid4()
    client = _ManagedRecordingGraphClient()
    recorded_kwargs: dict[str, object] = {}
    space = ResearchSpace(
        id=space_id,
        slug="graph-sync-space",
        name="Graph Sync Space",
        description="Graph sync test",
        owner_id=owner_id,
        status=SpaceStatus.ACTIVE,
        settings={"review_threshold": 0.67},
        tags=[],
    )

    def _build_client(**kwargs: object) -> _ManagedRecordingGraphClient:
        recorded_kwargs.update(kwargs)
        return client

    monkeypatch.setattr(
        "src.infrastructure.platform_graph.graph_service.space_sync.build_graph_service_client_for_service",
        _build_client,
    )

    sync_platform_space_to_graph(
        space=space,
        memberships=[],
    )

    assert recorded_kwargs == {"graph_service_capabilities": ("space_sync",)}
    assert len(client.calls) == 1
    assert client.closed is True
