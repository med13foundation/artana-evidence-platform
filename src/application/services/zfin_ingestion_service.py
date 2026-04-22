"""ZFIN scheduled ingestion service."""

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
    source_type=SourceType.ZFIN,
    source_label="ZFIN",
    query_keys=("query", "gene_symbol", "gene", "term", "zfin_id"),
    id_keys=("zfin_id", "id", "gene_symbol"),
    entity_type="GENE",
    default_max_results=10,
)


class ZFINIngestionService(StructuredSourceIngestionService):
    """Fetch ZFIN zebrafish gene records for scheduled ingestion."""

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


ZFINIngestionSummary = StructuredSourceIngestionSummary


__all__ = ["ZFINIngestionService", "ZFINIngestionSummary"]
