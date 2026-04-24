"""Service-local graph operation history models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID, uuid4

from artana_evidence_db.orm_base import Base, require_table
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_table_name,
)
from sqlalchemy import Boolean, Column, Index, String, Table, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Mapped
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


_graph_operation_runs_table = Base.metadata.tables.get(
    qualify_graph_table_name("graph_operation_runs"),
)
if _graph_operation_runs_table is None:
    _graph_operation_runs_table = Table(
        "graph_operation_runs",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
        ),
        Column(
            "operation_type",
            SQLEnum(
                GraphOperationRunTypeEnum,
                values_callable=_enum_values,
                name="graphoperationruntypeenum",
            ),
            nullable=False,
        ),
        Column(
            "status",
            SQLEnum(
                GraphOperationRunStatusEnum,
                values_callable=_enum_values,
                name="graphoperationrunstatusenum",
            ),
            nullable=False,
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        Column(
            "actor_user_id",
            PGUUID(as_uuid=True),
            nullable=True,
        ),
        Column(
            "actor_email",
            String(320),
            nullable=True,
        ),
        Column(
            "dry_run",
            Boolean,
            nullable=False,
            default=False,
        ),
        Column(
            "request_payload",
            JSONB,
            nullable=False,
            default=dict,
        ),
        Column(
            "summary_payload",
            JSONB,
            nullable=False,
            default=dict,
        ),
        Column(
            "failure_detail",
            Text,
            nullable=True,
        ),
        Column(
            "started_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column(
            "completed_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Index("idx_graph_operation_runs_started_at", "started_at"),
        Index("idx_graph_operation_runs_type", "operation_type"),
        Index("idx_graph_operation_runs_status", "status"),
        Index("idx_graph_operation_runs_space", "research_space_id"),
        **graph_table_options(
            comment="Standalone graph-service operation history and audit trail",
        ),
    )


_graph_operation_runs_table_model_table = require_table(_graph_operation_runs_table)

class GraphOperationRunModel(Base):
    """Recorded execution of one graph maintenance or audit operation."""


    __table__ = _graph_operation_runs_table_model_table

    if TYPE_CHECKING:
        id: Mapped[UUID]
        operation_type: Mapped[GraphOperationRunTypeEnum]
        status: Mapped[GraphOperationRunStatusEnum]
        research_space_id: Mapped[UUID | None]
        actor_user_id: Mapped[UUID | None]
        actor_email: Mapped[str | None]
        dry_run: Mapped[bool]
        request_payload: Mapped[JSONObject]
        summary_payload: Mapped[JSONObject]
        failure_detail: Mapped[str | None]
        started_at: Mapped[datetime]
        completed_at: Mapped[datetime]


__all__ = [
    "GraphOperationRunModel",
    "GraphOperationRunStatusEnum",
    "GraphOperationRunTypeEnum",
]
