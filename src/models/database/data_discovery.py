from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import Enum  # noqa: TC003
from uuid import UUID  # noqa: TC003

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class DataDiscoverySessionModel(Base):
    """
    SQLAlchemy model for data discovery sessions.

    Stores user data discovery sessions with their state and configuration.
    """

    __tablename__ = "data_discovery_sessions"

    # Primary key
    # Use String to store UUID-like identifiers and handle legacy numeric IDs.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Ownership and context
    # Use String to store UUID-like identifiers and handle legacy numeric IDs.
    owner_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
        doc="User who owns this session",
    )
    research_space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id"),
        nullable=False,
        index=True,
        doc="Research space this session belongs to",
    )

    # Basic information
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="Untitled Session",
    )

    # Current parameters (stored as JSON)
    gene_symbol: Mapped[str | None] = mapped_column(String(100), nullable=True)
    search_term: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Session state
    selected_sources: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="IDs of selected catalog entries",
    )
    tested_sources: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        doc="IDs of tested catalog entries",
    )
    pubmed_search_config: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Advanced PubMed search parameters stored for the session",
    )

    # Statistics
    total_tests_run: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    test_results = relationship(
        "QueryTestResultModel",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class SourceCatalogEntryModel(Base):
    """
    SQLAlchemy model for source catalog entries.

    Stores the catalog of available data sources for the workbench.
    """

    __tablename__ = "source_catalog_entries"

    # Primary key (using string ID for flexibility)
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Basic information
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Classification and search
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="api",
        server_default="api",
    )

    # Query capabilities
    param_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    url_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_format: Mapped[str | None] = mapped_column(String(50), nullable=True)
    api_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Governance
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Usage statistics
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    query_capabilities: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Template integration
    source_template_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("source_templates.id"),
        nullable=True,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class QueryTestResultModel(Base):
    """
    SQLAlchemy model for query test results.

    Stores the results of testing queries against data sources.
    """

    __tablename__ = "query_test_results"

    # Primary key
    # Use String to store UUID-like identifiers.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Relationships
    # Use String to store UUID-like identifiers.
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("data_discovery_sessions.id"),
        nullable=False,
        index=True,
    )
    catalog_entry_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("source_catalog_entries.id"),
        nullable=False,
        index=True,
    )

    # Test execution
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Parameters used (stored as JSON for flexibility)
    gene_symbol: Mapped[str | None] = mapped_column(String(100), nullable=True)
    search_term: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Results
    response_data: Mapped[JSONObject | None] = mapped_column(JSON, nullable=True)
    response_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Metadata
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    session = relationship("DataDiscoverySessionModel", back_populates="test_results")


class PresetScopeEnum(str, Enum):
    """Database enum for preset scopes."""

    USER = "user"
    SPACE = "space"


class DiscoveryPresetModel(Base):
    """SQLAlchemy model for saved discovery presets."""

    __tablename__ = "discovery_presets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scope: Mapped[PresetScopeEnum] = mapped_column(
        SQLEnum(
            PresetScopeEnum,
            name="presetscopeenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PresetScopeEnum.USER,
        server_default=PresetScopeEnum.USER.value,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    research_space_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DiscoverySearchJobModel(Base):
    """SQLAlchemy model for asynchronous discovery search jobs."""

    __tablename__ = "discovery_search_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("data_discovery_sessions.id"),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
