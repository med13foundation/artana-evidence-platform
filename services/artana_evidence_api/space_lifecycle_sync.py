"""Harness-local graph tenant lifecycle sync adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.graph_client import GraphRawMutationTransport
from artana_evidence_api.graph_integration.context import (
    GraphCallContext,
    make_graph_raw_mutation_transport_factory,
)
from artana_evidence_api.space_sync_types import (
    GraphSyncSpace,
    SpaceLifecycleSyncPort,
    SpaceMembershipSnapshotStore,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class HarnessGraphServiceSpaceLifecycleSync(SpaceLifecycleSyncPort):
    """Synchronize platform tenant changes into the standalone graph service."""

    def __init__(
        self,
        *,
        membership_repository: SpaceMembershipSnapshotStore,
        gateway_factory: Callable[[], GraphRawMutationTransport] | None = None,
    ) -> None:
        self._membership_repository = membership_repository
        self._gateway_factory = (
            gateway_factory
            or make_graph_raw_mutation_transport_factory(
                call_context=GraphCallContext.service(
                    graph_service_capabilities=("space_sync",),
                ),
            )
        )

    def sync_space(self, space: GraphSyncSpace) -> None:
        """Push one authoritative tenant snapshot to the graph service."""
        memberships = self._membership_repository.find_by_space(
            space.id,
            skip=0,
            limit=1000,
        )
        with self._gateway_factory() as gateway:
            gateway.sync_space(space=space, memberships=memberships)
