"""Service-local artifact and workspace storage for harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.types.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from .run_registry import HarnessRunRecord


@dataclass(frozen=True, slots=True)
class HarnessArtifactRecord:
    """One stored artifact associated with a harness run."""

    space_id: str
    run_id: str
    key: str
    media_type: str
    content: JSONObject
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessWorkspaceRecord:
    """One stored workspace snapshot associated with a harness run."""

    space_id: str
    run_id: str
    snapshot: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessArtifactStore:
    """Store artifacts and workspace snapshots for harness runs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._artifacts: dict[tuple[str, str], dict[str, HarnessArtifactRecord]] = {}
        self._workspaces: dict[tuple[str, str], HarnessWorkspaceRecord] = {}

    def seed_for_run(self, *, run: HarnessRunRecord) -> None:
        """Create the initial workspace snapshot and manifest artifact for a run."""
        now = datetime.now(UTC)
        workspace_snapshot: JSONObject = {
            "space_id": run.space_id,
            "run_id": run.id,
            "harness_id": run.harness_id,
            "title": run.title,
            "status": run.status,
            "input_payload": run.input_payload,
            "graph_service": {
                "status": run.graph_service_status,
                "version": run.graph_service_version,
            },
            "artifact_keys": ["run_manifest"],
        }
        manifest_content: JSONObject = {
            "run_id": run.id,
            "space_id": run.space_id,
            "harness_id": run.harness_id,
            "title": run.title,
            "status": run.status,
            "created_at": run.created_at.isoformat(),
            "graph_service_status": run.graph_service_status,
            "graph_service_version": run.graph_service_version,
        }
        artifact = HarnessArtifactRecord(
            space_id=run.space_id,
            run_id=run.id,
            key="run_manifest",
            media_type="application/json",
            content=manifest_content,
            created_at=now,
            updated_at=now,
        )
        workspace = HarnessWorkspaceRecord(
            space_id=run.space_id,
            run_id=run.id,
            snapshot=workspace_snapshot,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._artifacts[(run.space_id, run.id)] = {artifact.key: artifact}
            self._workspaces[(run.space_id, run.id)] = workspace

    def list_artifacts(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessArtifactRecord]:
        """Return all artifacts for one run."""
        key = (str(space_id), str(run_id))
        with self._lock:
            artifacts = self._artifacts.get(key, {})
            return list(artifacts.values())

    def get_artifact(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
    ) -> HarnessArtifactRecord | None:
        """Return one artifact for one run."""
        key = (str(space_id), str(run_id))
        normalized_artifact_key = artifact_key.strip()
        if not normalized_artifact_key:
            return None
        with self._lock:
            artifacts = self._artifacts.get(key, {})
            return artifacts.get(normalized_artifact_key)

    def get_workspace(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessWorkspaceRecord | None:
        """Return the workspace snapshot for one run."""
        key = (str(space_id), str(run_id))
        with self._lock:
            return self._workspaces.get(key)

    def delete_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> bool:
        """Delete all artifacts and workspace state for one run."""
        workspace_key = (str(space_id), str(run_id))
        with self._lock:
            had_workspace = self._workspaces.pop(workspace_key, None) is not None
            had_artifacts = self._artifacts.pop(workspace_key, None) is not None
            return had_workspace or had_artifacts

    def put_artifact(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
        media_type: str,
        content: JSONObject,
    ) -> HarnessArtifactRecord:
        """Store one artifact and reflect it into the workspace snapshot."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        normalized_key = artifact_key.strip()
        now = datetime.now(UTC)
        artifact = HarnessArtifactRecord(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
            key=normalized_key,
            media_type=media_type,
            content=content,
            created_at=now,
            updated_at=now,
        )
        workspace_key = (normalized_space_id, normalized_run_id)
        with self._lock:
            artifacts = self._artifacts.setdefault(workspace_key, {})
            artifacts[normalized_key] = artifact
            workspace = self._workspaces.get(workspace_key)
            if workspace is not None:
                artifact_keys = workspace.snapshot.get("artifact_keys", [])
                normalized_artifact_keys = (
                    list(artifact_keys) if isinstance(artifact_keys, list) else []
                )
                if normalized_key not in normalized_artifact_keys:
                    normalized_artifact_keys.append(normalized_key)
                updated_snapshot: JSONObject = {
                    **workspace.snapshot,
                    "artifact_keys": normalized_artifact_keys,
                    "last_updated_artifact_key": normalized_key,
                }
                self._workspaces[workspace_key] = HarnessWorkspaceRecord(
                    space_id=workspace.space_id,
                    run_id=workspace.run_id,
                    snapshot=updated_snapshot,
                    created_at=workspace.created_at,
                    updated_at=now,
                )
        return artifact

    def patch_workspace(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        patch: JSONObject,
    ) -> HarnessWorkspaceRecord | None:
        """Merge one patch into the workspace snapshot."""
        workspace_key = (str(space_id), str(run_id))
        now = datetime.now(UTC)
        with self._lock:
            workspace = self._workspaces.get(workspace_key)
            if workspace is None:
                return None
            updated_snapshot: JSONObject = {**workspace.snapshot, **patch}
            updated = HarnessWorkspaceRecord(
                space_id=workspace.space_id,
                run_id=workspace.run_id,
                snapshot=updated_snapshot,
                created_at=workspace.created_at,
                updated_at=now,
            )
            self._workspaces[workspace_key] = updated
            return updated


__all__ = [
    "HarnessArtifactRecord",
    "HarnessArtifactStore",
    "HarnessWorkspaceRecord",
]
