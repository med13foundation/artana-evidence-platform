"""
PubMed API client for Artana Resource Library.
Fetches scientific literature and publication data from PubMed.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.domain.services.pubmed_ingestion import PubMedQueryValidationResult

from .base_ingestor import BaseIngestor
from .pubmed_record_parser_mixin import PubMedRecordParserMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import JSONValue, RawRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PubMedSearchPage:
    """Search-stage page metadata returned by ESearch."""

    article_ids: list[str]
    total_count: int
    retstart: int
    retmax: int

    @property
    def returned_count(self) -> int:
        """Number of IDs returned in this page."""
        return len(self.article_ids)


@dataclass(frozen=True)
class PubMedFetchPage:
    """Fetch-stage result including records and cursor metadata."""

    records: list[RawRecord]
    total_count: int
    retstart: int
    retmax: int
    returned_count: int

    @property
    def next_retstart(self) -> int:
        """Cursor offset for the next page."""
        return self.retstart + self.returned_count

    @property
    def has_more(self) -> bool:
        """Whether additional pages are available."""
        return self.next_retstart < self.total_count


class PubMedIngestor(BaseIngestor, PubMedRecordParserMixin):
    """
    PubMed API client for fetching scientific literature data.

    PubMed provides access to biomedical literature citations and abstracts.
    This ingestor focuses on publications related to MED13 gene and
    associated conditions.
    """

    def __init__(self) -> None:
        super().__init__(
            source_name="pubmed",
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            requests_per_minute=10,  # NCBI limits: 10 requests per second
            timeout_seconds=60,  # PubMed can be slow
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Fetch PubMed data for specified search query.

        Args:
            query: Search query (default: MED13)
            **kwargs: Additional search parameters

        Returns:
            List of PubMed article records
        """
        page = await self.fetch_page(**kwargs)
        return page.records

    async def fetch_page(self, **kwargs: JSONValue) -> PubMedFetchPage:
        """Fetch one PubMed page with explicit cursor metadata."""
        pinned_pubmed_id_raw = kwargs.get("pinned_pubmed_id")
        if isinstance(pinned_pubmed_id_raw, str) and pinned_pubmed_id_raw.strip():
            pinned_pubmed_id = pinned_pubmed_id_raw.strip()
            records = await self._fetch_article_details([pinned_pubmed_id])
            retmax = max(self._coerce_int(kwargs.get("max_results"), 1), 1)
            total_count = 1 if records else 0
            return PubMedFetchPage(
                records=records,
                total_count=total_count,
                retstart=0,
                retmax=retmax,
                returned_count=len(records),
            )

        # Step 1: Search for publications
        query_value = kwargs.get("query")
        query = query_value if isinstance(query_value, str) else "MED13"

        search_kwargs = dict(kwargs)
        search_kwargs.pop("query", None)

        search_page = await self._search_publications(query, **search_kwargs)
        article_ids = list(search_page.article_ids)
        if not article_ids:
            return PubMedFetchPage(
                records=[],
                total_count=search_page.total_count,
                retstart=search_page.retstart,
                retmax=search_page.retmax,
                returned_count=0,
            )

        # Step 2: Fetch detailed records in batches
        all_records: list[RawRecord] = []
        batch_size = 50  # PubMed API limit

        for i in range(0, len(article_ids), batch_size):
            batch_ids = article_ids[i : i + batch_size]
            batch_records = await self._fetch_article_details(batch_ids)
            all_records.extend(batch_records)

            # Small delay between batches
            await asyncio.sleep(0.1)

        if self._coerce_bool(kwargs.get("open_access_only"), default=True):
            all_records = self._enforce_open_access_record_set(all_records)

        return PubMedFetchPage(
            records=all_records,
            total_count=search_page.total_count,
            retstart=search_page.retstart,
            retmax=search_page.retmax,
            returned_count=search_page.returned_count,
        )

    async def validate_query(
        self,
        query: str,
        **kwargs: JSONValue,
    ) -> PubMedQueryValidationResult:
        """Validate a PubMed query against ESearch and capture API feedback."""
        full_query = self._build_full_query(query, **kwargs)
        esearch_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in {"retstart", "retmax", "max_results", "query"}
        }
        params = self._build_esearch_params(
            full_query=full_query,
            retstart=0,
            retmax=0,
            **esearch_kwargs,
        )
        response = await self._make_request("GET", "esearch.fcgi", params=params)
        try:
            data = self._ensure_raw_record(response.json())
        except ValueError as exc:
            return PubMedQueryValidationResult(
                is_valid=False,
                api_feedback=f"PubMed query validation returned malformed JSON: {exc}",
            )

        top_level_error = data.get("error")
        if isinstance(top_level_error, str) and top_level_error.strip():
            return PubMedQueryValidationResult(
                is_valid=False,
                api_feedback=top_level_error.strip(),
            )

        esearch_section = data.get("esearchresult")
        if not isinstance(esearch_section, dict):
            return PubMedQueryValidationResult(
                is_valid=False,
                api_feedback="PubMed query validation response was missing esearchresult.",
            )

        errors = self._extract_feedback_messages(esearch_section.get("errorlist"))
        warnings = self._extract_feedback_messages(esearch_section.get("warninglist"))
        translated_query = self._coerce_optional_string(
            esearch_section.get("querytranslation"),
        )
        result_count = self._coerce_int(esearch_section.get("count"), 0)
        feedback_parts: list[str] = []
        if errors:
            feedback_parts.extend(errors)
        if warnings:
            feedback_parts.extend(warnings)
        if translated_query:
            feedback_parts.append(f"PubMed translated query: {translated_query}")

        return PubMedQueryValidationResult(
            is_valid=not errors,
            api_feedback=" ".join(feedback_parts) or None,
            translated_query=translated_query,
            result_count=result_count,
        )

    async def _search_publications(
        self,
        query: str,
        **kwargs: JSONValue,
    ) -> PubMedSearchPage:
        """
        Search PubMed for publications matching the query.

        Args:
            query: PubMed search query
            **kwargs: Additional search parameters

        Returns:
            List of PubMed article IDs
        """
        retstart = max(self._coerce_int(kwargs.get("retstart"), 0), 0)
        retmax = max(self._coerce_int(kwargs.get("max_results"), 500), 1)
        full_query = self._build_full_query(query, **kwargs)
        esearch_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key not in {"retstart", "retmax", "max_results", "query"}
        }
        params = self._build_esearch_params(
            full_query=full_query,
            retstart=retstart,
            retmax=retmax,
            **esearch_kwargs,
        )

        response = await self._make_request("GET", "esearch.fcgi", params=params)
        data = self._ensure_raw_record(response.json())

        # Extract article IDs from search results
        esearch_section = data.get("esearchresult")
        if not isinstance(esearch_section, dict):
            return PubMedSearchPage(
                article_ids=[],
                total_count=0,
                retstart=retstart,
                retmax=retmax,
            )
        response_total_count = self._coerce_int(esearch_section.get("count"), 0)
        response_retstart = self._coerce_int(esearch_section.get("retstart"), retstart)
        response_retmax = self._coerce_int(esearch_section.get("retmax"), retmax)
        id_list = esearch_section.get("idlist", [])
        if not isinstance(id_list, list):
            return PubMedSearchPage(
                article_ids=[],
                total_count=response_total_count,
                retstart=response_retstart,
                retmax=response_retmax,
            )
        return PubMedSearchPage(
            article_ids=[str(aid) for aid in id_list],
            total_count=response_total_count,
            retstart=response_retstart,
            retmax=response_retmax,
        )

    def _build_full_query(self, query: str, **kwargs: JSONValue) -> str:
        """Compose the final PubMed ESearch term including source filters."""
        query_terms = [query]

        publication_date_from = kwargs.get("publication_date_from")
        if isinstance(publication_date_from, str):
            query_terms.append(f"{publication_date_from}[pdat]")

        publication_types = kwargs.get("publication_types")
        if isinstance(publication_types, list):
            pub_types = " OR ".join(
                f'"{pt}"[pt]' for pt in publication_types if isinstance(pt, str)
            )
            if pub_types:
                query_terms.append(f"({pub_types})")

        if self._coerce_bool(kwargs.get("open_access_only"), default=True):
            query_terms.append('"free full text"[sb]')

        return " AND ".join(f"({term})" for term in query_terms)

    def _build_esearch_params(
        self,
        *,
        full_query: str,
        retstart: int,
        retmax: int,
        **kwargs: JSONValue,
    ) -> dict[str, str | int | float | bool | None]:
        """Build the PubMed ESearch request payload."""
        mindate_value = kwargs.get("mindate")
        maxdate_value = kwargs.get("maxdate")
        return {
            "db": "pubmed",
            "term": full_query,
            "retmode": "json",
            "retstart": retstart,
            "retmax": retmax,
            "sort": "relevance",
            "datetype": "pdat",
            "mindate": mindate_value if isinstance(mindate_value, str) else None,
            "maxdate": maxdate_value if isinstance(maxdate_value, str) else None,
        }

    @staticmethod
    def _extract_feedback_messages(raw_feedback: object) -> list[str]:
        if isinstance(raw_feedback, str):
            normalized = raw_feedback.strip()
            return [normalized] if normalized else []
        if isinstance(raw_feedback, list):
            return [
                entry.strip()
                for entry in raw_feedback
                if isinstance(entry, str) and entry.strip()
            ]
        if isinstance(raw_feedback, dict):
            messages = []
            for key, value in raw_feedback.items():
                if isinstance(value, str) and value.strip():
                    messages.append(f"{key}: {value.strip()}")
                    continue
                if isinstance(value, list):
                    normalized_values = [
                        item.strip()
                        for item in value
                        if isinstance(item, str) and item.strip()
                    ]
                    if normalized_values:
                        messages.append(f"{key}: {', '.join(normalized_values)}")
            return messages
        return []

    @staticmethod
    def _coerce_optional_string(raw_value: object) -> str | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        return normalized or None

    def _enforce_open_access_record_set(
        self,
        records: list[RawRecord],
    ) -> list[RawRecord]:
        retained: list[RawRecord] = []
        dropped_pubmed_ids: list[str] = []
        for record in records:
            pmc_id_value = record.get("pmc_id")
            has_pmc_id = isinstance(pmc_id_value, str) and bool(pmc_id_value.strip())
            if has_pmc_id:
                retained.append(record)
                continue
            pubmed_id_value = record.get("pubmed_id")
            if isinstance(pubmed_id_value, str) and pubmed_id_value.strip():
                dropped_pubmed_ids.append(pubmed_id_value.strip())

        if dropped_pubmed_ids:
            logger.info(
                "PubMed open-access enforcement removed records without PMCID",
                extra={
                    "dropped_count": len(dropped_pubmed_ids),
                    "dropped_pubmed_ids": dropped_pubmed_ids,
                    "retained_count": len(retained),
                },
            )

        return retained

    async def _fetch_article_details(
        self,
        article_ids: list[str],
    ) -> list[RawRecord]:
        """
        Fetch detailed PubMed records for given article IDs.

        Args:
            article_ids: List of PubMed article IDs

        Returns:
            List of detailed article records
        """
        if not article_ids:
            return []

        id_str = ",".join(article_ids)

        # Get detailed records using EFetch
        params = {
            "db": "pubmed",
            "id": id_str,
            "rettype": "medline",
            "retmode": "xml",
        }

        response = await self._make_request("GET", "efetch.fcgi", params=params)

        # Parse XML response
        xml_content = response.text
        records = self._parse_pubmed_xml(xml_content)

        # Add source metadata
        for record in records:
            record.update(
                {
                    "pubmed_ids": article_ids,
                    "source": "pubmed",
                    "fetched_at": response.headers.get("date", ""),
                },
            )

        return records

    async def fetch_med13_publications(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Convenience method to fetch MED13-related publications.

        Args:
            **kwargs: Additional search parameters

        Returns:
            List of MED13-related publication records
        """
        records = await self.fetch_data(query="MED13", **kwargs)

        # Filter for highly relevant publications
        relevant_records: list[RawRecord] = []
        for record in records:
            relevance = record.get("med13_relevance")
            if isinstance(relevance, dict) and relevance.get("is_relevant", False):
                relevant_records.append(record)
        return relevant_records

    async def fetch_recent_publications(
        self,
        days_back: int = 365,
        **kwargs: JSONValue,
    ) -> list[RawRecord]:
        """
        Fetch recent publications related to MED13.

        Args:
            days_back: Number of days to look back
            **kwargs: Additional search parameters

        Returns:
            List of recent publication records
        """
        # Calculate date range
        end_date = datetime.now(UTC)
        start_date = end_date - timedelta(days=days_back)

        kwargs["mindate"] = start_date.strftime("%Y/%m/%d")
        kwargs["maxdate"] = end_date.strftime("%Y/%m/%d")

        return await self.fetch_med13_publications(**kwargs)

    @staticmethod
    def _coerce_int(value: JSONValue | None, default: int) -> int:
        """Convert JSON value to integer range."""
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return default

    @staticmethod
    def _coerce_bool(value: JSONValue | None, *, default: bool) -> bool:
        """Convert JSON value to bool."""
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return default
