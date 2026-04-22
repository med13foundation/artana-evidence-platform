"""
ClinVar API client for Artana Resource Library.
Fetches genetic variant data from ClinVar database.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.infrastructure.ingest.base_ingestor import BaseIngestor
from src.infrastructure.ingest.clinvar_pages import ClinVarFetchPage, ClinVarSearchPage
from src.infrastructure.validation.api_response_validator import (
    APIResponseValidator,
)

if TYPE_CHECKING:
    from src.type_definitions.common import JSONValue, RawRecord
    from src.type_definitions.external_apis import (
        ClinVarSearchResponse,
        ClinVarVariantResponse,
    )

logger = logging.getLogger(__name__)


class ClinVarIngestor(BaseIngestor):
    """
    ClinVar API client for fetching genetic variant data.

    ClinVar aggregates information about genomic variation and its
    relationship to human health. This ingestor focuses on variants
    related to MED13.
    """

    def __init__(self) -> None:
        super().__init__(
            source_name="clinvar",
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            requests_per_minute=10,  # NCBI limits: 10 requests per second,
            # but be conservative
            timeout_seconds=60,  # NCBI can be slow
        )

    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Fetch ClinVar data for specified gene.

        Args:
            gene_symbol: Gene symbol to search for (default: MED13)
            **kwargs: Additional search parameters

        Returns:
            List of ClinVar records
        """
        page = await self.fetch_page(**kwargs)
        return page.records

    async def fetch_page(self, **kwargs: JSONValue) -> ClinVarFetchPage:
        """Fetch one ClinVar page with explicit cursor metadata."""
        # Step 1: Search for ClinVar records
        gene_symbol_value = kwargs.get("gene_symbol")
        gene_symbol = (
            gene_symbol_value if isinstance(gene_symbol_value, str) else "MED13"
        )

        search_kwargs = dict(kwargs)
        search_kwargs.pop("gene_symbol", None)

        search_page = await self._search_variants(gene_symbol, **search_kwargs)
        variant_ids = list(search_page.variant_ids)
        if not variant_ids:
            return ClinVarFetchPage(
                records=[],
                total_count=search_page.total_count,
                retstart=search_page.retstart,
                retmax=search_page.retmax,
                returned_count=0,
            )

        # Step 2: Fetch detailed records in batches
        all_records: list[RawRecord] = []
        batch_size = 50  # ClinVar API limit

        for i in range(0, len(variant_ids), batch_size):
            batch_ids = variant_ids[i : i + batch_size]
            batch_records = await self._fetch_variant_details(batch_ids)
            all_records.extend(batch_records)

            # Small delay between batches to be respectful
            await asyncio.sleep(0.1)

        return ClinVarFetchPage(
            records=all_records,
            total_count=search_page.total_count,
            retstart=search_page.retstart,
            retmax=search_page.retmax,
            returned_count=search_page.returned_count,
        )

    async def _search_variants(
        self,
        gene_symbol: str,
        **kwargs: JSONValue,
    ) -> ClinVarSearchPage:
        """
        Search ClinVar for variants related to a gene.

        Args:
            gene_symbol: Gene symbol to search for
            **kwargs: Additional search parameters

        Returns:
            List of ClinVar variant IDs
        """
        # Build search query using ClinVar's supported search fields.
        # Note: ClinVar does NOT support [organism] as a filter field.
        query_terms = [f"{gene_symbol}[gene]"]

        # Add additional filters if provided
        variant_type_filter = kwargs.get("variant_type")
        if isinstance(variant_type_filter, str):
            query_terms.append(f"{variant_type_filter}[variant_type]")
        clinical_sig_filter = kwargs.get("clinical_significance")
        if isinstance(clinical_sig_filter, str):
            query_terms.append(f"{clinical_sig_filter}[clinical_significance]")

        query = " AND ".join(query_terms)

        # Use ESearch to find relevant records
        retstart = max(self._coerce_int(kwargs.get("retstart"), 0), 0)
        retmax = max(self._coerce_int(kwargs.get("max_results"), 1000), 1)
        params: dict[str, str | int | float | bool | None] = {
            "db": "clinvar",
            "term": query,
            "retmode": "json",
            "retstart": retstart,
            "retmax": retmax,
            "sort": "relevance",
        }

        response = await self._make_request("GET", "esearch.fcgi", params=params)
        data = self._ensure_raw_record(response.json())

        # Validate response structure with runtime validation
        validation_result = APIResponseValidator.validate_clinvar_search_response(data)

        if not validation_result["is_valid"]:
            logger.warning(
                "ClinVar search response validation failed: %s",
                validation_result["issues"],
            )
            # Fallback to old extraction method
            id_list_raw = data.get("esearchresult", {})
            if isinstance(id_list_raw, dict):
                ids = id_list_raw.get("idlist", [])
                if isinstance(ids, list):
                    return ClinVarSearchPage(
                        variant_ids=[str(vid) for vid in ids],
                        total_count=self._coerce_int(id_list_raw.get("count"), 0),
                        retstart=self._coerce_int(
                            id_list_raw.get("retstart"),
                            retstart,
                        ),
                        retmax=self._coerce_int(id_list_raw.get("retmax"), retmax),
                    )
            return ClinVarSearchPage(
                variant_ids=[],
                total_count=0,
                retstart=retstart,
                retmax=retmax,
            )

        sanitized: ClinVarSearchResponse | None = validation_result["sanitized_data"]
        if sanitized is None:
            logger.warning(
                "ClinVar search response missing sanitized payload; falling back to raw data",
            )
            esearch_fallback = data.get("esearchresult")
            if isinstance(esearch_fallback, dict):
                raw_ids = esearch_fallback.get("idlist", [])
                if isinstance(raw_ids, list):
                    return ClinVarSearchPage(
                        variant_ids=[str(vid) for vid in raw_ids],
                        total_count=self._coerce_int(esearch_fallback.get("count"), 0),
                        retstart=self._coerce_int(
                            esearch_fallback.get("retstart"),
                            retstart,
                        ),
                        retmax=self._coerce_int(
                            esearch_fallback.get("retmax"),
                            retmax,
                        ),
                    )
            return ClinVarSearchPage(
                variant_ids=[],
                total_count=0,
                retstart=retstart,
                retmax=retmax,
            )

        search_result = sanitized["esearchresult"]
        return ClinVarSearchPage(
            variant_ids=[str(vid) for vid in search_result["idlist"]],
            total_count=self._coerce_int(search_result.get("count"), 0),
            retstart=self._coerce_int(search_result.get("retstart"), retstart),
            retmax=self._coerce_int(search_result.get("retmax"), retmax),
        )

    async def _fetch_variant_details(  # noqa: C901, PLR0912
        self,
        variant_ids: list[str],
    ) -> list[RawRecord]:
        """
        Fetch detailed ClinVar records for given variant IDs.

        Args:
            variant_ids: List of ClinVar variant IDs

        Returns:
            List of detailed variant records
        """
        if not variant_ids:
            return []

        # Use ESummary to get basic info, then EFetch for full details
        id_str = ",".join(variant_ids)

        # Get summaries first
        summary_params = {
            "db": "clinvar",
            "id": id_str,
            "retmode": "json",
        }

        response = await self._make_request(
            "GET",
            "esummary.fcgi",
            params=summary_params,
        )
        summary_data = self._ensure_raw_record(response.json())

        # Validate response structure with runtime validation
        validation_result = APIResponseValidator.validate_clinvar_variant_response(
            summary_data,
        )

        if not validation_result["is_valid"]:
            logger.warning(
                "ClinVar variant response validation failed: %s",
                validation_result["issues"],
            )
            # Fallback: raw summary_data used directly below for extraction.
        else:
            sanitized_variant: ClinVarVariantResponse | None = validation_result[
                "sanitized_data"
            ]
            if sanitized_variant is None:
                logger.warning(
                    "ClinVar variant validation returned no sanitized payload despite passing validation",
                )

        records: list[RawRecord] = []
        # Always use raw summary_data for field extraction — the validated
        # sanitized version may strip ClinVar-specific fields like
        # clinical_significance, genes, variation_set, and trait_set.
        result_section = summary_data.get("result")
        if isinstance(result_section, dict):
            for uid in result_section:
                if not isinstance(uid, str) or uid == "uids":
                    continue

                # Extract structured data directly from ESummary JSON.
                variant_data = result_section[uid]
                if isinstance(variant_data, dict):
                    # ClinVar API uses germline_classification (newer) or
                    # clinical_significance (older) for significance data.
                    germline = variant_data.get("germline_classification", {})
                    clin_sig_obj = variant_data.get("clinical_significance", {})
                    sig_source = (
                        germline
                        if isinstance(germline, dict) and germline.get("description")
                        else clin_sig_obj
                    )
                    clin_sig = (
                        sig_source.get("description", "")
                        if isinstance(sig_source, dict)
                        else ""
                    )
                    review_status = (
                        sig_source.get("review_status", "")
                        if isinstance(sig_source, dict)
                        else ""
                    )

                    # Extract conditions from germline trait_set or top-level
                    conditions: list[str] = []
                    trait_sets = (
                        sig_source.get("trait_set", [])
                        if isinstance(sig_source, dict)
                        else []
                    )
                    if isinstance(trait_sets, list):
                        for ts in trait_sets:
                            if isinstance(ts, dict):
                                for tn in (
                                    ts.get("trait_name", [])
                                    if isinstance(ts.get("trait_name"), list)
                                    else [ts.get("trait_name", "")]
                                ):
                                    if tn and isinstance(tn, str):
                                        conditions.append(tn)  # noqa: PERF401

                    genes = variant_data.get("genes", [])
                    gene_sym = (
                        genes[0].get("symbol", "")
                        if genes and isinstance(genes[0], dict)
                        else ""
                    )

                    hgvs: list[str] = []
                    variation_set = variant_data.get("variation_set", [])
                    if isinstance(variation_set, list):
                        for vs in variation_set:
                            if isinstance(vs, dict):
                                vname = vs.get(
                                    "variation_name",
                                    vs.get("cdna_change", ""),
                                )
                                if vname:
                                    hgvs.append(str(vname))

                    records.append(
                        {
                            "clinvar_id": uid,
                            "source": "clinvar",
                            "parsed_data": {
                                "gene_symbol": gene_sym,
                                "variant_type": variant_data.get("obj_type", "unknown"),
                                "clinical_significance": clin_sig or "not provided",
                                "hgvs_notations": hgvs,
                                "conditions": conditions,
                                "review_status": review_status or "unknown",
                            },
                        },
                    )

        return records

    async def _fetch_single_variant(self, variant_id: str) -> RawRecord | None:
        """
        Fetch detailed record for a single ClinVar variant.

        Args:
            variant_id: ClinVar variant ID

        Returns:
            Detailed variant record or None if failed
        """
        params = {
            "db": "clinvar",
            "id": variant_id,
            "rettype": "vcv",
            "retmode": "xml",
        }

        response = await self._make_request("GET", "efetch.fcgi", params=params)

        # Parse XML response (simplified - in production would use proper XML parsing)
        xml_content = response.text

        # For now, return basic structure - in production would parse XML properly
        return {
            "clinvar_id": variant_id,
            "raw_xml": xml_content,
            "source": "clinvar",
            "fetched_at": response.headers.get("date", ""),
            # TODO: Parse XML to extract structured data
            "parsed_data": self._parse_clinvar_xml(xml_content),
        }

    def _parse_clinvar_xml(self, _xml_content: str) -> RawRecord:
        """
        Parse ClinVar XML response into structured data.

        Args:
            xml_content: Raw XML response

        Returns:
            Parsed variant data
        """
        # Simplified XML parsing - in production would use proper XML parser
        # This is a placeholder that would be replaced with actual XML parsing logic
        try:
            # Basic extraction (would be replaced with proper XML parsing)
            parsed: RawRecord = {
                "gene_symbol": "MED13",  # Extract from XML
                "variant_type": "unknown",  # Extract from XML
                "clinical_significance": "unknown",  # Extract from XML
                "hgvs_notations": [],  # Extract from XML
                "conditions": [],  # Extract from XML
                "review_status": "unknown",  # Extract from XML
            }
        except Exception:  # noqa: BLE001
            return {"parsing_error": "Failed to parse ClinVar XML"}
        else:
            return parsed

    async def fetch_med13_variants(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Convenience method to fetch all MED13-related variants.

        Args:
            **kwargs: Additional search parameters

        Returns:
            List of MED13 variant records
        """
        return await self.fetch_data(gene_symbol="MED13", **kwargs)

    async def fetch_by_variant_type(
        self,
        variant_types: list[str],
        **kwargs: JSONValue,
    ) -> list[RawRecord]:
        """
        Fetch variants by specific types.

        Args:
            variant_types: List of variant types to search for
            **kwargs: Additional search parameters

        Returns:
            List of variant records
        """
        all_records: list[RawRecord] = []
        for variant_type in variant_types:
            kwargs_copy: dict[str, JSONValue] = kwargs.copy()
            kwargs_copy["variant_type"] = variant_type
            records = await self.fetch_med13_variants(**kwargs_copy)
            all_records.extend(records)

        return all_records

    async def fetch_by_clinical_significance(
        self,
        significances: list[str],
        **kwargs: JSONValue,
    ) -> list[RawRecord]:
        """
        Fetch variants by clinical significance.

        Args:
            significances: List of clinical significances to search for
            **kwargs: Additional search parameters

        Returns:
            List of variant records
        """
        all_records: list[RawRecord] = []
        for significance in significances:
            kwargs_copy: dict[str, JSONValue] = kwargs.copy()
            kwargs_copy["clinical_significance"] = significance
            records = await self.fetch_med13_variants(**kwargs_copy)
            all_records.extend(records)

        return all_records

    @staticmethod
    def _coerce_int(value: JSONValue | None, default: int) -> int:
        """Convert JSON value to int with fallback."""
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return default
