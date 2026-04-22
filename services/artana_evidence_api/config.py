"""Service-local startup configuration for the harness API."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DEFAULT_HOST = "0.0.0.0"  # noqa: S104
_DEFAULT_GRAPH_API_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class GraphHarnessServiceSettings:
    """Resolved runtime settings for the harness API service."""

    app_name: str
    host: str
    port: int
    reload: bool
    workers: int
    openapi_url: str
    version: str
    graph_api_url: str
    graph_api_timeout_seconds: float
    scheduler_poll_seconds: float
    scheduler_run_once: bool
    worker_id: str
    worker_poll_seconds: float
    worker_run_once: bool
    worker_lease_ttl_seconds: int
    sync_wait_timeout_seconds: float
    sync_wait_poll_seconds: float
    document_storage_base_path: str
    space_acl_mode: str


def _read_bool_env(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> GraphHarnessServiceSettings:
    """Return cached harness service settings."""
    raw_port = os.getenv(
        "ARTANA_EVIDENCE_API_SERVICE_PORT",
        os.getenv("PORT", "8080"),
    ).strip()
    return GraphHarnessServiceSettings(
        app_name=os.getenv(
            "ARTANA_EVIDENCE_API_APP_NAME",
            "Artana Evidence API",
        ).strip()
        or "Artana Evidence API",
        host=os.getenv("ARTANA_EVIDENCE_API_SERVICE_HOST", _DEFAULT_HOST).strip()
        or _DEFAULT_HOST,
        port=int(raw_port),
        reload=_read_bool_env("ARTANA_EVIDENCE_API_SERVICE_RELOAD", default=False),
        workers=int(
            os.getenv("ARTANA_EVIDENCE_API_SERVICE_WORKERS", "1").strip() or "1",
        ),
        openapi_url="/openapi.json",
        version="0.1.0",
        graph_api_url=os.getenv(
            "GRAPH_API_URL",
            "http://127.0.0.1:8090",
        ).strip()
        or "http://127.0.0.1:8090",
        graph_api_timeout_seconds=float(
            os.getenv(
                "ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS",
                str(_DEFAULT_GRAPH_API_TIMEOUT_SECONDS),
            ).strip(),
        ),
        scheduler_poll_seconds=float(
            os.getenv("ARTANA_EVIDENCE_API_SCHEDULER_POLL_SECONDS", "300").strip(),
        ),
        scheduler_run_once=_read_bool_env(
            "ARTANA_EVIDENCE_API_SCHEDULER_RUN_ONCE",
            default=False,
        ),
        worker_id=os.getenv(
            "ARTANA_EVIDENCE_API_WORKER_ID",
            "artana-evidence-api-worker",
        ).strip()
        or "artana-evidence-api-worker",
        worker_poll_seconds=float(
            os.getenv("ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS", "1").strip(),
        ),
        worker_run_once=_read_bool_env(
            "ARTANA_EVIDENCE_API_WORKER_RUN_ONCE",
            default=False,
        ),
        worker_lease_ttl_seconds=int(
            os.getenv("ARTANA_EVIDENCE_API_WORKER_LEASE_TTL_SECONDS", "300").strip(),
        ),
        sync_wait_timeout_seconds=float(
            os.getenv("ARTANA_EVIDENCE_API_SYNC_WAIT_TIMEOUT_SECONDS", "55").strip(),
        ),
        sync_wait_poll_seconds=float(
            os.getenv("ARTANA_EVIDENCE_API_SYNC_WAIT_POLL_SECONDS", "0.25").strip(),
        ),
        document_storage_base_path=str(
            Path(
                os.getenv(
                    "ARTANA_EVIDENCE_API_STORAGE_BASE_PATH",
                    str(Path(tempfile.gettempdir()) / "artana_evidence_api_storage"),
                ),
            )
            .expanduser()
            .resolve(),
        ),
        space_acl_mode=os.getenv(
            "SPACE_ACL_MODE",
            "audit",
        )
        .strip()
        .lower()
        or "audit",
    )


__all__ = ["GraphHarnessServiceSettings", "get_settings"]
