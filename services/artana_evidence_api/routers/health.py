"""Health endpoints for the standalone harness service."""

from __future__ import annotations

from artana_evidence_api.config import get_settings
from artana_evidence_api.process_health import ProcessHealth, read_heartbeat
from artana_evidence_api.runtime_support import get_artana_model_health
from artana_evidence_api.step_helpers import get_step_execution_health
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


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
    return read_heartbeat(path, max_age_seconds=max_age_seconds)


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
        artana_model=json_object_or_empty(artana_model),
    )


__all__ = ["HarnessHealthResponse", "health_check", "router"]
