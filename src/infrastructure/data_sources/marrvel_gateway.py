"""Infrastructure adapter for MARRVEL record retrieval."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.marrvel_ingestion import (
    MarrvelGateway,
    MarrvelGatewayFetchResult,
)
from src.infrastructure.ingest import MarrvelIngestor

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.entities.data_source_configs import MarrvelQueryConfig
    from src.type_definitions.common import JSONObject, JSONValue, RawRecord


class MarrvelSourceGateway(MarrvelGateway):
    """MARRVEL gateway backed by the infrastructure MARRVEL ingestor."""

    def __init__(
        self,
        ingestor_factory: Callable[[], MarrvelIngestor] | None = None,
    ) -> None:
        self._ingestor_factory = ingestor_factory or MarrvelIngestor

    async def fetch_records(self, config: MarrvelQueryConfig) -> list[RawRecord]:
        """Fetch MARRVEL records using normalized query configuration."""
        query_kwargs = self._build_query_kwargs(config=config, gene_index=0)

        ingestor = self._ingestor_factory()
        async with ingestor:
            return await ingestor.fetch_data(**query_kwargs)

    async def fetch_records_incremental(
        self,
        config: MarrvelQueryConfig,
        *,
        checkpoint: JSONObject | None = None,
    ) -> MarrvelGatewayFetchResult:
        """Fetch MARRVEL records with gene-index-based checkpoint semantics."""
        gene_index = self._extract_gene_index(checkpoint)
        remaining_symbols = config.gene_symbols[gene_index:]

        if not remaining_symbols:
            return MarrvelGatewayFetchResult(
                records=[],
                fetched_records=0,
                checkpoint_after=self._build_checkpoint(
                    gene_index=len(config.gene_symbols),
                    total_genes=len(config.gene_symbols),
                    current_symbol=None,
                    cycle_completed=True,
                ),
                checkpoint_kind=CheckpointKind.CURSOR,
            )

        query_kwargs = self._build_query_kwargs(config=config, gene_index=gene_index)

        ingestor = self._ingestor_factory()
        async with ingestor:
            records = await ingestor.fetch_data(**query_kwargs)

        next_index = len(config.gene_symbols)
        has_more = False

        checkpoint_after = self._build_checkpoint(
            gene_index=next_index,
            total_genes=len(config.gene_symbols),
            current_symbol=remaining_symbols[-1] if remaining_symbols else None,
            cycle_completed=not has_more,
        )

        return MarrvelGatewayFetchResult(
            records=records,
            fetched_records=len(records),
            checkpoint_after=checkpoint_after,
            checkpoint_kind=CheckpointKind.CURSOR,
        )

    @staticmethod
    def _build_query_kwargs(
        *,
        config: MarrvelQueryConfig,
        gene_index: int,
    ) -> dict[str, JSONValue]:
        remaining = config.gene_symbols[gene_index:]
        return {
            "gene_symbols": remaining,
            "taxon_id": config.taxon_id,
            "include_omim": config.include_omim_data,
            "include_dbnsfp": config.include_dbnsfp_data,
            "include_clinvar": config.include_clinvar_data,
            "include_geno2mp": config.include_geno2mp_data,
            "include_gnomad": config.include_gnomad_data,
            "include_dgv": config.include_dgv_data,
            "include_diopt": config.include_diopt_data,
            "include_gtex": config.include_gtex_data,
            "include_expression": config.include_expression_data,
            "include_pharos": config.include_pharos_data,
        }

    @staticmethod
    def _build_checkpoint(
        *,
        gene_index: int,
        total_genes: int,
        current_symbol: str | None,
        cycle_completed: bool,
    ) -> JSONObject:
        checkpoint: JSONObject = {
            "provider": "marrvel",
            "cursor_type": "gene_index",
            "gene_index": gene_index,
            "total_genes": total_genes,
            "cycle_completed": cycle_completed,
        }
        if current_symbol:
            checkpoint["current_symbol"] = current_symbol
        return checkpoint

    @staticmethod
    def _extract_gene_index(checkpoint: JSONObject | None) -> int:
        """Resolve gene index cursor from checkpoint payload."""
        if checkpoint is None:
            return 0
        provider = checkpoint.get("provider")
        if isinstance(provider, str) and provider.lower() != "marrvel":
            return 0
        if checkpoint.get("cycle_completed") is True:
            return 0
        index_raw = checkpoint.get("gene_index")
        if isinstance(index_raw, int) and index_raw >= 0:
            return index_raw
        if isinstance(index_raw, float):
            return max(int(index_raw), 0)
        return 0
