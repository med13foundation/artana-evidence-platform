"""
SQLAlchemy model for persisted system status flags.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SystemStatusModel(Base):
    """Represents a system status entry."""

    __tablename__ = "system_status"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = ["SystemStatusModel"]
