"""Service-local SQLAlchemy session wiring for graph-harness."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.db_schema import harness_runtime_postgres_search_path
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

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


def _resolve_database_url() -> str:
    return os.getenv(
        "ARTANA_EVIDENCE_API_DATABASE_URL",
        os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL),
    )


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value == "":
        return default
    value = int(raw_value)
    if value < 0:
        message = f"{name} must be greater than or equal to 0"
        raise ValueError(message)
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
    message = f"{name} must be a boolean value"
    raise ValueError(message)


def _is_postgres_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "postgresql"


def _build_engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }
    if not _is_postgres_url(database_url):
        return kwargs
    kwargs.update(
        {
            "pool_size": _env_int("ARTANA_EVIDENCE_API_DB_POOL_SIZE", 10),
            "max_overflow": _env_int("ARTANA_EVIDENCE_API_DB_MAX_OVERFLOW", 10),
            "pool_timeout": _env_int("ARTANA_EVIDENCE_API_DB_POOL_TIMEOUT_SECONDS", 30),
            "pool_recycle": _env_int(
                "ARTANA_EVIDENCE_API_DB_POOL_RECYCLE_SECONDS",
                1800,
            ),
            "pool_use_lifo": _env_bool(
                "ARTANA_EVIDENCE_API_DB_POOL_USE_LIFO",
                default=True,
            ),
        },
    )
    return kwargs


DATABASE_URL = _resolve_database_url()
engine = create_engine(DATABASE_URL, **_build_engine_kwargs(DATABASE_URL))


class _CursorProtocol(Protocol):
    def execute(self, statement: str) -> object: ...

    def close(self) -> object: ...


class _CursorConnectionProtocol(Protocol):
    def cursor(self) -> _CursorProtocol: ...


if _is_postgres_url(DATABASE_URL):
    _RUNTIME_SEARCH_PATH = harness_runtime_postgres_search_path()

    def _set_runtime_search_path(
        dbapi_connection: object,
        _connection_record: object,
    ) -> None:
        connection = cast("_CursorConnectionProtocol", dbapi_connection)
        cursor = connection.cursor()
        try:
            cursor.execute(f"SET search_path TO {_RUNTIME_SEARCH_PATH}")
        finally:
            cursor.close()

    event.listen(engine, "connect", _set_runtime_search_path)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def _bool_setting(*, value: bool) -> str:
    return "true" if value else "false"


def set_session_rls_context(
    session: Session,
    *,
    current_user_id: UUID | str | None = None,
    has_phi_access: bool = False,
    is_admin: bool = False,
    bypass_rls: bool = False,
) -> None:
    """Set PostgreSQL session settings used by row-level security policies."""
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return

    user_setting = str(current_user_id) if current_user_id is not None else ""
    session.execute(
        text("SELECT set_config('app.current_user_id', :value, false)"),
        {"value": user_setting},
    )
    session.execute(
        text("SELECT set_config('app.has_phi_access', :value, false)"),
        {"value": _bool_setting(value=has_phi_access)},
    )
    session.execute(
        text("SELECT set_config('app.is_admin', :value, false)"),
        {"value": _bool_setting(value=is_admin)},
    )
    session.execute(
        text("SELECT set_config('app.bypass_rls', :value, false)"),
        {"value": _bool_setting(value=bypass_rls)},
    )


def get_session() -> Generator[Session]:
    """Provide a SQLAlchemy session scoped to the current request."""
    db = SessionLocal()
    try:
        set_session_rls_context(db, bypass_rls=False)
        yield db
    finally:
        db.close()


__all__ = [
    "DATABASE_URL",
    "SessionLocal",
    "engine",
    "get_session",
    "set_session_rls_context",
]
