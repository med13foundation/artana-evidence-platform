"""Dependency providers for the standalone harness service."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    require_harness_read_access,
    require_harness_write_access,
)
from artana_evidence_api.composition import (
    GraphHarnessKernelRuntime,
    get_graph_harness_kernel_runtime,
)
from artana_evidence_api.config import get_settings
from artana_evidence_api.database import get_session
from artana_evidence_api.document_binary_store import (
    HarnessDocumentBinaryStore,
    LocalFilesystemHarnessDocumentBinaryStore,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.graph_integration.context import (
    GraphCallContext,
    make_graph_raw_mutation_transport_factory,
    make_graph_transport_bundle_factory,
)
from artana_evidence_api.graph_search_runtime import HarnessGraphSearchRunner
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.identity.contracts import IdentityGateway
from artana_evidence_api.identity.local_gateway import LocalIdentityGateway
from artana_evidence_api.models.research_space import (
    ResearchSpaceMembershipModel,
)
from artana_evidence_api.pubmed_discovery import (
    PubMedDiscoveryService,
    create_pubmed_discovery_service,
)
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingRunner,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.space_lifecycle_sync import (
    HarnessGraphServiceSpaceLifecycleSync,
)
from artana_evidence_api.space_sync_types import (
    GraphSyncMembership,
    graph_sync_membership_from_model,
)
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessDocumentStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchSpaceStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessReviewItemStore,
    SqlAlchemyHarnessScheduleStore,
)
from fastapi import Depends, HTTPException, status
from sqlalchemy import desc, select

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator
    from contextlib import AbstractContextManager

    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.chat_sessions import HarnessChatSessionStore
    from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
    from artana_evidence_api.document_store import HarnessDocumentStore
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.review_item_store import HarnessReviewItemStore
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from artana_evidence_api.schedule_store import HarnessScheduleStore
    from sqlalchemy.orm import Session

_SESSION_DEPENDENCY = Depends(get_session)
_KERNEL_RUNTIME_DEPENDENCY = Depends(get_graph_harness_kernel_runtime)
_HARNESS_READ_ACCESS_DEPENDENCY = Depends(require_harness_read_access)
_HARNESS_WRITE_ACCESS_DEPENDENCY = Depends(require_harness_write_access)


class _HarnessGraphSyncMembershipSnapshotStore:
    """Read active memberships through the harness ORM before graph sync."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def find_by_space(
        self,
        space_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[GraphSyncMembership]:
        stmt = (
            select(ResearchSpaceMembershipModel)
            .where(
                ResearchSpaceMembershipModel.space_id == space_id,
                ResearchSpaceMembershipModel.is_active.is_(True),
            )
            .order_by(desc(ResearchSpaceMembershipModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        rows = self._session.execute(stmt).scalars().all()
        return [graph_sync_membership_from_model(row) for row in rows]


def get_approval_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessApprovalStore:
    """Return the durable approval store."""
    return SqlAlchemyHarnessApprovalStore(session)


def get_artifact_store(
    runtime: GraphHarnessKernelRuntime = _KERNEL_RUNTIME_DEPENDENCY,
) -> HarnessArtifactStore:
    """Return the Artana-backed artifact and workspace store."""
    return ArtanaBackedHarnessArtifactStore(runtime=runtime)


def get_run_registry(
    session: Session = _SESSION_DEPENDENCY,
    runtime: GraphHarnessKernelRuntime = _KERNEL_RUNTIME_DEPENDENCY,
) -> HarnessRunRegistry:
    """Return the Artana-backed harness run registry."""
    return ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)


def get_chat_session_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessChatSessionStore:
    """Return the durable chat session store."""
    return SqlAlchemyHarnessChatSessionStore(session)


def get_document_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessDocumentStore:
    """Return the durable harness document store."""
    return SqlAlchemyHarnessDocumentStore(session)


@lru_cache(maxsize=1)
def _document_binary_store_singleton() -> HarnessDocumentBinaryStore:
    settings = get_settings()
    return LocalFilesystemHarnessDocumentBinaryStore(
        base_path=settings.document_storage_base_path,
    )


def get_document_binary_store() -> HarnessDocumentBinaryStore:
    """Return the binary document store used for PDF and enriched text payloads."""
    return _document_binary_store_singleton()


def get_graph_snapshot_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessGraphSnapshotStore:
    """Return the durable graph snapshot store."""
    return SqlAlchemyHarnessGraphSnapshotStore(session)


def get_proposal_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessProposalStore:
    """Return the durable proposal store."""
    return SqlAlchemyHarnessProposalStore(session)


def get_review_item_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessReviewItemStore:
    """Return the durable review-item store."""
    return SqlAlchemyHarnessReviewItemStore(session)


def get_research_space_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessResearchSpaceStore:
    """Return the local research-space table adapter used by identity."""
    return SqlAlchemyHarnessResearchSpaceStore(
        session,
        space_lifecycle_sync=HarnessGraphServiceSpaceLifecycleSync(
            membership_repository=_HarnessGraphSyncMembershipSnapshotStore(
                session=session,
            ),
            gateway_factory=make_graph_raw_mutation_transport_factory(
                call_context=GraphCallContext.service(
                    graph_service_capabilities=("space_sync",),
                ),
            ),
        ),
    )


_RESEARCH_SPACE_STORE_DEPENDENCY = Depends(get_research_space_store)


def get_identity_gateway(
    session: Session = _SESSION_DEPENDENCY,
    research_space_store: HarnessResearchSpaceStore = _RESEARCH_SPACE_STORE_DEPENDENCY,
) -> IdentityGateway:
    """Return the local identity boundary gateway."""
    return LocalIdentityGateway(
        session=session,
        research_space_store=research_space_store,
    )


_IDENTITY_GATEWAY_DEPENDENCY = Depends(get_identity_gateway)

_SPACE_WRITE_ROLES = frozenset({"owner", "admin", "curator", "researcher"})


def _graph_call_context_for_harness_user(current_user: HarnessUser) -> GraphCallContext:
    if current_user.role == HarnessUserRole.ADMIN:
        role = "admin"
    elif current_user.role == HarnessUserRole.CURATOR:
        role = "curator"
    elif current_user.role == HarnessUserRole.VIEWER:
        role = "viewer"
    else:
        role = "researcher"
    return GraphCallContext(
        user_id=str(current_user.id),
        role=role,
        graph_admin=current_user.role == HarnessUserRole.ADMIN,
    )


def _require_space_access(
    *,
    space_id: UUID,
    current_user: HarnessUser,
    identity_gateway: IdentityGateway,
    require_write: bool,
) -> HarnessUser:
    decision = identity_gateway.check_space_access(
        space_id=space_id,
        user_id=current_user.id,
        is_platform_admin=current_user.role == HarnessUserRole.ADMIN,
        is_service_user=current_user.role == HarnessUserRole.SERVICE,
        minimum_role="researcher" if require_write else "viewer",
    )
    if decision.space is None and current_user.role != HarnessUserRole.SERVICE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=decision.reason or "Access to this space is not permitted",
        )
    if require_write and decision.actual_role not in _SPACE_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access to this space is not permitted",
        )
    return current_user


def require_harness_space_read_access(
    space_id: UUID,
    current_user: HarnessUser = _HARNESS_READ_ACCESS_DEPENDENCY,
    identity_gateway: IdentityGateway = _IDENTITY_GATEWAY_DEPENDENCY,
) -> HarnessUser:
    """Require read access to one specific research space."""
    return _require_space_access(
        space_id=space_id,
        current_user=current_user,
        identity_gateway=identity_gateway,
        require_write=False,
    )


def require_harness_space_write_access(
    space_id: UUID,
    current_user: HarnessUser = _HARNESS_WRITE_ACCESS_DEPENDENCY,
    identity_gateway: IdentityGateway = _IDENTITY_GATEWAY_DEPENDENCY,
) -> HarnessUser:
    """Require write access to one specific research space."""
    return _require_space_access(
        space_id=space_id,
        current_user=current_user,
        identity_gateway=identity_gateway,
        require_write=True,
    )


def require_harness_space_owner_access(
    space_id: UUID,
    current_user: HarnessUser = _HARNESS_WRITE_ACCESS_DEPENDENCY,
    identity_gateway: IdentityGateway = _IDENTITY_GATEWAY_DEPENDENCY,
) -> HarnessUser:
    """Require owner-level access to one specific research space."""
    decision = identity_gateway.check_space_access(
        space_id=space_id,
        user_id=current_user.id,
        is_platform_admin=current_user.role == HarnessUserRole.ADMIN,
        is_service_user=current_user.role == HarnessUserRole.SERVICE,
        minimum_role="owner",
    )
    if decision.space is None and current_user.role != HarnessUserRole.SERVICE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access to this space is required",
        )
    if (
        current_user.role not in (HarnessUserRole.ADMIN, HarnessUserRole.SERVICE)
        and decision.actual_role != "owner"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access to this space is required",
        )
    return current_user


def get_research_state_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessResearchStateStore:
    """Return the durable research-state store."""
    return SqlAlchemyHarnessResearchStateStore(session)


def get_schedule_store(
    session: Session = _SESSION_DEPENDENCY,
) -> HarnessScheduleStore:
    """Return the durable schedule store."""
    return SqlAlchemyHarnessScheduleStore(session)


def get_graph_api_gateway(
    current_user: HarnessUser = _HARNESS_READ_ACCESS_DEPENDENCY,
) -> GraphTransportBundle:
    """Return the graph API gateway used by harness flows."""
    return GraphTransportBundle(
        call_context=_graph_call_context_for_harness_user(current_user),
    )


def get_graph_api_gateway_factory(
    current_user: HarnessUser = _HARNESS_READ_ACCESS_DEPENDENCY,
) -> Callable[[], GraphTransportBundle]:
    """Return the graph API gateway factory used by worker-owned harness execution."""
    return make_graph_transport_bundle_factory(
        call_context=_graph_call_context_for_harness_user(current_user),
    )


@contextmanager
def _pubmed_discovery_service_context() -> Iterator[PubMedDiscoveryService]:
    service = create_pubmed_discovery_service()
    try:
        yield service
    finally:
        service.close()


def get_pubmed_discovery_service() -> Generator[PubMedDiscoveryService]:
    """Return a scoped PubMed discovery service for literature refresh."""
    with _pubmed_discovery_service_context() as service:
        yield service


def get_pubmed_discovery_service_factory() -> Callable[
    [],
    AbstractContextManager[PubMedDiscoveryService],
]:
    """Return the scoped PubMed discovery-service factory used by harness execution."""
    return _pubmed_discovery_service_context


def get_graph_search_runner() -> HarnessGraphSearchRunner:
    """Return the harness-owned graph-search runner."""
    return HarnessGraphSearchRunner()


def get_graph_chat_runner() -> HarnessGraphChatRunner:
    """Return the harness-owned graph-chat runner."""
    return HarnessGraphChatRunner()


def get_graph_connection_runner() -> HarnessGraphConnectionRunner:
    """Return the harness-owned graph-connection runner."""
    return HarnessGraphConnectionRunner()


def get_research_onboarding_runner() -> HarnessResearchOnboardingRunner:
    """Return the harness-owned research-onboarding runner."""
    return HarnessResearchOnboardingRunner()


_RUN_REGISTRY_PROVIDER = Depends(get_run_registry)
_ARTIFACT_STORE_PROVIDER = Depends(get_artifact_store)
_CHAT_SESSION_STORE_PROVIDER = Depends(get_chat_session_store)
_DOCUMENT_STORE_PROVIDER = Depends(get_document_store)
_PROPOSAL_STORE_PROVIDER = Depends(get_proposal_store)
_APPROVAL_STORE_PROVIDER = Depends(get_approval_store)
_RESEARCH_STATE_STORE_PROVIDER = Depends(get_research_state_store)
_GRAPH_SNAPSHOT_STORE_PROVIDER = Depends(get_graph_snapshot_store)
_SCHEDULE_STORE_PROVIDER = Depends(get_schedule_store)
_GRAPH_CONNECTION_RUNNER_PROVIDER = Depends(get_graph_connection_runner)
_GRAPH_SEARCH_RUNNER_PROVIDER = Depends(get_graph_search_runner)
_GRAPH_CHAT_RUNNER_PROVIDER = Depends(get_graph_chat_runner)
_RESEARCH_ONBOARDING_RUNNER_PROVIDER = Depends(get_research_onboarding_runner)
_GRAPH_API_GATEWAY_FACTORY_PROVIDER = Depends(get_graph_api_gateway_factory)
_PUBMED_DISCOVERY_FACTORY_PROVIDER = Depends(get_pubmed_discovery_service_factory)
_DOCUMENT_BINARY_STORE_PROVIDER = Depends(get_document_binary_store)


def get_harness_execution_services(  # noqa: PLR0913
    runtime: GraphHarnessKernelRuntime = _KERNEL_RUNTIME_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_PROVIDER,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_PROVIDER,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_PROVIDER,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_PROVIDER,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_PROVIDER,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_PROVIDER,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_PROVIDER,
    graph_snapshot_store: HarnessGraphSnapshotStore = _GRAPH_SNAPSHOT_STORE_PROVIDER,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_PROVIDER,
    graph_connection_runner: HarnessGraphConnectionRunner = (
        _GRAPH_CONNECTION_RUNNER_PROVIDER
    ),
    graph_search_runner: HarnessGraphSearchRunner = _GRAPH_SEARCH_RUNNER_PROVIDER,
    graph_chat_runner: HarnessGraphChatRunner = _GRAPH_CHAT_RUNNER_PROVIDER,
    research_onboarding_runner: HarnessResearchOnboardingRunner = (
        _RESEARCH_ONBOARDING_RUNNER_PROVIDER
    ),
    graph_api_gateway_factory: Callable[[], GraphTransportBundle] = (
        _GRAPH_API_GATEWAY_FACTORY_PROVIDER
    ),
    pubmed_discovery_service_factory: Callable[
        [],
        AbstractContextManager[PubMedDiscoveryService],
    ] = _PUBMED_DISCOVERY_FACTORY_PROVIDER,
    document_binary_store: HarnessDocumentBinaryStore = _DOCUMENT_BINARY_STORE_PROVIDER,
) -> HarnessExecutionServices:
    """Return the shared service bundle used by the harness dispatcher and worker."""
    return HarnessExecutionServices(
        runtime=runtime,
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        document_store=document_store,
        proposal_store=proposal_store,
        approval_store=approval_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        schedule_store=schedule_store,
        graph_connection_runner=graph_connection_runner,
        graph_search_runner=graph_search_runner,
        graph_chat_runner=graph_chat_runner,
        research_onboarding_runner=research_onboarding_runner,
        graph_api_gateway_factory=graph_api_gateway_factory,
        pubmed_discovery_service_factory=pubmed_discovery_service_factory,
        document_binary_store=document_binary_store,
    )


__all__ = [
    "get_approval_store",
    "get_artifact_store",
    "get_document_binary_store",
    "get_chat_session_store",
    "get_document_store",
    "get_graph_api_gateway_factory",
    "get_graph_chat_runner",
    "get_graph_connection_runner",
    "get_graph_api_gateway",
    "get_graph_snapshot_store",
    "get_graph_search_runner",
    "get_harness_execution_services",
    "get_identity_gateway",
    "get_pubmed_discovery_service",
    "get_pubmed_discovery_service_factory",
    "get_proposal_store",
    "get_research_space_store",
    "get_research_state_store",
    "get_run_registry",
    "get_schedule_store",
    "require_harness_space_read_access",
    "require_harness_space_write_access",
    "require_harness_space_owner_access",
]
