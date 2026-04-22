from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import uuid4

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base

_E = TypeVar("_E", bound=Enum)


def _enum_values(enum_cls: type[_E]) -> list[str]:
    """Persist Python Enums using their .value strings (not their names)."""
    return [str(member.value) for member in enum_cls]


class SpaceStatusEnum(str, Enum):
    """SQLAlchemy enum for research space status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class MembershipRoleEnum(str, Enum):
    """SQLAlchemy enum for membership roles."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class ResearchSpaceModel(Base):
    """
    SQLAlchemy model for research spaces.

    Maps to the 'research_spaces' table and provides persistence for
    ResearchSpace domain entities.
    """

    __tablename__ = "research_spaces"

    # Identity
    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique research space identifier",
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="URL-safe unique identifier",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Display name",
    )

    # Metadata
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Space description",
    )
    owner_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        doc="User ID of the space owner",
    )
    status: Mapped[SpaceStatusEnum] = mapped_column(
        SQLEnum(
            SpaceStatusEnum,
            values_callable=_enum_values,
            name="spacestatusenum",
        ),
        nullable=False,
        default=SpaceStatusEnum.ACTIVE,
        doc="Space lifecycle status",
    )

    # Configuration
    settings: Mapped[JSONObject] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
        doc="Space-specific settings",
    )

    # Metadata
    tags: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        doc="Searchable tags",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Space creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        doc="Last space update timestamp",
    )

    # Relationships
    owner = relationship(
        "UserModel",
        back_populates="owned_research_spaces",
        foreign_keys=[owner_id],
    )
    memberships = relationship(
        "ResearchSpaceMembershipModel",
        back_populates="space",
        cascade="all, delete-orphan",
    )
    data_sources = relationship(
        "UserDataSourceModel",
        back_populates="research_space",
    )

    __table_args__ = (
        Index("idx_research_spaces_owner", "owner_id"),
        Index("idx_research_spaces_status", "status"),
        Index("idx_research_spaces_created_at", "created_at"),
        {
            "comment": "Research spaces for multi-tenancy support",
        },
    )

    def __repr__(self) -> str:
        return f"<ResearchSpaceModel(id={self.id}, slug={self.slug}, name={self.name})>"


class ResearchSpaceMembershipModel(Base):
    """
    SQLAlchemy model for research space memberships.

    Maps to the 'research_space_memberships' table and provides persistence for
    ResearchSpaceMembership domain entities.
    """

    __tablename__ = "research_space_memberships"

    # Identity
    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Unique membership identifier",
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_spaces.id"),
        nullable=False,
        doc="Research space ID",
    )
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        doc="User ID",
    )

    # Role & Permissions
    role: Mapped[MembershipRoleEnum] = mapped_column(
        SQLEnum(
            MembershipRoleEnum,
            values_callable=_enum_values,
            name="membershiproleenum",
        ),
        nullable=False,
        doc="User's role in the space",
    )

    # Invitation Workflow
    invited_by: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        doc="User ID who sent the invitation",
    )
    invited_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When the invitation was sent",
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When the user joined",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        doc="Whether the membership is active",
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        nullable=False,
        doc="Membership creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
        doc="Last membership update timestamp",
    )

    # Relationships
    space = relationship("ResearchSpaceModel", back_populates="memberships")
    user = relationship(
        "UserModel",
        foreign_keys=[user_id],
        back_populates="research_space_memberships",
    )
    inviter = relationship(
        "UserModel",
        foreign_keys=[invited_by],
        back_populates="sent_research_space_invitations",
    )

    __table_args__ = (
        Index("idx_memberships_space", "space_id"),
        Index("idx_memberships_user", "user_id"),
        Index("idx_memberships_space_user", "space_id", "user_id", unique=True),
        Index("idx_memberships_invited_by", "invited_by"),
        Index("idx_memberships_pending", "user_id", "invited_at", "joined_at"),
        {
            "comment": "Research space memberships for role-based access control",
        },
    )

    def __repr__(self) -> str:
        return (
            f"<ResearchSpaceMembershipModel(id={self.id}, space_id={self.space_id}, "
            f"user_id={self.user_id}, role={self.role})>"
        )
