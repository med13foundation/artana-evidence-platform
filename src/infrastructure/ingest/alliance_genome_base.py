"""Shared base class for Alliance of Genome Resources REST API ingestors.

The Alliance of Genome Resources federates MGI, ZFIN, FlyBase, WormBase,
RGD, and SGD into one consistent JSON shape (see
https://www.alliancegenome.org/api).  Every sibling ingestor we ship for
these Model Organism Databases uses the exact same ``/search`` endpoint,
rate limit, timeout, and response-parsing flow — they only differ in the
species filter, the provider prefix used to namespace identifiers, the
name of the identifier key in the returned ``RawRecord``, and any
source-specific extras (e.g. ZFIN extracts an extra ``expression_terms``
field).

``AllianceGenomeIngestor`` centralizes everything that is truly shared
and exposes a ``_normalize_gene`` template method that subclasses can
override to contribute extra fields via ``_extract_extra_fields``.
Sibling page dataclasses (``MGIFetchPage``, ``ZFINFetchPage``) remain
defined in their own modules as thin subclasses so test imports like
``from src.infrastructure.ingest.mgi_ingestor import MGIFetchPage``
continue to work unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

from src.infrastructure.ingest.base_ingestor import BaseIngestor

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject, JSONValue, RawRecord

logger = logging.getLogger(__name__)

ALLIANCE_BASE_URL = "https://www.alliancegenome.org/api"
ALLIANCE_RATE_LIMIT = 30  # requests per minute (conservative)
ALLIANCE_TIMEOUT = 30
ALLIANCE_MAX_PAGE_SIZE = 50


@dataclass(frozen=True)
class AllianceGenomePage:
    """Result of a gene-record fetch from the Alliance of Genome Resources API.

    Shared by every Model Organism Database ingestor that talks to the
    Alliance API.  Source-specific modules expose thin subclass aliases
    (e.g. ``MGIFetchPage``, ``ZFINFetchPage``) so existing import paths
    and ``isinstance(...)`` checks keep working.
    """

    records: list[RawRecord] = field(default_factory=list)
    total_count: int = 0

    @property
    def has_more(self) -> bool:
        # The Alliance search endpoint isn't paginated for our use case.
        return False


class AllianceGenomeIngestor(BaseIngestor):
    """Async HTTP client for the Alliance of Genome Resources gene search API.

    Subclasses configure the species filter, provider prefix, and
    identifier key name via class attributes (or by overriding the
    ``_SPECIES_FILTER`` / ``_PROVIDER_PREFIX`` / ``_ID_KEY`` class vars).
    The response-parsing flow and all scalar helpers live here.

    Subclasses may override ``_extract_extra_fields`` to contribute
    additional entries to the normalized record (e.g. ZFIN's
    ``expression_terms``); the default implementation returns an empty
    dict so the vast majority of MODs need only set the three class
    attributes above.
    """

    # Subclasses MUST override these three class attrs.
    _SOURCE_NAME: ClassVar[str] = ""
    _SPECIES_FILTER: ClassVar[str] = ""
    _PROVIDER_PREFIX: ClassVar[str] = ""
    _ID_KEY: ClassVar[str] = ""
    # Subclasses MAY override this to use their own dataclass alias.
    _PAGE_CLASS: ClassVar[type[AllianceGenomePage]] = AllianceGenomePage

    def __init__(self) -> None:
        if not self._SOURCE_NAME or not self._SPECIES_FILTER or not self._ID_KEY:
            message = (
                f"{type(self).__name__} must set _SOURCE_NAME, "
                "_SPECIES_FILTER, and _ID_KEY class attributes"
            )
            raise TypeError(message)
        super().__init__(
            source_name=self._SOURCE_NAME,
            base_url=ALLIANCE_BASE_URL,
            requests_per_minute=ALLIANCE_RATE_LIMIT,
            timeout_seconds=ALLIANCE_TIMEOUT,
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """Fetch gene records (``BaseIngestor`` abstract method).

        Accepts ``query`` (gene symbol or free-text, required) and
        ``max_results`` (int, default 10) as kwargs.
        """
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return []
        max_results_raw = kwargs.get("max_results", 10)
        try:
            max_results = int(max_results_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            max_results = 10
        page = await self.fetch_gene_records(query=query, max_results=max_results)
        return page.records

    async def fetch_gene_records(
        self,
        *,
        query: str,
        max_results: int = 10,
    ) -> AllianceGenomePage:
        """Search the Alliance API for gene records matching ``query``.

        Uses ``GET /search?q={query}&category=gene&species={species}``.
        ``max_results`` is capped at the API page-size limit.
        """
        if not query.strip():
            return self._PAGE_CLASS()
        page_size = max(1, min(max_results, ALLIANCE_MAX_PAGE_SIZE))
        params: dict[str, str] = {
            "q": query.strip(),
            "category": "gene",
            "species": self._SPECIES_FILTER,
            "limit": str(page_size),
        }

        try:
            response = await self._make_request("GET", "search", params=params)
            data = response.json()
        except Exception:  # noqa: BLE001
            logger.warning(
                "Alliance API (%s) request failed for query=%r",
                self._PROVIDER_PREFIX or self._SOURCE_NAME,
                query,
                exc_info=True,
            )
            return self._PAGE_CLASS()

        return self._parse_search_payload(data)

    def _parse_search_payload(self, data: object) -> AllianceGenomePage:
        """Project the Alliance ``/search`` response into flat gene records.

        Filters to the configured species.  Other model organism
        databases use the same shape but different ``species`` values,
        so the species filter is what makes each subclass source-specific.
        """
        if not isinstance(data, dict):
            return self._PAGE_CLASS()
        results_raw = data.get("results")
        if not isinstance(results_raw, list):
            return self._PAGE_CLASS()

        records: list[RawRecord] = []
        for entry in results_raw:
            if not isinstance(entry, dict):
                continue
            normalized = self._normalize_gene(entry)
            if normalized:
                records.append(normalized)

        total_raw = data.get("total")
        total_count = int(total_raw) if isinstance(total_raw, int) else len(records)
        return self._PAGE_CLASS(records=records, total_count=total_count)

    def _normalize_gene(self, entry: JSONObject) -> RawRecord | None:
        """Flatten one Alliance gene-search hit into a stable ``RawRecord``.

        The identifier key used in the returned dict is controlled by
        ``_ID_KEY``; the species filter by ``_SPECIES_FILTER``.  Any
        source-specific extras are merged in via ``_extract_extra_fields``.
        """
        species = entry.get("species")
        if isinstance(species, str) and species and species != self._SPECIES_FILTER:
            return None

        primary_id = self._scalar_string(entry, "primaryKey") or self._scalar_string(
            entry,
            "id",
        )
        if not primary_id:
            return None
        normalized_id = primary_id.strip()
        if (
            self._PROVIDER_PREFIX
            and not normalized_id.startswith(self._PROVIDER_PREFIX)
            and ":" not in normalized_id
        ):
            normalized_id = f"{self._PROVIDER_PREFIX}:{normalized_id}"

        symbol = self._scalar_string(entry, "symbol") or self._scalar_string(
            entry,
            "geneSymbol",
        )
        name = self._scalar_string(entry, "name") or self._scalar_string(
            entry,
            "geneName",
        )
        synonyms = self._scalar_list(entry, "synonyms")

        phenotype_statements = self._extract_phenotype_statements(entry)
        disease_associations = self._extract_disease_associations(entry)

        record: RawRecord = {
            self._ID_KEY: normalized_id,
            "gene_symbol": symbol,
            "gene_name": name,
            "synonyms": synonyms,
            "species": species if isinstance(species, str) else self._SPECIES_FILTER,
            "phenotype_statements": phenotype_statements,
            "disease_associations": disease_associations,
        }
        record.update(self._extract_extra_fields(entry))
        return record

    def _extract_extra_fields(
        self,
        entry: JSONObject,  # noqa: ARG002 - override hook
    ) -> RawRecord:
        """Template-method hook for subclass-specific record fields.

        Default: no extras.  Overridden by e.g. :class:`ZFINIngestor` to
        add ``expression_terms``.
        """
        return {}

    @staticmethod
    def _scalar_string(payload: object, key: str) -> str:
        if not isinstance(payload, dict):
            return ""
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _scalar_list(payload: object, key: str) -> list[str]:
        if not isinstance(payload, dict):
            return []
        value = payload.get(key)
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if isinstance(item, str) and item]

    @staticmethod
    def _extract_phenotype_statements(entry: JSONObject) -> list[str]:
        """Pull out the human-readable phenotype statements for a gene.

        The Alliance API exposes these under either ``phenotypeStatements``
        or ``phenotypes`` (depending on response variant); we accept both.
        """
        for key in ("phenotypeStatements", "phenotypes", "annotations"):
            raw = entry.get(key)
            if isinstance(raw, list):
                return [
                    item.strip()
                    for item in raw
                    if isinstance(item, str) and item.strip()
                ]
        return []

    @staticmethod
    def _extract_disease_associations(entry: JSONObject) -> list[JSONObject]:
        """Extract disease associations as ``{do_id, name}`` records."""
        raw = entry.get("diseases")
        if not isinstance(raw, list):
            return []
        results: list[JSONObject] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                results.append({"name": item.strip(), "do_id": None})
            elif isinstance(item, dict):
                name = item.get("name") or item.get("doName")
                do_id = item.get("doId") or item.get("id")
                if isinstance(name, str) and name.strip():
                    results.append(
                        {
                            "name": name.strip(),
                            "do_id": (
                                do_id.strip()
                                if isinstance(do_id, str) and do_id.strip()
                                else None
                            ),
                        },
                    )
        return results


__all__ = [
    "ALLIANCE_BASE_URL",
    "ALLIANCE_MAX_PAGE_SIZE",
    "ALLIANCE_RATE_LIMIT",
    "ALLIANCE_TIMEOUT",
    "AllianceGenomeIngestor",
    "AllianceGenomePage",
]
