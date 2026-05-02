from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.claim_relation_models import (
    ClaimRelationReviewStatus,
    ClaimRelationType,
    KernelClaimRelation,
)
from artana_evidence_db.claim_relation_service import KernelClaimRelationService
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.read_model_support import (
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    NullGraphReadModelUpdateDispatcher,
)
from artana_evidence_db.reasoning_path_service import (
    KernelReasoningPathInvalidationService,
)
from artana_evidence_db.relation_claim_models import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
    RelationClaimPersistability,
    RelationClaimPolarity,
    RelationClaimStatus,
    RelationClaimValidationState,
)
from artana_evidence_db.relation_claim_service import (
    CertaintyBand,
    KernelRelationClaimService,
)


@dataclass
class RecordingReadModelDispatcher:
    updates: list[GraphReadModelUpdate] = field(default_factory=list)

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        self.updates.append(update)
        return 1

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        self.updates.extend(updates)
        return len(updates)


@dataclass
class RecordingReasoningPathRepo:
    claim_calls: list[tuple[str, list[str]]] = field(default_factory=list)
    relation_calls: list[tuple[str, list[str]]] = field(default_factory=list)

    def mark_stale_for_claim_ids(
        self,
        *,
        research_space_id: str,
        claim_ids: list[str],
    ) -> int:
        self.claim_calls.append((research_space_id, claim_ids))
        return len(claim_ids)

    def mark_stale_for_claim_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> int:
        self.relation_calls.append((research_space_id, relation_ids))
        return len(relation_ids)


@dataclass
class RecordingReasoningPathInvalidation:
    claim_calls: list[tuple[str, list[str]]] = field(default_factory=list)
    relation_calls: list[tuple[str, list[str]]] = field(default_factory=list)

    def invalidate_for_claim_ids(
        self,
        claim_ids: list[str],
        research_space_id: str,
    ) -> int:
        self.claim_calls.append((research_space_id, claim_ids))
        return len(claim_ids)

    def invalidate_for_claim_relation_ids(
        self,
        relation_ids: list[str],
        research_space_id: str,
    ) -> int:
        self.relation_calls.append((research_space_id, relation_ids))
        return len(relation_ids)


class ClaimRelationRepoStub:
    def __init__(self, relation: KernelClaimRelation) -> None:
        self._relation = relation

    def create(
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
        del (
            research_space_id,
            source_claim_id,
            target_claim_id,
            relation_type,
            agent_run_id,
            source_document_id,
            confidence,
            review_status,
            evidence_summary,
            source_document_ref,
            metadata,
        )
        return self._relation

    def get_by_id(self, _relation_id: str) -> KernelClaimRelation | None:
        return self._relation

    def find_by_claim_ids(
        self,
        _research_space_id: str,
        _claim_ids: list[str],
        *,
        limit: int | None = None,
    ) -> list[KernelClaimRelation]:
        del limit
        return [self._relation]

    def find_by_research_space(
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
        del (
            research_space_id,
            relation_type,
            review_status,
            source_claim_id,
            target_claim_id,
            claim_id,
            limit,
            offset,
        )
        return [self._relation]

    def count_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
    ) -> int:
        del (
            research_space_id,
            relation_type,
            review_status,
            source_claim_id,
            target_claim_id,
            claim_id,
        )
        return 1

    def update_review_status(
        self,
        _relation_id: str,
        *,
        review_status: ClaimRelationReviewStatus,
    ) -> KernelClaimRelation:
        return self._relation.model_copy(update={"review_status": review_status})


class RelationClaimRepoStub:
    def __init__(self, claim: KernelRelationClaim) -> None:
        self._claim = claim

    def get_by_id(self, _claim_id: str) -> KernelRelationClaim | None:
        return self._claim

    def list_by_ids(self, _claim_ids: list[str]) -> list[KernelRelationClaim]:
        return [self._claim]

    def find_by_linked_relation_ids(
        self,
        *,
        research_space_id: str,
        linked_relation_ids: list[str],
    ) -> list[KernelRelationClaim]:
        del research_space_id, linked_relation_ids
        return [self._claim]

    def find_by_research_space(
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
        del (
            research_space_id,
            claim_status,
            assertion_class,
            validation_state,
            persistability,
            polarity,
            source_document_id,
            relation_type,
            linked_relation_id,
            certainty_band,
            limit,
            offset,
        )
        return [self._claim]

    def count_by_research_space(
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
        del (
            research_space_id,
            claim_status,
            assertion_class,
            validation_state,
            persistability,
            polarity,
            source_document_id,
            relation_type,
            linked_relation_id,
            certainty_band,
        )
        return 1

    def find_conflicts_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationConflictSummary]:
        del research_space_id, limit, offset
        return []

    def count_conflicts_by_research_space(self, _research_space_id: str) -> int:
        return 0

    def update_triage_status(
        self,
        _claim_id: str,
        *,
        claim_status: RelationClaimStatus,
        triaged_by: str,
    ) -> KernelRelationClaim:
        del triaged_by
        return self._claim.model_copy(update={"claim_status": claim_status})

    def link_relation(
        self,
        _claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim:
        return self._claim.model_copy(update={"linked_relation_id": linked_relation_id})

    def clear_relation_link(self, _claim_id: str) -> KernelRelationClaim:
        return self._claim.model_copy(update={"linked_relation_id": None})

    def set_system_status(
        self,
        _claim_id: str,
        *,
        claim_status: RelationClaimStatus,
    ) -> KernelRelationClaim:
        return self._claim.model_copy(update={"claim_status": claim_status})

    def create(
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
        del (
            research_space_id,
            source_document_id,
            agent_run_id,
            source_type,
            relation_type,
            target_type,
            source_label,
            target_label,
            confidence,
            validation_state,
            validation_reason,
            persistability,
            assertion_class,
            claim_status,
            polarity,
            claim_text,
            claim_section,
            linked_relation_id,
            source_document_ref,
            source_ref,
            metadata,
        )
        return self._claim

    def get_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str,
    ) -> KernelRelationClaim | None:
        del research_space_id, source_ref
        return self._claim


def _claim_relation() -> KernelClaimRelation:
    return KernelClaimRelation(
        id=uuid4(),
        research_space_id=uuid4(),
        source_claim_id=uuid4(),
        target_claim_id=uuid4(),
        relation_type="SUPPORTS",
        confidence=0.9,
        review_status="ACCEPTED",
        evidence_summary="test",
        created_at=datetime.now(UTC),
    )


def _relation_claim() -> KernelRelationClaim:
    now = datetime.now(UTC)
    return KernelRelationClaim(
        id=uuid4(),
        research_space_id=uuid4(),
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.8,
        validation_state="ALLOWED",
        validation_reason="test",
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        created_at=now,
        updated_at=now,
    )


def test_invalidation_marks_claim_paths_stale_and_updates_mechanism_index() -> None:
    repo = RecordingReasoningPathRepo()
    dispatcher = RecordingReadModelDispatcher()
    service = KernelReasoningPathInvalidationService(
        reasoning_path_repo=repo,
        read_model_update_dispatcher=dispatcher,
    )

    count = service.invalidate_for_claim_ids([" claim-a ", "claim-a", ""], "space-1")

    assert count == 1
    assert repo.claim_calls == [("space-1", ["claim-a"])]
    assert dispatcher.updates == [
        GraphReadModelUpdate(
            model_name="entity_mechanism_paths",
            trigger=GraphReadModelTrigger.CLAIM_CHANGE,
            claim_ids=("claim-a",),
            space_id="space-1",
        ),
    ]


def test_invalidation_marks_claim_relation_paths_stale() -> None:
    repo = RecordingReasoningPathRepo()
    dispatcher = RecordingReadModelDispatcher()
    service = KernelReasoningPathInvalidationService(
        reasoning_path_repo=repo,
        read_model_update_dispatcher=dispatcher,
    )

    count = service.invalidate_for_claim_relation_ids(
        ["relation-a", " relation-a "],
        "space-1",
    )

    assert count == 1
    assert repo.relation_calls == [("space-1", ["relation-a"])]
    assert dispatcher.updates == [
        GraphReadModelUpdate(
            model_name="entity_mechanism_paths",
            trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
            relation_ids=("relation-a",),
            space_id="space-1",
        ),
    ]


def test_claim_relation_service_invalidates_reasoning_paths_on_mutations() -> None:
    relation = _claim_relation()
    invalidation = RecordingReasoningPathInvalidation()
    service = KernelClaimRelationService(
        ClaimRelationRepoStub(relation),
        reasoning_path_invalidation_service=invalidation,
    )

    service.create_claim_relation(
        research_space_id=str(relation.research_space_id),
        source_claim_id=str(relation.source_claim_id),
        target_claim_id=str(relation.target_claim_id),
        relation_type="SUPPORTS",
        agent_run_id=None,
        source_document_id=None,
        confidence=0.9,
        review_status="ACCEPTED",
        evidence_summary="test",
    )
    service.update_review_status(str(relation.id), review_status="REJECTED")

    touched_claim_ids = [
        str(relation.source_claim_id),
        str(relation.target_claim_id),
    ]
    assert invalidation.claim_calls == [
        (str(relation.research_space_id), touched_claim_ids),
        (str(relation.research_space_id), touched_claim_ids),
    ]
    assert invalidation.relation_calls == [
        (str(relation.research_space_id), [str(relation.id)]),
        (str(relation.research_space_id), [str(relation.id)]),
    ]


def test_relation_claim_service_invalidates_reasoning_paths_on_claim_change() -> None:
    claim = _relation_claim()
    invalidation = RecordingReasoningPathInvalidation()
    service = KernelRelationClaimService(
        RelationClaimRepoStub(claim),
        read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
        reasoning_path_invalidation_service=invalidation,
    )

    service.update_claim_status(
        str(claim.id),
        claim_status="RESOLVED",
        triaged_by=str(uuid4()),
    )

    assert invalidation.claim_calls == [
        (str(claim.research_space_id), [str(claim.id)]),
    ]
