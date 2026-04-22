"""Service-local invariant checks for claim-backed relation projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import KernelRelation
    from artana_evidence_db.kernel_domain_ports import (
        KernelRelationProjectionSourceRepository,
    )


class OrphanCanonicalRelationError(ValueError):
    """Raised when a canonical relation exists without projection lineage."""


class KernelRelationProjectionInvariantService:
    """Application service for claim-backed canonical relation invariants."""

    def __init__(
        self,
        relation_projection_repo: KernelRelationProjectionSourceRepository,
    ) -> None:
        self._projection_sources = relation_projection_repo

    def list_orphan_relations(
        self,
        *,
        space_id: str | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        """List canonical relations that do not have projection lineage."""
        return self._projection_sources.list_orphan_relations(
            research_space_id=space_id,
            limit=limit,
            offset=offset,
        )

    def count_orphan_relations(
        self,
        *,
        space_id: str | None,
    ) -> int:
        """Count canonical relations that do not have projection lineage."""
        return self._projection_sources.count_orphan_relations(
            research_space_id=space_id,
        )

    def assert_no_orphan_relations_for_write(
        self,
        *,
        relation_id: str,
        research_space_id: str,
    ) -> None:
        """Ensure one canonical relation has at least one projection lineage row."""
        if self._projection_sources.has_projection_for_relation(
            research_space_id=research_space_id,
            relation_id=relation_id,
        ):
            return
        msg = (
            "Canonical relation write completed without claim-backed projection "
            f"lineage (relation_id={relation_id}, research_space_id={research_space_id})."
        )
        raise OrphanCanonicalRelationError(msg)


__all__ = [
    "KernelRelationProjectionInvariantService",
    "OrphanCanonicalRelationError",
]
