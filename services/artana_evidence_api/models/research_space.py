"""Research-space and membership models for graph-harness.

Self-contained copy of the platform research_spaces / research_space_memberships
SQLAlchemy models so that ``artana_evidence_api`` has no runtime dependency on
the shared backend package. The two models map to the same physical tables as
the platform originals.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TypeVar
from uuid import uuid4

from artana_evidence_api.db_schema import (
    qualify_shared_platform_foreign_key_target,
    shared_platform_table_options,
)
from artana_evidence_api.types.common import JSONObject
from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

_E = TypeVar("_E", bound=Enum)


def _enum_values(enum_cls: type[_E]) -> list[str]:
    """Persist Python Enums using their .value strings (not their names)."""
    return [str(member.value) for member in enum_cls]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SpaceStatusEnum(str, Enum):
    """Research space lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


class MembershipRoleEnum(str, Enum):
    """Research space membership role."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ResearchSpaceModel(Base):
    """Maps to the shared ``research_spaces`` table."""

    __tablename__ = "research_spaces"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_shared_platform_foreign_key_target("users.id")),
        nullable=False,
    )
    status: Mapped[SpaceStatusEnum] = mapped_column(
        SQLEnum(
            SpaceStatusEnum,
            values_callable=_enum_values,
            name="spacestatusenum",
        ),
        nullable=False,
        default=SpaceStatusEnum.ACTIVE,
    )
    settings: Mapped[JSONObject] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    tags: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_research_spaces_owner", "owner_id"),
        Index("idx_research_spaces_status", "status"),
        Index("idx_research_spaces_created_at", "created_at"),
        shared_platform_table_options(
            comment="Research spaces for multi-tenancy support",
        ),
    )

    def __repr__(self) -> str:
        return f"<ResearchSpaceModel(id={self.id}, slug={self.slug}, name={self.name})>"


class ResearchSpaceMembershipModel(Base):
    """Maps to the shared ``research_space_memberships`` table."""

    __tablename__ = "research_space_memberships"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_shared_platform_foreign_key_target("research_spaces.id"),
        ),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_shared_platform_foreign_key_target("users.id")),
        nullable=False,
    )
    role: Mapped[MembershipRoleEnum] = mapped_column(
        SQLEnum(
            MembershipRoleEnum,
            values_callable=_enum_values,
            name="membershiproleenum",
        ),
        nullable=False,
    )
    invited_by: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_shared_platform_foreign_key_target("users.id")),
        nullable=True,
    )
    invited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    joined_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (
        Index("idx_memberships_space", "space_id"),
        Index("idx_memberships_user", "user_id"),
        Index("idx_memberships_space_user", "space_id", "user_id", unique=True),
        Index("idx_memberships_invited_by", "invited_by"),
        Index("idx_memberships_pending", "user_id", "invited_at", "joined_at"),
        shared_platform_table_options(
            comment="Research space memberships for role-based access control",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ResearchSpaceMembershipModel(id={self.id}, space_id={self.space_id}, "
            f"user_id={self.user_id}, role={self.role})>"
        )
