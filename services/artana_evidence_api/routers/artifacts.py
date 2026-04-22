"""Artifact and workspace endpoints for the standalone harness service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactRecord,
    HarnessWorkspaceRecord,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_run_registry,
    require_harness_space_read_access,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.run_registry import (
        HarnessRunProgressRecord,
        HarnessRunRecord,
        HarnessRunRegistry,
    )

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)

router = APIRouter(
    prefix="/v1/spaces",
    tags=["artifacts"],
    dependencies=[Depends(require_harness_space_read_access)],
)


class HarnessArtifactResponse(BaseModel):
    """Serialized artifact payload."""

    model_config = ConfigDict(strict=True)

    key: str
    media_type: str
    content: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessArtifactRecord) -> HarnessArtifactResponse:
        """Serialize one artifact record."""
        return cls(
            key=record.key,
            media_type=record.media_type,
            content=record.content,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessArtifactListResponse(BaseModel):
    """List response for run artifacts."""

    model_config = ConfigDict(strict=True)

    artifacts: list[HarnessArtifactResponse]
    total: int
    offset: int
    limit: int


class HarnessWorkspaceResponse(BaseModel):
    """Serialized workspace snapshot payload."""

    model_config = ConfigDict(strict=True)

    snapshot: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessWorkspaceRecord) -> HarnessWorkspaceResponse:
        """Serialize one workspace snapshot record."""
        return cls(
            snapshot=record.snapshot,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


def _require_run(
    *,
    space_id: UUID,
    run_id: UUID,
    run_registry: HarnessRunRegistry,
) -> HarnessRunRecord:
    run = run_registry.get_run_fast(space_id=space_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )
    return run


def _fallback_manifest(run: HarnessRunRecord, *, degraded_reason: str) -> HarnessArtifactRecord:
    return HarnessArtifactRecord(
        space_id=run.space_id,
        run_id=run.id,
        key="run_manifest",
        media_type="application/json",
        content={
            "run_id": run.id,
            "space_id": run.space_id,
            "harness_id": run.harness_id,
            "title": run.title,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "graph_service_status": run.graph_service_status,
            "graph_service_version": run.graph_service_version,
            "read_degraded": True,
            "read_degraded_reason": degraded_reason,
        },
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _fallback_workspace(
    run: HarnessRunRecord,
    *,
    progress: HarnessRunProgressRecord | None,
    degraded_reason: str,
) -> HarnessWorkspaceRecord:
    updated_at = progress.updated_at if progress is not None else run.updated_at
    snapshot: JSONObject = {
        "space_id": run.space_id,
        "run_id": run.id,
        "harness_id": run.harness_id,
        "title": run.title,
        "status": progress.status if progress is not None else run.status,
        "input_payload": run.input_payload,
        "graph_service": {
            "status": run.graph_service_status,
            "version": run.graph_service_version,
        },
        "artifact_keys": ["run_manifest"],
        "read_degraded": True,
        "read_degraded_reason": degraded_reason,
    }
    if progress is not None:
        snapshot["progress"] = {
            "status": progress.status,
            "phase": progress.phase,
            "message": progress.message,
            "progress_percent": progress.progress_percent,
            "completed_steps": progress.completed_steps,
            "total_steps": progress.total_steps,
            "resume_point": progress.resume_point,
            "metadata": progress.metadata,
            "created_at": progress.created_at.isoformat(),
            "updated_at": progress.updated_at.isoformat(),
        }
    return HarnessWorkspaceRecord(
        space_id=run.space_id,
        run_id=run.id,
        snapshot=snapshot,
        created_at=run.created_at,
        updated_at=updated_at,
    )


@router.get(
    "/{space_id}/runs/{run_id}/artifacts",
    response_model=HarnessArtifactListResponse,
    summary="List artifacts for one harness run",
)
def list_artifacts(
    space_id: UUID,
    run_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessArtifactListResponse:
    """Return artifacts stored for one harness run."""
    run = _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    artifacts = artifact_store.list_artifacts(space_id=space_id, run_id=run_id)
    if not artifacts:
        artifacts = [
            _fallback_manifest(run, degraded_reason="artifact_list_unavailable"),
        ]
    total = len(artifacts)
    paged = artifacts[offset : offset + limit]
    return HarnessArtifactListResponse(
        artifacts=[HarnessArtifactResponse.from_record(artifact) for artifact in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/runs/{run_id}/artifacts/{artifact_key}",
    response_model=HarnessArtifactResponse,
    summary="Get one artifact for one harness run",
)
def get_artifact(
    space_id: UUID,
    run_id: UUID,
    artifact_key: str,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessArtifactResponse:
    """Return one artifact stored for one harness run."""
    run = _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=artifact_key,
    )
    if artifact is None and artifact_key.strip() == "run_manifest":
        artifact = _fallback_manifest(run, degraded_reason="artifact_unavailable")
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Artifact '{artifact_key}' not found for run '{run_id}' "
                f"in space '{space_id}'"
            ),
        )
    return HarnessArtifactResponse.from_record(artifact)


@router.get(
    "/{space_id}/runs/{run_id}/workspace",
    response_model=HarnessWorkspaceResponse,
    summary="Get workspace snapshot for one harness run",
)
def get_workspace(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessWorkspaceResponse:
    """Return the workspace snapshot stored for one harness run."""
    run = _require_run(space_id=space_id, run_id=run_id, run_registry=run_registry)
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is None:
        progress = run_registry.get_progress_fast(space_id=space_id, run_id=run_id)
        workspace = _fallback_workspace(
            run,
            progress=progress,
            degraded_reason="workspace_unavailable",
        )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace for run '{run_id}' not found in space '{space_id}'",
        )
    return HarnessWorkspaceResponse.from_record(workspace)


__all__ = [
    "HarnessArtifactListResponse",
    "HarnessArtifactResponse",
    "HarnessWorkspaceResponse",
    "get_artifact",
    "get_workspace",
    "list_artifacts",
    "router",
]
