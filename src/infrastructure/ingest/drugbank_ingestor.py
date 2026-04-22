"""DrugBank API client for fetching drug-target interaction data.

Uses the DrugBank open vocabulary API for drug lookups and the
structured JSON endpoint for drug-target interactions. Requires
an API key for authenticated access (free for academic use).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.infrastructure.ingest.base_ingestor import BaseIngestor

logger = logging.getLogger(__name__)

_DRUGBANK_BASE_URL = "https://go.drugbank.com/api/v1"
_DRUGBANK_RATE_LIMIT = 30  # requests per minute (conservative)
_DRUGBANK_TIMEOUT = 30


@dataclass(frozen=True)
class DrugBankFetchPage:
    """One page of DrugBank results."""

    records: list[dict[str, object]] = field(default_factory=list)
    total: int = 0
    has_more: bool = False
    cursor: str | None = None


class DrugBankIngestor(BaseIngestor):
    """Async HTTP client for the DrugBank API."""

    def __init__(self, *, api_key: str | None = None) -> None:
        super().__init__(
            source_name="drugbank",
            base_url=_DRUGBANK_BASE_URL,
            requests_per_minute=_DRUGBANK_RATE_LIMIT,
            timeout_seconds=_DRUGBANK_TIMEOUT,
        )
        self._api_key = api_key

    async def fetch_data(self, **kwargs: object) -> list[dict[str, object]]:  # type: ignore[override]
        """Fetch DrugBank records (BaseIngestor abstract method)."""
        drug_name = str(kwargs.get("drug_name", ""))
        if not drug_name:
            return []
        page = await self.fetch_drug_by_name(drug_name)
        return page.records

    async def fetch_drug_by_name(
        self,
        drug_name: str,
        *,
        max_results: int = 25,
    ) -> DrugBankFetchPage:
        """Search for drugs by name and return structured records."""
        if not drug_name.strip():
            return DrugBankFetchPage()

        params: dict[str, str | int] = {
            "q": drug_name.strip(),
            "per_page": min(max_results, 100),
        }
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = await self._make_request(
                "GET",
                "drugs",
                params=params,
                headers=headers,
            )
            data = response.json()
        except Exception:  # noqa: BLE001
            logger.warning(
                "DrugBank API request failed for %s",
                drug_name,
                exc_info=True,
            )
            return DrugBankFetchPage()

        records = self._parse_drug_response(data)
        return DrugBankFetchPage(
            records=records,
            total=len(records),
            has_more=False,
        )

    async def fetch_drug_targets(
        self,
        drugbank_id: str,
    ) -> list[dict[str, object]]:
        """Fetch drug-target interactions for a specific DrugBank ID."""
        if not drugbank_id.strip():
            return []

        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = await self._make_request(
                "GET",
                f"drugs/{drugbank_id.strip()}/targets",
                headers=headers,
            )
            data = response.json()
        except Exception:  # noqa: BLE001
            logger.warning(
                "DrugBank target fetch failed for %s",
                drugbank_id,
                exc_info=True,
            )
            return []

        if isinstance(data, list):
            return [self._normalize_target(t) for t in data if isinstance(t, dict)]
        return []

    @classmethod
    def _parse_drug_response(cls, data: object) -> list[dict[str, object]]:
        """Parse DrugBank drug search response into normalized records."""
        records: list[object]
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            maybe_records = (
                data.get("hits") or data.get("results") or data.get("drugs") or []
            )
            if isinstance(maybe_records, list):
                records = maybe_records
            else:
                records = [data] if data.get("drugbank_id") else []
        else:
            return []

        normalized: list[dict[str, object]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            drugbank_id = record.get("drugbank_id") or record.get("id", "")
            if not drugbank_id:
                continue
            normalized.append(
                {
                    "drugbank_id": str(drugbank_id),
                    "name": str(record.get("name", "")),
                    "generic_name": str(record.get("generic_name", "")),
                    "description": str(record.get("description", "")),
                    "synonyms": cls._extract_string_values(
                        record,
                        ("synonyms", "aliases", "brand_names", "product_names"),
                    ),
                    "brand_names": cls._extract_string_values(
                        record,
                        ("brand_names", "brands"),
                    ),
                    "product_names": cls._extract_string_values(
                        record,
                        ("product_names", "products"),
                    ),
                    "categories": record.get("categories", []),
                    "targets": record.get("targets", []),
                    "mechanisms": record.get("mechanism_of_action", ""),
                    "interactions": record.get("drug_interactions", []),
                },
            )
        return normalized

    @staticmethod
    def _extract_string_values(
        record: dict[str, object],
        keys: tuple[str, ...],
    ) -> list[str]:
        """Extract flat text values from common DrugBank alias fields."""
        values: list[str] = []
        seen: set[str] = set()
        for key in keys:
            raw_value = record.get(key)
            if isinstance(raw_value, str):
                candidates: list[object] = [raw_value]
            elif isinstance(raw_value, list):
                candidates = []
                for item in raw_value:
                    if isinstance(item, dict):
                        candidates.append(item.get("name", item.get("value", "")))
                    else:
                        candidates.append(item)
            else:
                candidates = []
            for candidate in candidates:
                if not isinstance(candidate, str):
                    continue
                normalized = " ".join(candidate.split())
                if not normalized:
                    continue
                normalized_key = normalized.casefold()
                if normalized_key in seen:
                    continue
                seen.add(normalized_key)
                values.append(normalized)
        return values

    @staticmethod
    def _normalize_target(target: dict[str, object]) -> dict[str, object]:
        """Normalize a drug-target record."""
        return {
            "gene_name": str(target.get("gene_name", target.get("name", ""))),
            "protein_name": str(target.get("protein_name", "")),
            "organism": str(target.get("organism", "Homo sapiens")),
            "actions": target.get("actions", []),
            "known_action": str(target.get("known_action", "")),
        }


__all__ = ["DrugBankFetchPage", "DrugBankIngestor"]
