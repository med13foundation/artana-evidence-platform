"""ClinicalTrials.gov scheduled ingestion service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.user_data_source import SourceType

from ._structured_source_ingestion import (
    StructuredSourceGateway,
    StructuredSourceIngestionConfig,
    StructuredSourceIngestionService,
    StructuredSourceIngestionSummary,
)

if TYPE_CHECKING:
    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.repositories.source_document_repository import (
        SourceDocumentRepository,
    )

_CONFIG = StructuredSourceIngestionConfig(
    source_type=SourceType.CLINICAL_TRIALS,
    source_label="ClinicalTrials.gov",
    query_keys=("query", "condition", "disease", "term", "nct_id"),
    id_keys=("nct_id", "id"),
    entity_type="CLINICAL_TRIAL",
    default_max_results=20,
)


class ClinicalTrialsIngestionService(StructuredSourceIngestionService):
    """Fetch ClinicalTrials.gov records for scheduled ingestion."""

    def __init__(
        self,
        *,
        gateway: StructuredSourceGateway,
        pipeline: IngestionPipelinePort | None = None,
        source_document_repository: SourceDocumentRepository | None = None,
    ) -> None:
        super().__init__(
            gateway=gateway,
            pipeline=pipeline,
            source_document_repository=source_document_repository,
            config=_CONFIG,
        )


ClinicalTrialsIngestionSummary = StructuredSourceIngestionSummary


__all__ = ["ClinicalTrialsIngestionService", "ClinicalTrialsIngestionSummary"]
