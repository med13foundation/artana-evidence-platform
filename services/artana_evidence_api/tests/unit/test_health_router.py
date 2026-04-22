"""Unit tests for harness heartbeat parsing."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from artana_evidence_api.routers.health import _read_heartbeat


def _write_heartbeat(
    path: Path,
    *,
    last_tick_at: datetime,
    pid: int,
    last_result: dict[str, object] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "last_tick_at": last_tick_at.isoformat(),
                "pid": pid,
                "last_result": last_result or {"scanned": 0, "errors": 0},
            },
        ),
    )


def test_read_heartbeat_marks_dead_process_with_reason(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "worker-heartbeat.json"
    _write_heartbeat(
        heartbeat_path,
        last_tick_at=datetime.now(UTC),
        pid=999_999,
    )

    health = _read_heartbeat(str(heartbeat_path), max_age_seconds=120.0)

    assert health.status == "degraded"
    assert health.pid == 999_999
    assert health.detail is not None
    assert health.detail["failure_reason"] == "process_not_running"
    assert health.detail["process_alive"] is False
    assert health.detail["heartbeat_path"] == str(heartbeat_path)


def test_read_heartbeat_marks_stale_process_with_reason(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "worker-heartbeat.json"
    _write_heartbeat(
        heartbeat_path,
        last_tick_at=datetime.now(UTC) - timedelta(seconds=300),
        pid=os.getpid(),
    )

    health = _read_heartbeat(str(heartbeat_path), max_age_seconds=120.0)

    assert health.status == "degraded"
    assert health.pid == os.getpid()
    assert health.detail is not None
    assert health.detail["failure_reason"] == "stale"
    assert health.detail["process_alive"] is True
    assert int(health.detail["heartbeat_age_seconds"]) >= 300


def test_read_heartbeat_marks_loop_error_as_degraded(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "worker-heartbeat.json"
    _write_heartbeat(
        heartbeat_path,
        last_tick_at=datetime.now(UTC),
        pid=os.getpid(),
        last_result={
            "loop_status": "error",
            "error_type": "RuntimeError",
            "error": "Synthetic worker tick failure.",
        },
    )

    health = _read_heartbeat(str(heartbeat_path), max_age_seconds=120.0)

    assert health.status == "degraded"
    assert health.detail is not None
    assert health.detail["failure_reason"] == "loop_error"
    assert health.detail["process_alive"] is True
    assert health.detail["error_type"] == "RuntimeError"
