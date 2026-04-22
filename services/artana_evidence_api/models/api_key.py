"""Service-local API key model for the standalone harness service."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class HarnessApiKeyModel(Base):
    """Persist hashed Artana API keys bound to one user."""

    __tablename__ = "harness_api_keys"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        index=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_harness_api_keys_user_status", "user_id", "status"),
        Index("idx_harness_api_keys_created_at", "created_at"),
        {
            "comment": "Service-local hashed API keys for standalone harness access",
        },
    )


__all__ = ["HarnessApiKeyModel"]
