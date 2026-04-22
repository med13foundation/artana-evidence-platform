"""Service-local mapping for the shared platform ``users`` table."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_api.db_schema import shared_platform_table_options
from sqlalchemy import TIMESTAMP, Boolean, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class HarnessUserModel(Base):
    """Minimal shared-user mapping used by the evidence API service."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="viewer",
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_verification",
        index=True,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    email_verification_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    password_reset_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    password_reset_expires: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    last_login: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
    )
    login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_users_email_active", "email", "status"),
        Index("idx_users_role_status", "role", "status"),
        Index("idx_users_created_at", "created_at"),
        shared_platform_table_options(
            comment="Shared user accounts mirrored for the evidence API service",
        ),
    )


__all__ = ["HarnessUserModel"]
