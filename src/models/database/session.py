"""
Session database model for Artana Resource Library.

SQLAlchemy model for user sessions with security tracking.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.entities.session import SessionStatus

from .base import Base


class SessionModel(Base):
    """
    SQLAlchemy model for user sessions.

    Tracks JWT tokens, session metadata, and security monitoring.
    """

    __tablename__ = "sessions"

    # Primary key
    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique session identifier",
    )

    # Foreign key to user
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who owns this session",
    )

    # JWT tokens
    session_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="JWT access token",
    )
    refresh_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="JWT refresh token",
    )

    # Session metadata
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 addresses can be up to 45 chars
        nullable=True,
        doc="Client IP address",
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Client user agent string",
    )
    device_fingerprint: Mapped[str | None] = mapped_column(
        String(32),  # SHA256 hex is 64 chars, we'll use truncated
        nullable=True,
        doc="Device fingerprint hash",
    )

    # Session lifecycle
    status: Mapped[SessionStatus] = mapped_column(
        SQLEnum(SessionStatus),
        nullable=False,
        default=SessionStatus.ACTIVE,
        index=True,
        doc="Current session status",
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
        doc="Access token expiration time",
    )
    refresh_expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        doc="Refresh token expiration time",
    )

    # Activity tracking
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="NOW()",
        doc="Session creation timestamp",
    )
    last_activity: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="NOW()",
        doc="Last session activity timestamp",
    )

    # Relationship to user (optional, for convenience)

    __table_args__ = (
        # Composite indexes for performance
        Index("idx_sessions_user_status", "user_id", "status"),
        Index("idx_sessions_session_token", "session_token"),
        Index("idx_sessions_refresh_token", "refresh_token"),
        Index("idx_sessions_expires_at", "expires_at"),
        Index("idx_sessions_refresh_expires", "refresh_expires_at"),
        Index("idx_sessions_last_activity", "last_activity"),
        Index("idx_sessions_ip_address", "ip_address"),
        # Partial indexes for active sessions
        Index(
            "idx_sessions_active_only",
            "id",
            postgresql_where=(status == SessionStatus.ACTIVE),
        ),
        # Index for cleanup operations
        Index(
            "idx_sessions_expired_cleanup",
            "created_at",
            postgresql_where=(
                status.in_([SessionStatus.EXPIRED, SessionStatus.REVOKED])
            ),
        ),
        {
            "schema": None,  # Use default schema
            "comment": "User sessions with JWT token tracking and security metadata",
        },
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<SessionModel(id={self.id}, user_id={self.user_id}, "
            f"status={self.status.value}, expires_at={self.expires_at})>"
        )
