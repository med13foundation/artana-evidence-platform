"""Application service for canonical graph relations."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from artana_evidence_db.graph_core_models import (
    KernelEntity,
    KernelMechanisticGap,
    KernelReachabilityGap,
    KernelRelation,
)

_ALLOWED_CURATION_STATUSES = frozenset(
    {"DRAFT", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETRACTED"},
)


class EntityRepositoryLike(Protocol):
    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        """Return one entity by ID."""


class RelationRepositoryLike(Protocol):
    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        """Update relation curation state."""

    def get_by_id(
        self,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        """Return one relation by ID."""

    def find_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        """Traverse the relation neighborhood for one entity."""

    def find_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        max_source_family_count: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """List relations in one research space."""

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        max_source_family_count: int | None = None,
    ) -> int:
        """Count relations in one research space."""

    def find_reachability_gaps(
        self,
        seed_entity_id: str,
        *,
        max_path_length: int = 2,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReachabilityGap]:
        """Find entities reachable via multi-hop paths but with no direct edge."""

    def find_mechanistic_gaps(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_types: list[str] | None = None,
        source_entity_type: str | None = None,
        target_entity_type: str | None = None,
        intermediate_entity_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        max_hops: int = 2,
    ) -> list[KernelMechanisticGap]:
        """Find direct relations that lack an N-hop mechanism bridge (default 2)."""

    def delete(self, relation_id: str) -> bool:
        """Delete one relation."""

    def delete_by_provenance(self, provenance_id: str) -> int:
        """Delete relations by provenance."""


class KernelRelationService:
    """Read and manage canonical graph relations."""

    def __init__(
        self,
        relation_repo: RelationRepositoryLike,
        entity_repo: EntityRepositoryLike | None = None,
        *_unused_dependencies: object,
    ) -> None:
        self._relations = relation_repo
        self._entities = entity_repo

    def update_curation_status(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        """Update the curation status of a relation."""
        normalized_status = curation_status.strip().upper()
        if normalized_status not in _ALLOWED_CURATION_STATUSES:
            msg = "Invalid relation curation_status. Expected one of: " + ", ".join(
                sorted(_ALLOWED_CURATION_STATUSES),
            )
            raise ValueError(msg)
        return self._relations.update_curation(
            relation_id,
            curation_status=normalized_status,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
        )

    def get_relation(
        self,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        return self._relations.get_by_id(
            relation_id,
            claim_backed_only=claim_backed_only,
        )

    def get_neighborhood(
        self,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        return self._relations.find_neighborhood(
            entity_id,
            depth=depth,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
            limit=limit,
        )

    def get_neighborhood_in_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        if self._entities is None:
            msg = "Entity repository is required for in-space neighborhood traversal"
            raise ValueError(msg)
        entity = self._entities.get_by_id(entity_id)
        if entity is None:
            msg = f"Entity {entity_id} not found"
            raise ValueError(msg)
        if str(entity.research_space_id) != str(research_space_id):
            msg = f"Entity {entity_id} is not in research space {research_space_id}"
            raise ValueError(msg)

        relations = self._relations.find_neighborhood(
            entity_id,
            depth=depth,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
            limit=limit,
        )
        return [
            relation
            for relation in relations
            if str(relation.research_space_id) == str(research_space_id)
        ]

    def list_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        max_source_family_count: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        return self._relations.find_by_research_space(
            research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
            max_source_family_count=max_source_family_count,
            limit=limit,
            offset=offset,
        )

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        max_source_family_count: int | None = None,
    ) -> int:
        return self._relations.count_by_research_space(
            research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
            max_source_family_count=max_source_family_count,
        )

    def find_reachability_gaps(
        self,
        seed_entity_id: str,
        *,
        max_path_length: int = 2,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReachabilityGap]:
        """Find entities reachable via multi-hop paths but with no direct edge."""
        return self._relations.find_reachability_gaps(
            seed_entity_id,
            max_path_length=max_path_length,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
            limit=limit,
            offset=offset,
        )

    def find_mechanistic_gaps(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_types: list[str] | None = None,
        source_entity_type: str | None = None,
        target_entity_type: str | None = None,
        intermediate_entity_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        max_hops: int = 2,
    ) -> list[KernelMechanisticGap]:
        """Find direct relations that lack an N-hop mechanism bridge (default 2)."""
        return self._relations.find_mechanistic_gaps(
            research_space_id,
            relation_types=relation_types,
            source_entity_type=source_entity_type,
            target_entity_type=target_entity_type,
            intermediate_entity_types=intermediate_entity_types,
            claim_backed_only=claim_backed_only,
            limit=limit,
            offset=offset,
            max_hops=max_hops,
        )

    def delete_relation(self, relation_id: str) -> bool:
        return self._relations.delete(relation_id)

    def rollback_provenance(self, provenance_id: str) -> int:
        return self._relations.delete_by_provenance(provenance_id)


__all__ = ["KernelRelationService"]
