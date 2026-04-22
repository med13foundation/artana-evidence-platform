"""Best-effort Postgres LISTEN/NOTIFY support for harness worker wake-ups."""

from __future__ import annotations

import json
import logging
import select
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypedDict, cast
from uuid import UUID

import psycopg2  # type: ignore[import-untyped]
from artana_evidence_api.database import DATABASE_URL
from psycopg2 import OperationalError  # type: ignore[import-untyped]
from sqlalchemy.engine import make_url

LOGGER = logging.getLogger(__name__)
_WORKER_NOTIFY_CHANNEL = "artana_evidence_api_worker_queue"


class _PsycopgCursor(Protocol):
    def execute(
        self,
        statement: str,
        params: Sequence[object] | None = None,
    ) -> None: ...

    def close(self) -> None: ...


class _PsycopgConnection(Protocol):
    autocommit: bool
    notifies: list[object]

    def close(self) -> None: ...

    def cursor(self) -> _PsycopgCursor: ...

    def fileno(self) -> int: ...

    def poll(self) -> None: ...


class _PostgresConnectionKwargs(TypedDict):
    dbname: str | None
    user: str | None
    password: str | None
    host: str
    port: int


def _postgres_connection_kwargs() -> _PostgresConnectionKwargs | None:
    url = make_url(DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        return None
    return {
        "dbname": url.database,
        "user": url.username,
        "password": url.password,
        "host": url.host or "localhost",
        "port": url.port or 5432,
    }


def _connect() -> _PsycopgConnection | None:
    conn_kwargs = _postgres_connection_kwargs()
    if conn_kwargs is None:
        return None
    connection = psycopg2.connect(
        dbname=conn_kwargs["dbname"],
        user=conn_kwargs["user"],
        password=conn_kwargs["password"],
        host=conn_kwargs["host"],
        port=conn_kwargs["port"],
    )
    return cast("_PsycopgConnection", connection)


@dataclass(slots=True)
class WorkerQueueNotificationListener:
    """Blocking LISTEN connection that can wake the async worker loop."""

    connection: _PsycopgConnection

    def wait(self, timeout_seconds: float) -> bool:
        """Block until a wake-up notification arrives or the timeout expires."""
        if self._drain_notifications():
            return True
        if timeout_seconds <= 0:
            return False
        ready, _, _ = select.select([self.connection], [], [], timeout_seconds)
        if not ready:
            return False
        self.connection.poll()
        return self._drain_notifications()

    def close(self) -> None:
        self.connection.close()

    def _drain_notifications(self) -> bool:
        notified = False
        while self.connection.notifies:
            self.connection.notifies.pop(0)
            notified = True
        return notified


def notify_worker_run_available(
    *,
    run_id: str,
    space_id: UUID | str,
    harness_id: str,
) -> bool:
    """Send one best-effort worker wake-up notification for a queued run."""
    connection = None
    cursor = None
    payload = json.dumps(
        {
            "run_id": run_id,
            "space_id": str(space_id),
            "harness_id": harness_id,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    try:
        connection = _connect()
        if connection is None:
            return False
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute(
            "SELECT pg_notify(%s, %s)",
            (_WORKER_NOTIFY_CHANNEL, payload),
        )
    except (OperationalError, OSError) as exc:
        LOGGER.warning("Worker queue notify failed", exc_info=exc)
        return False
    else:
        return True
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def open_worker_queue_notification_listener() -> WorkerQueueNotificationListener | None:
    """Open a best-effort LISTEN connection for worker wake-up notifications."""
    connection = None
    cursor = None
    try:
        connection = _connect()
        if connection is None:
            return None
        connection.autocommit = True
        cursor = connection.cursor()
        cursor.execute("LISTEN artana_evidence_api_worker_queue")
        return WorkerQueueNotificationListener(connection=connection)
    except (OperationalError, OSError) as exc:
        LOGGER.warning("Worker queue LISTEN setup failed", exc_info=exc)
        if connection is not None:
            connection.close()
        return None
    finally:
        if cursor is not None:
            cursor.close()


__all__ = [
    "WorkerQueueNotificationListener",
    "notify_worker_run_available",
    "open_worker_queue_notification_listener",
]
