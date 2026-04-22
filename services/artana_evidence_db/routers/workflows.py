"""Unified workflow routes for graph DB product modes."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_db.auth import get_current_active_user, graph_ai_principal_for_user
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_graph_workflow_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.graph_api_schemas.workflow_schemas import (
    ExplanationResponse,
    GraphWorkflowActionRequest,
    GraphWorkflowCreateRequest,
    GraphWorkflowListResponse,
    GraphWorkflowResponse,
    OperatingModeCapabilitiesResponse,
    OperatingModeRequest,
    OperatingModeResponse,
    ValidationExplanationRequest,
)
from artana_evidence_db.graph_workflow_service import (
    GraphWorkflowService,
    WorkflowActionRejected,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from artana_evidence_db.workflow_models import GraphWorkflowKind, GraphWorkflowStatus
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["workflows"])


def _manual_actor(current_user: User) -> str:
    return f"manual:{current_user.id}"


def _verify_viewer(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )


def _require_role(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
    required_role: MembershipRole,
) -> None:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=required_role,
    )


def _http_error(error: ValueError) -> HTTPException:
    message = str(error)
    if "not found" in message.lower():
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=message,
    )


@router.get(
    "/{space_id}/operating-mode",
    response_model=OperatingModeResponse,
    summary="Get the graph space operating mode",
)
def get_operating_mode(
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> OperatingModeResponse:
    _verify_viewer(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        config = workflow_service.get_operating_mode(str(space_id))
        capabilities = workflow_service.capabilities(str(space_id))
    except ValueError as exc:
        raise _http_error(exc) from exc
    return OperatingModeResponse.from_config(
        research_space_id=str(space_id),
        config=config,
        capabilities=capabilities,
    )


@router.patch(
    "/{space_id}/operating-mode",
    response_model=OperatingModeResponse,
    summary="Update the graph space operating mode",
)
def update_operating_mode(
    space_id: UUID,
    request: OperatingModeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> OperatingModeResponse:
    _require_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.ADMIN,
    )
    try:
        config = workflow_service.update_operating_mode(
            research_space_id=str(space_id),
            mode=request.mode,
            workflow_policy=cast(
                JSONObject,
                request.workflow_policy.model_dump(mode="json"),
            ),
        )
        session.commit()
        capabilities = workflow_service.capabilities(str(space_id))
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Operating mode update conflicts with graph-space state",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    return OperatingModeResponse.from_config(
        research_space_id=str(space_id),
        config=config,
        capabilities=capabilities,
    )


@router.get(
    "/{space_id}/operating-mode/capabilities",
    response_model=OperatingModeCapabilitiesResponse,
    summary="Get operating-mode capabilities",
)
def get_operating_mode_capabilities(
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> OperatingModeCapabilitiesResponse:
    _verify_viewer(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        config = workflow_service.get_operating_mode(str(space_id))
        capabilities = workflow_service.capabilities(str(space_id))
    except ValueError as exc:
        raise _http_error(exc) from exc
    return OperatingModeCapabilitiesResponse(
        research_space_id=str(space_id),
        mode=config.mode,
        capabilities=capabilities,
    )


@router.post(
    "/{space_id}/workflows",
    response_model=GraphWorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one unified graph workflow",
)
def create_workflow(
    space_id: UUID,
    request: GraphWorkflowCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> GraphWorkflowResponse:
    _require_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )
    try:
        workflow = workflow_service.create_workflow(
            research_space_id=str(space_id),
            kind=request.kind,
            input_payload=request.input_payload,
            decision_payload=request.decision_payload,
            source_ref=request.source_ref,
            created_by=_manual_actor(current_user),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow conflicts with existing idempotency scope",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    return GraphWorkflowResponse.from_model(workflow)


@router.get(
    "/{space_id}/workflows",
    response_model=GraphWorkflowListResponse,
    summary="List unified graph workflows",
)
def list_workflows(
    space_id: UUID,
    *,
    kind: GraphWorkflowKind | None = Query(default=None),
    status_filter: GraphWorkflowStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> GraphWorkflowListResponse:
    _verify_viewer(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    workflows = workflow_service.list_workflows(
        research_space_id=str(space_id),
        kind=kind,
        status=status_filter,
        offset=offset,
        limit=limit,
    )
    total = workflow_service.count_workflows(
        research_space_id=str(space_id),
        kind=kind,
        status=status_filter,
    )
    return GraphWorkflowListResponse(
        workflows=[GraphWorkflowResponse.from_model(item) for item in workflows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/workflows/{workflow_id}",
    response_model=GraphWorkflowResponse,
    summary="Get one unified graph workflow",
)
def get_workflow(
    space_id: UUID,
    workflow_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> GraphWorkflowResponse:
    _verify_viewer(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        workflow = workflow_service.get_workflow(
            research_space_id=str(space_id),
            workflow_id=str(workflow_id),
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
    return GraphWorkflowResponse.from_model(workflow)


@router.post(
    "/{space_id}/workflows/{workflow_id}/actions",
    response_model=GraphWorkflowResponse,
    summary="Take a governed action on one workflow",
)
def act_on_workflow(
    space_id: UUID,
    workflow_id: UUID,
    request: GraphWorkflowActionRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> GraphWorkflowResponse:
    _require_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )
    try:
        workflow = workflow_service.act_on_workflow(
            research_space_id=str(space_id),
            workflow_id=str(workflow_id),
            action=request.action,
            actor=_manual_actor(current_user),
            input_hash=request.input_hash,
            risk_tier=request.risk_tier,
            confidence_assessment=request.confidence_assessment,
            reason=request.reason,
            decision_payload=request.decision_payload,
            generated_resources_payload=request.generated_resources_payload,
            ai_decision_payload=(
                cast(JSONObject, request.ai_decision.model_dump(mode="json"))
                if request.ai_decision is not None
                else None
            ),
            authenticated_ai_principal=graph_ai_principal_for_user(current_user),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow action conflicts with graph state",
        ) from exc
    except WorkflowActionRejected as exc:
        session.commit()
        raise _http_error(exc) from exc
    except ValueError as exc:
        session.rollback()
        raise _http_error(exc) from exc
    return GraphWorkflowResponse.from_model(workflow)


@router.get(
    "/{space_id}/explain/{resource_type}/{resource_id}",
    response_model=ExplanationResponse,
    summary="Explain why a graph resource exists",
)
def explain_resource(
    space_id: UUID,
    resource_type: str,
    resource_id: str,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> ExplanationResponse:
    _verify_viewer(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        return workflow_service.explain_resource(
            research_space_id=str(space_id),
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{space_id}/validate/explain",
    response_model=ExplanationResponse,
    summary="Explain a validation result",
)
def explain_validation(
    space_id: UUID,
    request: ValidationExplanationRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    workflow_service: GraphWorkflowService = Depends(get_graph_workflow_service),
    session: Session = Depends(get_session),
) -> ExplanationResponse:
    _verify_viewer(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    return workflow_service.validate_explain(
        research_space_id=str(space_id),
        validation_payload=request.validation_payload,
        context_payload=request.context_payload,
    )


__all__ = ["router"]
