"""SQLite test helpers for transient test databases."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import event

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

DEFAULT_BUSY_TIMEOUT_MS = 5_000


def _adapt_sqlite_date(value: date) -> str:
    return value.isoformat()


def _adapt_sqlite_datetime(value: datetime) -> str:
    return value.isoformat(sep=" ")


def _convert_sqlite_date(value: bytes) -> date:
    return date.fromisoformat(value.decode())


def _convert_sqlite_datetime(value: bytes) -> datetime:
    return datetime.fromisoformat(value.decode())


@lru_cache(maxsize=1)
def register_sqlite_datetime_adapters() -> None:
    """Register explicit sqlite3 adapters so Python 3.12+ emits no deprecations."""
    sqlite3.register_adapter(date, _adapt_sqlite_date)
    sqlite3.register_adapter(datetime, _adapt_sqlite_datetime)
    sqlite3.register_converter("date", _convert_sqlite_date)
    sqlite3.register_converter("datetime", _convert_sqlite_datetime)
    sqlite3.register_converter("timestamp", _convert_sqlite_datetime)


register_sqlite_datetime_adapters()


class SQLiteCursor(Protocol):
    def execute(self, statement: str) -> object: ...

    def fetchone(self) -> object: ...

    def close(self) -> None: ...


class SQLiteConnection(Protocol):
    def cursor(self) -> SQLiteCursor: ...


def configure_sqlite_engine(
    engine: "Engine",  # noqa: UP037
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    synchronous_level: str = "NORMAL",
) -> None:
    """Attach pragmas needed by SQLite-based test engines."""
    register_sqlite_datetime_adapters()

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(
        dbapi_connection: SQLiteConnection,
        _: object,
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute(f"PRAGMA synchronous={synchronous_level};")
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.fetchone()
        cursor.close()


def build_sqlite_connect_args(
    timeout_seconds: int = 5,
    *,
    include_thread_check: bool = True,
) -> dict[str, int | bool]:
    """Build sqlite connect args for tests."""
    connect_args: dict[str, int | bool] = {"timeout": timeout_seconds}
    if include_thread_check:
        connect_args["check_same_thread"] = False
    return connect_args


__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS",
    "build_sqlite_connect_args",
    "configure_sqlite_engine",
    "register_sqlite_datetime_adapters",
]
