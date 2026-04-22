"""Application service for claim-backed canonical relation projection lineage."""

from __future__ import annotations

from typing import Protocol

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.relation_projection_source_model import (
    KernelRelationProjectionSource,
    RelationProjectionOrigin,
)


class RelationProjectionSourceRepositoryLike(Protocol):
    """Minimal repository contract required for projection-lineage workflows."""

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
        projection_origin: RelationProjectionOrigin,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationProjectionSource:
        """Create or return one claim-backed projection lineage row."""

    def find_by_relation_id(
        self,
        relation_id: str,
    ) -> list[KernelRelationProjectionSource]:
        """List lineage rows for one canonical relation."""

    def count_by_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> dict[str, int]:
        """Count lineage rows per canonical relation."""


class KernelRelationProjectionSourceService:
    """Application service for claim-backed canonical relation lineage."""

    def __init__(
        self,
        relation_projection_repo: RelationProjectionSourceRepositoryLike,
    ) -> None:
        self._projection_sources = relation_projection_repo

    def create_projection_source(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
        projection_origin: RelationProjectionOrigin,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationProjectionSource:
        """Create or return one claim-backed projection lineage row."""
        return self._projection_sources.create(
            research_space_id=research_space_id,
            relation_id=relation_id,
            claim_id=claim_id,
            projection_origin=projection_origin,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            agent_run_id=agent_run_id,
            metadata=metadata,
        )

    def list_for_relation(
        self,
        relation_id: str,
    ) -> list[KernelRelationProjectionSource]:
        """List claim lineage rows for one canonical relation."""
        return self._projection_sources.find_by_relation_id(relation_id)

    def count_by_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> dict[str, int]:
        """Count projection-lineage rows per canonical relation."""
        return self._projection_sources.count_by_relation_ids(
            research_space_id=research_space_id,
            relation_ids=relation_ids,
        )


__all__ = ["KernelRelationProjectionSourceService"]
