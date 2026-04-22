"""Service-local schedule storage contracts for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.schedule_policy import normalize_schedule_cadence
from artana_evidence_api.types.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class HarnessScheduleRecord:
    """One stored harness schedule definition."""

    id: str
    space_id: str
    harness_id: str
    title: str
    cadence: str
    status: str
    created_by: str
    configuration: JSONObject
    metadata: JSONObject
    last_run_id: str | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    active_trigger_claim_id: str | None = None
    active_trigger_claimed_at: datetime | None = None


def _normalized_utc_datetime(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _claim_is_stale(
    *,
    claimed_at: datetime | None,
    now: datetime,
    ttl_seconds: int,
) -> bool:
    if claimed_at is None:
        return True
    return claimed_at <= now - timedelta(seconds=ttl_seconds)


class HarnessScheduleStore:
    """Store and retrieve harness schedule definitions."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._schedules: dict[str, HarnessScheduleRecord] = {}

    def create_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        cadence: str,
        created_by: UUID | str,
        configuration: JSONObject,
        metadata: JSONObject,
        status: str = "active",
    ) -> HarnessScheduleRecord:
        """Persist one new schedule definition."""
        now = datetime.now(UTC)
        normalized_cadence = normalize_schedule_cadence(cadence)
        record = HarnessScheduleRecord(
            id=str(uuid4()),
            space_id=str(space_id),
            harness_id=harness_id,
            title=title,
            cadence=normalized_cadence,
            status=status,
            created_by=str(created_by),
            configuration=configuration,
            metadata=metadata,
            last_run_id=None,
            last_run_at=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._schedules[record.id] = record
        return record

    def list_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessScheduleRecord]:
        """Return schedules for one research space ordered by freshness."""
        normalized_space_id = str(space_id)
        with self._lock:
            schedules = [
                record
                for record in self._schedules.values()
                if record.space_id == normalized_space_id
            ]
        return sorted(schedules, key=lambda record: record.updated_at, reverse=True)

    def count_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        """Return how many schedules belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return sum(
                1
                for record in self._schedules.values()
                if record.space_id == normalized_space_id
            )

    def list_all_schedules(
        self,
        *,
        status: str | None = None,
    ) -> list[HarnessScheduleRecord]:
        """Return all schedules, optionally filtered by status."""
        normalized_status = status.strip() if isinstance(status, str) else None
        with self._lock:
            schedules = list(self._schedules.values())
        filtered = [
            record
            for record in schedules
            if normalized_status is None or record.status == normalized_status
        ]
        return sorted(filtered, key=lambda record: record.updated_at, reverse=True)

    def get_schedule(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        """Return one schedule definition."""
        with self._lock:
            schedule = self._schedules.get(str(schedule_id))
        if schedule is None or schedule.space_id != str(space_id):
            return None
        return schedule

    def update_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        title: str | None = None,
        cadence: str | None = None,
        status: str | None = None,
        configuration: JSONObject | None = None,
        metadata: JSONObject | None = None,
        last_run_id: UUID | str | None = None,
        last_run_at: datetime | None = None,
    ) -> HarnessScheduleRecord | None:
        """Update one stored schedule definition."""
        existing = self.get_schedule(space_id=space_id, schedule_id=schedule_id)
        if existing is None:
            return None
        updated = HarnessScheduleRecord(
            id=existing.id,
            space_id=existing.space_id,
            harness_id=existing.harness_id,
            title=(
                title
                if isinstance(title, str) and title.strip() != ""
                else existing.title
            ),
            cadence=(
                normalize_schedule_cadence(cadence)
                if isinstance(cadence, str) and cadence.strip() != ""
                else existing.cadence
            ),
            status=(
                status
                if isinstance(status, str) and status.strip() != ""
                else existing.status
            ),
            created_by=existing.created_by,
            configuration=(
                configuration if configuration is not None else existing.configuration
            ),
            metadata=metadata if metadata is not None else existing.metadata,
            last_run_id=(
                str(last_run_id) if last_run_id is not None else existing.last_run_id
            ),
            last_run_at=(
                last_run_at if last_run_at is not None else existing.last_run_at
            ),
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
            active_trigger_claim_id=existing.active_trigger_claim_id,
            active_trigger_claimed_at=existing.active_trigger_claimed_at,
        )
        with self._lock:
            self._schedules[existing.id] = updated
        return updated

    def acquire_trigger_claim(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        claim_id: UUID | str,
        claimed_at: datetime | None = None,
        ttl_seconds: int = 30,
    ) -> HarnessScheduleRecord | None:
        """Try to claim one schedule trigger across concurrent callers."""
        normalized_now = _normalized_utc_datetime(claimed_at)
        normalized_schedule_id = str(schedule_id)
        normalized_space_id = str(space_id)
        normalized_claim_id = str(claim_id)
        with self._lock:
            existing = self._schedules.get(normalized_schedule_id)
            if existing is None or existing.space_id != normalized_space_id:
                return None
            if (
                existing.active_trigger_claim_id is not None
                and existing.active_trigger_claim_id != normalized_claim_id
                and not _claim_is_stale(
                    claimed_at=existing.active_trigger_claimed_at,
                    now=normalized_now,
                    ttl_seconds=ttl_seconds,
                )
            ):
                return None
            updated = replace(
                existing,
                active_trigger_claim_id=normalized_claim_id,
                active_trigger_claimed_at=normalized_now,
                updated_at=datetime.now(UTC),
            )
            self._schedules[normalized_schedule_id] = updated
        return updated

    def release_trigger_claim(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        claim_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        """Release one previously-acquired schedule trigger claim."""
        normalized_schedule_id = str(schedule_id)
        normalized_space_id = str(space_id)
        normalized_claim_id = str(claim_id)
        with self._lock:
            existing = self._schedules.get(normalized_schedule_id)
            if existing is None or existing.space_id != normalized_space_id:
                return None
            if existing.active_trigger_claim_id != normalized_claim_id:
                return None
            updated = replace(
                existing,
                active_trigger_claim_id=None,
                active_trigger_claimed_at=None,
                updated_at=datetime.now(UTC),
            )
            self._schedules[normalized_schedule_id] = updated
        return updated


__all__ = ["HarnessScheduleRecord", "HarnessScheduleStore"]
