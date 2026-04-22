"""Process-local harness run registry for the standalone harness service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.types.common import JSONObject  # noqa: TC001

HarnessRunStatus = str
_INITIAL_PROGRESS_PERCENT = 0.0
_RUNNING_PROGRESS_FLOOR = 0.05
_COMPLETED_PROGRESS_PERCENT = 1.0


def _default_progress_percent(*, status: str, current: float | None = None) -> float:
    normalized_status = status.strip().lower()
    if normalized_status == "completed":
        return _COMPLETED_PROGRESS_PERCENT
    if normalized_status == "running":
        if current is None:
            return _RUNNING_PROGRESS_FLOOR
        return max(current, _RUNNING_PROGRESS_FLOOR)
    if current is None:
        return _INITIAL_PROGRESS_PERCENT
    return current


def _default_phase_for_status(status: str) -> str:
    normalized_status = status.strip().lower()
    if normalized_status == "paused":
        return "approval"
    return normalized_status or "queued"


def _default_message_for_status(status: str) -> str:
    normalized_status = status.strip().lower()
    if normalized_status == "queued":
        return "Run queued."
    if normalized_status == "running":
        return "Run is in progress."
    if normalized_status == "completed":
        return "Run completed."
    if normalized_status == "failed":
        return "Run failed."
    if normalized_status == "paused":
        return "Run paused pending approval."
    return f"Run status updated to {normalized_status or status}."


@dataclass(frozen=True, slots=True)
class HarnessRunRecord:
    """One harness run tracked by the service."""

    id: str
    space_id: str
    harness_id: str
    title: str
    status: HarnessRunStatus
    input_payload: JSONObject
    graph_service_status: str
    graph_service_version: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessRunProgressRecord:
    """Current progress snapshot for one harness run."""

    space_id: str
    run_id: str
    status: str
    phase: str
    message: str
    progress_percent: float
    completed_steps: int
    total_steps: int | None
    resume_point: str | None
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessRunEventRecord:
    """One immutable lifecycle event emitted for a harness run."""

    id: str
    space_id: str
    run_id: str
    event_type: str
    status: str
    message: str
    progress_percent: float | None
    payload: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessRunRegistry:
    """Store and retrieve harness run metadata."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, HarnessRunRecord] = {}
        self._runs_by_space: dict[str, list[str]] = {}
        self._progress_by_run: dict[str, HarnessRunProgressRecord] = {}
        self._events_by_run: dict[str, list[HarnessRunEventRecord]] = {}

    def create_run(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        input_payload: JSONObject,
        graph_service_status: str,
        graph_service_version: str,
    ) -> HarnessRunRecord:
        """Create and store one harness run."""
        now = datetime.now(UTC)
        run = HarnessRunRecord(
            id=str(uuid4()),
            space_id=str(space_id),
            harness_id=harness_id,
            title=title,
            status="queued",
            input_payload=input_payload,
            graph_service_status=graph_service_status,
            graph_service_version=graph_service_version,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._runs[run.id] = run
            self._runs_by_space.setdefault(run.space_id, []).append(run.id)
            self._progress_by_run[run.id] = HarnessRunProgressRecord(
                space_id=run.space_id,
                run_id=run.id,
                status=run.status,
                phase="queued",
                message="Run created and queued.",
                progress_percent=_INITIAL_PROGRESS_PERCENT,
                completed_steps=0,
                total_steps=None,
                resume_point=None,
                metadata={},
                created_at=now,
                updated_at=now,
            )
            self._events_by_run[run.id] = [
                HarnessRunEventRecord(
                    id=str(uuid4()),
                    space_id=run.space_id,
                    run_id=run.id,
                    event_type="run.created",
                    status=run.status,
                    message="Run created and queued.",
                    progress_percent=_INITIAL_PROGRESS_PERCENT,
                    payload={"harness_id": run.harness_id, "title": run.title},
                    created_at=now,
                    updated_at=now,
                ),
            ]
        return run

    def list_runs(self, *, space_id: UUID | str) -> list[HarnessRunRecord]:
        """List runs for one research space in reverse creation order."""
        normalized_space_id = str(space_id)
        with self._lock:
            run_ids = tuple(reversed(self._runs_by_space.get(normalized_space_id, [])))
            return [self._runs[run_id] for run_id in run_ids]

    def count_runs(self, *, space_id: UUID | str) -> int:
        """Return how many runs belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return len(self._runs_by_space.get(normalized_space_id, []))

    def get_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        """Return one run if it belongs to the supplied space."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        with self._lock:
            run = self._runs.get(normalized_run_id)
            if run is None or run.space_id != normalized_space_id:
                return None
            return run

    def get_run_fast(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunRecord | None:
        """Return one run using the cheapest available lookup path."""
        return self.get_run(space_id=space_id, run_id=run_id)

    def has_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> bool:
        """Report whether one run exists inside the supplied space."""
        return self.get_run_fast(space_id=space_id, run_id=run_id) is not None

    def delete_run(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> bool:
        """Delete one run and its progress/events if it belongs to the supplied space."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        with self._lock:
            run = self._runs.get(normalized_run_id)
            if run is None or run.space_id != normalized_space_id:
                return False
            del self._runs[normalized_run_id]
            run_ids = self._runs_by_space.get(normalized_space_id, [])
            self._runs_by_space[normalized_space_id] = [
                existing_run_id
                for existing_run_id in run_ids
                if existing_run_id != normalized_run_id
            ]
            self._progress_by_run.pop(normalized_run_id, None)
            self._events_by_run.pop(normalized_run_id, None)
            return True

    def replace_run_input_payload(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        input_payload: JSONObject,
    ) -> HarnessRunRecord | None:
        """Replace the stored input payload for one run."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        with self._lock:
            existing = self._runs.get(normalized_run_id)
            if existing is None or existing.space_id != normalized_space_id:
                return None
            updated = HarnessRunRecord(
                id=existing.id,
                space_id=existing.space_id,
                harness_id=existing.harness_id,
                title=existing.title,
                status=existing.status,
                input_payload=input_payload,
                graph_service_status=existing.graph_service_status,
                graph_service_version=existing.graph_service_version,
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
            )
            self._runs[normalized_run_id] = updated
            return updated

    def get_progress(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunProgressRecord | None:
        """Return the current progress snapshot for one run."""
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return None
        with self._lock:
            return self._progress_by_run.get(run.id)

    def get_progress_fast(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunProgressRecord | None:
        """Return progress using the cheapest available lookup path."""
        return self.get_progress(space_id=space_id, run_id=run_id)

    def set_run_status(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        status: HarnessRunStatus,
        existing_progress: HarnessRunProgressRecord | None = None,
    ) -> HarnessRunRecord | None:
        """Update one run status."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        with self._lock:
            existing = self._runs.get(normalized_run_id)
            if existing is None or existing.space_id != normalized_space_id:
                return None
            updated = HarnessRunRecord(
                id=existing.id,
                space_id=existing.space_id,
                harness_id=existing.harness_id,
                title=existing.title,
                status=status,
                input_payload=existing.input_payload,
                graph_service_status=existing.graph_service_status,
                graph_service_version=existing.graph_service_version,
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
            )
            self._runs[normalized_run_id] = updated
            now = updated.updated_at
            current_progress = existing_progress
            if current_progress is not None and (
                current_progress.run_id != normalized_run_id
                or current_progress.space_id != normalized_space_id
            ):
                current_progress = None
            if current_progress is None:
                current_progress = self._progress_by_run.get(normalized_run_id)
            if current_progress is None:
                self._progress_by_run[normalized_run_id] = HarnessRunProgressRecord(
                    space_id=updated.space_id,
                    run_id=updated.id,
                    status=status,
                    phase=_default_phase_for_status(status),
                    message=_default_message_for_status(status),
                    progress_percent=_default_progress_percent(status=status),
                    completed_steps=0,
                    total_steps=None,
                    resume_point=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                )
            else:
                self._progress_by_run[normalized_run_id] = HarnessRunProgressRecord(
                    space_id=current_progress.space_id,
                    run_id=current_progress.run_id,
                    status=status,
                    phase=_default_phase_for_status(status),
                    message=_default_message_for_status(status),
                    progress_percent=_default_progress_percent(
                        status=status,
                        current=current_progress.progress_percent,
                    ),
                    completed_steps=current_progress.completed_steps,
                    total_steps=current_progress.total_steps,
                    resume_point=(
                        current_progress.resume_point
                        if status.strip().lower() == "paused"
                        else None
                    ),
                    metadata=current_progress.metadata,
                    created_at=current_progress.created_at,
                    updated_at=now,
                )
            progress = self._progress_by_run[normalized_run_id]
            self._events_by_run.setdefault(normalized_run_id, []).append(
                HarnessRunEventRecord(
                    id=str(uuid4()),
                    space_id=updated.space_id,
                    run_id=updated.id,
                    event_type="run.status_changed",
                    status=updated.status,
                    message=progress.message,
                    progress_percent=progress.progress_percent,
                    payload={"phase": progress.phase},
                    created_at=now,
                    updated_at=now,
                ),
            )
            return updated

    def set_progress(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        resume_point: str | None = None,
        clear_resume_point: bool = False,
        metadata: JSONObject | None = None,
        merge_existing: bool = True,
    ) -> HarnessRunProgressRecord | None:
        """Update the current progress snapshot and emit a progress event."""
        normalized_run_id = str(run_id)
        normalized_space_id = str(space_id)
        with self._lock:
            run = self._runs.get(normalized_run_id)
            if run is None or run.space_id != normalized_space_id:
                return None
            existing = (
                self._progress_by_run.get(normalized_run_id) if merge_existing else None
            )
            now = datetime.now(UTC)
            existing_metadata = existing.metadata if existing is not None else {}
            merged_metadata = {
                **existing_metadata,
                **(metadata or {}),
            }
            updated = HarnessRunProgressRecord(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                status=run.status,
                phase=phase.strip()
                or (existing.phase if existing is not None else run.status),
                message=message.strip()
                or (
                    existing.message
                    if existing is not None
                    else _default_message_for_status(run.status)
                ),
                progress_percent=max(0.0, min(progress_percent, 1.0)),
                completed_steps=(
                    completed_steps
                    if completed_steps is not None
                    else (existing.completed_steps if existing is not None else 0)
                ),
                total_steps=(
                    total_steps
                    if total_steps is not None
                    else (existing.total_steps if existing is not None else None)
                ),
                resume_point=(
                    None
                    if clear_resume_point
                    else (
                        resume_point
                        if resume_point is not None
                        else (existing.resume_point if existing is not None else None)
                    )
                ),
                metadata=merged_metadata,
                created_at=existing.created_at if existing is not None else now,
                updated_at=now,
            )
            self._progress_by_run[normalized_run_id] = updated
            self._events_by_run.setdefault(normalized_run_id, []).append(
                HarnessRunEventRecord(
                    id=str(uuid4()),
                    space_id=normalized_space_id,
                    run_id=normalized_run_id,
                    event_type="run.progress",
                    status=run.status,
                    message=updated.message,
                    progress_percent=updated.progress_percent,
                    payload={
                        "phase": updated.phase,
                        "resume_point": updated.resume_point,
                        "completed_steps": updated.completed_steps,
                        "total_steps": updated.total_steps,
                        "metadata": updated.metadata,
                    },
                    created_at=now,
                    updated_at=now,
                ),
            )
            return updated

    def list_events(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        limit: int = 100,
    ) -> list[HarnessRunEventRecord]:
        """Return lifecycle events for one run in creation order."""
        run = self.get_run(space_id=space_id, run_id=run_id)
        if run is None:
            return []
        with self._lock:
            return list(self._events_by_run.get(run.id, []))[:limit]

    def record_event(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        event_type: str,
        message: str,
        payload: JSONObject | None = None,
        progress_percent: float | None = None,
    ) -> HarnessRunEventRecord | None:
        """Append one lifecycle event for a run."""
        normalized_run_id = str(run_id)
        normalized_space_id = str(space_id)
        with self._lock:
            run = self._runs.get(normalized_run_id)
            if run is None or run.space_id != normalized_space_id:
                return None
            progress = self._progress_by_run.get(normalized_run_id)
            now = datetime.now(UTC)
            event = HarnessRunEventRecord(
                id=str(uuid4()),
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                event_type=event_type.strip() or "run.event",
                status=run.status,
                message=message.strip() or "Run event recorded.",
                progress_percent=(
                    progress_percent
                    if progress_percent is not None
                    else (progress.progress_percent if progress is not None else None)
                ),
                payload=payload or {},
                created_at=now,
                updated_at=now,
            )
            self._events_by_run.setdefault(normalized_run_id, []).append(event)
            return event


__all__ = [
    "HarnessRunEventRecord",
    "HarnessRunProgressRecord",
    "HarnessRunRecord",
    "HarnessRunRegistry",
]
