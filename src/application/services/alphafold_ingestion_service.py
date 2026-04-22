"""AlphaFold ingestion service — orchestrates fetch, grounding, and pipeline entry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from src.domain.entities.user_data_source import SourceType
from src.type_definitions.ingestion import RawRecord

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.services.ingestion import IngestionExtractionTarget
    from src.infrastructure.data_sources.alphafold_gateway import (
        AlphaFoldSourceGateway,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlphaFoldIngestionSummary:
    """Summary of an AlphaFold ingestion run (satisfies IngestionRunSummary protocol)."""

    source_id: UUID
    fetched_records: int = 0
    parsed_publications: int = 0
    created_publications: int = 0
    updated_publications: int = 0
    extraction_targets: tuple[IngestionExtractionTarget, ...] = ()
    executed_query: str | None = None
    query_signature: str | None = None
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: str | None = None
    new_records: int = 0
    skipped_records: int = 0
    observations_created: int = 0


class AlphaFoldIngestionService:
    """Orchestrates AlphaFold structure prediction ingestion into the graph pipeline.

    Follows the same pattern as ClinVarIngestionService:
    1. Validate source type
    2. Fetch predictions via gateway
    3. Deduplicate against existing records
    4. Persist source documents
    5. Queue for extraction pipeline
    """

    def __init__(
        self,
        *,
        gateway: AlphaFoldSourceGateway,
        pipeline: IngestionPipelinePort | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline

    async def ingest(
        self,
        source: UserDataSource,
        *,
        context: object | None = None,  # noqa: ARG002
    ) -> AlphaFoldIngestionSummary:
        """Run an AlphaFold ingestion cycle for the given data source."""
        if source.source_type != SourceType.ALPHAFOLD.value:
            msg = f"Expected source_type={SourceType.ALPHAFOLD.value}, got {source.source_type}"
            raise ValueError(msg)

        config = source.configuration.metadata if source.configuration else {}
        uniprot_id = config.get("uniprot_id") or config.get("query") or ""

        max_results_raw = config.get("max_results", 100)
        result = self._gateway.fetch_records(
            uniprot_id=str(uniprot_id) if uniprot_id else None,
            max_results=(
                int(max_results_raw)
                if isinstance(max_results_raw, int | float)
                else 100
            ),
        )

        logger.info(
            "AlphaFold ingestion: fetched %d records for %s",
            result.fetched_records,
            uniprot_id,
        )

        observations_created = 0
        if self._pipeline is not None and source.research_space_id is not None:
            raw_records = [
                RawRecord(
                    source_id=(str(record.get("uniprot_id", "")) or str(uuid4())),
                    data={str(k): v for k, v in record.items()},  # type: ignore[misc]
                    metadata={
                        "original_source_id": str(source.id),
                        "type": "alphafold",
                        "entity_type": "PROTEIN",
                    },
                )
                for record in result.records
            ]
            pipeline_result = self._pipeline.run(
                raw_records,
                research_space_id=str(source.research_space_id),
            )
            observations_created = pipeline_result.observations_created
        elif self._pipeline is not None and source.research_space_id is None:
            logger.warning(
                "AlphaFold source %s has no research_space_id; skipping kernel pipeline",
                source.id,
            )

        return AlphaFoldIngestionSummary(
            source_id=source.id,
            fetched_records=result.fetched_records,
            new_records=len(result.records),
            executed_query=str(uniprot_id) if uniprot_id else None,
            observations_created=observations_created,
        )


__all__ = ["AlphaFoldIngestionService", "AlphaFoldIngestionSummary"]
