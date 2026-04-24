"""Operational maintenance routes for the standalone graph service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from artana_evidence_db.auth import (
    get_current_active_user,
    to_graph_principal,
    to_graph_rls_session_context,
)
from artana_evidence_db.claim_projection_readiness_support import (
    ClaimProjectionReadinessIssue,
)
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.database import (
    get_session,
    set_graph_rls_session_context,
)
from artana_evidence_db.dependencies import (
    get_kernel_claim_participant_backfill_service,
    get_kernel_claim_projection_readiness_service,
    get_kernel_reasoning_path_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.graph_access import evaluate_graph_admin_access
from artana_evidence_db.kernel_services import (
    KernelClaimParticipantBackfillService,
    KernelClaimProjectionReadinessService,
    KernelReasoningPathService,
)
from artana_evidence_db.operation_run_models import (
    GraphOperationRunModel,
    GraphOperationRunStatusEnum,
    GraphOperationRunTypeEnum,
)
from artana_evidence_db.operation_runs import GraphOperationRunStore
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.reasoning_path_support import ReasoningPathRebuildSummary
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1", tags=["operations"])


class ProjectionReadinessSampleResponse(BaseModel):
    """One sampled readiness issue row."""

    model_config = ConfigDict(strict=True)

    research_space_id: str
    claim_id: str | None
    relation_id: str | None
    detail: str


class ProjectionReadinessIssueResponse(BaseModel):
    """Aggregate readiness issue summary."""

    model_config = ConfigDict(strict=True)

    count: int
    samples: list[ProjectionReadinessSampleResponse]


class ProjectionReadinessReportResponse(BaseModel):
    """Full readiness audit response."""

    model_config = ConfigDict(strict=True)

    orphan_relations: ProjectionReadinessIssueResponse
    missing_claim_participants: ProjectionReadinessIssueResponse
    missing_claim_evidence: ProjectionReadinessIssueResponse
    linked_relation_mismatches: ProjectionReadinessIssueResponse
    invalid_projection_relations: ProjectionReadinessIssueResponse
    ready: bool


class ProjectionRepairRequest(BaseModel):
    """Projection repair request payload."""

    model_config = ConfigDict(strict=True)

    dry_run: bool = True
    batch_limit: int = Field(default=5000, ge=1, le=10000)


class ParticipantBackfillGlobalSummaryResponse(BaseModel):
    """Global participant backfill summary."""

    model_config = ConfigDict(strict=True)

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    research_spaces: int
    dry_run: bool


class ProjectionRepairSummaryResponse(BaseModel):
    """Projection repair response payload."""

    model_config = ConfigDict(strict=True)

    operation_run_id: UUID
    participant_backfill: ParticipantBackfillGlobalSummaryResponse
    materialized_claims: int
    detached_claims: int
    unresolved_claims: int
    dry_run: bool


class ReasoningPathRebuildRequest(BaseModel):
    """Reasoning-path rebuild request payload."""

    model_config = ConfigDict(strict=False)

    space_id: UUID | None = None
    max_depth: int = Field(default=4, ge=1, le=4)
    replace_existing: bool = True


class ReasoningPathRebuildResponse(BaseModel):
    """Reasoning-path rebuild response payload."""

    model_config = ConfigDict(strict=True)

    operation_run_id: UUID
    summaries: list[JSONObject]


class GraphOperationRunResponse(BaseModel):
    """Recorded graph-service operation run."""

    model_config = ConfigDict(strict=False)

    id: UUID
    operation_type: str
    status: str
    research_space_id: UUID | None
    actor_user_id: UUID | None
    actor_email: str | None
    dry_run: bool
    request_payload: JSONObject
    summary_payload: JSONObject
    failure_detail: str | None
    started_at: datetime
    completed_at: datetime

    @classmethod
    def from_model(cls, model: GraphOperationRunModel) -> GraphOperationRunResponse:
        return cls(
            id=model.id,
            operation_type=model.operation_type.value,
            status=model.status.value,
            research_space_id=model.research_space_id,
            actor_user_id=model.actor_user_id,
            actor_email=model.actor_email,
            dry_run=model.dry_run,
            request_payload=cast(JSONObject, dict(model.request_payload or {})),
            summary_payload=cast(JSONObject, dict(model.summary_payload or {})),
            failure_detail=model.failure_detail,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )


class GraphOperationRunListResponse(BaseModel):
    """List of recorded graph-service operation runs."""

    model_config = ConfigDict(strict=False)

    runs: list[GraphOperationRunResponse]
    total: int
    offset: int
    limit: int


def _require_graph_admin(*, current_user: User, session: Session) -> None:
    if not evaluate_graph_admin_access(to_graph_principal(current_user)).allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph service admin access is required for this operation",
        )
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user, bypass_rls=True),
    )


def _issue_response(
    issue: ClaimProjectionReadinessIssue,
) -> ProjectionReadinessIssueResponse:
    return ProjectionReadinessIssueResponse(
        count=issue.count,
        samples=[
            ProjectionReadinessSampleResponse(
                research_space_id=sample.research_space_id,
                claim_id=sample.claim_id,
                relation_id=sample.relation_id,
                detail=sample.detail,
            )
            for sample in issue.samples
        ],
    )


def _summary_payload(summary: ReasoningPathRebuildSummary) -> JSONObject:
    return {
        "research_space_id": summary.research_space_id,
        "eligible_claims": summary.eligible_claims,
        "accepted_claim_relations": summary.accepted_claim_relations,
        "rebuilt_paths": summary.rebuilt_paths,
        "max_depth": summary.max_depth,
    }


def _record_operation_run(
    *,
    session: Session,
    current_user: User,
    operation_type: GraphOperationRunTypeEnum,
    status: GraphOperationRunStatusEnum,
    research_space_id: UUID | None,
    dry_run: bool,
    request_payload: JSONObject,
    summary_payload: JSONObject,
    failure_detail: str | None,
    started_at: datetime,
    completed_at: datetime,
) -> GraphOperationRunModel:
    store = GraphOperationRunStore(session)
    return store.record(
        operation_type=operation_type,
        status=status,
        research_space_id=research_space_id,
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        dry_run=dry_run,
        request_payload=request_payload,
        summary_payload=summary_payload,
        failure_detail=failure_detail,
        started_at=started_at,
        completed_at=completed_at,
    )


@router.get(
    "/admin/projections/readiness",
    response_model=ProjectionReadinessReportResponse,
    summary="Audit global projection readiness",
)
def get_projection_readiness(
    *,
    sample_limit: int = 10,
    current_user: User = Depends(get_current_active_user),
    readiness_service: KernelClaimProjectionReadinessService = Depends(
        get_kernel_claim_projection_readiness_service,
    ),
    session: Session = Depends(get_session),
) -> ProjectionReadinessReportResponse:
    _require_graph_admin(current_user=current_user, session=session)
    started_at = datetime.now(UTC)
    normalized_sample_limit = max(1, min(int(sample_limit), 50))
    try:
        report = readiness_service.audit(sample_limit=normalized_sample_limit)
        response = ProjectionReadinessReportResponse(
            orphan_relations=_issue_response(report.orphan_relations),
            missing_claim_participants=_issue_response(
                report.missing_claim_participants,
            ),
            missing_claim_evidence=_issue_response(report.missing_claim_evidence),
            linked_relation_mismatches=_issue_response(
                report.linked_relation_mismatches,
            ),
            invalid_projection_relations=_issue_response(
                report.invalid_projection_relations,
            ),
            ready=report.ready,
        )
        _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.PROJECTION_READINESS_AUDIT,
            status=GraphOperationRunStatusEnum.SUCCEEDED,
            research_space_id=None,
            dry_run=False,
            request_payload={"sample_limit": normalized_sample_limit},
            summary_payload=cast(JSONObject, response.model_dump(mode="json")),
            failure_detail=None,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        return response
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.PROJECTION_READINESS_AUDIT,
            status=GraphOperationRunStatusEnum.FAILED,
            research_space_id=None,
            dry_run=False,
            request_payload={"sample_limit": normalized_sample_limit},
            summary_payload={},
            failure_detail=str(exc),
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        raise


@router.post(
    "/admin/projections/repair",
    response_model=ProjectionRepairSummaryResponse,
    summary="Repair global projection readiness issues",
)
def repair_projections(
    request: ProjectionRepairRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    readiness_service: KernelClaimProjectionReadinessService = Depends(
        get_kernel_claim_projection_readiness_service,
    ),
    session: Session = Depends(get_session),
) -> ProjectionRepairSummaryResponse:
    _require_graph_admin(current_user=current_user, session=session)
    started_at = datetime.now(UTC)
    request_payload = request.model_dump(mode="json")
    try:
        summary = readiness_service.repair_global(
            dry_run=request.dry_run,
            batch_limit=request.batch_limit,
        )
        if request.dry_run:
            session.rollback()
        response_payload: JSONObject = {
            "participant_backfill": {
                "scanned_claims": summary.participant_backfill.scanned_claims,
                "created_participants": summary.participant_backfill.created_participants,
                "skipped_existing": summary.participant_backfill.skipped_existing,
                "unresolved_endpoints": summary.participant_backfill.unresolved_endpoints,
                "research_spaces": summary.participant_backfill.research_spaces,
                "dry_run": summary.participant_backfill.dry_run,
            },
            "materialized_claims": summary.materialized_claims,
            "detached_claims": summary.detached_claims,
            "unresolved_claims": summary.unresolved_claims,
            "dry_run": summary.dry_run,
        }
        operation_run = _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.PROJECTION_REPAIR,
            status=GraphOperationRunStatusEnum.SUCCEEDED,
            research_space_id=None,
            dry_run=request.dry_run,
            request_payload=request_payload,
            summary_payload=response_payload,
            failure_detail=None,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        return ProjectionRepairSummaryResponse(
            operation_run_id=operation_run.id,
            participant_backfill=ParticipantBackfillGlobalSummaryResponse(
                scanned_claims=summary.participant_backfill.scanned_claims,
                created_participants=summary.participant_backfill.created_participants,
                skipped_existing=summary.participant_backfill.skipped_existing,
                unresolved_endpoints=summary.participant_backfill.unresolved_endpoints,
                research_spaces=summary.participant_backfill.research_spaces,
                dry_run=summary.participant_backfill.dry_run,
            ),
            materialized_claims=summary.materialized_claims,
            detached_claims=summary.detached_claims,
            unresolved_claims=summary.unresolved_claims,
            dry_run=summary.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.PROJECTION_REPAIR,
            status=GraphOperationRunStatusEnum.FAILED,
            research_space_id=None,
            dry_run=request.dry_run,
            request_payload=request_payload,
            summary_payload={},
            failure_detail=str(exc),
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        raise


@router.post(
    "/admin/reasoning-paths/rebuild",
    response_model=ReasoningPathRebuildResponse,
    summary="Rebuild persisted reasoning paths",
)
def rebuild_reasoning_paths(
    request: ReasoningPathRebuildRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> ReasoningPathRebuildResponse:
    _require_graph_admin(current_user=current_user, session=session)
    started_at = datetime.now(UTC)
    request_payload = request.model_dump(mode="json")
    try:
        summaries: list[ReasoningPathRebuildSummary]
        if request.space_id is not None:
            summaries = [
                reasoning_path_service.rebuild_for_space(
                    str(request.space_id),
                    max_depth=request.max_depth,
                    replace_existing=request.replace_existing,
                ),
            ]
        else:
            summaries = reasoning_path_service.rebuild_global(
                max_depth=request.max_depth,
            )
        summary_payload: JSONObject = {
            "summaries": [_summary_payload(summary) for summary in summaries],
        }
        operation_run = _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.REASONING_PATH_REBUILD,
            status=GraphOperationRunStatusEnum.SUCCEEDED,
            research_space_id=request.space_id,
            dry_run=False,
            request_payload=request_payload,
            summary_payload=summary_payload,
            failure_detail=None,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        return ReasoningPathRebuildResponse(
            operation_run_id=operation_run.id,
            summaries=cast(list[JSONObject], summary_payload["summaries"]),
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.REASONING_PATH_REBUILD,
            status=GraphOperationRunStatusEnum.FAILED,
            research_space_id=request.space_id,
            dry_run=False,
            request_payload=request_payload,
            summary_payload={},
            failure_detail=str(exc),
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        raise


class ClaimParticipantBackfillRequest(BaseModel):
    """Backfill request payload."""

    model_config = ConfigDict(strict=True)

    dry_run: bool = True
    limit: int = Field(default=500, ge=1, le=5000)
    offset: int = Field(default=0, ge=0)


class ClaimParticipantBackfillResponse(BaseModel):
    """Backfill response payload."""

    model_config = ConfigDict(strict=True)

    operation_run_id: UUID
    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    dry_run: bool


class ClaimParticipantCoverageResponse(BaseModel):
    """Participant coverage response payload."""

    model_config = ConfigDict(strict=True)

    total_claims: int
    claims_with_any_participants: int
    claims_with_subject: int
    claims_with_object: int
    unresolved_subject_endpoints: int
    unresolved_object_endpoints: int
    unresolved_endpoint_rate: float


@router.post(
    "/spaces/{space_id}/claim-participants/backfill",
    response_model=ClaimParticipantBackfillResponse,
    summary="Backfill structured participants for relation claims",
)
def backfill_claim_participants(
    space_id: UUID,
    request: ClaimParticipantBackfillRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    backfill_service: KernelClaimParticipantBackfillService = Depends(
        get_kernel_claim_participant_backfill_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimParticipantBackfillResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    started_at = datetime.now(UTC)
    request_payload = request.model_dump(mode="json")
    try:
        summary = backfill_service.backfill_for_space(
            research_space_id=str(space_id),
            dry_run=request.dry_run,
            limit=request.limit,
            offset=request.offset,
        )
        if request.dry_run:
            session.rollback()
        response_payload: JSONObject = {
            "scanned_claims": summary.scanned_claims,
            "created_participants": summary.created_participants,
            "skipped_existing": summary.skipped_existing,
            "unresolved_endpoints": summary.unresolved_endpoints,
            "dry_run": summary.dry_run,
        }
        operation_run = _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.CLAIM_PARTICIPANT_BACKFILL,
            status=GraphOperationRunStatusEnum.SUCCEEDED,
            research_space_id=space_id,
            dry_run=request.dry_run,
            request_payload=request_payload,
            summary_payload=response_payload,
            failure_detail=None,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        return ClaimParticipantBackfillResponse(
            operation_run_id=operation_run.id,
            scanned_claims=summary.scanned_claims,
            created_participants=summary.created_participants,
            skipped_existing=summary.skipped_existing,
            unresolved_endpoints=summary.unresolved_endpoints,
            dry_run=summary.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        _record_operation_run(
            session=session,
            current_user=current_user,
            operation_type=GraphOperationRunTypeEnum.CLAIM_PARTICIPANT_BACKFILL,
            status=GraphOperationRunStatusEnum.FAILED,
            research_space_id=space_id,
            dry_run=request.dry_run,
            request_payload=request_payload,
            summary_payload={},
            failure_detail=str(exc),
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
        session.commit()
        raise


@router.get(
    "/spaces/{space_id}/claim-participants/coverage",
    response_model=ClaimParticipantCoverageResponse,
    summary="Get participant coverage for relation claims",
)
def get_claim_participant_coverage(
    space_id: UUID,
    *,
    limit: int = 500,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    backfill_service: KernelClaimParticipantBackfillService = Depends(
        get_kernel_claim_participant_backfill_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimParticipantCoverageResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    coverage = backfill_service.coverage_for_space(
        research_space_id=str(space_id),
        limit=limit,
        offset=offset,
    )
    denominator = max(1, coverage.total_claims * 2)
    unresolved_total = (
        coverage.unresolved_subject_endpoints + coverage.unresolved_object_endpoints
    )
    unresolved_rate = float(unresolved_total) / float(denominator)
    return ClaimParticipantCoverageResponse(
        total_claims=coverage.total_claims,
        claims_with_any_participants=coverage.claims_with_any_participants,
        claims_with_subject=coverage.claims_with_subject,
        claims_with_object=coverage.claims_with_object,
        unresolved_subject_endpoints=coverage.unresolved_subject_endpoints,
        unresolved_object_endpoints=coverage.unresolved_object_endpoints,
        unresolved_endpoint_rate=round(unresolved_rate, 6),
    )


@router.get(
    "/admin/operations/runs",
    response_model=GraphOperationRunListResponse,
    summary="List recorded graph-service operation runs",
)
def list_operation_runs(
    *,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    operation_type: GraphOperationRunTypeEnum | None = Query(default=None),
    status_filter: GraphOperationRunStatusEnum | None = Query(
        default=None,
        alias="status",
    ),
    space_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> GraphOperationRunListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    runs, total = GraphOperationRunStore(session).list_runs(
        limit=limit,
        offset=offset,
        operation_type=operation_type,
        status=status_filter,
        research_space_id=space_id,
    )
    return GraphOperationRunListResponse(
        runs=[GraphOperationRunResponse.from_model(run) for run in runs],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/admin/operations/runs/{run_id}",
    response_model=GraphOperationRunResponse,
    summary="Get one recorded graph-service operation run",
)
def get_operation_run(
    run_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    session: Session = Depends(get_session),
) -> GraphOperationRunResponse:
    _require_graph_admin(current_user=current_user, session=session)
    run = GraphOperationRunStore(session).get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph operation run not found",
        )
    return GraphOperationRunResponse.from_model(run)


__all__ = [
    "backfill_claim_participants",
    "get_operation_run",
    "list_operation_runs",
    "get_claim_participant_coverage",
    "get_projection_readiness",
    "rebuild_reasoning_paths",
    "repair_projections",
    "router",
]
