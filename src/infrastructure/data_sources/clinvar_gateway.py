"""Infrastructure adapter for ClinVar record retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.clinvar_ingestion import (
    ClinVarGateway,
    ClinVarGatewayFetchResult,
)
from src.infrastructure.ingest import ClinVarIngestor

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.entities.data_source_configs import ClinVarQueryConfig
    from src.type_definitions.common import JSONObject, RawRecord


class ClinVarSourceGateway(ClinVarGateway):
    """ClinVar gateway backed by the infrastructure ClinVar ingestor."""

    def __init__(
        self,
        ingestor_factory: Callable[[], ClinVarIngestor] | None = None,
    ) -> None:
        self._ingestor_factory = ingestor_factory or ClinVarIngestor

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[RawRecord]:
        """Fetch ClinVar records using normalized query configuration."""
        query_kwargs = self._build_query_kwargs(config=config, retstart=None)

        ingestor = self._ingestor_factory()
        async with ingestor:
            return await ingestor.fetch_data(**query_kwargs)

    async def fetch_records_incremental(
        self,
        config: ClinVarQueryConfig,
        *,
        checkpoint: JSONObject | None = None,
    ) -> ClinVarGatewayFetchResult:
        """Fetch ClinVar records with cursor-aware checkpoint semantics."""
        retstart = self._extract_retstart(checkpoint)
        query_kwargs = self._build_query_kwargs(config=config, retstart=retstart)

        ingestor = self._ingestor_factory()
        async with ingestor:
            if hasattr(ingestor, "fetch_page"):
                page = await ingestor.fetch_page(**query_kwargs)
                fetched_records = page.returned_count
                next_retstart = page.next_retstart if page.has_more else 0
                total_count = page.total_count
                page_size = page.retmax
                has_more = page.has_more
                returned_count = page.returned_count
                records = list(page.records)
            else:
                records = await ingestor.fetch_data(**query_kwargs)
                fetched_records = len(records)
                total_count = fetched_records
                page_size = max(config.max_results, 1)
                next_retstart = retstart + fetched_records if fetched_records else 0
                has_more = False
                returned_count = fetched_records

        checkpoint_after: JSONObject = {
            "provider": "clinvar",
            "cursor_type": "retstart",
            "retstart": next_retstart,
            "retmax": page_size,
            "total_count": total_count,
            "returned_count": returned_count,
            "has_more": has_more,
            "cycle_completed": not has_more,
        }
        return ClinVarGatewayFetchResult(
            records=records,
            fetched_records=fetched_records,
            checkpoint_after=checkpoint_after,
            checkpoint_kind=CheckpointKind.CURSOR,
        )

    @staticmethod
    def _build_query_kwargs(
        *,
        config: ClinVarQueryConfig,
        retstart: int | None,
    ) -> dict[str, str | int]:
        query_kwargs: dict[str, str | int] = {
            "gene_symbol": config.gene_symbol,
            "max_results": config.max_results,
        }
        if retstart is not None:
            query_kwargs["retstart"] = max(retstart, 0)
        if config.variation_types:
            # ClinVar ingestor accepts a single variation_type filter.
            query_kwargs["variation_type"] = config.variation_types[0]
        if config.clinical_significance:
            # ClinVar ingestor accepts a single clinical_significance filter.
            query_kwargs["clinical_significance"] = config.clinical_significance[0]
        return query_kwargs

    @staticmethod
    def _extract_retstart(checkpoint: JSONObject | None) -> int:
        """Resolve provider cursor from checkpoint payload."""
        if checkpoint is None:
            return 0
        provider = checkpoint.get("provider")
        if isinstance(provider, str) and provider.lower() != "clinvar":
            return 0
        retstart_raw = checkpoint.get("retstart")
        if isinstance(retstart_raw, int) and retstart_raw >= 0:
            return retstart_raw
        if isinstance(retstart_raw, float):
            candidate = int(retstart_raw)
            return max(candidate, 0)
        if isinstance(retstart_raw, str) and retstart_raw.isdigit():
            return int(retstart_raw)
        return 0
