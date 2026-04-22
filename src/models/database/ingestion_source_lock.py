from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user_data_source import UserDataSourceModel


class IngestionSourceLockModel(Base):
    """Lease-style lock record for source-level ingestion coordination."""

    __tablename__ = "ingestion_source_locks"

    source_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("user_data_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    lock_token: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    acquired_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source: Mapped[UserDataSourceModel] = relationship("UserDataSourceModel")

    def __repr__(self) -> str:
        """String representation of the source lock model."""
        return (
            "<IngestionSourceLock("
            f"source_id={self.source_id}, lease_expires_at={self.lease_expires_at.isoformat()}"
            ")>"
        )
