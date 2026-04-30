"""Artana Postgres store configuration and lifecycle helpers."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from artana_evidence_api.runtime.artana_imports import (
    _ARTANA_IMPORT_ERROR,
    PostgresStore,
)
from artana_evidence_api.runtime.logging_support import logger

if TYPE_CHECKING:
    from artana.store import EventStore

_ENV_RUNTIME_ROLE = "ARTANA_RUNTIME_ROLE"
_ENV_ARTANA_POOL_MIN_SIZE = "ARTANA_POOL_MIN_SIZE"
_ENV_ARTANA_POOL_MAX_SIZE = "ARTANA_POOL_MAX_SIZE"
_ENV_ARTANA_COMMAND_TIMEOUT_SECONDS = "ARTANA_COMMAND_TIMEOUT_SECONDS"
_DEFAULT_API_POOL_MIN_SIZE = 1
_DEFAULT_API_POOL_MAX_SIZE = 1
_DEFAULT_SCHEDULER_POOL_MIN_SIZE = 1
_DEFAULT_SCHEDULER_POOL_MAX_SIZE = 2
_DEFAULT_COMBINED_POOL_MIN_SIZE = 1
_DEFAULT_COMBINED_POOL_MAX_SIZE = 2
_DEFAULT_COMMAND_TIMEOUT_SECONDS = 30.0
_DEFAULT_POSTGRES_HOST = os.getenv("ARTANA_POSTGRES_HOST", "localhost")
_DEFAULT_POSTGRES_PORT = os.getenv("ARTANA_POSTGRES_PORT", "5432")
_DEFAULT_POSTGRES_DB = os.getenv("ARTANA_POSTGRES_DB", "artana_dev")
_DEFAULT_POSTGRES_USER = os.getenv("ARTANA_POSTGRES_USER", "artana_dev")
_DEFAULT_POSTGRES_PASSWORD = os.getenv(
    "ARTANA_POSTGRES_PASSWORD",
    "artana_dev_password",
)
_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg2://"
    f"{_DEFAULT_POSTGRES_USER}:{_DEFAULT_POSTGRES_PASSWORD}"
    f"@{_DEFAULT_POSTGRES_HOST}:{_DEFAULT_POSTGRES_PORT}/{_DEFAULT_POSTGRES_DB}"
)
_SHARED_STORE_LOCK = Lock()


@dataclass(frozen=True)
class ArtanaPostgresStoreConfig:
    """Resolved process-local Artana Postgres store configuration."""

    dsn: str
    min_pool_size: int
    max_pool_size: int
    command_timeout_seconds: float


@dataclass
class _SharedStoreState:
    store: EventStore | None = None
    config: ArtanaPostgresStoreConfig | None = None


_SHARED_STORE_STATE = _SharedStoreState()


def _resolve_default_pool_bounds() -> tuple[int, int]:
    runtime_role = os.getenv(_ENV_RUNTIME_ROLE, "all").strip().lower()
    if runtime_role == "api":
        return _DEFAULT_API_POOL_MIN_SIZE, _DEFAULT_API_POOL_MAX_SIZE
    if runtime_role == "scheduler":
        return _DEFAULT_SCHEDULER_POOL_MIN_SIZE, _DEFAULT_SCHEDULER_POOL_MAX_SIZE
    return _DEFAULT_COMBINED_POOL_MIN_SIZE, _DEFAULT_COMBINED_POOL_MAX_SIZE


def _read_positive_int_env(env_name: str, *, default_value: int) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        logger.warning(
            "Invalid Artana pool override %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive Artana pool override %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def _read_positive_float_env(env_name: str, *, default_value: float) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        logger.warning(
            "Invalid Artana timeout override %s=%r; using default %.1f",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive Artana timeout override %s=%r; using default %.1f",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def _resolve_database_url() -> str:
    return os.getenv(
        "ARTANA_EVIDENCE_API_DATABASE_URL",
        os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL),
    )


def resolve_artana_state_uri() -> str:
    explicit_uri = os.getenv("ARTANA_STATE_URI")
    if explicit_uri:
        return explicit_uri
    return _add_artana_schema(_normalize_postgres_dsn(_resolve_database_url()))


def _normalize_postgres_dsn(database_url: str) -> str:
    replacements = (
        ("postgresql+psycopg2://", "postgresql://"),
        ("postgresql+psycopg://", "postgresql://"),
        ("postgresql+asyncpg://", "postgresql://"),
    )
    for prefix, replacement in replacements:
        if database_url.startswith(prefix):
            return database_url.replace(prefix, replacement, 1)
    return database_url


def _add_artana_schema(postgres_url: str) -> str:
    split = urlsplit(postgres_url)
    query_items = parse_qsl(split.query, keep_blank_values=True)

    existing_options = [value for key, value in query_items if key == "options"]
    if existing_options:
        new_options = f"{existing_options[0]} -c search_path=artana,public"
        query_items = [(key, value) for key, value in query_items if key != "options"]
        query_items.append(("options", new_options))
    else:
        query_items.append(("options", "-c search_path=artana,public"))

    rebuilt_query = urlencode(query_items, doseq=True)
    return urlunsplit(
        (
            split.scheme,
            split.netloc,
            split.path,
            rebuilt_query,
            split.fragment,
        ),
    )


def resolve_artana_postgres_store_config() -> ArtanaPostgresStoreConfig:
    default_min_pool_size, default_max_pool_size = _resolve_default_pool_bounds()
    min_pool_size = _read_positive_int_env(
        _ENV_ARTANA_POOL_MIN_SIZE,
        default_value=default_min_pool_size,
    )
    max_pool_size = _read_positive_int_env(
        _ENV_ARTANA_POOL_MAX_SIZE,
        default_value=default_max_pool_size,
    )
    if max_pool_size < min_pool_size:
        logger.warning(
            "Artana pool max (%d) is below min (%d); clamping max to min",
            max_pool_size,
            min_pool_size,
        )
        max_pool_size = min_pool_size
    return ArtanaPostgresStoreConfig(
        dsn=resolve_artana_state_uri(),
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size,
        command_timeout_seconds=_read_positive_float_env(
            _ENV_ARTANA_COMMAND_TIMEOUT_SECONDS,
            default_value=_DEFAULT_COMMAND_TIMEOUT_SECONDS,
        ),
    )


def create_artana_postgres_store() -> EventStore:
    """Create one request-local Artana PostgresStore."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        message = (
            "artana-kernel is required for Artana state storage. Install "
            "dependency 'artana-kernel @ git+https://github.com/"
            "aandresalvarez/artana-kernel.git@"
            "5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(message) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    return PostgresStore(
        resolved_config.dsn,
        min_pool_size=resolved_config.min_pool_size,
        max_pool_size=resolved_config.max_pool_size,
        command_timeout_seconds=resolved_config.command_timeout_seconds,
    )


def get_shared_artana_postgres_store() -> EventStore:
    """Return the process-local Artana store singleton."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        message = (
            "artana-kernel is required for shared Artana state storage. Install "
            "dependency 'artana-kernel @ git+https://github.com/"
            "aandresalvarez/artana-kernel.git@"
            "5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(message) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    with _SHARED_STORE_LOCK:
        if _SHARED_STORE_STATE.store is not None:
            if resolved_config == _SHARED_STORE_STATE.config:
                return _SHARED_STORE_STATE.store
            logger.warning(
                "Shared Artana PostgresStore already initialized with %s; "
                "ignoring later config change to %s for this process",
                _SHARED_STORE_STATE.config,
                resolved_config,
            )
            return _SHARED_STORE_STATE.store
        _SHARED_STORE_STATE.store = PostgresStore(
            resolved_config.dsn,
            min_pool_size=resolved_config.min_pool_size,
            max_pool_size=resolved_config.max_pool_size,
            command_timeout_seconds=resolved_config.command_timeout_seconds,
        )
        _SHARED_STORE_STATE.config = resolved_config
        return _SHARED_STORE_STATE.store


async def close_shared_artana_postgres_store() -> None:
    with _SHARED_STORE_LOCK:
        store = _SHARED_STORE_STATE.store
        _SHARED_STORE_STATE.store = None
        _SHARED_STORE_STATE.config = None
    if store is None:
        return
    try:
        await store.close()
    except Exception:  # noqa: BLE001
        logger.warning("Shared Artana PostgresStore close failed", exc_info=True)


def close_shared_artana_postgres_store_sync() -> None:
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(close_shared_artana_postgres_store())
        return
    running_loop.create_task(close_shared_artana_postgres_store())


__all__ = [
    "ArtanaPostgresStoreConfig",
    "_DEFAULT_DATABASE_URL",
    "_DEFAULT_POSTGRES_DB",
    "_DEFAULT_POSTGRES_HOST",
    "_DEFAULT_POSTGRES_PASSWORD",
    "_DEFAULT_POSTGRES_PORT",
    "_DEFAULT_POSTGRES_USER",
    "_SHARED_STORE_LOCK",
    "_SHARED_STORE_STATE",
    "_add_artana_schema",
    "_normalize_postgres_dsn",
    "_read_positive_float_env",
    "_read_positive_int_env",
    "_resolve_database_url",
    "_resolve_default_pool_bounds",
    "close_shared_artana_postgres_store",
    "close_shared_artana_postgres_store_sync",
    "create_artana_postgres_store",
    "get_shared_artana_postgres_store",
    "resolve_artana_postgres_store_config",
    "resolve_artana_state_uri",
]
