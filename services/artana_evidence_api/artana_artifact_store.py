"""Artana-backed artifact store adapter."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from artana_evidence_api.artana_store_records import (
    _fallback_manifest_artifact,
    _fallback_workspace_record,
    _summary_event_payload,
)
from artana_evidence_api.artana_stores import (
    _ARTIFACT_PREFIX,
    _FAST_READ_TIMEOUT_SECONDS,
    _LOGGER,
    _WORKSPACE_SUMMARY,
    _append_run_summary_with_retry,
    _parse_timestamp,
    _payload_json_object,
    _payload_string,
    _step_key,
    _summary_payload,
    _utcnow,
)
from artana_evidence_api.artifact_store import (
    HarnessArtifactRecord,
    HarnessArtifactStore,
    HarnessWorkspaceRecord,
)
from artana_evidence_api.run_registry import (
    HarnessRunProgressRecord,
    HarnessRunRecord,
    HarnessRunRegistry,
)

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.types.common import JSONObject


class ArtanaBackedHarnessArtifactStore(HarnessArtifactStore):
    """Store artifacts and workspace snapshots in Artana summaries."""

    def __init__(
        self,
        *,
        runtime: GraphHarnessKernelRuntime,
        run_registry: HarnessRunRegistry | None = None,
    ) -> None:
        super().__init__()
        self._runtime = runtime
        self._run_registry = run_registry

    def _fallback_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        if self._run_registry is None:
            return None
        return self._run_registry.get_run_fast(space_id=space_id, run_id=run_id)

    def _fallback_progress(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunProgressRecord | None:
        if self._run_registry is None:
            return None
        return self._run_registry.get_progress_fast(space_id=space_id, run_id=run_id)

    def _artifact_summary_type(self, artifact_key: str) -> str:
        return f"{_ARTIFACT_PREFIX}{artifact_key}"

    def seed_for_run(self, *, run: HarnessRunRecord) -> None:
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
        self.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="run_manifest",
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
            },
        )
        self._write_workspace(
            space_id=run.space_id,
            run_id=run.id,
            snapshot=workspace_snapshot,
            created_at=run.created_at,
            updated_at=run.created_at,
        )

    def _write_workspace(
        self,
        *,
        space_id: str,
        run_id: str,
        snapshot: JSONObject,
        created_at: datetime,
        updated_at: datetime,
    ) -> HarnessWorkspaceRecord:
        _append_run_summary_with_retry(
            runtime=self._runtime,
            run_id=run_id,
            tenant_id=space_id,
            summary_type=_WORKSPACE_SUMMARY,
            summary_json=json.dumps(
                {
                    "snapshot": snapshot,
                    "created_at": created_at.isoformat(),
                    "updated_at": updated_at.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            step_key=_step_key("workspace"),
        )
        return HarnessWorkspaceRecord(
            space_id=space_id,
            run_id=run_id,
            snapshot=snapshot,
            created_at=created_at,
            updated_at=updated_at,
        )

    def list_artifacts(  # noqa: PLR0911
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessArtifactRecord]:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        artifact_by_key: dict[str, HarnessArtifactRecord] = {}
        try:
            runtime_events = self._runtime.get_events(
                run_id=normalized_run_id,
                tenant_id=normalized_space_id,
                timeout_seconds=_FAST_READ_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            run = self._fallback_run(space_id=space_id, run_id=run_id)
            if run is None:
                return []
            return [
                _fallback_manifest_artifact(
                    run=run,
                    degraded_reason="artifact_list_read_timeout",
                ),
            ]
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to load Artana run artifacts; falling back to degraded manifest.",
                extra={"run_id": normalized_run_id, "space_id": normalized_space_id},
                exc_info=exc,
            )
            run = self._fallback_run(space_id=space_id, run_id=run_id)
            if run is None:
                return []
            return [
                _fallback_manifest_artifact(
                    run=run,
                    degraded_reason="artifact_list_read_error",
                ),
            ]
        for event in runtime_events:
            if event.event_type.value != "run_summary":
                continue
            summary_event = _summary_event_payload(event)
            if summary_event is None:
                continue
            summary_type, payload = summary_event
            if not summary_type.startswith(_ARTIFACT_PREFIX):
                continue
            artifact_key = summary_type.removeprefix(_ARTIFACT_PREFIX)
            artifact_by_key[artifact_key] = HarnessArtifactRecord(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                key=artifact_key,
                media_type=_payload_string(
                    payload,
                    "media_type",
                    default="application/json",
                ),
                content=_payload_json_object(payload, "content"),
                created_at=_parse_timestamp(payload.get("created_at"))
                or event.timestamp,
                updated_at=_parse_timestamp(payload.get("updated_at"))
                or event.timestamp,
            )
        if artifact_by_key:
            return list(artifact_by_key.values())
        run = self._fallback_run(space_id=space_id, run_id=run_id)
        if run is None:
            return []
        return [
            _fallback_manifest_artifact(
                run=run,
                degraded_reason="artifact_list_unavailable",
            ),
        ]

    def get_artifact(  # noqa: PLR0911
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
    ) -> HarnessArtifactRecord | None:
        normalized_key = artifact_key.strip()
        if normalized_key == "":
            return None
        try:
            summary = self._runtime.get_latest_run_summary(
                run_id=str(run_id),
                tenant_id=str(space_id),
                summary_type=self._artifact_summary_type(normalized_key),
                timeout_seconds=_FAST_READ_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            run = self._fallback_run(space_id=space_id, run_id=run_id)
            if run is None or normalized_key != "run_manifest":
                return None
            return _fallback_manifest_artifact(
                run=run,
                degraded_reason="artifact_read_timeout",
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to load Artana artifact summary; falling back when possible.",
                extra={"run_id": str(run_id), "space_id": str(space_id)},
                exc_info=exc,
            )
            run = self._fallback_run(space_id=space_id, run_id=run_id)
            if run is None or normalized_key != "run_manifest":
                return None
            return _fallback_manifest_artifact(
                run=run,
                degraded_reason="artifact_read_error",
            )
        payload = _summary_payload(summary)
        if payload is None:
            return None
        timestamp = (
            _parse_timestamp(payload.get("updated_at"))
            or getattr(summary, "created_at", None)
            or _utcnow()
        )
        created_at = _parse_timestamp(payload.get("created_at")) or timestamp
        return HarnessArtifactRecord(
            space_id=str(space_id),
            run_id=str(run_id),
            key=normalized_key,
            media_type=_payload_string(
                payload,
                "media_type",
                default="application/json",
            ),
            content=_payload_json_object(payload, "content"),
            created_at=created_at,
            updated_at=timestamp,
        )

    def get_workspace(  # noqa: PLR0911
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessWorkspaceRecord | None:
        try:
            summary = self._runtime.get_latest_run_summary(
                run_id=str(run_id),
                tenant_id=str(space_id),
                summary_type=_WORKSPACE_SUMMARY,
                timeout_seconds=_FAST_READ_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            run = self._fallback_run(space_id=space_id, run_id=run_id)
            if run is None:
                return None
            progress = self._fallback_progress(space_id=space_id, run_id=run_id)
            return _fallback_workspace_record(
                run=run,
                progress=progress,
                degraded_reason="workspace_read_timeout",
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to load Artana workspace summary; falling back to degraded workspace.",
                extra={"run_id": str(run_id), "space_id": str(space_id)},
                exc_info=exc,
            )
            run = self._fallback_run(space_id=space_id, run_id=run_id)
            if run is None:
                return None
            progress = self._fallback_progress(space_id=space_id, run_id=run_id)
            return _fallback_workspace_record(
                run=run,
                progress=progress,
                degraded_reason="workspace_read_error",
            )
        payload = _summary_payload(summary)
        if payload is None:
            return None
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict):
            return None
        return HarnessWorkspaceRecord(
            space_id=str(space_id),
            run_id=str(run_id),
            snapshot=snapshot,
            created_at=_parse_timestamp(payload.get("created_at")) or _utcnow(),
            updated_at=_parse_timestamp(payload.get("updated_at")) or _utcnow(),
        )

    def put_artifact(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
        media_type: str,
        content: JSONObject,
    ) -> HarnessArtifactRecord:
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        normalized_key = artifact_key.strip()
        now = _utcnow()
        artifact = HarnessArtifactRecord(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
            key=normalized_key,
            media_type=media_type,
            content=content,
            created_at=now,
            updated_at=now,
        )
        _append_run_summary_with_retry(
            runtime=self._runtime,
            run_id=normalized_run_id,
            tenant_id=normalized_space_id,
            summary_type=self._artifact_summary_type(normalized_key),
            summary_json=json.dumps(
                {
                    "media_type": media_type,
                    "content": content,
                    "created_at": artifact.created_at.isoformat(),
                    "updated_at": artifact.updated_at.isoformat(),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            step_key=_step_key(f"artifact_{normalized_key}"),
        )
        workspace = self.get_workspace(space_id=space_id, run_id=run_id)
        if workspace is not None:
            artifact_keys = workspace.snapshot.get("artifact_keys")
            normalized_artifact_keys = (
                list(artifact_keys) if isinstance(artifact_keys, list) else []
            )
            if normalized_key not in normalized_artifact_keys:
                normalized_artifact_keys.append(normalized_key)
            self._write_workspace(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                snapshot={
                    **workspace.snapshot,
                    "artifact_keys": normalized_artifact_keys,
                    "last_updated_artifact_key": normalized_key,
                },
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
        workspace = self.get_workspace(space_id=space_id, run_id=run_id)
        if workspace is None:
            return None
        return self._write_workspace(
            space_id=str(space_id),
            run_id=str(run_id),
            snapshot={**workspace.snapshot, **patch},
            created_at=workspace.created_at,
            updated_at=_utcnow(),
        )

    def delete_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> bool:
        """Report whether runtime-backed artifacts exist for one run.

        The Artana runtime does not yet expose a summary-deletion API, so this
        adapter cannot physically remove stored run summaries. Returning whether
        a workspace or artifact exists still lets composed workflows avoid the
        inherited in-memory-lock path and keep cleanup idempotent.
        """

        return self.get_workspace(space_id=space_id, run_id=run_id) is not None or bool(
            self.list_artifacts(space_id=space_id, run_id=run_id),
        )


__all__ = ["ArtanaBackedHarnessArtifactStore"]
