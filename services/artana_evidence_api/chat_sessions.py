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


class HarnessChatSessionStore:
    """Store and retrieve chat session state."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: dict[str, HarnessChatSessionRecord] = {}
        self._messages_by_session: dict[str, list[HarnessChatMessageRecord]] = {}

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
    "HarnessChatSessionRecord",
    "HarnessChatSessionStore",
]
