"""
Provenance tracker for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_db.kernel_repositories import (
        ProvenanceRepository,
    )

    from src.type_definitions.common import JSONObject


class ProvenanceTracker:
    """
    Tracks provenance of ingested data.
    """

    def __init__(self, provenance_repository: ProvenanceRepository) -> None:
        self.provenance_repo = provenance_repository

    def track_ingestion(  # noqa: PLR0913
        self,
        research_space_id: str,
        source_type: str,
        *,
        source_ref: str | None = None,
        extraction_run_id: str | None = None,
        mapping_method: str | None = None,
        mapping_confidence: float | None = None,
        agent_model: str | None = None,
        raw_input: JSONObject | None = None,
    ) -> str:
        """
        Create a provenance record for an ingestion event.
        Returns the ID of the created record.
        """
        provenance = self.provenance_repo.create(
            research_space_id=research_space_id,
            source_type=source_type,
            source_ref=source_ref,
            extraction_run_id=extraction_run_id,
            mapping_method=mapping_method,
            mapping_confidence=mapping_confidence,
            agent_model=agent_model,
            raw_input=raw_input,
        )
        return str(provenance.id)
