"""
User database model for Artana Resource Library.

SQLAlchemy model for user accounts with security fields and constraints.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import TIMESTAMP, Boolean, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.entities.user import UserRole, UserStatus

from .base import Base


class UserModel(Base):
    """
    SQLAlchemy model for users.

    Maps to the users table with all authentication and profile fields.
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique user identifier",
    )

    # Authentication fields
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        doc="User's email address",
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique username for login",
    )
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="User's full display name",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Bcrypt hashed password",
    )

    # Authorization
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        nullable=False,
        default=UserRole.VIEWER,
        index=True,
        doc="User's role for authorization",
    )
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus),
        nullable=False,
        default=UserStatus.PENDING_VERIFICATION,
        index=True,
        doc="Account status",
    )

    # Email verification
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether email has been verified",
    )
    email_verification_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Token for email verification",
    )

    # Password reset
    password_reset_token: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Token for password reset",
    )
    password_reset_expires: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="Expiration time for password reset token",
    )

    # Security tracking
    last_login: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        index=True,
        doc="Last successful login timestamp",
    )
    login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of consecutive failed login attempts",
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="Account lockout expiration time",
    )

    # Override base audit fields for explicit control
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        doc="Account creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        doc="Last account update timestamp",
    )

    # Relationships
    owned_research_spaces = relationship(
        "ResearchSpaceModel",
        back_populates="owner",
        foreign_keys="ResearchSpaceModel.owner_id",
        cascade="all, delete-orphan",
    )
    research_space_memberships = relationship(
        "ResearchSpaceMembershipModel",
        back_populates="user",
        foreign_keys="ResearchSpaceMembershipModel.user_id",
        cascade="all, delete-orphan",
    )
    sent_research_space_invitations = relationship(
        "ResearchSpaceMembershipModel",
        back_populates="inviter",
        foreign_keys="ResearchSpaceMembershipModel.invited_by",
    )

    __table_args__ = (
        # Composite indexes for common queries
        Index("idx_users_email_active", "email", "status"),
        Index("idx_users_role_status", "role", "status"),
        Index("idx_users_created_at", "created_at"),
        {
            "comment": "User accounts with authentication and authorization data",
        },
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<UserModel(id={self.id}, email={self.email}, "
            f"username={self.username}, role={self.role.value}, "
            f"status={self.status.value})>"
        )
