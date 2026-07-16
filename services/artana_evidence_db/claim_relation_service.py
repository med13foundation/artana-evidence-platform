"""Application service for claim-to-claim relation graph workflows."""

from __future__ import annotations

from typing import Protocol

from artana_evidence_db.claim_relation_models import (
    ClaimRelationReviewStatus,
    ClaimRelationType,
    KernelClaimRelation,
)
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.graph_api_schemas.governance.authorship import (
    GraphWriteAuthorship,
)
from artana_evidence_db.relation_claim_models import KernelRelationClaim
from artana_evidence_db.validation.ai_persistence_quarantine import (
    AIPersistenceQuarantineError,
    GraphAIPersistenceQuarantinePolicy,
)

_AI_PERSISTENCE_QUARANTINE = GraphAIPersistenceQuarantinePolicy()


class ReasoningPathInvalidationServiceLike(Protocol):
    """Minimal reasoning-path invalidation surface for claim-relation mutations."""

    def invalidate_for_claim_ids(
        self,
        claim_ids: list[str],
        research_space_id: str,
    ) -> int: ...

    def invalidate_for_claim_relation_ids(
        self,
        relation_ids: list[str],
        research_space_id: str,
    ) -> int: ...


class ClaimRelationRepositoryLike(Protocol):
    """Minimal repository contract required for claim-relation workflows."""

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_claim_id: str,
        target_claim_id: str,
        relation_type: ClaimRelationType,
        agent_run_id: str | None,
        source_document_id: str | None,
        confidence: float,
        review_status: ClaimRelationReviewStatus,
        evidence_summary: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelClaimRelation:
        """Create one claim-relation row."""

    def get_by_id(self, relation_id: str) -> KernelClaimRelation | None:
        """Fetch one claim relation by ID."""

    def find_by_claim_ids(
        self,
        research_space_id: str,
        claim_ids: list[str],
        *,
        limit: int | None = None,
    ) -> list[KernelClaimRelation]:
        """List claim relations touching any provided claim IDs."""

    def find_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimRelation]:
        """List claim relations in one research space."""

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
    ) -> int:
        """Count claim relations in one research space."""

    def update_review_status(
        self,
        relation_id: str,
        *,
        review_status: ClaimRelationReviewStatus,
    ) -> KernelClaimRelation:
        """Update review status for one claim-relation row."""


class RelationClaimRepositoryLike(Protocol):
    """Minimal claim lookup surface for claim-edge governance."""

    def get_by_id(self, claim_id: str) -> KernelRelationClaim | None:
        """Fetch one endpoint claim by ID."""


class KernelClaimRelationService:
    """Application service for claim-to-claim relation graph workflows."""

    def __init__(
        self,
        claim_relation_repo: ClaimRelationRepositoryLike,
        *,
        relation_claim_repo: RelationClaimRepositoryLike,
        reasoning_path_invalidation_service: ReasoningPathInvalidationServiceLike,
    ) -> None:
        self._claim_relations = claim_relation_repo
        self._relation_claims = relation_claim_repo
        self._reasoning_path_invalidation = reasoning_path_invalidation_service

    def create_claim_relation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_claim_id: str,
        target_claim_id: str,
        relation_type: ClaimRelationType,
        agent_run_id: str | None,
        source_document_id: str | None,
        confidence: float,
        review_status: ClaimRelationReviewStatus,
        evidence_summary: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
        authorship: GraphWriteAuthorship = "MANUAL",
    ) -> KernelClaimRelation:
        """Create one claim relation row."""
        normalized_metadata = metadata or {}
        violation = _AI_PERSISTENCE_QUARANTINE.violation_for_authorship_signals(
            authorship=authorship,
            agent_run_id=agent_run_id,
            metadata=normalized_metadata,
        )
        if violation is not None:
            raise AIPersistenceQuarantineError(violation)
        self._ensure_endpoint_claims_mutation_allowed(
            research_space_id=research_space_id,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
        )
        relation = self._claim_relations.create(
            research_space_id=research_space_id,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            relation_type=relation_type,
            agent_run_id=agent_run_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            confidence=confidence,
            review_status=review_status,
            evidence_summary=evidence_summary,
            metadata=normalized_metadata,
        )
        self._invalidate_relation(relation)
        return relation

    def get_claim_relation(self, relation_id: str) -> KernelClaimRelation | None:
        """Fetch one claim relation by ID."""
        return self._claim_relations.get_by_id(relation_id)

    def _ensure_endpoint_claims_mutation_allowed(
        self,
        *,
        research_space_id: str,
        source_claim_id: str,
        target_claim_id: str,
    ) -> None:
        source_claim = self._relation_claims.get_by_id(source_claim_id)
        target_claim = self._relation_claims.get_by_id(target_claim_id)
        if (
            source_claim is None
            or target_claim is None
            or str(source_claim.research_space_id) != research_space_id
            or str(target_claim.research_space_id) != research_space_id
        ):
            msg = "Source or target claim not found in research space"
            raise ValueError(msg)
        for claim in (source_claim, target_claim):
            violation = _AI_PERSISTENCE_QUARANTINE.violation_for_claim(claim)
            if violation is not None:
                raise AIPersistenceQuarantineError(violation)

    def list_by_claim_ids(
        self,
        research_space_id: str,
        claim_ids: list[str],
        *,
        limit: int | None = None,
    ) -> list[KernelClaimRelation]:
        """List claim relations touching any of the provided claim IDs."""
        return self._claim_relations.find_by_claim_ids(
            research_space_id,
            claim_ids,
            limit=limit,
        )

    def list_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimRelation]:
        """List claim relations in one research space."""
        return self._claim_relations.find_by_research_space(
            research_space_id,
            relation_type=relation_type,
            review_status=review_status,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            claim_id=claim_id,
            limit=limit,
            offset=offset,
        )

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
    ) -> int:
        """Count claim relations in one research space."""
        return self._claim_relations.count_by_research_space(
            research_space_id,
            relation_type=relation_type,
            review_status=review_status,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            claim_id=claim_id,
        )

    def update_review_status(
        self,
        relation_id: str,
        *,
        review_status: ClaimRelationReviewStatus,
    ) -> KernelClaimRelation:
        """Update review status for one claim relation row."""
        existing = self._claim_relations.get_by_id(relation_id)
        if existing is not None:
            violation = _AI_PERSISTENCE_QUARANTINE.violation_for_claim_relation(
                existing,
            )
            if violation is not None:
                raise AIPersistenceQuarantineError(violation)
            if review_status == "ACCEPTED":
                self._ensure_endpoint_claims_mutation_allowed(
                    research_space_id=str(existing.research_space_id),
                    source_claim_id=str(existing.source_claim_id),
                    target_claim_id=str(existing.target_claim_id),
                )
        relation = self._claim_relations.update_review_status(
            relation_id,
            review_status=review_status,
        )
        self._invalidate_relation(relation)
        return relation

    def _invalidate_relation(self, relation: KernelClaimRelation) -> None:
        research_space_id = str(relation.research_space_id)
        self._reasoning_path_invalidation.invalidate_for_claim_ids(
            [str(relation.source_claim_id), str(relation.target_claim_id)],
            research_space_id,
        )
        self._reasoning_path_invalidation.invalidate_for_claim_relation_ids(
            [str(relation.id)],
            research_space_id,
        )


__all__ = ["KernelClaimRelationService"]
