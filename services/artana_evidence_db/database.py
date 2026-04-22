"""Database session and RLS support for the standalone graph API service."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol, cast

from artana_evidence_db.schema_support import (
    graph_postgres_search_path,
    graph_schema_name,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings
from .graph_access import GraphRlsSessionContext

if TYPE_CHECKING:
    from collections.abc import Iterator
    from uuid import UUID

_SETTINGS = get_settings()

_DEFAULT_DB_POOL_SIZE = 10
_DEFAULT_DB_MAX_OVERFLOW = 10
_DEFAULT_DB_POOL_TIMEOUT_SECONDS = 30
_DEFAULT_DB_POOL_RECYCLE_SECONDS = 1800


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


def _build_graph_engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "pool_pre_ping": True,
    }

    if not _is_postgres_url(database_url):
        return kwargs

    kwargs.update(
        {
            "pool_size": _env_int("GRAPH_DB_POOL_SIZE", _DEFAULT_DB_POOL_SIZE),
            "max_overflow": _env_int(
                "GRAPH_DB_MAX_OVERFLOW",
                _DEFAULT_DB_MAX_OVERFLOW,
            ),
            "pool_timeout": _env_int(
                "GRAPH_DB_POOL_TIMEOUT_SECONDS",
                _DEFAULT_DB_POOL_TIMEOUT_SECONDS,
            ),
            "pool_recycle": _env_int(
                "GRAPH_DB_POOL_RECYCLE_SECONDS",
                _DEFAULT_DB_POOL_RECYCLE_SECONDS,
            ),
            "pool_use_lifo": _env_bool("GRAPH_DB_POOL_USE_LIFO", default=True),
        },
    )
    return kwargs


_ENGINE_KWARGS: dict[str, object] = {
    "future": True,
    **_build_graph_engine_kwargs(_SETTINGS.database_url),
}

engine = create_engine(_SETTINGS.database_url, **_ENGINE_KWARGS)

_GRAPH_SCHEMA = graph_schema_name(_SETTINGS.database_schema)


class _CursorProtocol(Protocol):
    def execute(self, statement: str) -> object: ...

    def close(self) -> object: ...


class _CursorConnectionProtocol(Protocol):
    def cursor(self) -> _CursorProtocol: ...


if _is_postgres_url(_SETTINGS.database_url) and _GRAPH_SCHEMA is not None:

    def _set_graph_search_path(
        dbapi_connection: object,
        _connection_record: object,
    ) -> None:
        connection = cast("_CursorConnectionProtocol", dbapi_connection)
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"SET search_path TO {graph_postgres_search_path(_GRAPH_SCHEMA)}",
            )
        finally:
            cursor.close()

    event.listen(engine, "connect", _set_graph_search_path)


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


def set_graph_rls_session_context(
    session: Session,
    *,
    context: GraphRlsSessionContext,
) -> None:
    """Apply one graph-core RLS session context to the SQLAlchemy session."""
    set_session_rls_context(
        session,
        current_user_id=context.current_user_id,
        has_phi_access=context.has_phi_access,
        is_admin=context.is_admin,
        bypass_rls=context.bypass_rls,
    )


def get_session() -> Iterator[Session]:
    """Provide a request-scoped SQLAlchemy session."""
    db = SessionLocal()
    try:
        set_session_rls_context(db, bypass_rls=False)
        yield db
    finally:
        db.close()


__all__ = [
    "SessionLocal",
    "engine",
    "get_session",
    "set_graph_rls_session_context",
    "set_session_rls_context",
]
