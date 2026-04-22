"""
PubMed source adapter for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    default_graph_domain_context_for_source_type,
    resolve_graph_domain_context,
)

from src.domain.services.domain_context_resolver import DomainContextResolver
from src.infrastructure.ingestion.types import RawRecord

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.type_definitions.common import JSONObject


class PubMedAdapter:
    """
    Adapts PubMed records to the ingestion pipeline's RawRecord format.
    """

    def to_raw_records(
        self,
        records: Iterable[JSONObject],
        source_id: str,
        *,
        domain_context: str = "clinical",
    ) -> list[RawRecord]:
        """
        Convert legacy PubMed records (dicts) to RawRecord dataclasses.
        """
        domain_context_policy = create_graph_domain_context_policy()
        normalized_domain_context = resolve_graph_domain_context(
            domain_context_policy=domain_context_policy,
            explicit_domain_context=domain_context,
            source_type="pubmed",
            fallback=default_graph_domain_context_for_source_type(
                "pubmed",
                domain_context_policy=domain_context_policy,
            ),
        )
        if normalized_domain_context is None:
            normalized_domain_context = (
                default_graph_domain_context_for_source_type(
                    "pubmed",
                    domain_context_policy=domain_context_policy,
                )
                or DomainContextResolver.GENERAL_DEFAULT_DOMAIN
            )
        raw_records = []
        for record in records:
            # Generate a unique record ID if not present, but use PMID if available for stability
            record_id = str(record.get("pmid", uuid4()))

            raw_records.append(
                RawRecord(
                    source_id=record_id,
                    data=record,
                    metadata={
                        "original_source_id": source_id,
                        "type": "pubmed",
                        "entity_type": "PUBLICATION",
                        "pmid": record.get("pmid"),
                        "doi": record.get("doi"),
                        "domain_context": normalized_domain_context,
                    },
                ),
            )
        return raw_records
