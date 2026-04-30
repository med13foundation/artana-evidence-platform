"""Unit tests for queued-run helper packages."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from artana_evidence_api.queued_run import failures, worker_readiness
from fastapi import HTTPException, status


def test_require_worker_ready_accepts_healthy_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        worker_readiness,
        "read_heartbeat",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="healthy",
            last_tick=None,
            detail={},
        ),
    )

    worker_readiness.require_worker_ready(operation_name="Graph search")


@pytest.mark.parametrize(
    ("worker", "expected_detail"),
    [
        (
            SimpleNamespace(
                status="unhealthy",
                last_tick="2026-04-30T17:00:00Z",
                detail={"failure_reason": "process_not_running"},
            ),
            "Worker process is not running.",
        ),
        (
            SimpleNamespace(
                status="unhealthy",
                last_tick=None,
                detail={"failure_reason": "stale"},
            ),
            "Worker heartbeat is stale.",
        ),
        (
            SimpleNamespace(
                status="unhealthy",
                last_tick=None,
                detail={"failure_reason": "loop_error"},
            ),
            "Worker loop is erroring.",
        ),
        (
            SimpleNamespace(status="unknown", last_tick=None, detail={}),
            "No worker heartbeat is available.",
        ),
    ],
)
def test_require_worker_ready_reports_worker_failure_reason(
    monkeypatch: pytest.MonkeyPatch,
    worker: SimpleNamespace,
    expected_detail: str,
) -> None:
    monkeypatch.setattr(
        worker_readiness,
        "read_heartbeat",
        lambda *_args, **_kwargs: worker,
    )

    with pytest.raises(HTTPException) as exc_info:
        worker_readiness.require_worker_ready(operation_name="Graph search")

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "Graph search worker unavailable." in str(exc_info.value.detail)
    assert expected_detail in str(exc_info.value.detail)


def test_should_require_worker_ready_only_for_production_worker() -> None:
    assert worker_readiness.should_require_worker_ready(
        execution_services=SimpleNamespace(execution_override=None),
    )
    assert not worker_readiness.should_require_worker_ready(
        execution_services=SimpleNamespace(execution_override=object()),
    )
    assert not worker_readiness.should_require_worker_ready(
        execution_services=object(),
    )


def test_worker_failure_payload_preserves_http_exception_status() -> None:
    payload = failures.worker_failure_payload(
        exc=HTTPException(status_code=status.HTTP_409_CONFLICT, detail="budget"),
    )

    assert payload == {
        "error": "budget",
        "detail": "budget",
        "status_code": status.HTTP_409_CONFLICT,
        "error_type": "HTTPException",
    }


def test_worker_failure_payload_defaults_to_internal_error() -> None:
    payload = failures.worker_failure_payload(exc=RuntimeError("boom"))

    assert payload == {
        "error": "boom",
        "detail": "boom",
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error_type": "RuntimeError",
    }


class _FakeArtifactStore:
    def __init__(
        self,
        *,
        worker_error: object | None = None,
        workspace: object | None = None,
    ) -> None:
        self.worker_error = worker_error
        self.workspace = workspace

    def get_artifact(self, **_kwargs: object) -> object | None:
        return self.worker_error

    def get_workspace(self, **_kwargs: object) -> object | None:
        return self.workspace


def test_raise_for_failed_run_prefers_worker_error_payload() -> None:
    run = SimpleNamespace(id="run-1", space_id="space-1")
    artifact_store = _FakeArtifactStore(
        worker_error=SimpleNamespace(
            content={
                "status_code": status.HTTP_400_BAD_REQUEST,
                "detail": "bad request",
            },
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        failures.raise_for_failed_run(run=run, artifact_store=artifact_store)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == "bad request"


def test_raise_for_failed_run_uses_workspace_error_status() -> None:
    run = SimpleNamespace(id="run-1", space_id="space-1")
    artifact_store = _FakeArtifactStore(
        workspace=SimpleNamespace(
            snapshot={
                "error": "workspace failed",
                "error_status_code": status.HTTP_503_SERVICE_UNAVAILABLE,
            },
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        failures.raise_for_failed_run(run=run, artifact_store=artifact_store)

    assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert exc_info.value.detail == "workspace failed"


def test_raise_for_failed_run_falls_back_when_error_payload_is_missing() -> None:
    run = SimpleNamespace(id="run-1", space_id="space-1")

    with pytest.raises(HTTPException) as exc_info:
        failures.raise_for_failed_run(
            run=run,
            artifact_store=_FakeArtifactStore(),
        )

    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "failed without a persisted error payload" in str(exc_info.value.detail)
