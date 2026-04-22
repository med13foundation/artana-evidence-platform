"""DrugBank ingestion service — orchestrates fetch, grounding, and pipeline entry."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from src.application.services.structured_source_aliases import (
    StructuredSourceAliasWriteResult,
    build_drugbank_alias_candidates,
    count_alias_candidates,
)
from src.domain.entities.user_data_source import SourceType
from src.type_definitions.ingestion import RawRecord

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.services.ports.ingestion_pipeline_port import (
        IngestionPipelinePort,
    )
    from src.application.services.structured_source_aliases import (
        StructuredEntityAliasCandidate,
        StructuredSourceAliasWriter,
    )
    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.services.ingestion import IngestionExtractionTarget
    from src.infrastructure.data_sources.drugbank_gateway import (
        DrugBankSourceGateway,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DrugBankIngestionSummary:
    """Summary of a DrugBank ingestion run (satisfies IngestionRunSummary protocol)."""

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
    alias_candidates_count: int = 0
    aliases_persisted: int = 0
    aliases_skipped: int = 0
    alias_entities_touched: int = 0
    alias_errors: tuple[str, ...] = ()


class DrugBankIngestionService:
    """Orchestrates DrugBank data ingestion into the graph pipeline.

    Follows the same pattern as ClinVarIngestionService:
    1. Validate source type
    2. Fetch records via gateway
    3. Deduplicate against existing records
    4. Persist source documents
    5. Queue for extraction pipeline
    """

    def __init__(
        self,
        *,
        gateway: DrugBankSourceGateway,
        pipeline: IngestionPipelinePort | None = None,
        alias_writer: StructuredSourceAliasWriter | None = None,
    ) -> None:
        self._gateway = gateway
        self._pipeline = pipeline
        self._alias_writer = alias_writer

    async def ingest(
        self,
        source: UserDataSource,
        *,
        context: object | None = None,  # noqa: ARG002
    ) -> DrugBankIngestionSummary:
        """Run a DrugBank ingestion cycle for the given data source."""
        if source.source_type != SourceType.DRUGBANK.value:
            msg = f"Expected source_type={SourceType.DRUGBANK.value}, got {source.source_type}"
            raise ValueError(msg)

        config = source.configuration.metadata if source.configuration else {}
        drug_name = config.get("drug_name") or config.get("query") or ""

        max_results_raw = config.get("max_results", 100)
        result = self._gateway.fetch_records(
            drug_name=str(drug_name) if drug_name else None,
            max_results=(
                int(max_results_raw)
                if isinstance(max_results_raw, int | float)
                else 100
            ),
        )

        logger.info(
            "DrugBank ingestion: fetched %d records for %s",
            result.fetched_records,
            drug_name,
        )

        alias_candidates = tuple(
            candidate
            for record in result.records
            for candidate in build_drugbank_alias_candidates(record)
        )
        alias_write_result = self._write_alias_candidates(
            source=source,
            alias_candidates=alias_candidates,
        )

        observations_created = 0
        if self._pipeline is not None and source.research_space_id is not None:
            raw_records = [
                RawRecord(
                    source_id=(str(record.get("drugbank_id", "")) or str(uuid4())),
                    data={str(k): v for k, v in record.items()},  # type: ignore[misc]
                    metadata={
                        "original_source_id": str(source.id),
                        "type": "drugbank",
                        "entity_type": "DRUG",
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
                "DrugBank source %s has no research_space_id; skipping kernel pipeline",
                source.id,
            )

        return DrugBankIngestionSummary(
            source_id=source.id,
            fetched_records=result.fetched_records,
            new_records=len(result.records),
            executed_query=str(drug_name) if drug_name else None,
            observations_created=observations_created,
            alias_candidates_count=alias_write_result.alias_candidates_count,
            aliases_persisted=alias_write_result.aliases_persisted,
            aliases_skipped=alias_write_result.aliases_skipped,
            alias_entities_touched=alias_write_result.alias_entities_touched,
            alias_errors=alias_write_result.errors,
        )

    def _write_alias_candidates(
        self,
        *,
        source: UserDataSource,
        alias_candidates: tuple[StructuredEntityAliasCandidate, ...],
    ) -> StructuredSourceAliasWriteResult:
        alias_candidates_count = count_alias_candidates(alias_candidates)
        if self._alias_writer is None:
            return StructuredSourceAliasWriteResult(
                alias_candidates_count=alias_candidates_count,
            )
        if source.research_space_id is None:
            logger.warning(
                "DrugBank source %s has no research_space_id; skipping alias persistence",
                source.id,
            )
            return StructuredSourceAliasWriteResult(
                alias_candidates_count=alias_candidates_count,
            )
        return self._alias_writer.ensure_aliases(
            research_space_id=str(source.research_space_id),
            candidates=alias_candidates,
        )


__all__ = ["DrugBankIngestionService", "DrugBankIngestionSummary"]
