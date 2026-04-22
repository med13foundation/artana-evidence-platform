"""AlphaFold data source gateway for fetching protein structure predictions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ALPHAFOLD_SOURCE_TYPE = "alphafold"


@dataclass(frozen=True)
class AlphaFoldGatewayFetchResult:
    """Result of an AlphaFold fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class AlphaFoldSourceGateway:
    """Gateway for fetching AlphaFold structure predictions.

    Uses the AlphaFoldIngestor for real API calls against the
    AlphaFold DB REST API (open access, no authentication).
    """

    def __init__(self, *, base_url: str | None = None) -> None:
        self._base_url = base_url or "https://alphafold.ebi.ac.uk/api"

    def fetch_records(
        self,
        *,
        uniprot_id: str | None = None,
        max_results: int = 100,  # noqa: ARG002
    ) -> AlphaFoldGatewayFetchResult:
        """Fetch AlphaFold predictions for a UniProt accession.

        Returns raw JSON records suitable for Tier 1 grounding.
        """
        if not uniprot_id or not uniprot_id.strip():
            return AlphaFoldGatewayFetchResult()

        from src.infrastructure.ingest.alphafold_ingestor import AlphaFoldIngestor

        ingestor = AlphaFoldIngestor()
        try:
            return asyncio.get_event_loop().run_until_complete(
                self._fetch_async(ingestor, uniprot_id),
            )
        except RuntimeError:
            return asyncio.run(
                self._fetch_async(ingestor, uniprot_id),
            )

    @staticmethod
    async def _fetch_async(
        ingestor: object,
        uniprot_id: str,
    ) -> AlphaFoldGatewayFetchResult:
        from src.infrastructure.ingest.alphafold_ingestor import AlphaFoldIngestor

        assert isinstance(ingestor, AlphaFoldIngestor)  # noqa: S101
        async with ingestor:
            prediction = await ingestor.fetch_prediction(uniprot_id)
            if prediction is None:
                return AlphaFoldGatewayFetchResult()
            record: dict[str, object] = {
                "uniprot_id": prediction.uniprot_id,
                "protein_name": prediction.protein_name,
                "organism": prediction.organism,
                "gene_name": prediction.gene_name,
                "model_url": prediction.model_url,
                "pdb_url": prediction.pdb_url,
                "predicted_structure_confidence": prediction.confidence_avg,
                "domains": prediction.domains,
            }
            return AlphaFoldGatewayFetchResult(records=[record], fetched_records=1)

    def fetch_records_incremental(
        self,
        *,
        uniprot_id: str | None = None,
        checkpoint: dict[str, object] | None = None,  # noqa: ARG002
        max_results: int = 100,  # noqa: ARG002
    ) -> AlphaFoldGatewayFetchResult:
        """Fetch AlphaFold records with checkpoint support."""
        return self.fetch_records(
            uniprot_id=uniprot_id,
            max_results=max_results,
        )


__all__ = ["AlphaFoldGatewayFetchResult", "AlphaFoldSourceGateway"]
