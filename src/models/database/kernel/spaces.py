"""Graph-owned tenant space registry model."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import graph_table_options
from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001

_E = TypeVar("_E", bound=Enum)


class GraphSpaceStatusEnum(str, Enum):
    """Lifecycle status for graph-owned tenant spaces."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


def _enum_values(enum_cls: type[_E]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class GraphSpaceModel(Base):
    """Graph-owned registry entry for one tenant space."""

    __tablename__ = "graph_spaces"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        doc="Graph-owned tenant space identifier",
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        doc="Stable service-local slug",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Display name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional space description",
    )
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        doc="Owning actor id without cross-service foreign key",
    )
    status: Mapped[GraphSpaceStatusEnum] = mapped_column(
        SQLEnum(
            GraphSpaceStatusEnum,
            values_callable=_enum_values,
            name="graphspacestatusenum",
        ),
        nullable=False,
        default=GraphSpaceStatusEnum.ACTIVE,
        doc="Space lifecycle status",
    )
    settings: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        doc="Graph-owned tenant settings payload",
    )
    sync_source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Origin of the latest tenant snapshot applied to graph",
    )
    sync_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Deterministic fingerprint of the latest synced tenant snapshot",
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="Upstream platform updated_at captured for the synced snapshot",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        doc="When the graph control plane last applied the tenant snapshot",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_graph_spaces_owner", "owner_id"),
        Index("idx_graph_spaces_status", "status"),
        Index("idx_graph_spaces_sync_fingerprint", "sync_fingerprint"),
        graph_table_options(
            comment="Graph-owned tenant registry for the standalone graph service",
        ),
    )


__all__ = ["GraphSpaceModel", "GraphSpaceStatusEnum"]
