"""DrugBank data source gateway for fetching drug-target interaction records."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DRUGBANK_SOURCE_TYPE = "drugbank"


@dataclass(frozen=True)
class DrugBankGatewayFetchResult:
    """Result of a DrugBank fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class DrugBankSourceGateway:
    """Gateway for fetching DrugBank drug records.

    Uses the DrugBankIngestor for real API calls when an API key
    is available. Falls back to empty results when no key is configured.
    """

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("DRUGBANK_API_KEY")

    def fetch_records(
        self,
        *,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        max_results: int = 100,
    ) -> DrugBankGatewayFetchResult:
        """Fetch DrugBank records for a drug name or ID.

        Returns raw JSON records suitable for Tier 1 grounding.
        """
        if not self._api_key:
            logger.info(
                "DrugBank API key not configured (set DRUGBANK_API_KEY). "
                "Returning empty results.",
            )
            return DrugBankGatewayFetchResult()

        from src.infrastructure.ingest.drugbank_ingestor import DrugBankIngestor

        ingestor = DrugBankIngestor(api_key=self._api_key)
        try:
            return asyncio.get_event_loop().run_until_complete(
                self._fetch_async(ingestor, drug_name, drugbank_id, max_results),
            )
        except RuntimeError:
            return asyncio.run(
                self._fetch_async(ingestor, drug_name, drugbank_id, max_results),
            )

    @staticmethod
    async def _fetch_async(
        ingestor: object,
        drug_name: str | None,
        drugbank_id: str | None,
        max_results: int,
    ) -> DrugBankGatewayFetchResult:
        from src.infrastructure.ingest.drugbank_ingestor import DrugBankIngestor

        assert isinstance(ingestor, DrugBankIngestor)  # noqa: S101
        async with ingestor:
            if drugbank_id:
                targets = await ingestor.fetch_drug_targets(drugbank_id)
                return DrugBankGatewayFetchResult(
                    records=targets,
                    fetched_records=len(targets),
                )
            if drug_name:
                page = await ingestor.fetch_drug_by_name(
                    drug_name,
                    max_results=max_results,
                )
                return DrugBankGatewayFetchResult(
                    records=page.records,
                    fetched_records=page.total,
                )
            return DrugBankGatewayFetchResult()

    def fetch_records_incremental(
        self,
        *,
        drug_name: str | None = None,
        checkpoint: dict[str, object] | None = None,  # noqa: ARG002
        max_results: int = 100,
    ) -> DrugBankGatewayFetchResult:
        """Fetch DrugBank records with checkpoint support for incremental ingestion."""
        return self.fetch_records(
            drug_name=drug_name,
            max_results=max_results,
        )


__all__ = ["DrugBankGatewayFetchResult", "DrugBankSourceGateway"]
