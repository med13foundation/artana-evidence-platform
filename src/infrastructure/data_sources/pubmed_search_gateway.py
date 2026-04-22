"""PubMed gateway implementations for discovery workflows."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from src.application.services.pubmed_query_builder import PubMedQueryBuilder
from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,  # noqa: TC001
)
from src.domain.services.pubmed_search import (
    PubMedSearchGateway,
    PubMedSearchPayload,
)
from src.infrastructure.data_sources.pubmed_pdf_gateway import SimplePubMedPdfGateway
from src.infrastructure.data_sources.pubmed_search_gateway_ncbi import (
    NCBIPubMedGatewaySettings,
    NCBIPubMedSearchGateway,
    build_ncbi_pubmed_gateway_settings,
    resolve_pubmed_search_backend,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class DeterministicPubMedSearchGateway(PubMedSearchGateway):
    """
    Generates deterministic PubMed search payloads without external API calls.

    This keeps tests hermetic while providing realistic-looking metadata.
    """

    def __init__(self, query_builder: PubMedQueryBuilder | None = None):
        self._query_builder = query_builder or PubMedQueryBuilder()

    async def run_search(
        self,
        parameters: AdvancedQueryParameters,
    ) -> PubMedSearchPayload:
        query = self._query_builder.build_query(parameters)
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        total_results = max(5, min(parameters.max_results, 25))
        article_ids = [
            f"{digest[:12]}{index:03d}" for index in range(1, total_results + 1)
        ]
        preview_records: list[JSONObject] = []
        for idx, article_id in enumerate(article_ids[:10]):
            preview_records.append(
                {
                    "pmid": article_id,
                    "title": f"{parameters.search_term or parameters.gene_symbol or 'MED13'} result {idx + 1}",
                    "query": query,
                    "generated_at": datetime.now(UTC).isoformat(),
                },
            )
        return PubMedSearchPayload(
            article_ids=article_ids,
            total_count=total_results,
            preview_records=preview_records,
        )


def create_pubmed_search_gateway(
    query_builder: PubMedQueryBuilder | None = None,
) -> PubMedSearchGateway:
    """Create the configured PubMed search gateway for the current runtime."""
    backend = resolve_pubmed_search_backend()
    if backend == "deterministic":
        return DeterministicPubMedSearchGateway(query_builder)
    return NCBIPubMedSearchGateway(
        query_builder,
        settings=build_ncbi_pubmed_gateway_settings(),
    )


__all__ = [
    "DeterministicPubMedSearchGateway",
    "NCBIPubMedGatewaySettings",
    "NCBIPubMedSearchGateway",
    "SimplePubMedPdfGateway",
    "create_pubmed_search_gateway",
]
