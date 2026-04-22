from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

from sqlalchemy import delete, func, select

from src.models.database.audit import AuditLog

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session
    from sqlalchemy.sql import Select

_SelectType = TypeVar("_SelectType", bound=tuple[object, ...])


@dataclass(slots=True)
class AuditLogQuery:
    """Structured filters for audit log queries."""

    action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    actor_id: str | None = None
    request_id: str | None = None
    ip_address: str | None = None
    success: bool | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None


class AuditRepository(Protocol):
    def record(self, db: Session, log: AuditLog) -> AuditLog: ...

    def list_logs(
        self,
        db: Session,
        *,
        query: AuditLogQuery,
        offset: int,
        limit: int,
    ) -> list[AuditLog]: ...

    def count_logs(
        self,
        db: Session,
        *,
        query: AuditLogQuery,
    ) -> int: ...

    def delete_older_than(
        self,
        db: Session,
        *,
        cutoff: datetime,
        limit: int,
    ) -> int: ...


class SqlAlchemyAuditRepository:
    def record(self, db: Session, log: AuditLog) -> AuditLog:
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def list_logs(
        self,
        db: Session,
        *,
        query: AuditLogQuery,
        offset: int,
        limit: int,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        stmt = self._apply_filters(stmt, query)
        return list(
            db.execute(stmt.offset(max(offset, 0)).limit(max(limit, 1))).scalars(),
        )

    def count_logs(
        self,
        db: Session,
        *,
        query: AuditLogQuery,
    ) -> int:
        count_stmt = select(func.count()).select_from(AuditLog)
        count_stmt = self._apply_filters(count_stmt, query)
        return int(db.execute(count_stmt).scalar_one())

    def delete_older_than(
        self,
        db: Session,
        *,
        cutoff: datetime,
        limit: int,
    ) -> int:
        effective_limit = max(limit, 1)
        candidate_ids = list(
            db.execute(
                select(AuditLog.id)
                .where(AuditLog.created_at < cutoff)
                .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
                .limit(effective_limit),
            ).scalars(),
        )
        if not candidate_ids:
            return 0
        result = db.execute(delete(AuditLog).where(AuditLog.id.in_(candidate_ids)))
        db.commit()
        count = getattr(result, "rowcount", None)
        return int(count) if isinstance(count, int) else 0

    @staticmethod
    def _apply_filters(
        statement: Select[_SelectType],
        query: AuditLogQuery,
    ) -> Select[_SelectType]:
        stmt = statement
        if query.action:
            stmt = stmt.where(AuditLog.action == query.action)
        if query.entity_type:
            stmt = stmt.where(AuditLog.entity_type == query.entity_type)
        if query.entity_id:
            stmt = stmt.where(AuditLog.entity_id == query.entity_id)
        if query.actor_id:
            stmt = stmt.where(AuditLog.user == query.actor_id)
        if query.request_id:
            stmt = stmt.where(AuditLog.request_id == query.request_id)
        if query.ip_address:
            stmt = stmt.where(AuditLog.ip_address == query.ip_address)
        if query.success is not None:
            stmt = stmt.where(AuditLog.success == query.success)
        if query.created_after is not None:
            stmt = stmt.where(AuditLog.created_at >= query.created_after)
        if query.created_before is not None:
            stmt = stmt.where(AuditLog.created_at <= query.created_before)
        return stmt


__all__ = ["AuditLogQuery", "AuditRepository", "SqlAlchemyAuditRepository"]
