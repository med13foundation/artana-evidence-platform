"""Shared Artana Postgres store lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from threading import Lock

from src.infrastructure.llm.config import resolve_artana_state_uri

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.store import PostgresStore
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

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
    """Mutable process-local cache for the shared Artana store."""

    store: PostgresStore | None = None
    config: ArtanaPostgresStoreConfig | None = None


_SHARED_STORE_STATE = _SharedStoreState()


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


def _resolve_default_pool_bounds() -> tuple[int, int]:
    runtime_role = os.getenv(_ENV_RUNTIME_ROLE, "all").strip().lower()
    if runtime_role == "api":
        return _DEFAULT_API_POOL_MIN_SIZE, _DEFAULT_API_POOL_MAX_SIZE
    if runtime_role == "scheduler":
        return _DEFAULT_SCHEDULER_POOL_MIN_SIZE, _DEFAULT_SCHEDULER_POOL_MAX_SIZE
    return _DEFAULT_COMBINED_POOL_MIN_SIZE, _DEFAULT_COMBINED_POOL_MAX_SIZE


def resolve_artana_postgres_store_config() -> ArtanaPostgresStoreConfig:
    """Resolve effective process-level Artana pool settings from the environment."""
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


def get_shared_artana_postgres_store() -> PostgresStore:
    """Return one shared Artana PostgresStore instance per process."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        msg = (
            "artana-kernel is required for shared Artana state storage. Install dependency "
            "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

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


def create_artana_postgres_store() -> PostgresStore:
    """Create a new Artana PostgresStore using the effective runtime config."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        msg = (
            "artana-kernel is required for Artana state storage. Install dependency "
            "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    return PostgresStore(
        resolved_config.dsn,
        min_pool_size=resolved_config.min_pool_size,
        max_pool_size=resolved_config.max_pool_size,
        command_timeout_seconds=resolved_config.command_timeout_seconds,
    )


async def close_shared_artana_postgres_store() -> None:
    """Best-effort shutdown for the shared Artana PostgresStore."""
    with _SHARED_STORE_LOCK:
        store = _SHARED_STORE_STATE.store
        _SHARED_STORE_STATE.store = None
        _SHARED_STORE_STATE.config = None
    if store is None:
        return
    try:
        await store.close()
    except Exception:  # noqa: BLE001 - shutdown should not fail request teardown
        logger.warning(
            "Shared Artana PostgresStore close failed",
            exc_info=True,
        )


def close_shared_artana_postgres_store_sync() -> None:
    """Synchronous wrapper used by tests and non-async cleanup paths."""
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(close_shared_artana_postgres_store())
        return
    running_loop.create_task(close_shared_artana_postgres_store())


def _reset_shared_artana_postgres_store_for_tests() -> None:
    """Reset store cache between deterministic unit tests."""
    with _SHARED_STORE_LOCK:
        _SHARED_STORE_STATE.store = None
        _SHARED_STORE_STATE.config = None


__all__ = [
    "ArtanaPostgresStoreConfig",
    "_reset_shared_artana_postgres_store_for_tests",
    "create_artana_postgres_store",
    "close_shared_artana_postgres_store",
    "close_shared_artana_postgres_store_sync",
    "get_shared_artana_postgres_store",
    "resolve_artana_postgres_store_config",
]
