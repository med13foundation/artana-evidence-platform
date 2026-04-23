"""Shared process heartbeat models and readers."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict


class ProcessHealth(BaseModel):
    """Health status of a background process."""

    model_config = ConfigDict(strict=True)

    status: str  # "healthy", "degraded", "unknown"
    last_tick: str | None = None
    pid: int | None = None
    detail: JSONObject | None = None


def read_heartbeat(
    path: str,
    *,
    max_age_seconds: float,
) -> ProcessHealth:
    """Read a heartbeat file and return health status."""
    heartbeat_path = Path(path)
    try:
        with heartbeat_path.open() as f:
            data = json.load(f)
        last_tick_at = datetime.fromisoformat(data["last_tick_at"])
        age = (datetime.now(UTC) - last_tick_at).total_seconds()
        pid = data.get("pid")
        is_alive = False
        if pid:
            try:
                os.kill(pid, 0)
                is_alive = True
            except (OSError, ProcessLookupError):
                pass
        raw_detail = data.get("last_result")
        detail: JSONObject = dict(raw_detail) if isinstance(raw_detail, dict) else {}
        if not isinstance(raw_detail, dict) and raw_detail is not None:
            detail["last_result"] = raw_detail
        detail.update(
            {
                "heartbeat_path": str(heartbeat_path),
                "heartbeat_age_seconds": int(age),
                "max_age_seconds": max_age_seconds,
                "process_alive": is_alive,
            },
        )
        loop_status = detail.get("loop_status")
        loop_error = isinstance(loop_status, str) and loop_status == "error"
        if age > max_age_seconds or not is_alive or loop_error:
            if age > max_age_seconds:
                detail["failure_reason"] = "stale"
            elif not is_alive:
                detail["failure_reason"] = "process_not_running"
            elif loop_error:
                detail["failure_reason"] = "loop_error"
            return ProcessHealth(
                status="degraded",
                pid=pid,
                last_tick=f"{int(age)}s ago",
                detail=detail,
            )
        return ProcessHealth(
            status="healthy",
            pid=pid,
            last_tick=f"{int(age)}s ago",
            detail=detail,
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return ProcessHealth(status="unknown")


__all__ = ["ProcessHealth", "read_heartbeat"]
