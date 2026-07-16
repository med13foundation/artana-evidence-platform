"""Regression tests for quarantine-aware relation projection rebuilds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from artana_evidence_db.claim_evidence_models import KernelClaimEvidence
from artana_evidence_db.claim_participant_models import KernelClaimParticipant
from artana_evidence_db.dictionary_models import RelationConstraint
from artana_evidence_db.graph_core_models import KernelEntity, KernelRelation
from artana_evidence_db.relation_claim_models import KernelRelationClaim
from artana_evidence_db.relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from artana_evidence_db.relation_projection_source_model import (
    KernelRelationProjectionSource,
)


@dataclass(frozen=True, slots=True)
class _Lineage:
    claim: KernelRelationClaim
    projection_source: KernelRelationProjectionSource
    participants: tuple[KernelClaimParticipant, KernelClaimParticipant]
    evidence: KernelClaimEvidence


@dataclass(frozen=True, slots=True)
class _Harness:
    service: KernelRelationProjectionMaterializationService
    relations: Mock
    claims: Mock
    claim_evidence: Mock
    projection_sources: Mock
    eligibility: Mock
    read_model_updates: Mock
    reasoning_path_invalidation: Mock


def test_mixed_manual_and_legacy_ai_lineage_rebuilds_from_manual_claim_only() -> None:
    relation = _relation()
    manual = _lineage(relation=relation)
    legacy_ai = _lineage(relation=relation, agent_run_id="legacy-agent-run")
    harness = _build_harness(
        relation=relation,
        lineages=(legacy_ai, manual),
    )

    result = harness.service.rebuild_relation_projection(
        relation_id=str(relation.id),
        research_space_id=str(relation.research_space_id),
    )

    assert result.relation == relation
    harness.projection_sources.delete_projection_source.assert_called_once_with(
        research_space_id=str(relation.research_space_id),
        relation_id=str(relation.id),
        claim_id=str(legacy_ai.claim.id),
    )
    harness.claims.clear_relation_link.assert_called_once_with(
        str(legacy_ai.claim.id),
    )
    harness.claims.link_relation.assert_called_once_with(
        str(manual.claim.id),
        linked_relation_id=str(relation.id),
    )
    derived = harness.relations.replace_derived_evidence_cache.call_args.kwargs[
        "evidences"
    ]
    assert len(derived) == 1
    assert derived[0].source_document_ref == manual.evidence.source_document_ref
    assert derived[0].agent_run_id is None


def test_ai_only_lineage_removes_projection_relation_and_claim_link() -> None:
    relation = _relation()
    legacy_ai = _lineage(relation=relation, agent_run_id="legacy-agent-run")
    harness = _build_harness(relation=relation, lineages=(legacy_ai,))

    result = harness.service.rebuild_relation_projection(
        relation_id=str(relation.id),
        research_space_id=str(relation.research_space_id),
    )

    assert result.relation is None
    assert result.deleted_relation_ids == (str(relation.id),)
    harness.projection_sources.delete_projection_source.assert_called_once()
    harness.claims.clear_relation_link.assert_called_once_with(
        str(legacy_ai.claim.id),
    )
    harness.relations.delete.assert_called_once_with(str(relation.id))
    harness.relations.upsert_relation.assert_not_called()
    harness.relations.replace_derived_evidence_cache.assert_not_called()


def test_legacy_ai_claim_evidence_is_not_reattached_to_manual_projection() -> None:
    relation = _relation()
    manual = _lineage(relation=relation)
    legacy_evidence = _lineage(
        relation=relation,
        evidence_agent_run_id="legacy-evidence-agent-run",
    )
    harness = _build_harness(
        relation=relation,
        lineages=(legacy_evidence, manual),
    )

    harness.service.rebuild_relation_projection(
        relation_id=str(relation.id),
        research_space_id=str(relation.research_space_id),
    )

    harness.claims.clear_relation_link.assert_called_once_with(
        str(legacy_evidence.claim.id),
    )
    derived = harness.relations.replace_derived_evidence_cache.call_args.kwargs[
        "evidences"
    ]
    assert [row.source_document_ref for row in derived] == [
        manual.evidence.source_document_ref,
    ]
    assert all(row.agent_run_id is None for row in derived)
    assert harness.claim_evidence.find_by_claim_id.call_count == 2


def test_rebuild_preflight_failure_does_not_partially_mutate_lineage() -> None:
    relation = _relation()
    legacy_ai = _lineage(relation=relation, agent_run_id="legacy-agent-run")
    manual = _lineage(relation=relation)
    harness = _build_harness(
        relation=relation,
        lineages=(legacy_ai, manual),
    )
    harness.eligibility.eligible_evidence_ids_for_claim.side_effect = RuntimeError(
        "eligibility lookup failed",
    )

    with pytest.raises(RuntimeError, match="eligibility lookup failed"):
        harness.service.rebuild_relation_projection(
            relation_id=str(relation.id),
            research_space_id=str(relation.research_space_id),
        )

    harness.projection_sources.delete_projection_source.assert_not_called()
    harness.claims.clear_relation_link.assert_not_called()
    harness.claims.link_relation.assert_not_called()
    harness.relations.delete.assert_not_called()
    harness.relations.upsert_relation.assert_not_called()
    harness.relations.replace_derived_evidence_cache.assert_not_called()
    harness.read_model_updates.dispatch_many.assert_not_called()
    harness.reasoning_path_invalidation.invalidate_for_claim_ids.assert_not_called()


def _build_harness(
    *,
    relation: KernelRelation,
    lineages: tuple[_Lineage, ...],
) -> _Harness:
    relations = Mock()
    relations.get_by_id.return_value = relation
    relations.upsert_relation.return_value = relation
    relations.replace_derived_evidence_cache.return_value = relation

    claims = Mock()
    claims.list_by_ids.return_value = [lineage.claim for lineage in lineages]

    participants = Mock()
    participants.find_by_claim_ids.return_value = {
        str(lineage.claim.id): list(lineage.participants) for lineage in lineages
    }

    evidence_by_claim_id = {
        str(lineage.claim.id): [lineage.evidence] for lineage in lineages
    }
    claim_evidence = Mock()
    claim_evidence.find_by_claim_id.side_effect = evidence_by_claim_id.__getitem__

    eligibility = Mock()
    eligibility.claim_has_eligible_evidence.return_value = True
    eligible_ids = {
        str(lineage.claim.id): {lineage.evidence.id} for lineage in lineages
    }
    eligibility.eligible_evidence_ids_for_claim.side_effect = (
        lambda *, claim_id, research_space_id: eligible_ids[str(claim_id)]
    )

    source_id = relation.source_id
    target_id = relation.target_id
    entities = Mock()
    entities.get_by_id.side_effect = {
        str(source_id): _entity(
            entity_id=source_id,
            research_space_id=relation.research_space_id,
            entity_type="GENE",
            label="MED13",
        ),
        str(target_id): _entity(
            entity_id=target_id,
            research_space_id=relation.research_space_id,
            entity_type="PHENOTYPE",
            label="Developmental delay",
        ),
    }.get

    dictionary = Mock()
    dictionary.resolve_relation_synonym.return_value = None
    dictionary.is_triple_allowed.return_value = True
    dictionary.get_constraints.return_value = [_relation_constraint()]

    projection_sources = Mock()
    projection_sources.find_by_relation_id.return_value = [
        lineage.projection_source for lineage in lineages
    ]
    projection_sources.delete_projection_source.return_value = True

    read_model_updates = Mock()
    reasoning_path_invalidation = Mock()
    service = KernelRelationProjectionMaterializationService(
        relation_repo=relations,
        relation_claim_repo=claims,
        claim_participant_repo=participants,
        claim_evidence_repo=claim_evidence,
        claim_evidence_eligibility_service=eligibility,
        entity_repo=entities,
        dictionary_repo=dictionary,
        relation_projection_repo=projection_sources,
        read_model_update_dispatcher=read_model_updates,
        reasoning_path_invalidation_service=reasoning_path_invalidation,
    )
    return _Harness(
        service=service,
        relations=relations,
        claims=claims,
        claim_evidence=claim_evidence,
        projection_sources=projection_sources,
        eligibility=eligibility,
        read_model_updates=read_model_updates,
        reasoning_path_invalidation=reasoning_path_invalidation,
    )


def _relation() -> KernelRelation:
    now = datetime.now(UTC)
    return KernelRelation(
        id=uuid4(),
        research_space_id=uuid4(),
        source_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        target_id=uuid4(),
        curation_status="DRAFT",
        created_at=now,
        updated_at=now,
    )


def _lineage(
    *,
    relation: KernelRelation,
    agent_run_id: str | None = None,
    evidence_agent_run_id: str | None = None,
) -> _Lineage:
    now = datetime.now(UTC)
    claim_id = uuid4()
    source_document_id = uuid4()
    claim = KernelRelationClaim(
        id=claim_id,
        research_space_id=relation.research_space_id,
        source_document_id=source_document_id,
        source_document_ref=f"PMID:{claim_id.int % 10_000_000}",
        agent_run_id=agent_run_id,
        source_type="GENE",
        relation_type=relation.relation_type,
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.9,
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 is associated with developmental delay.",
        linked_relation_id=relation.id,
        metadata_payload={},
        created_at=now,
        updated_at=now,
    )
    projection_source = KernelRelationProjectionSource(
        id=uuid4(),
        research_space_id=relation.research_space_id,
        relation_id=relation.id,
        claim_id=claim_id,
        projection_origin="CLAIM_RESOLUTION",
        source_document_id=source_document_id,
        source_document_ref=claim.source_document_ref,
        agent_run_id=agent_run_id,
        metadata_payload={"origin": "claim_resolution"},
        created_at=now,
        updated_at=now,
    )
    participants = (
        _participant(
            claim_id=claim_id,
            research_space_id=relation.research_space_id,
            entity_id=relation.source_id,
            role="SUBJECT",
            position=0,
        ),
        _participant(
            claim_id=claim_id,
            research_space_id=relation.research_space_id,
            entity_id=relation.target_id,
            role="OBJECT",
            position=1,
        ),
    )
    evidence = KernelClaimEvidence(
        id=uuid4(),
        claim_id=claim_id,
        source_document_id=source_document_id,
        source_document_ref=claim.source_document_ref,
        source_snapshot_id=uuid4(),
        agent_run_id=evidence_agent_run_id or agent_run_id,
        sentence="MED13 is associated with developmental delay.",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        confidence=0.9,
        metadata_payload={"origin": "curator_import"},
        provenance_status="VERIFIED",
        provenance_reason_codes=("verified",),
        created_at=now,
    )
    return _Lineage(
        claim=claim,
        projection_source=projection_source,
        participants=participants,
        evidence=evidence,
    )


def _participant(
    *,
    claim_id: UUID,
    research_space_id: UUID,
    entity_id: UUID,
    role: str,
    position: int,
) -> KernelClaimParticipant:
    return KernelClaimParticipant.model_validate(
        {
            "id": uuid4(),
            "claim_id": claim_id,
            "research_space_id": research_space_id,
            "entity_id": entity_id,
            "role": role,
            "position": position,
            "qualifiers": {},
            "created_at": datetime.now(UTC),
        },
    )


def _entity(
    *,
    entity_id: UUID,
    research_space_id: UUID,
    entity_type: str,
    label: str,
) -> KernelEntity:
    now = datetime.now(UTC)
    return KernelEntity(
        id=entity_id,
        research_space_id=research_space_id,
        entity_type=entity_type,
        display_label=label,
        created_at=now,
        updated_at=now,
    )


def _relation_constraint() -> RelationConstraint:
    now = datetime.now(UTC)
    return RelationConstraint(
        id=1,
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        is_allowed=True,
        requires_evidence=True,
        profile="ALLOWED",
        created_at=now,
        updated_at=now,
    )
