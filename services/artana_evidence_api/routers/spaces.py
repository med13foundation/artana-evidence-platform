"""Research-space discovery and creation endpoints for the harness service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    require_harness_read_access,
    require_harness_write_access,
)
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_chat_session_store,
    get_document_store,
    get_graph_snapshot_store,
    get_identity_gateway,
    get_proposal_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
    require_harness_space_owner_access,
    require_harness_space_read_access,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.identity.contracts import (
    IdentityGateway,
    IdentityUserConflictError,
    IdentityUserNotFoundError,
    IdentityUserRecord,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessSpaceMemberRecord,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.space_acl import SpaceRole
from artana_evidence_api.types.common import ResearchSpaceSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/v1/spaces",
    tags=["spaces"],
)

AssignableSpaceRole = Literal["admin", "curator", "researcher", "viewer"]
ResearchOrchestrationMode = Literal[
    "deterministic",
    "full_ai_shadow",
    "full_ai_guarded",
]
GuardedRolloutProfile = Literal[
    "guarded_dry_run",
    "guarded_chase_only",
    "guarded_source_chase",
    "guarded_low_risk",
]
_DEFAULT_RESEARCH_ORCHESTRATION_MODE: ResearchOrchestrationMode = "full_ai_guarded"
_RESEARCH_ORCHESTRATION_MODES = frozenset(
    ("deterministic", "full_ai_shadow", "full_ai_guarded"),
)
_GUARDED_ROLLOUT_PROFILES = frozenset(
    (
        "guarded_dry_run",
        "guarded_chase_only",
        "guarded_source_chase",
        "guarded_low_risk",
    ),
)


def _identity_from_user(user: HarnessUser) -> IdentityUserRecord:
    return IdentityUserRecord(
        id=user.id,
        email=str(user.email),
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        status=user.status.value,
    )


class HarnessResearchSpaceResponse(BaseModel):
    """Serialized harness research-space record."""

    model_config = ConfigDict(strict=True)

    id: str
    slug: str
    name: str
    description: str
    status: str
    role: str
    is_default: bool = False
    settings: ResearchSpaceSettings = Field(default_factory=dict)

    @classmethod
    def from_record(
        cls,
        record: HarnessResearchSpaceRecord,
    ) -> HarnessResearchSpaceResponse:
        """Build one response model from a space record."""
        return cls(
            id=record.id,
            slug=record.slug,
            name=record.name,
            description=record.description,
            status=record.status,
            role=record.role,
            is_default=record.is_default,
            settings=dict(record.settings or {}),
        )


class HarnessResearchSpaceListResponse(BaseModel):
    """List response for harness research spaces."""

    model_config = ConfigDict(strict=True)

    spaces: list[HarnessResearchSpaceResponse]
    total: int
    offset: int
    limit: int


class CreateHarnessResearchSpaceRequest(BaseModel):
    """Create request for one harness research space."""

    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    sources: dict[str, bool] | None = Field(
        default=None,
        description="Enabled data sources (pubmed, marrvel, clinvar, mondo, pdf, text, drugbank, alphafold, uniprot, hgnc, clinical_trials, mgi, zfin).",
    )


class UpdateHarnessResearchSpaceSettingsRequest(BaseModel):
    """Update request for supported owner-managed research-space settings."""

    model_config = ConfigDict(strict=True)

    research_orchestration_mode: ResearchOrchestrationMode | None = Field(
        default=None,
        description=(
            "Research-init execution shell. Defaults to full_ai_guarded. "
            "Use deterministic as the explicit rollback mode."
        ),
    )
    full_ai_guarded_rollout_profile: GuardedRolloutProfile | None = Field(
        default=None,
        description="Guarded authority profile used when full_ai_guarded is active.",
    )


class HarnessResearchSpaceDependencyCountsResponse(BaseModel):
    """Counts of tracked records that still belong to one space."""

    model_config = ConfigDict(strict=True)

    runs: int
    documents: int
    proposals: int
    chat_sessions: int
    schedules: int
    graph_snapshots: int
    research_state_records: int
    total_records: int


class HarnessResearchSpaceArchiveResponse(BaseModel):
    """Response payload returned after archiving one space."""

    model_config = ConfigDict(strict=True)

    id: str
    slug: str
    name: str
    status: str
    archived: bool
    confirmed: bool
    message: str
    dependency_counts: HarnessResearchSpaceDependencyCountsResponse


def _space_dependency_counts(
    *,
    space_id: UUID,
    run_registry: HarnessRunRegistry,
    chat_session_store: HarnessChatSessionStore,
    document_store: HarnessDocumentStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    schedule_store: HarnessScheduleStore,
) -> HarnessResearchSpaceDependencyCountsResponse:
    runs = run_registry.count_runs(space_id=space_id)
    documents = document_store.count_documents(space_id=space_id)
    proposals = proposal_store.count_proposals(space_id=space_id)
    chat_sessions = chat_session_store.count_sessions(space_id=space_id)
    schedules = schedule_store.count_schedules(space_id=space_id)
    graph_snapshots = graph_snapshot_store.count_snapshots(space_id=space_id)
    research_state_records = (
        1 if research_state_store.get_state(space_id=space_id) else 0
    )
    total_records = (
        runs
        + documents
        + proposals
        + chat_sessions
        + schedules
        + graph_snapshots
        + research_state_records
    )
    return HarnessResearchSpaceDependencyCountsResponse(
        runs=runs,
        documents=documents,
        proposals=proposals,
        chat_sessions=chat_sessions,
        schedules=schedules,
        graph_snapshots=graph_snapshots,
        research_state_records=research_state_records,
        total_records=total_records,
    )


def _non_empty_space_conflict_detail(
    *,
    dependency_counts: HarnessResearchSpaceDependencyCountsResponse,
) -> dict[str, object]:
    return {
        "message": (
            "Space contains tracked data. Re-run DELETE with ?confirm=true to "
            "archive it while preserving the underlying records."
        ),
        "confirmation_required": True,
        "dependency_counts": dependency_counts.model_dump(),
    }


@router.get("", response_model=HarnessResearchSpaceListResponse, summary="List spaces")
def list_spaces(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: HarnessUser = Depends(require_harness_read_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessResearchSpaceListResponse:
    """Return research spaces visible to the authenticated caller."""
    records = identity_gateway.list_spaces(
        user_id=current_user.id,
        is_admin=current_user.role == HarnessUserRole.ADMIN,
    )
    total = len(records)
    paged = records[offset : offset + limit]
    return HarnessResearchSpaceListResponse(
        spaces=[HarnessResearchSpaceResponse.from_record(record) for record in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "",
    response_model=HarnessResearchSpaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create space",
)
def create_space(
    request: CreateHarnessResearchSpaceRequest,
    current_user: HarnessUser = Depends(require_harness_write_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessResearchSpaceResponse:
    """Create one new research space owned by the authenticated caller."""
    try:
        record = identity_gateway.create_space(
            owner=_identity_from_user(current_user),
            name=request.name,
            description=request.description,
            settings={"sources": request.sources} if request.sources else None,
        )
    except IdentityUserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return HarnessResearchSpaceResponse.from_record(record)


@router.patch(
    "/{space_id}/settings",
    response_model=HarnessResearchSpaceResponse,
    summary="Update space settings",
)
def update_space_settings(
    space_id: UUID,
    request: UpdateHarnessResearchSpaceSettingsRequest,
    current_user: HarnessUser = Depends(require_harness_space_owner_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessResearchSpaceResponse:
    """Update owner-managed settings for one research space."""
    current = identity_gateway.get_space(
        space_id=space_id,
        user_id=current_user.id,
        is_admin=current_user.role == HarnessUserRole.ADMIN,
    )
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )
    next_settings: ResearchSpaceSettings = dict(current.settings or {})
    if request.research_orchestration_mode is not None:
        mode = request.research_orchestration_mode
        if mode not in _RESEARCH_ORCHESTRATION_MODES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid research_orchestration_mode.",
            )
        if mode == _DEFAULT_RESEARCH_ORCHESTRATION_MODE:
            next_settings.pop("research_orchestration_mode", None)
        else:
            next_settings["research_orchestration_mode"] = mode
        if mode != "full_ai_guarded":
            next_settings.pop("full_ai_guarded_rollout_profile", None)
    if request.full_ai_guarded_rollout_profile is not None:
        profile = request.full_ai_guarded_rollout_profile
        if profile not in _GUARDED_ROLLOUT_PROFILES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid full_ai_guarded_rollout_profile.",
            )
        next_settings["full_ai_guarded_rollout_profile"] = profile
    try:
        updated = identity_gateway.update_space_settings(
            space_id=space_id,
            settings=next_settings,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        ) from exc
    return HarnessResearchSpaceResponse.from_record(updated)


@router.put(
    "/default",
    response_model=HarnessResearchSpaceResponse,
    summary="Get or create the caller's personal default space",
)
def ensure_default_space(
    current_user: HarnessUser = Depends(require_harness_write_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessResearchSpaceResponse:
    """Return the caller's personal default space, creating it when needed."""
    try:
        record = identity_gateway.ensure_default_space(
            owner=_identity_from_user(current_user),
        )
    except IdentityUserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return HarnessResearchSpaceResponse.from_record(record)


@router.delete(
    "/{space_id}",
    response_model=HarnessResearchSpaceArchiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Archive space",
)
def delete_space(
    space_id: UUID,
    confirm: bool = Query(  # noqa: FBT001
        default=False,
        description="Required when archiving a non-empty space.",
    ),
    current_user: HarnessUser = Depends(require_harness_write_access),
    run_registry: HarnessRunRegistry = Depends(get_run_registry),
    chat_session_store: HarnessChatSessionStore = Depends(get_chat_session_store),
    document_store: HarnessDocumentStore = Depends(get_document_store),
    graph_snapshot_store: HarnessGraphSnapshotStore = Depends(
        get_graph_snapshot_store,
    ),
    proposal_store: HarnessProposalStore = Depends(get_proposal_store),
    research_state_store: HarnessResearchStateStore = Depends(get_research_state_store),
    schedule_store: HarnessScheduleStore = Depends(get_schedule_store),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessResearchSpaceArchiveResponse:
    """Archive one research space owned by the caller or visible to an admin."""
    try:
        identity_gateway.prepare_space_archive(
            space_id=space_id,
            user_id=current_user.id,
            is_admin=current_user.role == HarnessUserRole.ADMIN,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    dependency_counts = _space_dependency_counts(
        space_id=space_id,
        run_registry=run_registry,
        chat_session_store=chat_session_store,
        document_store=document_store,
        graph_snapshot_store=graph_snapshot_store,
        proposal_store=proposal_store,
        research_state_store=research_state_store,
        schedule_store=schedule_store,
    )
    if dependency_counts.total_records > 0 and not confirm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_non_empty_space_conflict_detail(
                dependency_counts=dependency_counts,
            ),
        )

    try:
        archived_record = identity_gateway.archive_space(
            space_id=space_id,
            user_id=current_user.id,
            is_admin=current_user.role == HarnessUserRole.ADMIN,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return HarnessResearchSpaceArchiveResponse(
        id=archived_record.id,
        slug=archived_record.slug,
        name=archived_record.name,
        status=archived_record.status,
        archived=True,
        confirmed=confirm,
        message=(
            "Space archived. Underlying records were preserved."
            if dependency_counts.total_records > 0
            else "Space archived."
        ),
        dependency_counts=dependency_counts,
    )


# ---------------------------------------------------------------------------
# Space membership management
# ---------------------------------------------------------------------------


class HarnessSpaceMemberResponse(BaseModel):
    """Serialized space-member record."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    user_id: str
    role: str
    invited_by: str | None = None
    invited_at: str | None = None
    joined_at: str | None = None
    is_active: bool = True

    @classmethod
    def from_record(
        cls,
        record: HarnessSpaceMemberRecord,
    ) -> HarnessSpaceMemberResponse:
        """Build one response model from a member record."""
        return cls(
            id=record.id,
            space_id=record.space_id,
            user_id=record.user_id,
            role=record.role,
            invited_by=record.invited_by,
            invited_at=record.invited_at,
            joined_at=record.joined_at,
            is_active=record.is_active,
        )


class HarnessSpaceMemberListResponse(BaseModel):
    """List response for space members."""

    model_config = ConfigDict(strict=True)

    members: list[HarnessSpaceMemberResponse]
    total: int


class AddSpaceMemberRequest(BaseModel):
    """Request to add or invite a member to a space."""

    model_config = ConfigDict(strict=True)

    user_id: str = Field(min_length=1, max_length=255)
    role: AssignableSpaceRole = Field(
        default=SpaceRole.VIEWER.value,
        description=(
            "Assignable membership role: admin, curator, researcher, or viewer."
        ),
    )


@router.get(
    "/{space_id}/members",
    response_model=HarnessSpaceMemberListResponse,
    summary="List space members",
    dependencies=[Depends(require_harness_space_read_access)],
)
def list_space_members(
    space_id: UUID,
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessSpaceMemberListResponse:
    """Return all active members for one research space."""
    records = identity_gateway.list_members(space_id=space_id)
    return HarnessSpaceMemberListResponse(
        members=[HarnessSpaceMemberResponse.from_record(r) for r in records],
        total=len(records),
    )


@router.post(
    "/{space_id}/members",
    response_model=HarnessSpaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add space member",
    dependencies=[Depends(require_harness_space_owner_access)],
)
def add_space_member(
    space_id: UUID,
    request: AddSpaceMemberRequest,
    current_user: HarnessUser = Depends(require_harness_write_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessSpaceMemberResponse:
    """Add or invite a user to one research space. Requires owner-level access."""
    try:
        record = identity_gateway.add_member(
            space_id=space_id,
            user_id=request.user_id,
            role=request.role,
            invited_by=current_user.id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        ) from exc
    except IdentityUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return HarnessSpaceMemberResponse.from_record(record)


@router.delete(
    "/{space_id}/members/{user_id}",
    response_model=HarnessSpaceMemberResponse,
    summary="Remove space member",
    dependencies=[Depends(require_harness_space_owner_access)],
)
def remove_space_member(
    space_id: UUID,
    user_id: UUID,
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> HarnessSpaceMemberResponse:
    """Remove a user from one research space. Requires owner-level access."""
    record = identity_gateway.remove_member(
        space_id=space_id,
        user_id=user_id,
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found or already removed",
        )
    return HarnessSpaceMemberResponse.from_record(record)


__all__ = [
    "AddSpaceMemberRequest",
    "CreateHarnessResearchSpaceRequest",
    "HarnessResearchSpaceArchiveResponse",
    "HarnessResearchSpaceDependencyCountsResponse",
    "HarnessResearchSpaceListResponse",
    "HarnessResearchSpaceResponse",
    "HarnessSpaceMemberListResponse",
    "HarnessSpaceMemberResponse",
    "add_space_member",
    "create_space",
    "delete_space",
    "ensure_default_space",
    "list_space_members",
    "list_spaces",
    "remove_space_member",
    "router",
]
