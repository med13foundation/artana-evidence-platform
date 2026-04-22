"""HGNC alias ingestion service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.services._structured_source_ingestion_support import (
    checkpoint_payload,
)
from src.application.services.structured_source_aliases import (
    StructuredSourceAliasWriteResult,
    build_hgnc_alias_candidates,
    count_alias_candidates,
)
from src.domain.entities.user_data_source import SourceType

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from src.application.services.structured_source_aliases import (
        StructuredEntityAliasCandidate,
        StructuredSourceAliasWriter,
    )
    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.services.ingestion import IngestionExtractionTarget
    from src.infrastructure.data_sources.hgnc_gateway import HGNCSourceGateway
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HGNCIngestionSummary:
    """Summary of an HGNC alias ingestion run."""

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
    updated_records: int = 0
    unchanged_records: int = 0
    skipped_records: int = 0
    observations_created: int = 0
    alias_candidates_count: int = 0
    aliases_persisted: int = 0
    aliases_skipped: int = 0
    alias_entities_touched: int = 0
    alias_errors: tuple[str, ...] = ()


class HGNCIngestionService:
    """Fetch HGNC nomenclature records and persist gene aliases.

    HGNC records are deterministic identity data. This service therefore stops
    at entity identifier and alias persistence; it does not enqueue Tier 2
    relation extraction or create biological relation claims.
    """

    def __init__(
        self,
        *,
        gateway: HGNCSourceGateway,
        alias_writer: StructuredSourceAliasWriter | None = None,
    ) -> None:
        self._gateway = gateway
        self._alias_writer = alias_writer

    async def ingest(
        self,
        source: UserDataSource,
        *,
        context: object | None = None,  # noqa: ARG002
    ) -> HGNCIngestionSummary:
        """Run one HGNC alias ingestion cycle for the given source."""
        if source.source_type != SourceType.HGNC.value:
            msg = f"Expected source_type={SourceType.HGNC.value}, got {source.source_type}"
            raise ValueError(msg)

        config = source.configuration.metadata if source.configuration else {}
        query = _first_config_text(config, ("query", "term", "gene"))
        symbol = _first_config_text(
            config,
            ("symbol", "approved_symbol", "gene_symbol"),
        )
        hgnc_id = _first_config_text(config, ("hgnc_id", "hgncId", "hgnc"))
        status = _first_config_text(config, ("status",))
        max_results = _resolve_max_results(config.get("max_results"))

        result = self._gateway.fetch_records(
            query=query,
            symbol=symbol,
            hgnc_id=hgnc_id,
            status=status,
            max_results=max_results,
        )
        alias_candidates = tuple(
            candidate
            for record in result.records
            for candidate in build_hgnc_alias_candidates(record)
        )
        alias_write_result = self._write_alias_candidates(
            source=source,
            alias_candidates=alias_candidates,
        )

        return HGNCIngestionSummary(
            source_id=source.id,
            fetched_records=result.fetched_records,
            new_records=len(result.records),
            executed_query=_executed_query(
                hgnc_id=hgnc_id,
                symbol=symbol,
                status=status,
                query=query,
            ),
            checkpoint_after=checkpoint_payload(result.checkpoint_after),
            checkpoint_kind=result.checkpoint_kind,
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
                "HGNC source %s has no research_space_id; skipping alias persistence",
                source.id,
            )
            return StructuredSourceAliasWriteResult(
                alias_candidates_count=alias_candidates_count,
            )
        return self._alias_writer.ensure_aliases(
            research_space_id=str(source.research_space_id),
            candidates=alias_candidates,
        )


def _first_config_text(
    config: Mapping[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def _resolve_max_results(value: object) -> int:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(1, int(value))
    if isinstance(value, str):
        try:
            return max(1, int(value))
        except ValueError:
            return 100
    return 100


def _executed_query(
    *,
    hgnc_id: str | None,
    symbol: str | None,
    status: str | None,
    query: str | None,
) -> str | None:
    if hgnc_id:
        return f"hgnc_id:{hgnc_id}"
    if symbol:
        return f"symbol:{symbol}"
    if status:
        return f"status:{status}"
    return query


__all__ = ["HGNCIngestionService", "HGNCIngestionSummary"]
