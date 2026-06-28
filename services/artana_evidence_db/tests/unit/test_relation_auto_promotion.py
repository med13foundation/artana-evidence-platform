"""Regression tests for governed relation auto-promotion."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from artana_evidence_db.graph_core_models import KernelRelation, RelationEvidenceWrite
from artana_evidence_db.kernel_claim_models import RelationClaimModel
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
)
from artana_evidence_db.kernel_entity_models import GraphEntityModel
from artana_evidence_db.relation_autopromotion_policy import AutoPromotionPolicy
from artana_evidence_db.relation_repository import SqlAlchemyKernelRelationRepository
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

_DOMAIN_CONTEXT = "autopromotion"
_SOURCE_TYPE = "AUTO_SOURCE"
_RELATION_TYPE = "AUTO_RELATES_TO"
_TARGET_TYPE = "AUTO_TARGET"


def test_auto_promotion_requires_an_active_promotable_constraint(
    db_session: Session,
) -> None:
    _add_relation_constraint(db_session, profile="REVIEW_ONLY", is_allowed=True)

    promoted_candidate = _create_threshold_satisfying_relation(db_session)

    assert promoted_candidate.curation_status == "UNDER_REVIEW"


def test_auto_promotion_does_not_promote_forbidden_constraint(
    db_session: Session,
) -> None:
    _add_relation_constraint(db_session, profile="FORBIDDEN", is_allowed=False)

    if db_session.get_bind().dialect.name == "postgresql":
        with pytest.raises(SQLAlchemyError, match="not allowed"):
            _create_threshold_satisfying_relation(db_session)
        db_session.rollback()
        return

    promoted_candidate = _create_threshold_satisfying_relation(db_session)

    assert promoted_candidate.curation_status == "UNDER_REVIEW"


def test_auto_promotion_allows_explicit_allowed_constraint(
    db_session: Session,
) -> None:
    _add_relation_constraint(db_session, profile="ALLOWED", is_allowed=True)

    promoted_candidate = _create_threshold_satisfying_relation(db_session)

    assert promoted_candidate.curation_status == "APPROVED"


def test_auto_promotion_ignores_refute_claim_below_conflict_threshold(
    db_session: Session,
) -> None:
    _add_relation_constraint(db_session, profile="ALLOWED", is_allowed=True)

    promoted_candidate = _create_relation_with_refute_claim(
        db_session,
        refute_confidence=0.2,
        conflict_threshold=0.8,
    )

    assert promoted_candidate.curation_status == "APPROVED"


def test_auto_promoted_relation_demotes_when_supporting_evidence_is_removed(
    db_session: Session,
) -> None:
    _add_relation_constraint(db_session, profile="ALLOWED", is_allowed=True)
    promoted_candidate = _create_threshold_satisfying_relation(db_session)
    repository = SqlAlchemyKernelRelationRepository(
        db_session,
        auto_promotion_policy=AutoPromotionPolicy(
            min_distinct_sources=2,
            min_aggregate_confidence=0.8,
            require_distinct_documents=False,
            require_distinct_runs=False,
            block_if_conflicting_evidence=True,
        ),
    )

    demoted_candidate = repository.replace_derived_evidence_cache(
        str(promoted_candidate.id),
        evidences=[],
    )

    assert demoted_candidate.curation_status == "UNDER_REVIEW"


def _create_threshold_satisfying_relation(session: Session) -> KernelRelation:
    _seed_dictionary_triplet(session)
    space_id = uuid4()
    source_entity = _create_entity(
        session,
        research_space_id=space_id,
        entity_type=_SOURCE_TYPE,
        label="source",
    )
    target_entity = _create_entity(
        session,
        research_space_id=space_id,
        entity_type=_TARGET_TYPE,
        label="target",
    )

    repository = SqlAlchemyKernelRelationRepository(
        session,
        auto_promotion_policy=AutoPromotionPolicy(
            min_distinct_sources=2,
            min_aggregate_confidence=0.8,
            require_distinct_documents=False,
            require_distinct_runs=False,
            block_if_conflicting_evidence=True,
        ),
    )
    relation = repository.upsert_relation(
        research_space_id=str(space_id),
        source_id=str(source_entity.id),
        relation_type=_RELATION_TYPE,
        target_id=str(target_entity.id),
        curation_status="UNDER_REVIEW",
    )

    return repository.replace_derived_evidence_cache(
        str(relation.id),
        evidences=[
            RelationEvidenceWrite(
                confidence=0.95,
                evidence_summary="First literature source supports the relation.",
                evidence_tier="LITERATURE",
                source_document_ref="doc:one",
            ),
            RelationEvidenceWrite(
                confidence=0.95,
                evidence_summary="Second literature source supports the relation.",
                evidence_tier="LITERATURE",
                source_document_ref="doc:two",
            ),
        ],
    )


def _create_relation_with_refute_claim(
    session: Session,
    *,
    refute_confidence: float,
    conflict_threshold: float,
) -> KernelRelation:
    _seed_dictionary_triplet(session)
    space_id = uuid4()
    source_entity = _create_entity(
        session,
        research_space_id=space_id,
        entity_type=_SOURCE_TYPE,
        label="source",
    )
    target_entity = _create_entity(
        session,
        research_space_id=space_id,
        entity_type=_TARGET_TYPE,
        label="target",
    )
    repository = SqlAlchemyKernelRelationRepository(
        session,
        auto_promotion_policy=AutoPromotionPolicy(
            min_distinct_sources=2,
            min_aggregate_confidence=0.8,
            require_distinct_documents=False,
            require_distinct_runs=False,
            block_if_conflicting_evidence=True,
            conflicting_confidence_threshold=conflict_threshold,
        ),
    )
    relation = repository.upsert_relation(
        research_space_id=str(space_id),
        source_id=str(source_entity.id),
        relation_type=_RELATION_TYPE,
        target_id=str(target_entity.id),
        curation_status="UNDER_REVIEW",
    )
    session.add(
        RelationClaimModel(
            research_space_id=space_id,
            source_type=_SOURCE_TYPE,
            relation_type=_RELATION_TYPE,
            target_type=_TARGET_TYPE,
            source_label="source",
            target_label="target",
            confidence=refute_confidence,
            validation_state="VALID",
            persistability="PERSISTABLE",
            assertion_class="SOURCE_BACKED",
            claim_status="OPEN",
            polarity="REFUTE",
            claim_text="Low confidence contradictory claim.",
            linked_relation_id=UUID(str(relation.id)),
            metadata_payload={},
        ),
    )
    session.flush()
    return repository.replace_derived_evidence_cache(
        str(relation.id),
        evidences=[
            RelationEvidenceWrite(
                confidence=0.95,
                evidence_summary="First literature source supports the relation.",
                evidence_tier="LITERATURE",
                source_document_ref="doc:one",
            ),
            RelationEvidenceWrite(
                confidence=0.95,
                evidence_summary="Second literature source supports the relation.",
                evidence_tier="LITERATURE",
                source_document_ref="doc:two",
            ),
        ],
    )


def _seed_dictionary_triplet(session: Session) -> None:
    if session.get(DictionaryDomainContextModel, _DOMAIN_CONTEXT) is None:
        session.add(
            DictionaryDomainContextModel(
                id=_DOMAIN_CONTEXT,
                display_name="Auto Promotion",
                description="Test domain for relation auto-promotion governance.",
                is_active=True,
            ),
        )

    for entity_type in (_SOURCE_TYPE, _TARGET_TYPE):
        if session.get(DictionaryEntityTypeModel, entity_type) is not None:
            continue
        session.add(
            DictionaryEntityTypeModel(
                id=entity_type,
                display_name=entity_type.replace("_", " ").title(),
                description="Test entity type for relation auto-promotion.",
                domain_context=_DOMAIN_CONTEXT,
                expected_properties={},
                created_by="test",
                review_status="ACTIVE",
                is_active=True,
            ),
        )

    if session.get(DictionaryRelationTypeModel, _RELATION_TYPE) is None:
        session.add(
            DictionaryRelationTypeModel(
                id=_RELATION_TYPE,
                display_name="Auto Relates To",
                description="Test relation type for relation auto-promotion.",
                domain_context=_DOMAIN_CONTEXT,
                is_directional=True,
                created_by="test",
                review_status="ACTIVE",
                is_active=True,
            ),
        )
    session.flush()


def _add_relation_constraint(
    session: Session,
    *,
    profile: str,
    is_allowed: bool,
) -> None:
    _seed_dictionary_triplet(session)
    session.add(
        RelationConstraintModel(
            source_type=_SOURCE_TYPE,
            relation_type=_RELATION_TYPE,
            target_type=_TARGET_TYPE,
            is_allowed=is_allowed,
            requires_evidence=True,
            profile=profile,
            created_by="test",
            review_status="ACTIVE",
            is_active=True,
        ),
    )
    session.flush()


def _create_entity(
    session: Session,
    *,
    research_space_id: UUID,
    entity_type: str,
    label: str,
) -> GraphEntityModel:
    entity = GraphEntityModel(
        id=uuid4(),
        research_space_id=research_space_id,
        entity_type=entity_type,
        display_label=label,
        display_label_normalized=label.lower(),
        metadata_payload={},
    )
    session.add(entity)
    session.flush()
    return entity
