"""Service-local chat session storage contracts for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.types.common import JSONObject  # noqa: TC001


@dataclass(frozen=True, slots=True)
class HarnessChatSessionRecord:
    """Durable metadata for one chat session."""

    id: str
    space_id: str
    title: str
    created_by: str
    last_run_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessChatMessageRecord:
    """One message in a harness chat session."""

    id: str
    session_id: str
    space_id: str
    role: str
    content: str
    run_id: str | None
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessChatSessionStartRecord:
    """One idempotent request to start a chat session with its first message."""

    id: str
    space_id: str
    created_by: str
    idempotency_key: str
    request_signature: JSONObject
    session_id: str | None
    run_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class HarnessChatSessionStore:
    """Store and retrieve chat session state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, HarnessChatSessionRecord] = {}
        self._messages_by_session: dict[str, list[HarnessChatMessageRecord]] = {}
        self._first_message_starts: dict[
            tuple[str, str, str],
            HarnessChatSessionStartRecord,
        ] = {}

    def reserve_first_message_start(
        self,
        *,
        space_id: UUID | str,
        created_by: UUID | str,
        idempotency_key: str,
        request_signature: JSONObject,
    ) -> tuple[HarnessChatSessionStartRecord, bool]:
        """Reserve one idempotent first-message chat start."""
        now = datetime.now(UTC)
        key = (str(space_id), str(created_by), idempotency_key)
        with self._lock:
            existing = self._first_message_starts.get(key)
            if existing is not None:
                return existing, False
            record = HarnessChatSessionStartRecord(
                id=str(uuid4()),
                space_id=str(space_id),
                created_by=str(created_by),
                idempotency_key=idempotency_key,
                request_signature=request_signature,
                session_id=None,
                run_id=None,
                status="reserved",
                created_at=now,
                updated_at=now,
            )
            self._first_message_starts[key] = record
        return record, True

    def complete_first_message_start(
        self,
        *,
        space_id: UUID | str,
        created_by: UUID | str,
        idempotency_key: str,
        session_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessChatSessionStartRecord | None:
        """Attach the created chat session and queued run to a reservation."""
        key = (str(space_id), str(created_by), idempotency_key)
        with self._lock:
            existing = self._first_message_starts.get(key)
            if existing is None:
                return None
            updated = HarnessChatSessionStartRecord(
                id=existing.id,
                space_id=existing.space_id,
                created_by=existing.created_by,
                idempotency_key=existing.idempotency_key,
                request_signature=existing.request_signature,
                session_id=str(session_id),
                run_id=str(run_id),
                status="queued",
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
            )
            self._first_message_starts[key] = updated
        return updated

    def delete_first_message_start(
        self,
        *,
        space_id: UUID | str,
        created_by: UUID | str,
        idempotency_key: str,
    ) -> None:
        """Remove a reservation that failed before a run was queued."""
        key = (str(space_id), str(created_by), idempotency_key)
        with self._lock:
            self._first_message_starts.pop(key, None)

    def create_session(
        self,
        *,
        space_id: UUID | str,
        title: str,
        created_by: UUID | str,
        status: str = "active",
    ) -> HarnessChatSessionRecord:
        now = datetime.now(UTC)
        session = HarnessChatSessionRecord(
            id=str(uuid4()),
            space_id=str(space_id),
            title=title,
            created_by=str(created_by),
            last_run_id=None,
            status=status,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._sessions[session.id] = session
            self._messages_by_session[session.id] = []
        return session

    def list_sessions(self, *, space_id: UUID | str) -> list[HarnessChatSessionRecord]:
        normalized_space_id = str(space_id)
        with self._lock:
            sessions = [
                record
                for record in self._sessions.values()
                if record.space_id == normalized_space_id
            ]
        return sorted(sessions, key=lambda record: record.updated_at, reverse=True)

    def count_sessions(self, *, space_id: UUID | str) -> int:
        """Return how many chat sessions belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return sum(
                1
                for record in self._sessions.values()
                if record.space_id == normalized_space_id
            )

    def get_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> HarnessChatSessionRecord | None:
        with self._lock:
            session = self._sessions.get(str(session_id))
        if session is None or session.space_id != str(space_id):
            return None
        return session

    def list_messages(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> list[HarnessChatMessageRecord]:
        session = self.get_session(space_id=space_id, session_id=session_id)
        if session is None:
            return []
        with self._lock:
            return list(self._messages_by_session.get(str(session_id), []))

    def add_message(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
        role: str,
        content: str,
        run_id: UUID | str | None = None,
        metadata: JSONObject | None = None,
    ) -> HarnessChatMessageRecord | None:
        session = self.get_session(space_id=space_id, session_id=session_id)
        if session is None:
            return None
        now = datetime.now(UTC)
        message = HarnessChatMessageRecord(
            id=str(uuid4()),
            session_id=str(session_id),
            space_id=str(space_id),
            role=role,
            content=content,
            run_id=str(run_id) if run_id is not None else None,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._messages_by_session.setdefault(str(session_id), []).append(message)
            self._sessions[str(session_id)] = HarnessChatSessionRecord(
                id=session.id,
                space_id=session.space_id,
                title=session.title,
                created_by=session.created_by,
                last_run_id=str(run_id) if run_id is not None else session.last_run_id,
                status=session.status,
                created_at=session.created_at,
                updated_at=now,
            )
        return message

    def discard_empty_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
    ) -> bool | None:
        """Delete a session only when it has not become a real conversation."""
        normalized_session_id = str(session_id)
        with self._lock:
            session = self._sessions.get(normalized_session_id)
            if session is None or session.space_id != str(space_id):
                return None
            messages = self._messages_by_session.get(normalized_session_id, [])
            if messages or session.last_run_id is not None:
                return False
            self._sessions.pop(normalized_session_id, None)
            self._messages_by_session.pop(normalized_session_id, None)
        return True

    def update_session(
        self,
        *,
        space_id: UUID | str,
        session_id: UUID | str,
        title: str | None = None,
        last_run_id: UUID | str | None = None,
        status: str | None = None,
    ) -> HarnessChatSessionRecord | None:
        existing = self.get_session(space_id=space_id, session_id=session_id)
        if existing is None:
            return None
        updated = HarnessChatSessionRecord(
            id=existing.id,
            space_id=existing.space_id,
            title=(
                title
                if isinstance(title, str) and title.strip() != ""
                else existing.title
            ),
            created_by=existing.created_by,
            last_run_id=(
                str(last_run_id) if last_run_id is not None else existing.last_run_id
            ),
            status=(
                status
                if isinstance(status, str) and status.strip() != ""
                else existing.status
            ),
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        with self._lock:
            self._sessions[existing.id] = updated
        return updated


__all__ = [
    "HarnessChatMessageRecord",
    "HarnessChatSessionStartRecord",
    "HarnessChatSessionRecord",
    "HarnessChatSessionStore",
]
