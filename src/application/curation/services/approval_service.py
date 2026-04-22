from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.curation.repositories.review_repository import ReviewRepository


class ApprovalService:
    def __init__(self, repository: ReviewRepository) -> None:
        self._repository = repository

    def approve(self, db: Session, ids: tuple[int, ...] | list[int]) -> int:
        return self._repository.bulk_update_status(db, ids, "approved")

    def reject(self, db: Session, ids: tuple[int, ...] | list[int]) -> int:
        return self._repository.bulk_update_status(db, ids, "rejected")

    def quarantine(self, db: Session, ids: tuple[int, ...] | list[int]) -> int:
        return self._repository.bulk_update_status(db, ids, "quarantined")


__all__ = ["ApprovalService"]
