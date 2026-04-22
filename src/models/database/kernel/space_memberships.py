"""Graph-owned space membership model."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from src.models.database.base import Base

_E = TypeVar("_E", bound=Enum)


def _enum_values(enum_cls: type[_E]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class GraphSpaceMembershipRoleEnum(str, Enum):
    """Lifecycle role for one graph-space member."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class GraphSpaceMembershipModel(Base):
    """Graph-owned user membership inside one graph space."""

    __tablename__ = "graph_space_memberships"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("graph_spaces.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        doc="External actor identifier without platform user FK coupling",
    )
    role: Mapped[GraphSpaceMembershipRoleEnum] = mapped_column(
        SQLEnum(
            GraphSpaceMembershipRoleEnum,
            values_callable=_enum_values,
            name="graphspacemembershiproleenum",
        ),
        nullable=False,
        default=GraphSpaceMembershipRoleEnum.RESEARCHER,
    )
    invited_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    invited_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint(
            "space_id",
            "user_id",
            name="uq_graph_space_memberships_space_user",
        ),
        Index("idx_graph_space_memberships_space", "space_id"),
        Index("idx_graph_space_memberships_user", "user_id"),
        Index("idx_graph_space_memberships_role", "role"),
        graph_table_options(
            comment="Graph-owned tenant memberships for graph-service authz",
        ),
    )


__all__ = ["GraphSpaceMembershipModel", "GraphSpaceMembershipRoleEnum"]
