"""Approval and intent endpoints for the standalone harness service."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalRecord,
    HarnessApprovalStore,
    HarnessRunIntentRecord,
)
from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.run_registry import (  # noqa: TC001
    HarnessRunRecord,
    HarnessRunRegistry,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/v1/spaces",
    tags=["approvals"],
    dependencies=[Depends(require_harness_space_read_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)


class HarnessIntentActionRequest(BaseModel):
    """One proposed action in an intent plan."""

    model_config = ConfigDict(strict=True)

    approval_key: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=256)
    risk_level: str = Field(..., min_length=1, max_length=32)
    target_type: str = Field(..., min_length=1, max_length=128)
    target_id: str | None = Field(default=None, min_length=1, max_length=128)
    requires_approval: bool = True
    metadata: JSONObject = Field(default_factory=dict)

    def to_record(self) -> HarnessApprovalAction:
        """Convert the request model into the stored action record."""
        return HarnessApprovalAction(
            approval_key=self.approval_key,
            title=self.title,
            risk_level=self.risk_level,
            target_type=self.target_type,
            target_id=self.target_id,
            requires_approval=self.requires_approval,
            metadata=self.metadata,
        )


class HarnessRunIntentRequest(BaseModel):
    """Record an intent plan for one harness run."""

    model_config = ConfigDict(strict=True)

    summary: str = Field(..., min_length=1, max_length=2000)
    proposed_actions: list[HarnessIntentActionRequest] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)


class HarnessIntentActionResponse(BaseModel):
    """Serialized proposed intent action."""

    model_config = ConfigDict(strict=True)

    approval_key: str
    title: str
    risk_level: str
    target_type: str
    target_id: str | None
    requires_approval: bool
    metadata: JSONObject

    @classmethod
    def from_record(
        cls,
        record: HarnessApprovalAction,
    ) -> HarnessIntentActionResponse:
        """Serialize one intent action."""
        return cls(
            approval_key=record.approval_key,
            title=record.title,
            risk_level=record.risk_level,
            target_type=record.target_type,
            target_id=record.target_id,
            requires_approval=record.requires_approval,
            metadata=record.metadata,
        )


class HarnessRunIntentResponse(BaseModel):
    """Serialized run intent plan."""

    model_config = ConfigDict(strict=True)

    summary: str
    proposed_actions: list[HarnessIntentActionResponse]
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(
        cls,
        record: HarnessRunIntentRecord,
    ) -> HarnessRunIntentResponse:
        """Serialize one stored intent plan."""
        return cls(
            summary=record.summary,
            proposed_actions=[
                HarnessIntentActionResponse.from_record(action)
                for action in record.proposed_actions
            ],
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessApprovalResponse(BaseModel):
    """Serialized approval decision record."""

    model_config = ConfigDict(strict=True)

    approval_key: str
    title: str
    risk_level: str
    target_type: str
    target_id: str | None
    status: str
    decision_reason: str | None
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(
        cls,
        record: HarnessApprovalRecord,
    ) -> HarnessApprovalResponse:
        """Serialize one approval record."""
        return cls(
            approval_key=record.approval_key,
            title=record.title,
            risk_level=record.risk_level,
            target_type=record.target_type,
            target_id=record.target_id,
            status=record.status,
            decision_reason=record.decision_reason,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessApprovalListResponse(BaseModel):
    """List response for approval decisions."""

    model_config = ConfigDict(strict=True)

    approvals: list[HarnessApprovalResponse]
    total: int
    offset: int
    limit: int


class HarnessApprovalDecisionRequest(BaseModel):
    """Approve or reject one gated action."""

    model_config = ConfigDict(strict=True)

    decision: str = Field(..., min_length=1, max_length=32)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)


def _require_run(
    *,
    space_id: UUID,
    run_id: UUID,
    run_registry: HarnessRunRegistry,
) -> HarnessRunRecord:
    run = run_registry.get_run(space_id=space_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )
    return run


@router.post(
    "/{space_id}/runs/{run_id}/intent",
    response_model=HarnessRunIntentResponse,
    summary="Record one run intent plan",
    description=(
        "Store the gated actions a run wants to take so callers can review them "
        "before resuming execution."
    ),
    dependencies=[Depends(require_harness_space_write_access)],
)
def record_intent(  # noqa: PLR0913
    space_id: UUID,
    run_id: UUID,
    request: HarnessRunIntentRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessRunIntentResponse:
    """Create or replace the intent plan for one run."""
    run = _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    intent = approval_store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary=request.summary,
        proposed_actions=tuple(
            action.to_record() for action in request.proposed_actions
        ),
        metadata=request.metadata,
    )
    approvals = approval_store.list_approvals(space_id=space_id, run_id=run_id)
    run_registry.record_event(
        space_id=space_id,
        run_id=run_id,
        event_type="run.intent_recorded",
        message="Run intent plan recorded.",
        payload={
            "summary": request.summary,
            "approval_count": len(approvals),
        },
    )
    if approvals and run.status != "failed":
        current_progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
        run_registry.set_run_status(
            space_id=space_id,
            run_id=run_id,
            status="paused",
            existing_progress=current_progress,
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run_id,
            phase="approval",
            message="Run paused pending approval.",
            progress_percent=(
                current_progress.progress_percent
                if current_progress is not None
                else 0.0
            ),
            completed_steps=(
                current_progress.completed_steps if current_progress is not None else 0
            ),
            total_steps=(
                current_progress.total_steps if current_progress is not None else None
            ),
            resume_point="approval_gate",
            metadata={"pending_approvals": len(approvals)},
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run_id,
            event_type="run.paused",
            message="Run paused at approval gate.",
            payload={"pending_approvals": len(approvals)},
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run_id,
            patch={
                "status": "paused",
                "resume_point": "approval_gate",
                "pending_approvals": len(approvals),
            },
        )
    return HarnessRunIntentResponse.from_record(intent)


@router.get(
    "/{space_id}/runs/{run_id}/approvals",
    response_model=HarnessApprovalListResponse,
    summary="List run approval gates",
    description=(
        "Return the lower-level approval records for one run. Most callers "
        "should use the unified review queue when they want pending approvals "
        "mixed with proposals and other review items."
    ),
)
def list_approvals(
    space_id: UUID,
    run_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
) -> HarnessApprovalListResponse:
    """Return approval records for one run."""
    _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    approvals = approval_store.list_approvals(space_id=space_id, run_id=run_id)
    total = len(approvals)
    paged = approvals[offset : offset + limit]
    return HarnessApprovalListResponse(
        approvals=[HarnessApprovalResponse.from_record(record) for record in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/runs/{run_id}/approvals/{approval_key}",
    response_model=HarnessApprovalResponse,
    summary="Approve or reject one run action",
    description=(
        "Set the approval decision for one gated run action. Use the unified "
        "review queue when you want the product-facing review surface."
    ),
    dependencies=[Depends(require_harness_space_write_access)],
)
def decide_approval(  # noqa: PLR0913
    space_id: UUID,
    run_id: UUID,
    approval_key: str,
    request: HarnessApprovalDecisionRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessApprovalResponse:
    """Set the decision for one approval record."""
    run = _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    try:
        approval = approval_store.decide_approval(
            space_id=space_id,
            run_id=run_id,
            approval_key=approval_key,
            status=request.decision,
            decision_reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if "already decided" in str(exc)
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Approval '{approval_key}' not found for run '{run_id}' "
                f"in space '{space_id}'"
            ),
        )
    pending_approvals = [
        record.approval_key
        for record in approval_store.list_approvals(space_id=space_id, run_id=run_id)
        if record.status == "pending"
    ]
    run_registry.record_event(
        space_id=space_id,
        run_id=run_id,
        event_type="run.approval_decided",
        message=f"Approval '{approval_key}' marked {approval.status}.",
        payload={
            "approval_key": approval_key,
            "decision": approval.status,
            "pending_approvals": pending_approvals,
        },
    )
    current_progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
    if run.status == "paused":
        run_registry.set_progress(
            space_id=space_id,
            run_id=run_id,
            phase="approval_resolved" if not pending_approvals else "approval",
            message=(
                "All approvals resolved. Resume to continue run."
                if not pending_approvals
                else f"Awaiting {len(pending_approvals)} approval decision(s)."
            ),
            progress_percent=(
                current_progress.progress_percent
                if current_progress is not None
                else 0.0
            ),
            completed_steps=(
                current_progress.completed_steps if current_progress is not None else 0
            ),
            total_steps=(
                current_progress.total_steps if current_progress is not None else None
            ),
            resume_point="approval_gate",
            metadata={"pending_approvals": len(pending_approvals)},
        )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "pending_approvals": len(pending_approvals),
            "last_approval_key": approval_key,
            "last_approval_status": approval.status,
        },
    )
    return HarnessApprovalResponse.from_record(approval)


__all__ = [
    "HarnessApprovalDecisionRequest",
    "HarnessApprovalListResponse",
    "HarnessApprovalResponse",
    "HarnessRunIntentRequest",
    "HarnessRunIntentResponse",
    "decide_approval",
    "list_approvals",
    "record_intent",
    "router",
]
