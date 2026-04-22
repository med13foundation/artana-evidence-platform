from __future__ import annotations

import os

from sqlalchemy.engine import make_url

DEFAULT_DB_POOL_SIZE = 10
DEFAULT_DB_MAX_OVERFLOW = 10
DEFAULT_DB_POOL_TIMEOUT_SECONDS = 30
DEFAULT_DB_POOL_RECYCLE_SECONDS = 1800


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default

    value = int(raw_value)
    if value < 0:
        msg = f"{name} must be greater than or equal to 0"
        raise ValueError(msg)
    return value


def _env_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    msg = f"{name} must be a boolean value"
    raise ValueError(msg)


def _is_postgres_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "postgresql"


def build_engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }

    if not _is_postgres_url(database_url):
        return kwargs

    kwargs.update(
        {
            "pool_size": _env_int("ARTANA_DB_POOL_SIZE", DEFAULT_DB_POOL_SIZE),
            "max_overflow": _env_int(
                "ARTANA_DB_MAX_OVERFLOW",
                DEFAULT_DB_MAX_OVERFLOW,
            ),
            "pool_timeout": _env_int(
                "ARTANA_DB_POOL_TIMEOUT_SECONDS",
                DEFAULT_DB_POOL_TIMEOUT_SECONDS,
            ),
            "pool_recycle": _env_int(
                "ARTANA_DB_POOL_RECYCLE_SECONDS",
                DEFAULT_DB_POOL_RECYCLE_SECONDS,
            ),
            "pool_use_lifo": _env_bool("ARTANA_DB_POOL_USE_LIFO", default=True),
        },
    )
    return kwargs
