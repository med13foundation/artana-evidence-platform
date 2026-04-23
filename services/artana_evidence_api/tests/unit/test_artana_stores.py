"""Unit tests for Artana-kernel-backed graph-harness lifecycle adapters."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from artana_evidence_api import artana_stores as artana_stores_module
from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.composition import GraphHarnessKernelRuntime
from artana_evidence_api.db_schema import resolve_harness_db_schema
from artana_evidence_api.models.base import Base
from artana_evidence_api.tests.support import (
    FakeStepToolResult,
    fake_tool_allowlist,
    fake_tool_result_payload,
)
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass(frozen=True, slots=True)
class _FakeSummary:
    summary_json: str


@dataclass(frozen=True, slots=True)
class _FakeEventType:
    value: str


@dataclass(frozen=True, slots=True)
class _FakePayload:
    payload: dict[str, object]

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        _ = mode
        return self.payload


@dataclass(frozen=True, slots=True)
class _FakeEvent:
    event_id: str
    event_type: _FakeEventType
    payload: _FakePayload
    timestamp: datetime


class _SynchronousRunner:
    def run(self, coroutine, *, timeout_seconds: float | None = None):
        import asyncio

        _ = timeout_seconds
        return asyncio.run(coroutine)


class _FakeKernelRuntime:
    def __init__(self) -> None:
        self._runs: set[tuple[str, str]] = set()
        self._summaries: dict[tuple[str, str, str], _FakeSummary] = {}
        self._events: dict[tuple[str, str], list[_FakeEvent]] = {}

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        key = (tenant_id, run_id)
        if key in self._runs:
            return False
        self._runs.add(key)
        return True

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        _ = parent_step_key
        summary = _FakeSummary(summary_json=summary_json)
        self._summaries[(tenant_id, run_id, summary_type)] = summary
        self._events.setdefault((tenant_id, run_id), []).append(
            _FakeEvent(
                event_id=f"{step_key}:{len(self._events.get((tenant_id, run_id), []))}",
                event_type=_FakeEventType(value="run_summary"),
                payload=_FakePayload(
                    payload={
                        "summary_type": summary_type,
                        "summary_json": summary_json,
                        "step_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        return len(self._events[(tenant_id, run_id)])

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeSummary | None:
        _ = timeout_seconds
        return self._summaries.get((tenant_id, run_id, summary_type))

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[_FakeEvent, ...]:
        _ = timeout_seconds
        return tuple(self._events.get((tenant_id, run_id), []))

    def get_run_status(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id, timeout_seconds

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id, timeout_seconds

    def get_resume_point(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id, timeout_seconds

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, run_id
        return fake_tool_allowlist(visible_tool_names=visible_tool_names)

    def step_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> FakeStepToolResult:
        _ = run_id, tenant_id, step_key, parent_step_key
        return FakeStepToolResult(
            result_json=json.dumps(
                fake_tool_result_payload(tool_name=tool_name, arguments=arguments),
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )

    def reconcile_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        _ = run_id, tenant_id, step_key, parent_step_key
        return json.dumps(
            fake_tool_result_payload(tool_name=tool_name, arguments=arguments),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


class _RunStateReadBlockedRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.run_state_read_count = 0

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeSummary | None:
        _ = timeout_seconds
        if summary_type == "harness::run_state":
            self.run_state_read_count += 1
            raise AssertionError("run-state hydration should not be on this path")
        return super().get_latest_run_summary(
            run_id=run_id,
            tenant_id=tenant_id,
            summary_type=summary_type,
            timeout_seconds=timeout_seconds,
        )


class _ProgressReadBlockedRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.progress_read_count = 0

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeSummary | None:
        _ = timeout_seconds
        if summary_type == "harness::progress":
            self.progress_read_count += 1
            raise AssertionError("progress hydration should be skipped")
        return super().get_latest_run_summary(
            run_id=run_id,
            tenant_id=tenant_id,
            summary_type=summary_type,
            timeout_seconds=timeout_seconds,
        )


class _ProgressWriteTimeoutRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.fail_progress_writes = False
        self.progress_write_timeout_count = 0

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        if self.fail_progress_writes and (
            summary_type == "harness::progress" or summary_type.startswith("event::")
        ):
            self.progress_write_timeout_count += 1
            raise TimeoutError
        return super().append_run_summary(
            run_id=run_id,
            tenant_id=tenant_id,
            summary_type=summary_type,
            summary_json=summary_json,
            step_key=step_key,
            parent_step_key=parent_step_key,
        )


class _TransientSummaryWriteRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._failed_once_summary_types: set[str] = set()
        self.timeout_counts: dict[str, int] = {}

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        if (
            summary_type == "harness::progress"
            or summary_type.startswith(("event::", "artifact::"))
        ) and summary_type not in self._failed_once_summary_types:
            self._failed_once_summary_types.add(summary_type)
            self.timeout_counts[summary_type] = (
                self.timeout_counts.get(summary_type, 0) + 1
            )
            raise TimeoutError
        return super().append_run_summary(
            run_id=run_id,
            tenant_id=tenant_id,
            summary_type=summary_type,
            summary_json=summary_json,
            step_key=step_key,
            parent_step_key=parent_step_key,
        )


class _StatusTransitionWriteTimeoutRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.fail_status_transition_writes = False
        self.timeout_counts: dict[str, int] = {}

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        if self.fail_status_transition_writes and (
            summary_type in {"harness::run_state", "harness::progress"}
            or summary_type.startswith("event::")
        ):
            self.timeout_counts[summary_type] = (
                self.timeout_counts.get(summary_type, 0) + 1
            )
            raise TimeoutError
        return super().append_run_summary(
            run_id=run_id,
            tenant_id=tenant_id,
            summary_type=summary_type,
            summary_json=summary_json,
            step_key=step_key,
            parent_step_key=parent_step_key,
        )


class _HydrationFailureRuntime(_FakeKernelRuntime):
    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeSummary | None:
        _ = run_id, tenant_id, summary_type, timeout_seconds
        raise ValueError("No events found for run")


class _FastReadTimeoutRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.summary_timeout_requests: list[float | None] = []
        self.progress_timeout_requests: list[float | None] = []
        self.status_timeout_requests: list[float | None] = []
        self.resume_timeout_requests: list[float | None] = []

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeSummary | None:
        _ = run_id, tenant_id, summary_type
        self.summary_timeout_requests.append(timeout_seconds)
        raise TimeoutError

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id
        self.progress_timeout_requests.append(timeout_seconds)
        raise TimeoutError

    def get_run_status(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id
        self.status_timeout_requests.append(timeout_seconds)
        raise TimeoutError

    def get_resume_point(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id
        self.resume_timeout_requests.append(timeout_seconds)
        raise TimeoutError


class _EventReadTimeoutRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.event_timeout_requests: list[float | None] = []

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[_FakeEvent, ...]:
        _ = run_id, tenant_id
        self.event_timeout_requests.append(timeout_seconds)
        raise TimeoutError


class _KernelWithCurrentArtanaSignatures:
    def __init__(self) -> None:
        self._runs: set[str] = set()
        self._summaries: dict[tuple[str, str], _FakeSummary] = {}
        self._events: dict[str, list[_FakeEvent]] = {}

    async def load_run(self, *, run_id: str) -> str:
        if run_id not in self._runs:
            raise ValueError("missing")
        return run_id

    async def start_run(self, *, tenant, run_id: str | None = None) -> str:
        if run_id is None:
            raise ValueError("run_id is required")
        self._runs.add(run_id)
        self._events.setdefault(run_id, [])
        _ = tenant
        return run_id

    async def append_run_summary(
        self,
        *,
        run_id: str,
        tenant,
        summary_type: str,
        summary_json: str,
        step_key: str | None = None,
        parent_step_key: str | None = None,
    ) -> int:
        _ = parent_step_key, tenant
        self._summaries[(run_id, summary_type)] = _FakeSummary(
            summary_json=summary_json,
        )
        events = self._events.setdefault(run_id, [])
        event_index = len(events)
        events.append(
            _FakeEvent(
                event_id=f"{step_key or 'summary'}:{event_index}",
                event_type=_FakeEventType(value="run_summary"),
                payload=_FakePayload(
                    payload={
                        "summary_type": summary_type,
                        "summary_json": summary_json,
                        "step_key": step_key or "summary",
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        return len(events)

    async def get_latest_run_summary(
        self,
        *,
        run_id: str,
        summary_type: str,
    ) -> _FakeSummary | None:
        return self._summaries.get((run_id, summary_type))

    async def get_events(self, *, run_id: str) -> tuple[_FakeEvent, ...]:
        return tuple(self._events.get(run_id, ()))

    async def get_run_status(self, *, run_id: str) -> None:
        _ = run_id

    async def get_run_progress(self, *, run_id: str) -> None:
        _ = run_id

    async def resume_point(self, *, run_id: str) -> None:
        _ = run_id


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    harness_schema = resolve_harness_db_schema("graph_harness")
    public_schema = "public"

    @event.listens_for(engine, "connect")
    def _attach_harness_schema(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"ATTACH DATABASE ':memory:' AS {public_schema}")
            cursor.execute(f"ATTACH DATABASE ':memory:' AS {harness_schema}")
        finally:
            cursor.close()

    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    db_session = session_local()
    try:
        yield db_session
    finally:
        db_session.close()


def test_artana_backed_run_registry_persists_catalog_and_kernel_lifecycle(
    session: Session,
) -> None:
    runtime = _FakeKernelRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Chat run",
        input_payload={"question": "What is known?"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    assert run.status == "queued"
    progress = registry.get_progress(space_id=space_id, run_id=run.id)
    assert progress is not None
    assert progress.phase == "queued"

    updated = registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    assert updated is not None
    assert updated.status == "completed"

    finalized = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="finalize",
        message="Artifacts finalized.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        metadata={"artifact_key": "chat_summary"},
        clear_resume_point=True,
    )
    assert finalized is not None
    assert finalized.progress_percent == 1.0
    assert finalized.metadata["artifact_key"] == "chat_summary"

    recorded_event = registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.summary_written",
        message="Summary stored.",
        payload={"artifact_key": "chat_summary"},
    )
    assert recorded_event is not None

    fetched = registry.get_run(space_id=space_id, run_id=run.id)
    assert fetched is not None
    assert fetched.status == "completed"

    events = registry.list_events(space_id=space_id, run_id=run.id)
    assert [event.event_type for event in events] == [
        "run.created",
        "run.status_changed",
        "run.progress",
        "run.summary_written",
    ]


def test_artana_backed_run_registry_writes_do_not_hydrate_run_state(
    session: Session,
) -> None:
    runtime = _RunStateReadBlockedRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find BRCA1 evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    progress = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 1/12 selected documents.",
        progress_percent=0.61,
        completed_steps=3,
        metadata={"document_extraction_completed_count": 1},
    )
    assert progress is not None
    assert progress.phase == "document_extraction"

    completed = registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    assert completed is not None
    assert completed.status == "completed"
    assert runtime.run_state_read_count == 0


def test_artana_backed_run_registry_falls_back_to_catalog_metadata_on_hydration_failure(
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _HydrationFailureRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())
    caplog.set_level(logging.WARNING)

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Fallback hydration run",
        input_payload={"objective": "Recover gracefully"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    fetched = registry.get_run(space_id=space_id, run_id=run.id)
    runs = registry.list_runs(space_id=space_id)

    assert fetched is not None
    assert fetched.id == run.id
    assert fetched.status == "queued"
    assert [record.id for record in runs] == [run.id]
    assert "Failed to hydrate harness run summaries" in caplog.text


def test_artana_backed_run_registry_can_write_progress_without_hydrating_existing(
    session: Session,
) -> None:
    runtime = _ProgressReadBlockedRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find CFTR evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    progress = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 1/12 selected documents.",
        progress_percent=0.61,
        completed_steps=3,
        metadata={"document_extraction_completed_count": 1},
        merge_existing=False,
    )

    assert progress is not None
    assert progress.phase == "document_extraction"
    assert progress.metadata["document_extraction_completed_count"] == 1
    assert runtime.progress_read_count == 0


def test_artana_backed_run_registry_progress_write_timeout_is_best_effort(
    session: Session,
) -> None:
    runtime = _ProgressWriteTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find CFTR evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    runtime.fail_progress_writes = True

    progress = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 3/12 selected documents.",
        progress_percent=0.63,
        completed_steps=3,
        metadata={"document_extraction_completed_count": 3},
        merge_existing=False,
    )

    assert progress is not None
    assert progress.phase == "document_extraction"
    assert progress.metadata["document_extraction_completed_count"] == 3
    assert runtime.progress_write_timeout_count == 2
    fetched = registry.get_run(space_id=space_id, run_id=run.id)
    assert fetched is not None
    assert fetched.updated_at >= progress.updated_at


def test_artana_backed_run_registry_progress_timeouts_enter_backoff(
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _ProgressWriteTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())
    caplog.set_level(logging.INFO)

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find CFTR evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    runtime.fail_progress_writes = True

    first = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 1/12 selected documents.",
        progress_percent=0.61,
        completed_steps=1,
        merge_existing=False,
    )
    second = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 2/12 selected documents.",
        progress_percent=0.62,
        completed_steps=2,
        merge_existing=False,
    )

    assert first is not None
    assert second is not None
    assert runtime.progress_write_timeout_count == 2
    assert "Entering Artana progress summary backoff after timeout" in caplog.text
    assert "Entering Artana progress event backoff after timeout" in caplog.text


def test_artana_backed_run_registry_status_transition_timeouts_keep_catalog_authoritative(
    session: Session,
) -> None:
    runtime = _StatusTransitionWriteTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find CFTR evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    existing_progress = registry.get_progress(space_id=space_id, run_id=run.id)
    runtime.fail_status_transition_writes = True

    updated = registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
        existing_progress=existing_progress,
    )

    assert updated is not None
    assert updated.status == "completed"
    fetched = registry.get_run(space_id=space_id, run_id=run.id)
    assert fetched is not None
    assert fetched.status == "completed"
    progress = registry.get_progress(space_id=space_id, run_id=run.id)
    assert progress is not None
    assert progress.status == "completed"
    assert (
        runtime.timeout_counts["harness::run_state"]
        == artana_stores_module._SUMMARY_WRITE_MAX_ATTEMPTS
    )
    assert (
        runtime.timeout_counts["harness::progress"]
        == artana_stores_module._SUMMARY_WRITE_MAX_ATTEMPTS
    )


def test_artana_backed_run_registry_set_run_status_skips_progress_hydration_by_default(
    session: Session,
) -> None:
    runtime = _ProgressReadBlockedRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find BRCA1 evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    updated = registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )

    assert updated is not None
    assert updated.status == "completed"
    assert runtime.progress_read_count == 0


def test_artana_backed_run_registry_retries_transient_progress_write_timeouts(
    session: Session,
) -> None:
    runtime = _TransientSummaryWriteRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Guarded eval run",
        input_payload={"objective": "Find CFTR evidence"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    runtime._failed_once_summary_types.clear()
    runtime.timeout_counts.clear()

    progress = registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Processed extraction for 4/12 selected documents.",
        progress_percent=0.64,
        completed_steps=4,
        metadata={"document_extraction_completed_count": 4},
        merge_existing=False,
    )

    assert progress is not None
    assert progress.phase == "document_extraction"
    assert progress.metadata["document_extraction_completed_count"] == 4
    assert runtime.timeout_counts["harness::progress"] == 1
    assert (
        sum(
            count
            for summary_type, count in runtime.timeout_counts.items()
            if summary_type.startswith("event::")
        )
        == 1
    )


def test_artana_backed_artifact_store_uses_kernel_summaries(
    session: Session,
) -> None:
    runtime = _FakeKernelRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    artifact_store = ArtanaBackedHarnessArtifactStore(runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title="Search run",
        input_payload={"question": "Find MED13 links"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    artifact_store.seed_for_run(run=run)
    seeded = artifact_store.list_artifacts(space_id=space_id, run_id=run.id)
    assert [artifact.key for artifact in seeded] == ["run_manifest"]

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    assert workspace is not None
    assert workspace.snapshot["artifact_keys"] == ["run_manifest"]

    stored_artifact = artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
        media_type="application/json",
        content={"decision": "generated"},
    )
    assert stored_artifact.key == "graph_search_result"

    patched_workspace = artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "completed"},
    )
    assert patched_workspace is not None
    assert patched_workspace.snapshot["status"] == "completed"

    artifacts = artifact_store.list_artifacts(space_id=space_id, run_id=run.id)
    assert {artifact.key for artifact in artifacts} == {
        "run_manifest",
        "graph_search_result",
    }
    fetched = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
    )
    assert fetched is not None


def test_artana_backed_artifact_store_retries_transient_artifact_write_timeouts(
    session: Session,
) -> None:
    runtime = _TransientSummaryWriteRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    artifact_store = ArtanaBackedHarnessArtifactStore(runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title="Search run",
        input_payload={"question": "Find MED13 links"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    artifact_store.seed_for_run(run=run)
    stored_artifact = artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
        media_type="application/json",
        content={"decision": "generated"},
    )
    fetched = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
    )

    assert stored_artifact.key == "graph_search_result"
    assert runtime.timeout_counts["artifact::run_manifest"] == 1
    assert runtime.timeout_counts["artifact::graph_search_result"] == 1
    assert fetched is not None
    assert fetched.content["decision"] == "generated"


def test_artana_backed_artifact_store_delete_run_is_safe_for_runtime_backed_records(
    session: Session,
) -> None:
    runtime = _FakeKernelRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    artifact_store = ArtanaBackedHarnessArtifactStore(runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="claim-curation",
        title="Claim curation run",
        input_payload={"workflow": "claim_curation", "proposal_ids": ["p-1"]},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    artifact_store.seed_for_run(run=run)
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="approval_intent",
        media_type="application/json",
        content={"summary": "Review one proposal."},
    )

    assert artifact_store.delete_run(space_id=space_id, run_id=run.id) is True


def test_artana_backed_run_registry_fast_read_timeout_falls_back_to_catalog_progress(
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _FastReadTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())
    caplog.set_level(logging.WARNING)
    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Slow read run",
        input_payload={"objective": "Investigate BRCA1"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    hydrated_run = registry.get_run(space_id=space_id, run_id=run.id)
    assert hydrated_run is not None
    assert hydrated_run.status == "queued"

    progress = registry.get_progress(space_id=space_id, run_id=run.id)
    assert progress is not None
    assert progress.status == "queued"
    assert progress.phase == "queued"
    assert progress.message == "Run created and queued."

    assert runtime.summary_timeout_requests == [
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
    ]
    assert runtime.progress_timeout_requests == []
    assert runtime.status_timeout_requests == []
    assert runtime.resume_timeout_requests == []
    assert "Failed to hydrate harness run summaries" not in caplog.text


def test_artana_backed_run_registry_event_timeout_returns_degraded_event(
    session: Session,
) -> None:
    runtime = _EventReadTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Slow events run",
        input_payload={"objective": "Investigate CDC27"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    events = registry.list_events(space_id=space_id, run_id=run.id)

    assert [event.event_type for event in events] == ["run.events_degraded"]
    assert events[0].payload["read_degraded"] is True
    assert events[0].payload["read_degraded_reason"] == "events_read_timeout"
    assert runtime.event_timeout_requests == [
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
    ]


def test_artana_backed_artifact_store_fast_read_timeout_returns_none(
    session: Session,
) -> None:
    runtime = _FastReadTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    artifact_store = ArtanaBackedHarnessArtifactStore(runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Slow artifact read run",
        input_payload={"objective": "Investigate CFTR"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    assert artifact_store.get_workspace(space_id=space_id, run_id=run.id) is None
    assert (
        artifact_store.get_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="shadow_planner_timeline",
        )
        is None
    )

    assert runtime.summary_timeout_requests == [
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
    ]


def test_artana_backed_artifact_store_with_run_registry_returns_degraded_fallbacks(
    session: Session,
) -> None:
    runtime = _FastReadTimeoutRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    artifact_store = ArtanaBackedHarnessArtifactStore(
        runtime=runtime,
        run_registry=registry,
    )
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Slow workspace read run",
        input_payload={"objective": "Investigate CDC27"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    manifest = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="run_manifest",
    )
    artifacts = artifact_store.list_artifacts(space_id=space_id, run_id=run.id)

    assert workspace is not None
    assert workspace.snapshot["read_degraded"] is True
    assert workspace.snapshot["read_degraded_reason"] == "workspace_read_timeout"
    assert manifest is not None
    assert manifest.content["read_degraded"] is True
    assert manifest.content["read_degraded_reason"] == "artifact_read_timeout"
    assert [artifact.key for artifact in artifacts] == ["run_manifest"]
    assert artifacts[0].content["read_degraded_reason"] == "artifact_list_unavailable"
    assert runtime.summary_timeout_requests == [
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
        artana_stores_module._FAST_READ_TIMEOUT_SECONDS,
    ]
    assert runtime.progress_timeout_requests == []


def test_artana_backed_run_registry_delete_run_is_safe_for_runtime_backed_records(
    session: Session,
) -> None:
    runtime = _FakeKernelRuntime()
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())
    run = registry.create_run(
        space_id=space_id,
        harness_id="claim-curation",
        title="Claim curation run",
        input_payload={"workflow": "claim_curation", "proposal_ids": ["p-1"]},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    assert registry.delete_run(space_id=space_id, run_id=run.id) is True
    assert registry.get_run(space_id=space_id, run_id=run.id) is None
    assert registry.delete_run(space_id=space_id, run_id=run.id) is False


def test_artana_backed_run_registry_works_through_runtime_adapter(
    session: Session,
) -> None:
    kernel = _KernelWithCurrentArtanaSignatures()
    runtime = GraphHarnessKernelRuntime(
        kernel=kernel,
        _runner=_SynchronousRunner(),
    )
    registry = ArtanaBackedHarnessRunRegistry(session=session, runtime=runtime)
    space_id = str(uuid4())

    run = registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Adapter-backed chat run",
        input_payload={"question": "What changed?"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )

    progress = registry.get_progress(space_id=space_id, run_id=run.id)
    assert progress is not None
    assert progress.phase == "queued"
    assert progress.status == "queued"

    events = registry.list_events(space_id=space_id, run_id=run.id)
    assert [event.event_type for event in events] == ["run.created"]
