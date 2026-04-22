from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.database.base import Base


class ReviewRecord(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    issues: Mapped[int] = mapped_column(Integer, default=0)
    research_space_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id"),
        nullable=True,
        index=True,
        doc="Research space this review belongs to",
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
    )


__all__ = ["ReviewRecord"]
