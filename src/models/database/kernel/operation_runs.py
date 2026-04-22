"""Graph-service operation history models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database.graph_schema import graph_table_options
from src.models.database.base import Base
from src.type_definitions.common import JSONObject  # noqa: TC001

_E = TypeVar("_E", bound=Enum)


class GraphOperationRunTypeEnum(str, Enum):
    """Supported standalone graph-service operation types."""

    PROJECTION_READINESS_AUDIT = "projection_readiness_audit"
    PROJECTION_REPAIR = "projection_repair"
    REASONING_PATH_REBUILD = "reasoning_path_rebuild"
    CLAIM_PARTICIPANT_BACKFILL = "claim_participant_backfill"


class GraphOperationRunStatusEnum(str, Enum):
    """Lifecycle status for one recorded operation run."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _enum_values(enum_cls: type[_E]) -> list[str]:
    return [str(member.value) for member in enum_cls]


class GraphOperationRunModel(Base):
    """Recorded execution of one graph maintenance or audit operation."""

    __tablename__ = "graph_operation_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    operation_type: Mapped[GraphOperationRunTypeEnum] = mapped_column(
        SQLEnum(
            GraphOperationRunTypeEnum,
            values_callable=_enum_values,
            name="graphoperationruntypeenum",
        ),
        nullable=False,
    )
    status: Mapped[GraphOperationRunStatusEnum] = mapped_column(
        SQLEnum(
            GraphOperationRunStatusEnum,
            values_callable=_enum_values,
            name="graphoperationrunstatusenum",
        ),
        nullable=False,
    )
    research_space_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    actor_email: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )
    dry_run: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    request_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    summary_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    failure_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    completed_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_graph_operation_runs_started_at", "started_at"),
        Index("idx_graph_operation_runs_type", "operation_type"),
        Index("idx_graph_operation_runs_status", "status"),
        Index("idx_graph_operation_runs_space", "research_space_id"),
        graph_table_options(
            comment="Standalone graph-service operation history and audit trail",
        ),
    )


__all__ = [
    "GraphOperationRunModel",
    "GraphOperationRunStatusEnum",
    "GraphOperationRunTypeEnum",
]
