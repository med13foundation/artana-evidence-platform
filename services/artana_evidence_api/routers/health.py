"""Health endpoints for the standalone harness service."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from artana_evidence_api.config import get_settings
from artana_evidence_api.runtime_support import get_artana_model_health
from artana_evidence_api.step_helpers import get_step_execution_health
from artana_evidence_api.types.common import JSONObject
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class ProcessHealth(BaseModel):
    """Health status of a background process."""

    model_config = ConfigDict(strict=True)

    status: str  # "healthy", "degraded", "unknown"
    last_tick: str | None = None
    pid: int | None = None
    detail: JSONObject | None = None


class HarnessHealthResponse(BaseModel):
    """Service health response with optional background process status."""

    model_config = ConfigDict(strict=True)

    status: str
    service: str
    version: str
    scheduler: ProcessHealth | None = None
    worker: ProcessHealth | None = None
    artana_model: JSONObject | None = None


def _read_heartbeat(
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
        # Check if process is still alive
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
                last_tick=f"{int(age)}s ago",
                pid=pid,
                detail=detail,
            )
        return ProcessHealth(
            status="healthy",
            last_tick=f"{int(age)}s ago",
            pid=pid,
            detail=detail,
        )
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return ProcessHealth(status="unknown")


@router.get("/health", response_model=HarnessHealthResponse, summary="Health check")
def health_check() -> HarnessHealthResponse:
    """Return liveness information for the harness service and background processes."""
    settings = get_settings()
    artana_model = {
        "probe": get_artana_model_health().model_dump(mode="json"),
        "step_execution": get_step_execution_health().model_dump(mode="json"),
    }
    return HarnessHealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        scheduler=_read_heartbeat(
            "logs/artana-evidence-api-scheduler-heartbeat.json",
            max_age_seconds=600,  # 10 minutes (scheduler polls every 5min)
        ),
        worker=_read_heartbeat(
            "logs/artana-evidence-api-worker-heartbeat.json",
            max_age_seconds=120,  # 2 minutes (worker polls every 30s)
        ),
        artana_model=artana_model,
    )


__all__ = ["HarnessHealthResponse", "health_check", "router"]
