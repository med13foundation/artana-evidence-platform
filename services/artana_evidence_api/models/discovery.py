"""Service-local SQLAlchemy models for PubMed discovery state."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_api.db_schema import (
    qualify_shared_platform_foreign_key_target,
    shared_platform_table_options,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class DataDiscoverySessionModel(Base):
    """Shared-platform data-discovery session rows used by PubMed workflows."""

    __tablename__ = "data_discovery_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    research_space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(qualify_shared_platform_foreign_key_target("research_spaces.id")),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    gene_symbol: Mapped[str | None] = mapped_column(String(100), nullable=True)
    search_term: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_sources: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    tested_sources: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    pubmed_search_config: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    total_tests_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "idx_data_discovery_sessions_owner_activity",
            "owner_id",
            "last_activity_at",
        ),
        shared_platform_table_options(
            comment="PubMed discovery sessions for harness flows.",
        ),
    )


class DiscoverySearchJobModel(Base):
    """Persisted PubMed discovery search job rows."""

    __tablename__ = "discovery_search_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            qualify_shared_platform_foreign_key_target("data_discovery_sessions.id"),
        ),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query_preview: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)
    total_results: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_discovery_search_jobs_owner_created_at", "owner_id", "created_at"),
        shared_platform_table_options(
            comment="PubMed discovery jobs for harness flows.",
        ),
    )


__all__ = ["DataDiscoverySessionModel", "DiscoverySearchJobModel"]
