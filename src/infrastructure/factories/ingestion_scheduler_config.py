"""Configuration helpers for ingestion scheduler factory wiring."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.database.session import SessionLocal
from src.database.url_resolver import resolve_sync_database_url
from src.infrastructure.scheduling import InMemoryScheduler, PostgresScheduler

if TYPE_CHECKING:
    from src.application.services.ports.scheduler_port import SchedulerPort

POSTGRES_PREFIXES = (
    "postgresql://",
    "postgresql+psycopg2://",
    "postgresql+psycopg://",
    "postgresql+asyncpg://",
)
BACKEND_INMEMORY = "inmemory"
BACKEND_POSTGRES = "postgres"
ENV_SCHEDULER_HEARTBEAT_SECONDS = "ARTANA_INGESTION_SCHEDULER_HEARTBEAT_SECONDS"
ENV_SCHEDULER_LEASE_TTL_SECONDS = "ARTANA_INGESTION_SCHEDULER_LEASE_TTL_SECONDS"
ENV_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS = (
    "ARTANA_INGESTION_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS"
)
ENV_INGESTION_JOB_HARD_TIMEOUT_SECONDS = "ARTANA_INGESTION_JOB_HARD_TIMEOUT_SECONDS"
ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK = "ARTANA_ENABLE_POST_INGESTION_PIPELINE_HOOK"
ENV_ENABLE_POST_INGESTION_GRAPH_STAGE = "ARTANA_ENABLE_POST_INGESTION_GRAPH_STAGE"
ENV_POST_INGESTION_HOOK_TIMEOUT_SECONDS = "ARTANA_POST_INGESTION_HOOK_TIMEOUT_SECONDS"
ENV_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS = (
    "ARTANA_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS"
)
DEFAULT_SCHEDULER_HEARTBEAT_SECONDS = 30
DEFAULT_SCHEDULER_LEASE_TTL_SECONDS = 120
DEFAULT_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS = 300
DEFAULT_INGESTION_JOB_HARD_TIMEOUT_SECONDS = 7200
DEFAULT_POST_INGESTION_HOOK_TIMEOUT_SECONDS = 1800
DEFAULT_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS = 180

_INMEMORY_SCHEDULER = InMemoryScheduler()


def get_configured_scheduler_backend_name() -> str:
    """Return the normalized scheduler backend name from env configuration."""
    configured = os.getenv(
        "ARTANA_INGESTION_SCHEDULER_BACKEND",
        BACKEND_INMEMORY,
    ).strip()
    normalized = configured.lower()
    if normalized in {"in-memory", "memory"}:
        return BACKEND_INMEMORY
    if normalized in {BACKEND_INMEMORY, BACKEND_POSTGRES}:
        return normalized
    msg = (
        "Unsupported ARTANA_INGESTION_SCHEDULER_BACKEND value. "
        "Use 'inmemory' or 'postgres'."
    )
    raise ValueError(msg)


def resolve_scheduler_backend() -> SchedulerPort:
    """Build the configured scheduler backend."""
    backend_name = get_configured_scheduler_backend_name()
    if backend_name == BACKEND_INMEMORY:
        return _INMEMORY_SCHEDULER

    database_url = resolve_sync_database_url()
    if not database_url.startswith(POSTGRES_PREFIXES):
        msg = (
            "Postgres scheduler backend requires a Postgres DATABASE_URL. "
            f"Resolved URL: {database_url}"
        )
        raise ValueError(msg)
    return PostgresScheduler(session_factory=SessionLocal)


def read_positive_int_env(env_key: str, *, default: int) -> int:
    """Read a positive integer from an env var with a default."""
    raw_value = os.getenv(env_key)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed_value = int(raw_value.strip())
    except ValueError as exc:
        msg = f"{env_key} must be a positive integer (received: {raw_value!r})"
        raise ValueError(msg) from exc
    if parsed_value <= 0:
        msg = f"{env_key} must be a positive integer (received: {raw_value!r})"
        raise ValueError(msg)
    return parsed_value


def read_bool_env(env_key: str, *, default: bool) -> bool:
    """Read a boolean feature flag from an env var with a default."""
    raw_value = os.getenv(env_key)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


__all__ = [
    "DEFAULT_INGESTION_JOB_HARD_TIMEOUT_SECONDS",
    "DEFAULT_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS",
    "DEFAULT_POST_INGESTION_HOOK_TIMEOUT_SECONDS",
    "DEFAULT_SCHEDULER_HEARTBEAT_SECONDS",
    "DEFAULT_SCHEDULER_LEASE_TTL_SECONDS",
    "DEFAULT_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS",
    "ENV_ENABLE_POST_INGESTION_GRAPH_STAGE",
    "ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK",
    "ENV_INGESTION_JOB_HARD_TIMEOUT_SECONDS",
    "ENV_POST_INGESTION_GRAPH_SEED_TIMEOUT_SECONDS",
    "ENV_POST_INGESTION_HOOK_TIMEOUT_SECONDS",
    "ENV_SCHEDULER_HEARTBEAT_SECONDS",
    "ENV_SCHEDULER_LEASE_TTL_SECONDS",
    "ENV_SCHEDULER_STALE_RUNNING_TIMEOUT_SECONDS",
    "read_bool_env",
    "read_positive_int_env",
    "resolve_scheduler_backend",
]
