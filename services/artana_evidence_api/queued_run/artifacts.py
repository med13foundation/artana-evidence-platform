"""Primary-result artifact helpers for queued runs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.queued_run.constants import (
    _PRIMARY_RESULT_WORKSPACE_KEY,
    _RESULT_KEYS_WORKSPACE_KEY,
)
from artana_evidence_api.types.common import JSONObject
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore


def _normalized_result_keys(
    *,
    primary_result_key: str,
    result_keys: list[str] | tuple[str, ...],
) -> list[str]:
    normalized_keys: list[str] = []
    for key in (primary_result_key, *result_keys):
        if not isinstance(key, str):
            continue
        trimmed = key.strip()
        if trimmed == "" or trimmed in normalized_keys:
            continue
        normalized_keys.append(trimmed)
    return normalized_keys


def store_primary_result_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID | str,
    run_id: UUID | str,
    artifact_key: str,
    content: JSONObject,
    status_value: str,
    result_keys: list[str] | tuple[str, ...] = (),
    workspace_patch: JSONObject | None = None,
) -> None:
    """Store one primary result artifact and record standardized workspace keys."""
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=artifact_key,
        media_type="application/json",
        content=content,
    )
    patch: JSONObject = {
        "status": status_value,
        _PRIMARY_RESULT_WORKSPACE_KEY: artifact_key,
        _RESULT_KEYS_WORKSPACE_KEY: _normalized_result_keys(
            primary_result_key=artifact_key,
            result_keys=result_keys,
        ),
        "error": None,
    }
    if workspace_patch is not None:
        patch.update(workspace_patch)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch=patch,
    )


def load_primary_result_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID | str,
    run_id: UUID | str,
) -> JSONObject:
    """Load the standardized primary result artifact content for one run."""
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace for run '{run_id}' was not found.",
        )
    primary_result_key = workspace.snapshot.get(_PRIMARY_RESULT_WORKSPACE_KEY)
    if not isinstance(primary_result_key, str) or primary_result_key.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' does not expose a primary result artifact yet.",
        )
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=primary_result_key,
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Primary result artifact '{primary_result_key}' for run '{run_id}' "
                "is missing."
            ),
        )
    return artifact.content


__all__ = [
    "_normalized_result_keys",
    "load_primary_result_artifact",
    "store_primary_result_artifact",
]
