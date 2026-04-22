"""Unit tests for Postgres-backed worker wake-up notifications."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from artana_evidence_api import worker_notifications


@dataclass
class _FakeCursor:
    executed: list[tuple[str, tuple[object, ...] | None]] = field(default_factory=list)
    closed: bool = False

    def execute(
        self,
        statement: str,
        params: tuple[object, ...] | None = None,
    ) -> None:
        self.executed.append((statement, params))

    def close(self) -> None:
        self.closed = True


@dataclass
class _FakeConnection:
    cursor_instance: _FakeCursor = field(default_factory=_FakeCursor)
    notifies: list[object] = field(default_factory=list)
    autocommit: bool = False
    closed: bool = False
    polled: bool = False

    def close(self) -> None:
        self.closed = True

    def cursor(self) -> _FakeCursor:
        return self.cursor_instance

    def fileno(self) -> int:
        return 0

    def poll(self) -> None:
        self.polled = True
        self.notifies.append(object())


def test_listener_wait_short_circuits_when_notification_already_buffered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection(notifies=[object()])
    listener = worker_notifications.WorkerQueueNotificationListener(
        connection=connection,
    )

    def _unexpected_select(
        *_args: object,
        **_kwargs: object,
    ) -> tuple[list[object], list[object], list[object]]:
        raise AssertionError("select.select should not run when notifications exist")

    monkeypatch.setattr(worker_notifications.select, "select", _unexpected_select)

    assert listener.wait(timeout_seconds=1.0) is True
    assert connection.notifies == []


def test_listener_wait_uses_select_and_polls_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    listener = worker_notifications.WorkerQueueNotificationListener(
        connection=connection,
    )
    select_calls: list[float] = []

    def _fake_select(
        readers: list[object],
        _writers: list[object],
        _errors: list[object],
        timeout: float,
    ) -> tuple[list[object], list[object], list[object]]:
        assert readers == [connection]
        select_calls.append(timeout)
        return ([connection], [], [])

    monkeypatch.setattr(worker_notifications.select, "select", _fake_select)

    assert listener.wait(timeout_seconds=2.5) is True
    assert connection.polled is True
    assert select_calls == [2.5]
    assert connection.notifies == []


def test_notify_worker_run_available_emits_pg_notify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(worker_notifications, "_connect", lambda: connection)

    notified = worker_notifications.notify_worker_run_available(
        run_id="run-123",
        space_id="space-456",
        harness_id="graph-chat",
    )

    assert notified is True
    assert connection.autocommit is True
    assert connection.closed is True
    assert connection.cursor_instance.closed is True
    assert connection.cursor_instance.executed == [
        (
            "SELECT pg_notify(%s, %s)",
            (
                "artana_evidence_api_worker_queue",
                '{"harness_id": "graph-chat", "run_id": "run-123", "space_id": "space-456"}',
            ),
        ),
    ]


def test_notify_worker_run_available_returns_false_without_postgres_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_notifications, "_connect", lambda: None)

    notified = worker_notifications.notify_worker_run_available(
        run_id="run-123",
        space_id="space-456",
        harness_id="graph-chat",
    )

    assert notified is False


def test_open_worker_queue_notification_listener_registers_listen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    monkeypatch.setattr(worker_notifications, "_connect", lambda: connection)

    listener = worker_notifications.open_worker_queue_notification_listener()

    assert listener is not None
    assert connection.autocommit is True
    assert connection.closed is False
    assert connection.cursor_instance.closed is True
    assert connection.cursor_instance.executed == [
        ("LISTEN artana_evidence_api_worker_queue", None),
    ]


def test_open_worker_queue_notification_listener_returns_none_without_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_notifications, "_connect", lambda: None)

    listener = worker_notifications.open_worker_queue_notification_listener()

    assert listener is None
