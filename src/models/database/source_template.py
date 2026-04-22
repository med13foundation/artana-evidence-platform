from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base

# SQLAlchemy model for reusable data source templates.


class TemplateCategoryEnum(str, Enum):
    """SQLAlchemy enum for template categories."""

    CLINICAL = "clinical"
    RESEARCH = "research"
    LITERATURE = "literature"
    GENOMIC = "genomic"
    PHENOTYPIC = "phenotypic"
    ONTOLOGY = "ontology"
    OTHER = "other"


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


class SourceTemplateModel(Base):
    """
    SQLAlchemy model for data source templates.

    Stores reusable configurations for common biomedical data sources,
    enabling users to quickly set up new sources with validated settings.
    """

    __tablename__ = "source_templates"

    # Primary key
    id: Mapped[str] = mapped_column(PGUUID(as_uuid=False), primary_key=True)

    # Ownership
    created_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
        doc="User who created this template",
    )

    # Basic information
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[TemplateCategoryEnum] = mapped_column(
        SQLEnum(
            TemplateCategoryEnum,
            name="templatecategoryenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TemplateCategoryEnum.OTHER,
        server_default=TemplateCategoryEnum.OTHER.value,
        index=True,
    )

    # Template definition
    source_type: Mapped[SourceTypeEnum] = mapped_column(
        SQLEnum(
            SourceTypeEnum,
            name="sourcetypeenum",
            create_constraint=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    schema_definition: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    validation_rules: Mapped[list[JSONObject]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    # UI configuration
    ui_config: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    # Governance
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    is_approved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    approval_required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # Usage statistics
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Timestamps
    approved_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Metadata
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    compatibility_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0",
    )

    # Relationships
    sources = relationship(
        "UserDataSourceModel",
        back_populates="template",
    )

    def __repr__(self) -> str:
        """String representation of the source template."""
        return f"<SourceTemplate(id={self.id}, name='{self.name}', public={self.is_public})>"
