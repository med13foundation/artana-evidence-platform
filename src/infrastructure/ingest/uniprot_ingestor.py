"""
UniProt API client for Artana Resource Library.
Fetches protein sequence, function, and annotation data from UniProt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import httpx
from defusedxml import ElementTree

from .base_ingestor import BaseIngestor, HeaderMap, IngestionError, QueryParams
from .uniprot_record_parser_mixin import UniProtRecordParserMixin
from .uniprot_xml_parser_mixin import UniProtXmlParserMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element  # nosec B405

    from src.type_definitions.common import JSONValue, RawRecord

# HTTP status constants
STATUS_TOO_MANY_REQUESTS: int = 429
SERVER_ERROR_MIN_STATUS: int = 500

logger = logging.getLogger(__name__)


class UniProtIngestor(UniProtRecordParserMixin, UniProtXmlParserMixin, BaseIngestor):
    """
    UniProt API client for fetching protein data.

    UniProt provides comprehensive protein sequence and functional information.
    This ingestor focuses on MED13 protein data and related annotations.
    """

    def __init__(self) -> None:
        super().__init__(
            source_name="uniprot",
            base_url="https://www.ebi.ac.uk/proteins/api",  # Try EBI Proteins API
            requests_per_minute=30,  # UniProt allows up to 200 requests/minute
            # for programmatic access
            timeout_seconds=60,  # Protein data can be large
        )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: QueryParams | None = None,
        headers: HeaderMap | None = None,
    ) -> httpx.Response:
        """
        Override base _make_request to handle UniProt's redirect issues.
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit token
                await self.rate_limiter.wait_for_token()

                # Use a fresh client for each request to avoid redirect issues
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout_seconds),
                    follow_redirects=False,  # Don't follow redirects for UniProt
                    headers={
                        "User-Agent": "Artana-Resource-Library/1.0 (research@artana.org)",
                    },
                ) as temp_client:
                    response = await temp_client.request(
                        method,
                        url,
                        params=params,
                        headers=headers,
                    )

                    # Check for rate limiting
                    if response.status_code == STATUS_TOO_MANY_REQUESTS:
                        # Exponential backoff for rate limiting
                        wait_time = 2**attempt
                        await asyncio.sleep(wait_time)
                        continue

                    response.raise_for_status()
                    return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= SERVER_ERROR_MIN_STATUS and (
                    attempt < self.max_retries - 1
                ):
                    # Server error - retry
                    await asyncio.sleep(2**attempt)
                    continue
                message = f"HTTP {e.response.status_code}: {e.response.text}"
                raise IngestionError(message, self.source_name) from e

            except Exception as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                message = f"Request failed after {self.max_retries} attempts: {e!s}"
                raise IngestionError(message, self.source_name) from e

        final_message = f"Request failed after {self.max_retries} attempts"
        raise IngestionError(final_message, self.source_name)

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Fetch UniProt data for specified protein query.

        Args:
            query: Protein search query (default: MED13)
            **kwargs: Additional search parameters

        Returns:
            List of UniProt protein records
        """
        # Step 1: Search for proteins
        query_value = kwargs.get("query")
        query = query_value if isinstance(query_value, str) else "MED13"

        # Remove 'query' from kwargs to avoid duplicate argument error
        search_kwargs = {k: v for k, v in kwargs.items() if k != "query"}
        protein_ids = await self._search_proteins(query, **search_kwargs)
        if not protein_ids:
            return []

        # Step 2: Fetch detailed records
        all_records = []
        batch_size = 25  # UniProt batch limit

        for i in range(0, len(protein_ids), batch_size):
            batch_ids = protein_ids[i : i + batch_size]
            batch_records = await self._fetch_protein_details(batch_ids)
            all_records.extend(batch_records)

            # Small delay between batches
            await asyncio.sleep(0.1)

        return all_records

    async def _search_proteins(self, query: str, **kwargs: JSONValue) -> list[str]:
        """
        Search UniProt for proteins matching the query.

        Args:
            query: Protein search query
            **kwargs: Additional search parameters

        Returns:
            List of UniProt accession numbers
        """
        # Build search query - start simple
        # UniProt might not support complex queries with AND
        full_query = query  # Just use the basic query for now

        raw_size = kwargs.get("max_results", 50)
        size = 50
        if isinstance(raw_size, int | float) or (
            isinstance(raw_size, str) and raw_size.isdigit()
        ):
            size = int(raw_size)
        if size <= 0:
            size = 50
        params: dict[str, str | int | float | bool | None] = {
            "protein": full_query,  # EBI uses 'protein' parameter
            "size": size,
        }

        response = await self._make_request("GET", "/proteins", params=params)
        response_text = response.text

        # Parse XML response to extract accession numbers
        try:
            root = ElementTree.fromstring(response_text)

            # Extract accession numbers from XML
            accession_numbers = []
            ns = {
                "u": "http://uniprot.org/uniprot",
                "u2": "https://uniprot.org/uniprot",
            }

            # Try explicit namespaces
            for ns_name in ["u", "u2"]:
                accession_numbers.extend(
                    [
                        entry.text.strip()
                        for entry in root.findall(f".//{ns_name}:accession", ns)
                        if entry.text
                    ],
                )

        except Exception:  # noqa: BLE001
            accession_numbers = [
                line.strip() for line in response_text.splitlines() if line.strip()
            ]

        # Remove duplicates and limit results
        return list(set(accession_numbers))[:size]

    async def _fetch_protein_details(  # noqa: C901
        self,
        accession_numbers: list[str],
    ) -> list[RawRecord]:
        """
        Fetch detailed UniProt records for given accession numbers.

        Args:
            accession_numbers: List of UniProt accession numbers

        Returns:
            List of detailed protein records
        """
        if not accession_numbers:
            return []

        # Join accessions for batch request
        accessions = ",".join(accession_numbers)

        params = {"accession": accessions}

        response = await self._make_request("GET", "/proteins", params=params)
        records: list[RawRecord] = []

        # Try JSON parsing first
        try:
            data = self._coerce_json_value(response.json())
        except json.JSONDecodeError:
            data = None

        if isinstance(data, dict):
            for entry in data.get("results", []):
                if isinstance(entry, dict):
                    parsed = self._parse_uniprot_record(entry)
                    parsed.update(
                        {
                            "source": "uniprot",
                            "fetched_at": response.headers.get("date", ""),
                            "accession_numbers": accession_numbers,
                        },
                    )
                    records.append(parsed)
            if records:
                return records

        # Fallback to XML parsing
        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            return records

        ns = {"u": "http://uniprot.org/uniprot", "u2": "https://uniprot.org/uniprot"}

        # Try finding entries with different namespace approaches
        entries: list[Element] = []
        for ns_name in ["u", "u2"]:
            entries = root.findall(f".//{ns_name}:entry", ns)
            if entries:
                break

        for entry in entries:
            record = self._parse_uniprot_record(self._parse_xml_entry(entry))
            record.update(
                {
                    "source": "uniprot",
                    "fetched_at": response.headers.get("date", ""),
                    "accession_numbers": accession_numbers,
                },
            )
            records.append(record)

        return records

    async def fetch_med13_protein(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Convenience method to fetch MED13 protein data.

        Args:
            **kwargs: Additional search parameters

        Returns:
            List of MED13 protein records
        """
        return await self.fetch_data(query="MED13", **kwargs)

    async def fetch_protein_by_accession(
        self,
        accession: str,
    ) -> RawRecord | None:
        """
        Fetch specific protein by UniProt accession number.

        Args:
            accession: UniProt accession number

        Returns:
            Protein record or None if not found
        """
        records = await self._fetch_protein_details([accession])
        if records:
            return records[0]
        return None

    async def fetch_protein_sequence(self, accession: str) -> str | None:
        """
        Fetch protein sequence for given accession.

        Args:
            accession: UniProt accession number

        Returns:
            Protein sequence as string or None if not found
        """
        try:
            response = await self._make_request("GET", f"/uniprotkb/{accession}.fasta")
            # Parse FASTA format (skip header line)
            lines = response.text.strip().split("\n")
            if lines and lines[0].startswith(">"):
                return "".join(lines[1:])  # Join sequence lines
        except Exception:
            logger.exception("Failed to fetch protein sequence")
        return None
