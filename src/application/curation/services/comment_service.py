from __future__ import annotations

from typing import TYPE_CHECKING

from src.models.database.audit import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.curation.repositories.audit_repository import AuditRepository


class CommentService:
    def __init__(self, audit_repository: AuditRepository) -> None:
        self._audit_repository = audit_repository

    def add_comment(
        self,
        db: Session,
        entity_type: str,
        entity_id: str,
        comment: str,
        user: str | None = None,
    ) -> int:
        log = AuditLog(
            action="comment",
            entity_type=entity_type,
            entity_id=entity_id,
            user=user,
            details=comment,
        )
        saved = self._audit_repository.record(db, log)
        return int(saved.id)


__all__ = ["CommentService"]
