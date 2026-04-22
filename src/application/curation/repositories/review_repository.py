from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy.exc import OperationalError, ProgrammingError

from src.models.database.review import ReviewRecord

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.curation import ReviewRecordLike


@dataclass(frozen=True)
class ReviewFilter:
    entity_type: str | None = None
    status: str | None = None
    priority: str | None = None
    research_space_id: str | None = None


class ReviewRepository(Protocol):
    def list_records(
        self,
        db: Session,
        flt: ReviewFilter,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecordLike]: ...

    def bulk_update_status(
        self,
        db: Session,
        ids: tuple[int, ...] | list[int],
        status: str,
    ) -> int: ...

    def add(self, db: Session, record: object) -> ReviewRecordLike: ...

    def find_by_entity(
        self,
        db: Session,
        entity_type: str,
        entity_id: str,
        research_space_id: str | None = None,
    ) -> ReviewRecordLike | None: ...

    def get_stats(
        self,
        db: Session,
        research_space_id: str | None = None,
    ) -> dict[str, int]: ...


class SqlAlchemyReviewRepository:
    @staticmethod
    def _is_missing_reviews_table_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            'relation "reviews" does not exist' in message
            or "no such table: reviews" in message
        )

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        return {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
        }

    def list_records(
        self,
        db: Session,
        flt: ReviewFilter,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewRecordLike]:
        logger = logging.getLogger(__name__)
        query = db.query(ReviewRecord)
        if flt.entity_type:
            query = query.filter(ReviewRecord.entity_type == flt.entity_type)
        if flt.status:
            query = query.filter(ReviewRecord.status == flt.status)
        if flt.priority:
            query = query.filter(ReviewRecord.priority == flt.priority)
        if flt.research_space_id:
            query = query.filter(
                ReviewRecord.research_space_id == flt.research_space_id,
            )
        try:
            orm_records = list(query.offset(offset).limit(limit).all())
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_reviews_table_error(exc):
                raise
            logger.warning(
                (
                    "Reviews table unavailable while listing curation queue; "
                    "returning empty list"
                ),
                exc_info=exc,
            )
            db.rollback()
            return []
        return [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "status": r.status,
                "priority": r.priority,
                "quality_score": r.quality_score,
                "issues": r.issues,
                "research_space_id": r.research_space_id,
                "last_updated": r.last_updated,
            }
            for r in orm_records
        ]

    def bulk_update_status(
        self,
        db: Session,
        ids: tuple[int, ...] | list[int],
        status: str,
    ) -> int:
        updated = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.id.in_(list(ids)))
            .update({ReviewRecord.status: status}, synchronize_session=False)
        )
        db.commit()
        return int(updated)

    def add(self, db: Session, record: object) -> ReviewRecordLike:
        db.add(record)
        db.commit()
        db.refresh(record)
        # Build a dict view of the saved record
        return {
            "id": record.id,  # type: ignore[attr-defined]
            "entity_type": record.entity_type,  # type: ignore[attr-defined]
            "entity_id": record.entity_id,  # type: ignore[attr-defined]
            "status": record.status,  # type: ignore[attr-defined]
            "priority": record.priority,  # type: ignore[attr-defined]
            "quality_score": getattr(record, "quality_score", None),
            "issues": getattr(record, "issues", 0),
            "research_space_id": getattr(record, "research_space_id", None),
            "last_updated": getattr(record, "last_updated", None),
        }

    def find_by_entity(
        self,
        db: Session,
        entity_type: str,
        entity_id: str,
        research_space_id: str | None = None,
    ) -> ReviewRecordLike | None:
        query = db.query(ReviewRecord).filter(
            ReviewRecord.entity_type == entity_type,
            ReviewRecord.entity_id == entity_id,
        )
        if research_space_id is not None:
            query = query.filter(ReviewRecord.research_space_id == research_space_id)
        orm = query.order_by(ReviewRecord.last_updated.desc()).first()
        if orm is None:
            return None
        return {
            "id": orm.id,
            "entity_type": orm.entity_type,
            "entity_id": orm.entity_id,
            "status": orm.status,
            "priority": orm.priority,
            "quality_score": orm.quality_score,
            "issues": orm.issues,
            "research_space_id": orm.research_space_id,
            "last_updated": orm.last_updated,
        }

    def get_stats(
        self,
        db: Session,
        research_space_id: str | None = None,
    ) -> dict[str, int]:
        """Get curation statistics for a research space."""
        logger = logging.getLogger(__name__)
        query = db.query(ReviewRecord)
        if research_space_id:
            query = query.filter(ReviewRecord.research_space_id == research_space_id)

        try:
            total = query.count()
            pending = query.filter(ReviewRecord.status == "pending").count()
            approved = query.filter(ReviewRecord.status == "approved").count()
            rejected = query.filter(ReviewRecord.status == "rejected").count()
        except (OperationalError, ProgrammingError) as exc:
            if not self._is_missing_reviews_table_error(exc):
                raise
            logger.warning(
                (
                    "Reviews table unavailable while calculating curation stats; "
                    "returning zeros"
                ),
                exc_info=exc,
            )
            db.rollback()
            return self._empty_stats()

        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
        }


__all__ = [
    "ReviewFilter",
    "ReviewRepository",
    "SqlAlchemyReviewRepository",
]
