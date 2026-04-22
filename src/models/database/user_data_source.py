from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base

if TYPE_CHECKING:
    from .ingestion_job import IngestionJobModel
    from .research_space import ResearchSpaceModel
    from .source_template import SourceTemplateModel

# SQLAlchemy model for user-managed data sources.


class SourceTypeEnum(str, Enum):
    """SQLAlchemy enum for source types."""

    FILE_UPLOAD = "file_upload"
    API = "api"
    DATABASE = "database"
    WEB_SCRAPING = "web_scraping"
    PUBMED = "pubmed"
    CLINVAR = "clinvar"
    MARRVEL = "marrvel"
    HPO = "hpo"
    UBERON = "uberon"
    CELL_ONTOLOGY = "cell_ontology"
    GENE_ONTOLOGY = "gene_ontology"
    MONDO = "mondo"
    UNIPROT = "uniprot"
    DRUGBANK = "drugbank"
    HGNC = "hgnc"
    ALPHAFOLD = "alphafold"
    CLINICAL_TRIALS = "clinical_trials"
    MGI = "mgi"
    ZFIN = "zfin"


class SourceStatusEnum(str, Enum):
    """SQLAlchemy enum for source status."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    PENDING_REVIEW = "pending_review"
    ARCHIVED = "archived"


class UserDataSourceModel(Base):
    """
    SQLAlchemy model for user-managed data sources.

    Stores configuration and metadata for data sources created by users,
    with relationships to templates and ingestion jobs.
    """

    __tablename__ = "user_data_sources"

    # Primary key
    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)

    # Ownership
    owner_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
        doc="User who created this source",
    )
    research_space_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("research_spaces.id"),
        nullable=True,
        index=True,
        doc="Research space this source belongs to",
    )

    # Basic information
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Configuration
    source_type: Mapped[SourceTypeEnum] = mapped_column(
        SQLEnum(
            SourceTypeEnum,
            name="usersourcetypeenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    template_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("source_templates.id"),
        nullable=True,
        index=True,
    )
    configuration: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Status and lifecycle
    status: Mapped[SourceStatusEnum] = mapped_column(
        SQLEnum(
            SourceStatusEnum,
            name="sourcestatusenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=SourceStatusEnum.DRAFT,
        server_default=SourceStatusEnum.DRAFT.value,
        index=True,
    )
    ingestion_schedule: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Quality metrics
    quality_metrics: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Timestamps
    last_ingested_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Metadata
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")

    # Relationships
    template: Mapped[SourceTemplateModel | None] = relationship(
        "SourceTemplateModel",
        back_populates="sources",
    )
    research_space: Mapped[ResearchSpaceModel | None] = relationship(
        "ResearchSpaceModel",
        back_populates="data_sources",
    )
    ingestion_jobs: Mapped[list[IngestionJobModel]] = relationship(
        "IngestionJobModel",
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation of the user data source."""
        return (
            f"<UserDataSource(id={self.id}, name='{self.name}', status={self.status})>"
        )
