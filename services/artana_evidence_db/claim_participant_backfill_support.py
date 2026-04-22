"""Support types and queries for claim participant backfill."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_db.kernel_claim_models import (
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_domain_models import ConceptMember, KernelEntity
from artana_evidence_db.semantic_ports import ConceptPort
from sqlalchemy import and_, or_, select

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session


class EntityRepositoryLike(Protocol):
    """Minimal entity lookup surface required for participant backfill."""

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        """Load one graph entity by ID."""


@dataclass(frozen=True)
class ClaimParticipantBackfillSummary:
    """Backfill result summary for one research space."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    dry_run: bool


@dataclass(frozen=True)
class ClaimParticipantCoverageSummary:
    """Coverage summary for claim participant anchors in one research space."""

    total_claims: int
    claims_with_any_participants: int
    claims_with_subject: int
    claims_with_object: int
    unresolved_subject_endpoints: int
    unresolved_object_endpoints: int


@dataclass(frozen=True)
class ClaimParticipantBackfillGlobalSummary:
    """Backfill result summary across all research spaces."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    research_spaces: int
    dry_run: bool


@dataclass(frozen=True)
class _Anchor:
    entity_id: str | None
    label: str | None


def list_projection_relevant_claim_models(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> list[RelationClaimModel]:
    projection_exists = (
        select(RelationProjectionSourceModel.id)
        .where(
            RelationProjectionSourceModel.claim_id == RelationClaimModel.id,
            RelationProjectionSourceModel.research_space_id
            == RelationClaimModel.research_space_id,
        )
        .exists()
    )
    stmt = (
        select(RelationClaimModel)
        .where(
            RelationClaimModel.polarity == "SUPPORT",
            or_(
                and_(
                    RelationClaimModel.claim_status == "RESOLVED",
                    RelationClaimModel.persistability == "PERSISTABLE",
                ),
                RelationClaimModel.linked_relation_id.is_not(None),
                projection_exists,
            ),
        )
        .order_by(RelationClaimModel.created_at.asc(), RelationClaimModel.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(stmt).all())


def resolve_claim_anchor(  # noqa: PLR0913
    *,
    research_space_id: str,
    claim_metadata: JSONObject,
    endpoint: str,
    fallback_label: str | None,
    entities: EntityRepositoryLike,
    concepts: ConceptPort,
) -> _Anchor | None:
    entity_id = resolve_entity_id_from_metadata(
        research_space_id=research_space_id,
        claim_metadata=claim_metadata,
        endpoint=endpoint,
        entities=entities,
    )
    if entity_id is not None:
        entity = entities.get_by_id(entity_id)
        if entity is not None and str(entity.research_space_id) == research_space_id:
            entity_label = (
                entity.display_label.strip()
                if isinstance(entity.display_label, str)
                else ""
            )
            return _Anchor(
                entity_id=str(entity.id),
                label=entity_label or None,
            )

    concept_anchor = resolve_concept_member_anchor_from_metadata(
        research_space_id=research_space_id,
        claim_metadata=claim_metadata,
        endpoint=endpoint,
        entities=entities,
        concepts=concepts,
    )
    if concept_anchor is not None:
        return concept_anchor

    normalized_fallback = (
        fallback_label.strip() if isinstance(fallback_label, str) else ""
    )
    if normalized_fallback:
        return _Anchor(entity_id=None, label=normalized_fallback)
    return None


def resolve_entity_id_from_metadata(
    *,
    research_space_id: str,
    claim_metadata: JSONObject,
    endpoint: str,
    entities: EntityRepositoryLike,
) -> str | None:
    entity_key = f"{endpoint}_entity_id"
    raw_entity_id = claim_metadata.get(entity_key)
    if not isinstance(raw_entity_id, str):
        return None
    return resolve_entity_id_in_space(
        research_space_id=research_space_id,
        candidate_entity_id=raw_entity_id,
        entities=entities,
    )


def resolve_concept_member_anchor_from_metadata(
    *,
    research_space_id: str,
    claim_metadata: JSONObject,
    endpoint: str,
    entities: EntityRepositoryLike,
    concepts: ConceptPort,
) -> _Anchor | None:
    raw_refs = claim_metadata.get("concept_refs")
    if not isinstance(raw_refs, dict):
        return None
    member_key = f"{endpoint}_member_id"
    raw_member_id = raw_refs.get(member_key)
    if not isinstance(raw_member_id, str):
        return None
    normalized_member_id = raw_member_id.strip()
    if not normalized_member_id:
        return None

    concept_set_id = raw_refs.get("concept_set_id")
    if not isinstance(concept_set_id, str) or not concept_set_id.strip():
        return None

    members = concepts.list_concept_members(
        research_space_id=research_space_id,
        concept_set_id=concept_set_id.strip(),
        include_inactive=True,
        offset=0,
        limit=1000,
    )
    for member in members:
        if member.id != normalized_member_id:
            continue
        return build_anchor_from_concept_member(
            research_space_id=research_space_id,
            member=member,
            entities=entities,
        )
    return None


def build_anchor_from_concept_member(
    *,
    research_space_id: str,
    member: ConceptMember,
    entities: EntityRepositoryLike,
) -> _Anchor:
    resolved_entity_id = resolve_entity_id_from_concept_member(
        research_space_id=research_space_id,
        member=member,
        entities=entities,
    )
    label = (
        member.canonical_label.strip()
        if isinstance(member.canonical_label, str)
        else ""
    )
    if resolved_entity_id is None:
        return _Anchor(entity_id=None, label=label or None)

    entity = entities.get_by_id(resolved_entity_id)
    if entity is not None and str(entity.research_space_id) == research_space_id:
        entity_label = (
            entity.display_label.strip()
            if isinstance(entity.display_label, str)
            else ""
        )
        return _Anchor(
            entity_id=resolved_entity_id,
            label=entity_label or label or None,
        )

    return _Anchor(entity_id=resolved_entity_id, label=label or None)


def resolve_entity_id_from_concept_member(
    *,
    research_space_id: str,
    member: ConceptMember,
    entities: EntityRepositoryLike,
) -> str | None:
    candidate_ids: list[str] = []

    dimension_raw = (
        member.dictionary_dimension.strip().lower()
        if isinstance(member.dictionary_dimension, str)
        else ""
    )
    dictionary_entry_id = (
        member.dictionary_entry_id.strip()
        if isinstance(member.dictionary_entry_id, str)
        else ""
    )
    if dictionary_entry_id and dimension_raw in {
        "entity",
        "entity_id",
        "kernel_entity",
        "kernel_entity_id",
        "kernel.entities",
    }:
        candidate_ids.append(dictionary_entry_id)

    metadata_payload = member.metadata_payload
    if isinstance(metadata_payload, dict):
        for key in (
            "entity_id",
            "kernel_entity_id",
            "linked_entity_id",
            "resolved_entity_id",
        ):
            raw_value = metadata_payload.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                candidate_ids.append(raw_value)

        raw_entity = metadata_payload.get("entity")
        if isinstance(raw_entity, dict):
            raw_nested_id = raw_entity.get("id")
            if isinstance(raw_nested_id, str) and raw_nested_id.strip():
                candidate_ids.append(raw_nested_id)

    for candidate_id in candidate_ids:
        normalized = resolve_entity_id_in_space(
            research_space_id=research_space_id,
            candidate_entity_id=candidate_id,
            entities=entities,
        )
        if normalized is not None:
            return normalized
    return None


def resolve_entity_id_in_space(
    *,
    research_space_id: str,
    candidate_entity_id: str,
    entities: EntityRepositoryLike,
) -> str | None:
    candidate = candidate_entity_id.strip()
    if not candidate:
        return None
    try:
        canonical = str(UUID(candidate))
    except ValueError:
        return None
    entity = entities.get_by_id(canonical)
    if entity is None:
        return None
    if str(entity.research_space_id) != research_space_id:
        return None
    return canonical


__all__ = [
    "ClaimParticipantBackfillGlobalSummary",
    "ClaimParticipantBackfillSummary",
    "ClaimParticipantCoverageSummary",
    "EntityRepositoryLike",
    "list_projection_relevant_claim_models",
    "resolve_claim_anchor",
]
