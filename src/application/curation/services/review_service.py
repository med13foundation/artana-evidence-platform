from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.curation.repositories.review_repository import (
    ReviewFilter,
    ReviewRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject
    from src.type_definitions.curation import ReviewRecordLike


@dataclass(frozen=True)
class ReviewQuery:
    entity_type: str | None = None
    status: str | None = None
    priority: str | None = None
    research_space_id: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class ReviewQueueItem:
    id: int
    entity_type: str
    entity_id: str
    status: str
    priority: str
    quality_score: float | None
    issues: int
    last_updated: datetime | None

    @classmethod
    def from_record(cls, record: ReviewRecordLike) -> ReviewQueueItem:
        raw_id = record.get("id")
        if raw_id is None:
            msg = "Review record missing required id"
            raise ValueError(msg)
        entity_type = str(record.get("entity_type", "")).strip()
        entity_id = str(record.get("entity_id", "")).strip()
        status = str(record.get("status", "")).strip()
        priority = str(record.get("priority", "")).strip()

        quality_score_raw = record.get("quality_score")
        quality_score = (
            float(quality_score_raw)
            if isinstance(quality_score_raw, float | int)
            else None
        )

        issues_raw = record.get("issues", 0)
        issues = int(issues_raw) if isinstance(issues_raw, int | float) else 0

        last_updated_raw = record.get("last_updated")
        last_updated: datetime | None
        if isinstance(last_updated_raw, datetime):
            last_updated = last_updated_raw
        elif isinstance(last_updated_raw, str):
            try:
                last_updated = datetime.fromisoformat(last_updated_raw)
            except ValueError:
                last_updated = None
        else:
            last_updated = None

        return cls(
            id=int(raw_id),
            entity_type=entity_type,
            entity_id=entity_id,
            status=status or "pending",
            priority=priority or "medium",
            quality_score=quality_score,
            issues=issues,
            last_updated=last_updated,
        )

    def to_serializable(self) -> JSONObject:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "status": self.status,
            "priority": self.priority,
            "quality_score": self.quality_score,
            "issues": self.issues,
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
        }


class ReviewService:
    def __init__(self, repository: ReviewRepository) -> None:
        self._repository = repository

    def list_queue(self, db: Session, query: ReviewQuery) -> list[ReviewQueueItem]:
        records = self._repository.list_records(
            db,
            ReviewFilter(
                entity_type=query.entity_type,
                status=query.status,
                priority=query.priority,
                research_space_id=query.research_space_id,
            ),
            limit=query.limit,
            offset=query.offset,
        )

        return [ReviewQueueItem.from_record(r) for r in records]

    def submit(
        self,
        db: Session,
        entity_type: str,
        entity_id: str,
        priority: str = "medium",
        research_space_id: str | None = None,
    ) -> ReviewQueueItem:
        # Local import to avoid application-layer hard dependency
        from src.models.database.review import ReviewRecord  # noqa: PLC0415

        record = ReviewRecord(
            entity_type=entity_type,
            entity_id=entity_id,
            status="pending",
            priority=priority,
            research_space_id=research_space_id,
        )
        saved = self._repository.add(db, record)
        return ReviewQueueItem.from_record(saved)

    def bulk_update_status(
        self,
        db: Session,
        ids: tuple[int, ...] | list[int],
        status: str,
    ) -> int:
        return self._repository.bulk_update_status(db, ids, status)

    def get_stats(
        self,
        db: Session,
        research_space_id: str | None = None,
    ) -> dict[str, int]:
        """Get curation statistics for a research space."""
        return self._repository.get_stats(db, research_space_id)


__all__ = ["ReviewQuery", "ReviewQueueItem", "ReviewService"]
