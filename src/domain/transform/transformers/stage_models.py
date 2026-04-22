"""
Shared data models used across ETL transformation stages.

These dataclasses capture the parsed, normalized, mapped, validated,
and exported artefacts that flow through the ETL pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..parsers.clinvar_parser import ClinVarVariant
from ..parsers.hpo_parser import HPOTerm
from ..parsers.pubmed_parser import PubMedPublication
from ..parsers.uniprot_parser import UniProtProtein

if TYPE_CHECKING:
    from ..mappers.gene_variant_mapper import GeneVariantLink, GeneVariantMapper
    from ..mappers.variant_phenotype_mapper import (
        VariantPhenotypeLink,
        VariantPhenotypeMapper,
    )
    from ..normalizers.gene_normalizer import NormalizedGene
    from ..normalizers.phenotype_normalizer import NormalizedPhenotype
    from ..normalizers.publication_models import NormalizedPublication
    from ..normalizers.variant_normalizer import NormalizedVariant

StageData = dict[str, object]


@dataclass
class ParsedDataBundle:
    """Container for parsed source records."""

    clinvar: list[ClinVarVariant] = field(default_factory=list)
    pubmed: list[PubMedPublication] = field(default_factory=list)
    hpo: list[HPOTerm] = field(default_factory=list)
    uniprot: list[UniProtProtein] = field(default_factory=list)
    extras: dict[str, list[object]] = field(default_factory=dict)

    def add(self, source: str, records: list[object]) -> None:
        """Persist parsed records under the appropriate collection."""
        if source == "clinvar":
            self.clinvar = [
                record for record in records if isinstance(record, ClinVarVariant)
            ]
        elif source == "pubmed":
            self.pubmed = [
                record for record in records if isinstance(record, PubMedPublication)
            ]
        elif source == "hpo":
            self.hpo = [record for record in records if isinstance(record, HPOTerm)]
        elif source == "uniprot":
            self.uniprot = [
                record for record in records if isinstance(record, UniProtProtein)
            ]
        else:
            self.extras[source] = records

    def total_records(self) -> int:
        """Count the total number of parsed records."""
        return (
            len(self.clinvar)
            + len(self.pubmed)
            + len(self.hpo)
            + len(self.uniprot)
            + sum(len(values) for values in self.extras.values())
        )

    def as_dict(self) -> StageData:
        """Expose parsed data as plain dictionaries for reporting."""
        payload: StageData = {
            "clinvar": list(self.clinvar),
            "pubmed": list(self.pubmed),
            "hpo": list(self.hpo),
            "uniprot": list(self.uniprot),
        }
        payload.update({key: list(values) for key, values in self.extras.items()})
        return payload


@dataclass
class NormalizedDataBundle:
    """Container for normalized entities."""

    genes: list[NormalizedGene] = field(default_factory=list)
    variants: list[NormalizedVariant] = field(default_factory=list)
    phenotypes: list[NormalizedPhenotype] = field(default_factory=list)
    publications: list[NormalizedPublication] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def total_records(self) -> int:
        return (
            len(self.genes)
            + len(self.variants)
            + len(self.phenotypes)
            + len(self.publications)
        )

    def as_dict(self) -> StageData:
        return {
            "genes": list(self.genes),
            "variants": list(self.variants),
            "phenotypes": list(self.phenotypes),
            "publications": list(self.publications),
        }


@dataclass
class MappedDataBundle:
    """Container for relationship mapping outputs."""

    gene_variant_links: list[GeneVariantLink] = field(default_factory=list)
    variant_phenotype_links: list[VariantPhenotypeLink] = field(default_factory=list)
    networks: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    gene_variant_mapper: GeneVariantMapper | None = None
    variant_phenotype_mapper: VariantPhenotypeMapper | None = None

    def as_dict(self) -> StageData:
        return {
            "gene_variant_links": [asdict(link) for link in self.gene_variant_links],
            "variant_phenotype_links": [
                asdict(link) for link in self.variant_phenotype_links
            ],
            "networks": self.networks,
        }

    def relationship_count(self) -> int:
        return len(self.gene_variant_links) + len(self.variant_phenotype_links)


@dataclass
class ValidationSummary:
    """Summary of validation outcomes."""

    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def record_success(self) -> None:
        self.passed += 1

    def record_failure(self, messages: Sequence[str]) -> None:
        self.failed += 1
        self.errors.extend(messages)

    def as_dict(self) -> StageData:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "errors": list(self.errors),
        }


@dataclass
class ExportReport:
    """Details of export artefacts."""

    files_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> StageData:
        return {
            "files_created": list(self.files_created),
            "errors": list(self.errors),
        }


class TransformationStage(Enum):
    """Stages of the ETL transformation pipeline."""

    PARSING = "parsing"
    NORMALIZATION = "normalization"
    MAPPING = "mapping"
    VALIDATION = "validation"
    EXPORT = "export"


class TransformationStatus(Enum):
    """Status of transformation operations."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class TransformationResult:
    """Result of a transformation operation."""

    stage: TransformationStage
    status: TransformationStatus
    records_processed: int
    records_failed: int
    data: StageData
    errors: list[str]
    duration_seconds: float
    timestamp: float


@dataclass
class ETLTransformationMetrics:
    """Metrics collected during ETL transformation."""

    total_input_records: int
    parsed_records: int
    normalized_records: int
    mapped_relationships: int
    validation_errors: int
    processing_time_seconds: float
    stage_metrics: dict[str, StageData]


__all__ = [
    "ETLTransformationMetrics",
    "ExportReport",
    "MappedDataBundle",
    "NormalizedDataBundle",
    "ParsedDataBundle",
    "StageData",
    "TransformationResult",
    "TransformationStage",
    "TransformationStatus",
    "ValidationSummary",
]
