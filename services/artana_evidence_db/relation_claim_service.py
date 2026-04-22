"""Application service for relation-claim curation workflows."""

from __future__ import annotations

from typing import Literal, Protocol

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.read_model_support import (
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    GraphReadModelUpdateDispatcher,
)
from artana_evidence_db.relation_claim_models import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
    RelationClaimPersistability,
    RelationClaimPolarity,
    RelationClaimStatus,
    RelationClaimValidationState,
)

CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]


class RelationClaimRepositoryLike(Protocol):
    """Minimal repository contract required for relation-claim workflows."""

    def get_by_id(self, claim_id: str) -> KernelRelationClaim | None: ...

    def list_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]: ...

    def find_by_linked_relation_ids(
        self,
        *,
        research_space_id: str,
        linked_relation_ids: list[str],
    ) -> list[KernelRelationClaim]: ...

    def find_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationClaim]: ...

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
    ) -> int: ...

    def find_conflicts_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationConflictSummary]: ...

    def count_conflicts_by_research_space(self, research_space_id: str) -> int: ...

    def update_triage_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
        triaged_by: str,
    ) -> KernelRelationClaim: ...

    def link_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim: ...

    def clear_relation_link(self, claim_id: str) -> KernelRelationClaim: ...

    def set_system_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
    ) -> KernelRelationClaim: ...

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        assertion_class: str = "SOURCE_BACKED",
        claim_status: RelationClaimStatus = "OPEN",
        polarity: RelationClaimPolarity = "UNCERTAIN",
        claim_text: str | None = None,
        claim_section: str | None = None,
        linked_relation_id: str | None = None,
        source_document_ref: str | None = None,
        source_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationClaim: ...

    def get_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str,
    ) -> KernelRelationClaim | None: ...


class KernelRelationClaimService:
    """Application service for relation-claim curation workflows."""

    def __init__(
        self,
        relation_claim_repo: RelationClaimRepositoryLike,
        *,
        read_model_update_dispatcher: GraphReadModelUpdateDispatcher,
    ) -> None:
        self._claims = relation_claim_repo
        self._read_model_updates = read_model_update_dispatcher

    def get_claim(self, claim_id: str) -> KernelRelationClaim | None:
        return self._claims.get_by_id(claim_id)

    def list_claims_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]:
        return self._claims.list_by_ids(claim_ids)

    def get_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str,
    ) -> KernelRelationClaim | None:
        return self._claims.get_by_source_ref(
            research_space_id=research_space_id,
            source_ref=source_ref,
        )

    def list_by_linked_relation_ids(
        self,
        *,
        research_space_id: str,
        linked_relation_ids: list[str],
    ) -> list[KernelRelationClaim]:
        return self._claims.find_by_linked_relation_ids(
            research_space_id=research_space_id,
            linked_relation_ids=linked_relation_ids,
        )

    def list_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationClaim]:
        return self._claims.find_by_research_space(
            research_space_id,
            claim_status=claim_status,
            assertion_class=assertion_class,
            validation_state=validation_state,
            persistability=persistability,
            polarity=polarity,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
            limit=limit,
            offset=offset,
        )

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
    ) -> int:
        return self._claims.count_by_research_space(
            research_space_id,
            claim_status=claim_status,
            assertion_class=assertion_class,
            validation_state=validation_state,
            persistability=persistability,
            polarity=polarity,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
        )

    def list_conflicts_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationConflictSummary]:
        return self._claims.find_conflicts_by_research_space(
            research_space_id,
            limit=limit,
            offset=offset,
        )

    def count_conflicts_by_research_space(self, research_space_id: str) -> int:
        return self._claims.count_conflicts_by_research_space(research_space_id)

    def update_claim_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
        triaged_by: str,
    ) -> KernelRelationClaim:
        claim = self._claims.update_triage_status(
            claim_id,
            claim_status=claim_status,
            triaged_by=triaged_by,
        )
        self._dispatch_claim_change(claim)
        return claim

    def link_claim_to_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim:
        claim = self._claims.link_relation(
            claim_id,
            linked_relation_id=linked_relation_id,
        )
        self._dispatch_claim_change(claim)
        return claim

    def clear_claim_relation_link(
        self,
        claim_id: str,
    ) -> KernelRelationClaim:
        claim = self._claims.clear_relation_link(claim_id)
        self._dispatch_claim_change(claim)
        return claim

    def set_system_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
    ) -> KernelRelationClaim:
        claim = self._claims.set_system_status(
            claim_id,
            claim_status=claim_status,
        )
        self._dispatch_claim_change(claim)
        return claim

    def create_claim(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        assertion_class: str = "SOURCE_BACKED",
        claim_status: RelationClaimStatus = "OPEN",
        polarity: RelationClaimPolarity = "UNCERTAIN",
        claim_text: str | None = None,
        claim_section: str | None = None,
        linked_relation_id: str | None = None,
        source_document_ref: str | None = None,
        source_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationClaim:
        claim = self._claims.create(
            research_space_id=research_space_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            source_ref=source_ref,
            agent_run_id=agent_run_id,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            source_label=source_label,
            target_label=target_label,
            confidence=confidence,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            assertion_class=assertion_class,
            claim_status=claim_status,
            polarity=polarity,
            claim_text=claim_text,
            claim_section=claim_section,
            linked_relation_id=linked_relation_id,
            metadata=metadata,
        )
        self._dispatch_claim_change(claim)
        return claim

    def create_hypothesis_claim(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        claim_text: str | None,
        metadata: JSONObject | None = None,
        source_document_id: str | None = None,
        source_document_ref: str | None = None,
        source_ref: str | None = None,
        agent_run_id: str | None = None,
        claim_status: RelationClaimStatus = "OPEN",
    ) -> KernelRelationClaim:
        claim = self._claims.create(
            research_space_id=research_space_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            source_ref=source_ref,
            agent_run_id=agent_run_id,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            source_label=source_label,
            target_label=target_label,
            confidence=confidence,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            assertion_class="COMPUTATIONAL",
            claim_status=claim_status,
            polarity="HYPOTHESIS",
            claim_text=claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata=metadata,
        )
        self._dispatch_claim_change(claim)
        return claim

    def create_curated_claim(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        claim_text: str | None,
        metadata: JSONObject | None = None,
        source_document_id: str | None = None,
        source_document_ref: str | None = None,
        source_ref: str | None = None,
        agent_run_id: str | None = None,
        claim_status: RelationClaimStatus = "OPEN",
        polarity: RelationClaimPolarity = "SUPPORT",
    ) -> KernelRelationClaim:
        """Create an expert-curated relation claim."""
        claim = self._claims.create(
            research_space_id=research_space_id,
            source_document_id=source_document_id,
            source_document_ref=source_document_ref,
            source_ref=source_ref,
            agent_run_id=agent_run_id,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            source_label=source_label,
            target_label=target_label,
            confidence=confidence,
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            assertion_class="CURATED",
            claim_status=claim_status,
            polarity=polarity,
            claim_text=claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata=metadata,
        )
        self._dispatch_claim_change(claim)
        return claim

    def _dispatch_claim_change(self, claim: KernelRelationClaim) -> None:
        self._read_model_updates.dispatch(
            GraphReadModelUpdate(
                model_name="entity_claim_summary",
                trigger=GraphReadModelTrigger.CLAIM_CHANGE,
                claim_ids=(str(claim.id),),
                relation_ids=(
                    (str(claim.linked_relation_id),)
                    if claim.linked_relation_id is not None
                    else ()
                ),
                space_id=str(claim.research_space_id),
            ),
        )

    @staticmethod
    def normalize_status_alias(
        value: str,
    ) -> Literal["OPEN", "NEEDS_MAPPING", "REJECTED", "RESOLVED"]:
        normalized = value.strip().upper()
        if normalized == "OPEN":
            return "OPEN"
        if normalized == "NEEDS_MAPPING":
            return "NEEDS_MAPPING"
        if normalized == "REJECTED":
            return "REJECTED"
        if normalized == "RESOLVED":
            return "RESOLVED"
        msg = f"Unsupported claim_status '{value}'"
        raise ValueError(msg)


__all__ = ["CertaintyBand", "KernelRelationClaimService"]
