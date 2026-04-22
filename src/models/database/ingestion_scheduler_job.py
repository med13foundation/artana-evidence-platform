from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user_data_source import UserDataSourceModel


class IngestionSchedulerJobModel(Base):
    """Durable scheduler metadata for recurring source ingestion jobs."""

    __tablename__ = "ingestion_scheduler_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="UTC",
    )
    start_time: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    next_run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    source: Mapped[UserDataSourceModel] = relationship("UserDataSourceModel")

    def __repr__(self) -> str:
        """String representation of the scheduler job model."""
        return (
            "<IngestionSchedulerJob("
            f"job_id={self.job_id}, source_id={self.source_id}, "
            f"next_run_at={self.next_run_at.isoformat()}"
            ")>"
        )
