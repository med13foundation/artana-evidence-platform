"""Unit tests for the graph-harness schedule queueing loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from artana_evidence_api import scheduler as scheduler_module
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.schedule_policy import is_schedule_due
from artana_evidence_api.schedule_store import (
    HarnessScheduleRecord,
    HarnessScheduleStore,
)
from artana_evidence_api.scheduler import run_scheduler_tick


def test_is_schedule_due_uses_period_windows() -> None:
    now = datetime(2026, 3, 13, 15, 0, tzinfo=UTC)

    assert is_schedule_due(cadence="manual", last_run_at=None, now=now) is False
    assert is_schedule_due(
        cadence="hourly",
        last_run_at=now - timedelta(hours=1),
        now=now,
    )
    assert is_schedule_due(
        cadence="daily",
        last_run_at=now - timedelta(days=1),
        now=now,
    )
    assert is_schedule_due(
        cadence="weekly",
        last_run_at=now - timedelta(days=7),
        now=now,
    )
    assert is_schedule_due(
        cadence="weekday",
        last_run_at=now - timedelta(days=1),
        now=now,
    )
    assert is_schedule_due(cadence="daily", last_run_at=now, now=now) is False


def test_run_scheduler_tick_queues_due_schedules() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = uuid4()
    created = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Daily refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={
            "seed_entity_ids": ["11111111-1111-1111-1111-111111111111"],
            "source_type": "pubmed",
        },
        metadata={},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=created.id,
        last_run_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.scanned_schedule_count == 1
    assert result.due_schedule_count == 1
    assert len(result.triggered_runs) == 1
    assert result.errors == ()

    updated_schedule = schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=created.id,
    )
    assert updated_schedule is not None
    assert updated_schedule.last_run_id == result.triggered_runs[0].run_id
    assert updated_schedule.last_run_at is not None

    runs = run_registry.list_runs(space_id=space_id)
    assert len(runs) == 1
    assert runs[0].harness_id == "continuous-learning"
    assert runs[0].status == "queued"
    progress = run_registry.get_progress(space_id=space_id, run_id=runs[0].id)
    assert progress is not None
    assert progress.phase == "queued"

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=runs[0].id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "queued"
    assert workspace.snapshot["schedule_id"] == created.id


def test_run_scheduler_tick_skips_not_due_and_manual_schedules() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = uuid4()
    schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Manual refresh",
        cadence="manual",
        created_by=uuid4(),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={},
    )
    daily_schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Daily refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=daily_schedule.id,
        last_run_at=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
    )
    paused_schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Paused refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=paused_schedule.id,
        status="paused",
        last_run_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
    )

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.scanned_schedule_count == 2
    assert result.due_schedule_count == 0
    assert result.triggered_runs == ()
    assert result.errors == ()
    assert run_registry.list_runs(space_id=space_id) == []


def test_run_scheduler_tick_records_schedule_configuration_errors() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = str(uuid4())
    invalid_schedule = HarnessScheduleRecord(
        id="invalid-schedule",
        space_id=space_id,
        harness_id="continuous-learning",
        title="Broken refresh",
        cadence="daily",
        status="active",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": [], "source_type": "pubmed"},
        metadata={},
        last_run_id=None,
        last_run_at=None,
        created_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
    )
    schedule_store._schedules[invalid_schedule.id] = invalid_schedule  # noqa: SLF001

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.due_schedule_count == 1
    assert result.triggered_runs == ()
    assert len(result.errors) == 1
    assert "missing required seed_entity_ids" in result.errors[0]


def test_run_scheduler_tick_continues_after_one_due_schedule_errors() -> None:
    schedule_store = HarnessScheduleStore()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    space_id = str(uuid4())
    invalid_schedule = HarnessScheduleRecord(
        id="invalid-schedule",
        space_id=space_id,
        harness_id="continuous-learning",
        title="Broken refresh",
        cadence="daily",
        status="active",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": [], "source_type": "pubmed"},
        metadata={},
        last_run_id=None,
        last_run_at=None,
        created_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 12, 8, 0, tzinfo=UTC),
    )
    schedule_store._schedules[invalid_schedule.id] = invalid_schedule  # noqa: SLF001
    valid_schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Healthy refresh",
        cadence="daily",
        created_by=uuid4(),
        configuration={
            "seed_entity_ids": ["11111111-1111-1111-1111-111111111111"],
            "source_type": "pubmed",
        },
        metadata={},
    )

    result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        ),
    )

    assert result.scanned_schedule_count == 2
    assert result.due_schedule_count == 2
    assert len(result.triggered_runs) == 1
    assert len(result.errors) == 1
    assert valid_schedule.id == result.triggered_runs[0].schedule_id
    queued_runs = run_registry.list_runs(space_id=space_id)
    assert len(queued_runs) == 1
    assert queued_runs[0].id == result.triggered_runs[0].run_id


@pytest.mark.asyncio
async def test_run_scheduler_loop_recovers_from_tick_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    heartbeats: list[dict[str, object]] = []
    tick_calls = 0
    sleep_calls = 0

    async def _fake_run_service_scheduler_tick() -> (
        scheduler_module.SchedulerTickResult
    ):
        nonlocal tick_calls
        tick_calls += 1
        if tick_calls == 1:
            raise RuntimeError("Synthetic scheduler tick failure.")
        now = datetime.now(UTC)
        return scheduler_module.SchedulerTickResult(
            started_at=now,
            completed_at=now,
            scanned_schedule_count=1,
            due_schedule_count=0,
            triggered_runs=(),
            errors=(),
        )

    def _fake_write_heartbeat(path: str, last_result: dict[str, object]) -> None:
        assert path.endswith("artana-evidence-api-scheduler-heartbeat.json")
        heartbeats.append(dict(last_result))

    class _StopLoopError(Exception):
        pass

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 2:
            raise _StopLoopError

    monkeypatch.setattr(
        scheduler_module,
        "run_service_scheduler_tick",
        _fake_run_service_scheduler_tick,
    )
    monkeypatch.setattr(
        scheduler_module,
        "_write_heartbeat",
        _fake_write_heartbeat,
    )
    monkeypatch.setattr(scheduler_module.asyncio, "sleep", _fake_sleep)

    with pytest.raises(_StopLoopError), caplog.at_level("ERROR"):
        await scheduler_module.run_scheduler_loop(
            poll_seconds=1.0,
            run_once=False,
        )

    assert tick_calls == 2
    assert heartbeats[0]["loop_status"] == "working"
    assert heartbeats[1]["loop_status"] == "error"
    assert heartbeats[1]["error_type"] == "RuntimeError"
    assert heartbeats[2]["loop_status"] == "working"
    assert heartbeats[3]["loop_status"] == "ok"
    assert heartbeats[3]["scanned"] == 1
    assert any(
        record.message == "Harness scheduler tick failed" for record in caplog.records
    )


@pytest.mark.asyncio
async def test_run_scheduler_loop_emits_keepalive_heartbeat_during_long_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeats: list[dict[str, object]] = []
    keepalive_seen = asyncio.Event()

    async def _fake_run_service_scheduler_tick() -> (
        scheduler_module.SchedulerTickResult
    ):
        while len(heartbeats) < 2:
            await asyncio.sleep(0)
        keepalive_seen.set()
        now = datetime.now(UTC)
        return scheduler_module.SchedulerTickResult(
            started_at=now,
            completed_at=now,
            scanned_schedule_count=1,
            due_schedule_count=0,
            triggered_runs=(),
            errors=(),
        )

    def _fake_write_heartbeat(path: str, last_result: dict[str, object]) -> None:
        assert path.endswith("artana-evidence-api-scheduler-heartbeat.json")
        heartbeats.append(dict(last_result))

    monkeypatch.setattr(
        scheduler_module,
        "run_service_scheduler_tick",
        _fake_run_service_scheduler_tick,
    )
    monkeypatch.setattr(
        scheduler_module,
        "_write_heartbeat",
        _fake_write_heartbeat,
    )
    monkeypatch.setattr(
        scheduler_module,
        "_SCHEDULER_HEARTBEAT_KEEPALIVE_SECONDS",
        0.001,
    )

    await scheduler_module.run_scheduler_loop(
        poll_seconds=1.0,
        run_once=True,
    )

    assert keepalive_seen.is_set()
    assert heartbeats[0]["loop_status"] == "working"
    assert any(
        heartbeat.get("loop_status") == "working" for heartbeat in heartbeats[1:-1]
    )
    assert heartbeats[-1]["loop_status"] == "ok"
    assert heartbeats[-1]["scanned"] == 1
