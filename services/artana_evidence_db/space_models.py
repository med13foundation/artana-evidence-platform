"""Service-local ORM models for graph-space registry and memberships."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import uuid4

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
    qualify_graph_table_name,
)
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

_E = TypeVar("_E", bound=Enum)


def _enum_values(enum_cls: type[_E]) -> list[str]:
    return [str(member.value) for member in enum_cls]


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


class GraphSpaceStatusEnum(str, Enum):
    """Lifecycle status for one graph-owned space."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


_graph_spaces_table = _existing_table("graph_spaces")
if _graph_spaces_table is None:
    _graph_spaces_table = Table(
        "graph_spaces",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
            doc="Graph-owned tenant space identifier",
        ),
        Column(
            "slug",
            String(50),
            unique=True,
            nullable=False,
            index=True,
            doc="Stable service-local slug",
        ),
        Column(
            "name",
            String(100),
            nullable=False,
            doc="Display name",
        ),
        Column(
            "description",
            Text,
            nullable=True,
            doc="Optional space description",
        ),
        Column(
            "owner_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="Owning actor id without cross-service foreign key",
        ),
        Column(
            "status",
            SQLEnum(
                GraphSpaceStatusEnum,
                values_callable=_enum_values,
                name="graphspacestatusenum",
            ),
            nullable=False,
            default=GraphSpaceStatusEnum.ACTIVE,
            doc="Space lifecycle status",
        ),
        Column(
            "settings",
            JSONB,
            nullable=False,
            default=dict,
            doc="Graph-owned tenant settings payload",
        ),
        Column(
            "sync_source",
            String(64),
            nullable=True,
            doc="Origin of the latest tenant snapshot applied to graph",
        ),
        Column(
            "sync_fingerprint",
            String(64),
            nullable=True,
            doc="Deterministic fingerprint of the latest synced tenant snapshot",
        ),
        Column(
            "source_updated_at",
            TIMESTAMP(timezone=True),
            nullable=True,
            doc="Upstream platform updated_at captured for the synced snapshot",
        ),
        Column(
            "last_synced_at",
            TIMESTAMP(timezone=True),
            nullable=True,
            doc="When the graph control plane last applied the tenant snapshot",
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
        Index("idx_graph_spaces_owner", "owner_id"),
        Index("idx_graph_spaces_status", "status"),
        Index("idx_graph_spaces_sync_fingerprint", "sync_fingerprint"),
        **graph_table_options(
            comment="Graph-owned tenant registry for the standalone graph service",
        ),
    )


class ServiceGraphSpaceModel(Base):
    """Service-local registry entry for one tenant space."""

    __table__ = _graph_spaces_table


GraphSpaceModel = ServiceGraphSpaceModel


class GraphSpaceMembershipRoleEnum(str, Enum):
    """Lifecycle role for one graph-space member."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


_graph_space_memberships_table = _existing_table("graph_space_memberships")
if _graph_space_memberships_table is None:
    _graph_space_memberships_table = Table(
        "graph_space_memberships",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column(
            "space_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("graph_spaces.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        Column(
            "user_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="External actor identifier without platform user FK coupling",
        ),
        Column(
            "role",
            SQLEnum(
                GraphSpaceMembershipRoleEnum,
                values_callable=_enum_values,
                name="graphspacemembershiproleenum",
            ),
            nullable=False,
            default=GraphSpaceMembershipRoleEnum.RESEARCHER,
        ),
        Column(
            "invited_by",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        Column(
            "invited_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
        Column(
            "joined_at",
            TIMESTAMP(timezone=True),
            nullable=True,
        ),
        Column(
            "is_active",
            Boolean,
            nullable=False,
            default=True,
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
        UniqueConstraint(
            "space_id",
            "user_id",
            name="uq_graph_space_memberships_space_user",
        ),
        Index("idx_graph_space_memberships_space", "space_id"),
        Index("idx_graph_space_memberships_user", "user_id"),
        Index("idx_graph_space_memberships_role", "role"),
        **graph_table_options(
            comment="Graph-owned tenant memberships for graph-service authz",
        ),
    )


class ServiceGraphSpaceMembershipModel(Base):
    """Service-local user membership inside one graph space."""

    __table__ = _graph_space_memberships_table


GraphSpaceMembershipModel = ServiceGraphSpaceMembershipModel

__all__ = [
    "GraphSpaceMembershipModel",
    "GraphSpaceMembershipRoleEnum",
    "GraphSpaceModel",
    "GraphSpaceStatusEnum",
]
