"""Due-run selection and queueing for recurring graph-harness workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.composition import get_graph_harness_kernel_runtime
from artana_evidence_api.config import get_settings
from artana_evidence_api.continuous_learning_runtime import (
    ActiveScheduleRunConflictError,
    ScheduleTriggerClaimConflictError,
    normalize_seed_entity_ids,
    queue_schedule_bound_continuous_learning_run,
)
from artana_evidence_api.database import SessionLocal, set_session_rls_context
from artana_evidence_api.run_budget import (
    budget_from_json,
    resolve_continuous_learning_run_budget,
)
from artana_evidence_api.schedule_policy import is_schedule_due
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessScheduleStore,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from artana_evidence_api.schedule_store import (
        HarnessScheduleRecord,
        HarnessScheduleStore,
    )

LOGGER = logging.getLogger(__name__)
_SCHEDULER_HEARTBEAT_PATH = "logs/artana-evidence-api-scheduler-heartbeat.json"
_SCHEDULER_HEARTBEAT_KEEPALIVE_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class TriggeredScheduleRun:
    """One schedule execution triggered by a scheduler tick."""

    schedule_id: str
    space_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class SchedulerTickResult:
    """Summary of one scheduler tick."""

    started_at: datetime
    completed_at: datetime
    scanned_schedule_count: int
    due_schedule_count: int
    triggered_runs: tuple[TriggeredScheduleRun, ...]
    errors: tuple[str, ...]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip() for item in value if isinstance(item, str) and item.strip() != ""
    ]


def _schedule_configuration(schedule: HarnessScheduleRecord) -> JSONObject:
    return schedule.configuration if isinstance(schedule.configuration, dict) else {}


def _configuration_string(
    configuration: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = configuration.get(key)
    return value if isinstance(value, str) else default


def _configuration_optional_string(
    configuration: JSONObject,
    key: str,
) -> str | None:
    value = configuration.get(key)
    return value if isinstance(value, str) else None


def _configuration_int(
    configuration: JSONObject,
    key: str,
    *,
    default: int,
) -> int:
    value = configuration.get(key)
    return value if isinstance(value, int) else default


async def _queue_schedule_run(
    *,
    schedule: HarnessScheduleRecord,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    schedule_store: HarnessScheduleStore,
) -> TriggeredScheduleRun:
    configuration = _schedule_configuration(schedule)
    seed_entity_ids = normalize_seed_entity_ids(
        _string_list(configuration.get("seed_entity_ids")),
    )
    if not seed_entity_ids:
        message = f"Schedule '{schedule.id}' is missing required seed_entity_ids"
        raise ValueError(message)
    run_budget = resolve_continuous_learning_run_budget(
        budget_from_json(configuration.get("run_budget")),
    )
    run = queue_schedule_bound_continuous_learning_run(
        space_id=UUID(schedule.space_id),
        title=schedule.title,
        seed_entity_ids=seed_entity_ids,
        source_type=_configuration_string(
            configuration,
            "source_type",
            default="pubmed",
        ),
        relation_types=_string_list(configuration.get("relation_types")) or None,
        max_depth=_configuration_int(configuration, "max_depth", default=2),
        max_new_proposals=_configuration_int(
            configuration,
            "max_new_proposals",
            default=20,
        ),
        max_next_questions=_configuration_int(
            configuration,
            "max_next_questions",
            default=5,
        ),
        model_id=_configuration_optional_string(configuration, "model_id"),
        schedule_id=schedule.id,
        run_budget=run_budget,
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        schedule_store=schedule_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    artifact_store.patch_workspace(
        space_id=schedule.space_id,
        run_id=run.id,
        patch={
            "schedule_id": schedule.id,
            "queued_by": "scheduler",
            "run_budget": run_budget.model_dump(mode="json"),
        },
    )
    run_registry.record_event(
        space_id=schedule.space_id,
        run_id=run.id,
        event_type="schedule.triggered",
        message="Scheduled run queued for worker execution.",
        payload={"schedule_id": schedule.id, "cadence": schedule.cadence},
        progress_percent=0.0,
    )
    updated_schedule = schedule_store.update_schedule(
        space_id=schedule.space_id,
        schedule_id=schedule.id,
        last_run_id=run.id,
        last_run_at=run.created_at,
    )
    if updated_schedule is None:
        message = f"Schedule '{schedule.id}' disappeared during execution"
        raise RuntimeError(message)
    return TriggeredScheduleRun(
        schedule_id=schedule.id,
        space_id=schedule.space_id,
        run_id=run.id,
    )


def _scheduler_error_message(schedule: HarnessScheduleRecord, exc: Exception) -> str:
    return f"schedule:{schedule.id}:{exc}"


async def run_scheduler_tick(
    *,
    schedule_store: HarnessScheduleStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    now: datetime | None = None,
) -> SchedulerTickResult:
    """Queue all active schedules that are due in the current tick."""
    if isinstance(now, datetime):
        started_at = (
            now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        )
    else:
        started_at = datetime.now(UTC)
    schedules = schedule_store.list_all_schedules(status="active")
    due_schedule_count = 0
    triggered_runs: list[TriggeredScheduleRun] = []
    errors: list[str] = []
    for schedule in schedules:
        try:
            if not is_schedule_due(
                cadence=schedule.cadence,
                last_run_at=schedule.last_run_at,
                now=started_at,
            ):
                continue
            due_schedule_count += 1
            triggered_runs.append(
                await _queue_schedule_run(
                    schedule=schedule,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    schedule_store=schedule_store,
                ),
            )
        except (
            ActiveScheduleRunConflictError,
            ScheduleTriggerClaimConflictError,
        ):
            continue
        except Exception as exc:  # noqa: BLE001
            errors.append(_scheduler_error_message(schedule, exc))
    return SchedulerTickResult(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        scanned_schedule_count=len(schedules),
        due_schedule_count=due_schedule_count,
        triggered_runs=tuple(triggered_runs),
        errors=tuple(errors),
    )


async def run_service_scheduler_tick(
    *,
    now: datetime | None = None,
) -> SchedulerTickResult:
    """Run one queueing tick against the service's durable stores."""
    with SessionLocal() as session:
        set_session_rls_context(session, bypass_rls=False)
        runtime = get_graph_harness_kernel_runtime()
        return await run_scheduler_tick(
            schedule_store=SqlAlchemyHarnessScheduleStore(session),
            run_registry=ArtanaBackedHarnessRunRegistry(
                session=session,
                runtime=runtime,
            ),
            artifact_store=ArtanaBackedHarnessArtifactStore(runtime=runtime),
            now=now,
        )


def _write_heartbeat(path: str, last_result: JSONObject) -> None:
    """Write a heartbeat JSON file for health monitoring."""
    heartbeat_path = Path(path)
    try:
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        with heartbeat_path.open("w") as f:
            json.dump(
                {
                    "last_tick_at": datetime.now(UTC).isoformat(),
                    "pid": os.getpid(),
                    "last_result": last_result,
                },
                f,
            )
    except OSError:
        pass  # Non-critical — don't crash the loop


def _success_heartbeat_payload(result: SchedulerTickResult) -> JSONObject:
    return {
        "loop_status": "ok",
        "scanned": result.scanned_schedule_count,
        "due": result.due_schedule_count,
        "triggered": len(result.triggered_runs),
        "errors": len(result.errors),
    }


def _error_heartbeat_payload(exc: Exception) -> JSONObject:
    return {
        "loop_status": "error",
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _working_heartbeat_payload() -> JSONObject:
    return {
        "loop_status": "working",
    }


@asynccontextmanager
async def _heartbeat_keepalive(
    *,
    path: str,
    interval_seconds: float,
    payload_factory: Callable[[], JSONObject],
) -> AsyncIterator[None]:
    stop_event = asyncio.Event()

    async def _keepalive() -> None:
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                if stop_event.is_set():
                    break
                _write_heartbeat(path, payload_factory())
                continue
            break

    task = asyncio.create_task(_keepalive())
    try:
        yield
    finally:
        stop_event.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def run_scheduler_loop(
    *,
    poll_seconds: float,
    run_once: bool,
) -> None:
    """Run the thin scheduler loop until stopped or after one tick."""
    if poll_seconds <= 0:
        message = "poll_seconds must be greater than zero"
        raise ValueError(message)
    while True:
        _write_heartbeat(
            _SCHEDULER_HEARTBEAT_PATH,
            _working_heartbeat_payload(),
        )
        try:
            async with _heartbeat_keepalive(
                path=_SCHEDULER_HEARTBEAT_PATH,
                interval_seconds=_SCHEDULER_HEARTBEAT_KEEPALIVE_SECONDS,
                payload_factory=_working_heartbeat_payload,
            ):
                result = await run_service_scheduler_tick()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Harness scheduler tick failed")
            _write_heartbeat(
                _SCHEDULER_HEARTBEAT_PATH,
                _error_heartbeat_payload(exc),
            )
            if run_once:
                return
            await asyncio.sleep(poll_seconds)
            continue
        LOGGER.info(
            "Harness scheduler tick completed: scanned=%s due=%s triggered=%s errors=%s",
            result.scanned_schedule_count,
            result.due_schedule_count,
            len(result.triggered_runs),
            len(result.errors),
        )
        _write_heartbeat(
            _SCHEDULER_HEARTBEAT_PATH,
            _success_heartbeat_payload(result),
        )
        if run_once:
            return
        await asyncio.sleep(poll_seconds)


def main() -> None:
    """Start the schedule-queueing loop for recurring harness schedules."""
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    try:
        asyncio.run(
            run_scheduler_loop(
                poll_seconds=settings.scheduler_poll_seconds,
                run_once=settings.scheduler_run_once,
            ),
        )
    except Exception:
        LOGGER.exception("Harness scheduler exited unexpectedly")
        raise


if __name__ == "__main__":
    main()


__all__ = [
    "SchedulerTickResult",
    "TriggeredScheduleRun",
    "main",
    "run_scheduler_loop",
    "run_scheduler_tick",
    "run_service_scheduler_tick",
]
