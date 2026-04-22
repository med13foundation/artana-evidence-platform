"""Pack-version seed status persistence for graph spaces."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import uuid4

from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import graph_table_options
from sqlalchemy import Column, Index, Integer, String, Table, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

_E = TypeVar("_E", bound=Enum)


def _enum_values(enum_cls: type[_E]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class GraphPackSeedStatusEnum(str, Enum):
    """Lifecycle status for one successful pack seed."""

    SEEDED = "seeded"


class GraphPackSeedOperationEnum(str, Enum):
    """Operation that last touched one pack seed status."""

    SEED = "seed"
    REPAIR = "repair"


_graph_pack_seed_status_table = Base.metadata.tables.get("graph_pack_seed_status")
if _graph_pack_seed_status_table is None:
    _graph_pack_seed_status_table = Table(
        "graph_pack_seed_status",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True, default=uuid4),
        Column("research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column("pack_name", String(64), nullable=False),
        Column("pack_version", String(64), nullable=False),
        Column(
            "status",
            SQLEnum(
                GraphPackSeedStatusEnum,
                values_callable=_enum_values,
                name="graphpackseedstatusenum",
            ),
            nullable=False,
            default=GraphPackSeedStatusEnum.SEEDED,
        ),
        Column(
            "last_operation",
            SQLEnum(
                GraphPackSeedOperationEnum,
                values_callable=_enum_values,
                name="graphpackseedoperationenum",
            ),
            nullable=False,
            default=GraphPackSeedOperationEnum.SEED,
        ),
        Column("seed_count", Integer, nullable=False, default=1),
        Column("repair_count", Integer, nullable=False, default=0),
        Column("metadata_payload", JSONB, nullable=False, default=dict),
        Column(
            "seeded_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column("repaired_at", TIMESTAMP(timezone=True), nullable=True),
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
            "research_space_id",
            "pack_name",
            "pack_version",
            name="uq_graph_pack_seed_status_space_pack_version",
        ),
        Index("idx_graph_pack_seed_status_space", "research_space_id"),
        Index("idx_graph_pack_seed_status_pack", "pack_name", "pack_version"),
        **graph_table_options(
            comment="Per-space domain-pack seed status and version ledger",
        ),
    )


class GraphPackSeedStatusModel(Base):
    """Recorded successful seeding of one domain pack into one graph space."""

    __table__ = _graph_pack_seed_status_table


__all__ = [
    "GraphPackSeedOperationEnum",
    "GraphPackSeedStatusEnum",
    "GraphPackSeedStatusModel",
]
