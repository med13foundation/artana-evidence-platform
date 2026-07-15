"""Regression tests for governed relation auto-promotion."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_db.graph_core_models import KernelRelation, RelationEvidenceWrite
from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
)
from artana_evidence_db.kernel_entity_models import GraphEntityModel
from artana_evidence_db.relation_autopromotion_policy import AutoPromotionPolicy
from artana_evidence_db.relation_repository import SqlAlchemyKernelRelationRepository
from artana_evidence_db.source_provenance.models import (
    ExactEvidenceLocator,
    SourceEvidenceHandoff,
    SourceEvidenceUpstream,
    SourceIdentity,
)
from artana_evidence_db.source_provenance.service import SourceProvenanceService
from artana_evidence_db.space_models import GraphSpaceModel
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
    constraint = _add_relation_constraint(
        db_session,
        profile="REVIEW_ONLY",
        is_allowed=True,
    )
    promoted_candidate = _create_threshold_satisfying_relation(db_session)
    constraint.profile = "FORBIDDEN"
    constraint.is_allowed = False
    db_session.flush()
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

    decision = repository._apply_auto_promotion(  # noqa: SLF001
        UUID(str(promoted_candidate.id)),
    )

    assert decision.reason == "constraint_not_promotable"
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
        evidences=_verified_support_evidence(
            session,
            space_id=space_id,
            relation_id=UUID(str(relation.id)),
        ),
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
        evidences=_verified_support_evidence(
            session,
            space_id=space_id,
            relation_id=UUID(str(relation.id)),
        ),
    )


def _verified_support_evidence(
    session: Session,
    *,
    space_id: UUID,
    relation_id: UUID,
) -> list[RelationEvidenceWrite]:
    _ensure_graph_space(session, space_id=space_id)
    writes: list[RelationEvidenceWrite] = []
    for index, pmid in enumerate(("12345678", "87654321"), start=1):
        text = f"Independent literature source {index} supports the relation."
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document_id = uuid4()
        locator = ExactEvidenceLocator(
            source_content_sha256=source_hash,
            char_start=0,
            char_end=len(text),
            exact_quote=text,
            quote_sha256=source_hash,
        )
        submission = SourceProvenanceService(session).verify_and_snapshot(
            research_space_id=space_id,
            source_document_id=document_id,
            source_evidence=SourceEvidenceHandoff(
                upstream=SourceEvidenceUpstream(
                    research_space_id=space_id,
                    document_id=document_id,
                    attested_at=datetime.now(UTC),
                ),
                identity=SourceIdentity(
                    source_kind="pubmed",
                    authoritative_identifier=f"PMID:{pmid}",
                    canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    retrieved_at=datetime.now(UTC),
                    content_sha256=source_hash,
                    pmid=pmid,
                ),
                canonical_text=text,
                locator=locator,
            ),
            source_attestation_capability=True,
            authenticated_attestation_service="artana_evidence_api",
        )
        assert submission.snapshot is not None
        claim_id = uuid4()
        session.add(
            RelationClaimModel(
                id=claim_id,
                research_space_id=space_id,
                source_document_id=document_id,
                source_document_ref=f"PMID:{pmid}",
                agent_run_id=f"agent-run-{index}",
                source_type=_SOURCE_TYPE,
                relation_type=_RELATION_TYPE,
                target_type=_TARGET_TYPE,
                source_label="source",
                target_label="target",
                confidence=0.95,
                validation_state="VALID",
                persistability="PERSISTABLE",
                assertion_class="SOURCE_BACKED",
                claim_status="RESOLVED",
                polarity="SUPPORT",
                claim_text=text,
                linked_relation_id=relation_id,
                metadata_payload={},
            ),
        )
        session.flush()
        session.add(
            ClaimEvidenceModel(
                id=uuid4(),
                claim_id=claim_id,
                source_document_id=document_id,
                source_document_ref=f"PMID:{pmid}",
                source_snapshot_id=submission.snapshot.id,
                agent_run_id=f"agent-run-{index}",
                sentence=text,
                confidence=0.95,
                metadata_payload={},
                evidence_locator_payload=locator.model_dump(mode="json"),
                provenance_status="VERIFIED",
                provenance_reason_codes=["verified"],
            ),
        )
        session.add(
            RelationProjectionSourceModel(
                id=uuid4(),
                research_space_id=space_id,
                relation_id=relation_id,
                claim_id=claim_id,
                projection_origin="CLAIM_RESOLUTION",
                source_document_id=document_id,
                source_document_ref=f"PMID:{pmid}",
                agent_run_id=f"agent-run-{index}",
                metadata_payload={},
            ),
        )
        writes.append(
            RelationEvidenceWrite(
                confidence=0.95,
                evidence_summary=text,
                evidence_sentence=text,
                evidence_tier="LITERATURE",
                source_document_id=document_id,
                source_document_ref=f"PMID:{pmid}",
                source_snapshot_id=submission.snapshot.id,
                agent_run_id=f"agent-run-{index}",
            ),
        )
    session.flush()
    return writes


def _ensure_graph_space(session: Session, *, space_id: UUID) -> None:
    if session.get(GraphSpaceModel, space_id) is not None:
        return
    session.add(
        GraphSpaceModel(
            id=space_id,
            slug=f"auto-promotion-{space_id.hex[:12]}",
            name="Auto promotion test",
            owner_id=uuid4(),
            status="active",
            settings={},
        ),
    )
    session.flush()


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
) -> RelationConstraintModel:
    _seed_dictionary_triplet(session)
    constraint = RelationConstraintModel(
        source_type=_SOURCE_TYPE,
        relation_type=_RELATION_TYPE,
        target_type=_TARGET_TYPE,
        is_allowed=is_allowed,
        requires_evidence=True,
        profile=profile,
        created_by="test",
        review_status="ACTIVE",
        is_active=True,
    )
    session.add(constraint)
    session.flush()
    return constraint


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
