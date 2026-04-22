"""Application service for provenance tracking."""

from __future__ import annotations

from typing import Protocol

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.graph_core_models import KernelProvenanceRecord


class ProvenanceRepositoryLike(Protocol):
    """Minimal repository contract required for provenance workflows."""

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        source_ref: str | None = None,
        extraction_run_id: str | None = None,
        mapping_method: str | None = None,
        mapping_confidence: float | None = None,
        agent_model: str | None = None,
        raw_input: JSONObject | None = None,
    ) -> KernelProvenanceRecord:
        """Create a provenance record for one data-ingestion batch."""

    def get_by_id(self, provenance_id: str) -> KernelProvenanceRecord | None:
        """Return one provenance record by ID."""

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        source_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelProvenanceRecord]:
        """List provenance records for one research space."""

    def find_by_extraction_run(
        self,
        extraction_run_id: str,
    ) -> list[KernelProvenanceRecord]:
        """List provenance records for one extraction run."""


class ProvenanceService:
    """Application service for provenance tracking."""

    def __init__(self, provenance_repo: ProvenanceRepositoryLike) -> None:
        self._provenance = provenance_repo

    def create_provenance(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        source_ref: str | None = None,
        extraction_run_id: str | None = None,
        mapping_method: str | None = None,
        mapping_confidence: float | None = None,
        agent_model: str | None = None,
        raw_input: JSONObject | None = None,
    ) -> KernelProvenanceRecord:
        """Create a provenance record for a data ingestion batch."""
        return self._provenance.create(
            research_space_id=research_space_id,
            source_type=source_type,
            source_ref=source_ref,
            extraction_run_id=extraction_run_id,
            mapping_method=mapping_method,
            mapping_confidence=mapping_confidence,
            agent_model=agent_model,
            raw_input=raw_input,
        )

    def get_provenance(self, provenance_id: str) -> KernelProvenanceRecord | None:
        """Retrieve a single provenance record."""
        return self._provenance.get_by_id(provenance_id)

    def list_by_research_space(
        self,
        research_space_id: str,
        *,
        source_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelProvenanceRecord]:
        """List provenance records for a research space."""
        return self._provenance.find_by_research_space(
            research_space_id,
            source_type=source_type,
            limit=limit,
            offset=offset,
        )

    def find_by_extraction_run(
        self,
        extraction_run_id: str,
    ) -> list[KernelProvenanceRecord]:
        """Find provenance records for an extraction run."""
        return self._provenance.find_by_extraction_run(extraction_run_id)


__all__ = ["ProvenanceService"]
