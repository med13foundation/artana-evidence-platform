"""Support types and helpers for reasoning-path rebuilds and reads."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING

from artana_evidence_db.kernel_domain_ports import (
    ReasoningPathStepWrite,
    ReasoningPathWrite,
    ReasoningPathWriteBundle,
)

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONValue
    from artana_evidence_db.kernel_domain_models import (
        KernelClaimEvidence,
        KernelClaimParticipant,
        KernelClaimRelation,
        KernelReasoningPath,
        KernelReasoningPathStep,
        KernelRelation,
        KernelRelationClaim,
    )


@dataclass(frozen=True)
class ReasoningPathListResult:
    """Paginated reasoning-path listing."""

    paths: tuple[KernelReasoningPath, ...]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True)
class ReasoningPathRebuildSummary:
    """Summary of one reasoning-path rebuild run."""

    research_space_id: str
    eligible_claims: int
    accepted_claim_relations: int
    rebuilt_paths: int
    max_depth: int


@dataclass(frozen=True)
class KernelReasoningPathDetail:
    """Fully expanded reasoning-path read model."""

    path: KernelReasoningPath
    steps: tuple[KernelReasoningPathStep, ...]
    claims: tuple[KernelRelationClaim, ...]
    claim_relations: tuple[KernelClaimRelation, ...]
    canonical_relations: tuple[KernelRelation, ...]
    participants: tuple[KernelClaimParticipant, ...]
    evidence: tuple[KernelClaimEvidence, ...]


@dataclass(frozen=True)
class KernelMechanismPathCandidate:
    """Compact candidate row for seed-entity mechanism reasoning reads."""

    reasoning_path_id: str
    start_entity_id: str
    end_entity_id: str
    source_type: str
    target_type: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    confidence: float
    path_length: int
    supporting_claim_ids: tuple[str, ...]


def build_adjacency(
    accepted_relations: list[KernelClaimRelation],
) -> dict[str, list[KernelClaimRelation]]:
    adjacency: dict[str, list[KernelClaimRelation]] = defaultdict(list)
    for relation in accepted_relations:
        adjacency[str(relation.source_claim_id)].append(relation)
    for relations in adjacency.values():
        relations.sort(
            key=lambda relation: (
                -float(relation.confidence),
                str(relation.target_claim_id),
                str(relation.id),
            ),
        )
    return adjacency


def collect_paths_from_root(  # noqa: PLR0913
    *,
    research_space_id: str,
    root_claim_id: str,
    eligible_claim_map: dict[str, KernelRelationClaim],
    participant_anchor_map: dict[str, tuple[str, str]],
    adjacency: dict[str, list[KernelClaimRelation]],
    max_depth: int,
    bundles_by_signature: dict[str, ReasoningPathWriteBundle],
) -> None:
    def _walk(
        current_claim_id: str,
        visited_claim_ids: tuple[str, ...],
        traversed_relations: tuple[KernelClaimRelation, ...],
    ) -> None:
        if traversed_relations:
            bundle = build_bundle(
                research_space_id=research_space_id,
                root_claim_id=root_claim_id,
                claim_ids=visited_claim_ids,
                traversed_relations=traversed_relations,
                claim_map=eligible_claim_map,
                participant_anchor_map=participant_anchor_map,
            )
            bundles_by_signature.setdefault(bundle.path.path_signature_hash, bundle)
        if len(traversed_relations) >= max_depth:
            return
        for relation in adjacency.get(current_claim_id, []):
            next_claim_id = str(relation.target_claim_id)
            if next_claim_id in visited_claim_ids:
                continue
            _walk(
                next_claim_id,
                (*visited_claim_ids, next_claim_id),
                (*traversed_relations, relation),
            )

    _walk(root_claim_id, (root_claim_id,), ())


def resolve_participant_anchor_entities(
    participants: list[KernelClaimParticipant],
) -> tuple[str, str] | None:
    subject_entity_id: str | None = None
    object_entity_id: str | None = None
    for participant in participants:
        if participant.entity_id is None:
            continue
        participant_entity_id = str(participant.entity_id)
        if participant.role == "SUBJECT" and subject_entity_id is None:
            subject_entity_id = participant_entity_id
        if participant.role == "OBJECT" and object_entity_id is None:
            object_entity_id = participant_entity_id
    if subject_entity_id is None or object_entity_id is None:
        return None
    return subject_entity_id, object_entity_id


def build_bundle(  # noqa: PLR0913
    *,
    research_space_id: str,
    root_claim_id: str,
    claim_ids: tuple[str, ...],
    traversed_relations: tuple[KernelClaimRelation, ...],
    claim_map: dict[str, KernelRelationClaim],
    participant_anchor_map: dict[str, tuple[str, str]],
) -> ReasoningPathWriteBundle:
    start_entity_id = participant_anchor_map[root_claim_id][0]
    last_claim_id = claim_ids[-1]
    end_entity_id = participant_anchor_map[last_claim_id][1]
    path_confidence = min(
        max(0.0, min(1.0, float(relation.confidence)))
        for relation in traversed_relations
    )
    claim_relation_ids = [str(relation.id) for relation in traversed_relations]
    signature_hash = build_signature_hash(
        claim_ids=claim_ids,
        claim_relation_ids=claim_relation_ids,
    )
    terminal_claim = claim_map[last_claim_id]
    metadata: dict[str, JSONValue] = {
        "supporting_claim_ids": list(claim_ids),
        "claim_relation_ids": claim_relation_ids,
        "start_claim_id": root_claim_id,
        "end_claim_id": last_claim_id,
        "terminal_relation_type": str(terminal_claim.relation_type),
    }
    steps = tuple(
        ReasoningPathStepWrite(
            step_index=index,
            source_claim_id=str(relation.source_claim_id),
            target_claim_id=str(relation.target_claim_id),
            claim_relation_id=str(relation.id),
            canonical_relation_id=resolve_step_canonical_relation_id(
                source_claim=claim_map[str(relation.source_claim_id)],
                target_claim=claim_map[str(relation.target_claim_id)],
            ),
            metadata={
                "relation_type": str(relation.relation_type),
                "confidence": float(relation.confidence),
            },
        )
        for index, relation in enumerate(traversed_relations)
    )
    return ReasoningPathWriteBundle(
        path=ReasoningPathWrite(
            research_space_id=research_space_id,
            path_kind="MECHANISM",
            status="ACTIVE",
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            root_claim_id=root_claim_id,
            path_length=len(traversed_relations),
            confidence=path_confidence,
            path_signature_hash=signature_hash,
            generated_by="kernel_reasoning_path_service",
            metadata=metadata,
        ),
        steps=steps,
    )


def build_signature_hash(
    *,
    claim_ids: tuple[str, ...],
    claim_relation_ids: list[str],
) -> str:
    payload = json.dumps(
        {
            "claim_ids": list(claim_ids),
            "claim_relation_ids": claim_relation_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def resolve_step_canonical_relation_id(
    *,
    source_claim: KernelRelationClaim,
    target_claim: KernelRelationClaim,
) -> str | None:
    if source_claim.linked_relation_id is not None:
        return str(source_claim.linked_relation_id)
    if target_claim.linked_relation_id is not None:
        return str(target_claim.linked_relation_id)
    return None


def resolve_ordered_claim_ids(
    *,
    path: KernelReasoningPath,
    steps: list[KernelReasoningPathStep],
) -> list[str]:
    claim_ids = [str(path.root_claim_id)]
    seen = {str(path.root_claim_id)}
    for step in steps:
        source_claim_id = str(step.source_claim_id)
        target_claim_id = str(step.target_claim_id)
        if source_claim_id not in seen:
            claim_ids.append(source_claim_id)
            seen.add(source_claim_id)
        if target_claim_id not in seen:
            claim_ids.append(target_claim_id)
            seen.add(target_claim_id)
    return claim_ids


def resolve_ordered_canonical_relation_ids(
    *,
    steps: tuple[KernelReasoningPathStep, ...] | list[KernelReasoningPathStep],
    claims: tuple[KernelRelationClaim, ...],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if step.canonical_relation_id is None:
            continue
        relation_id = str(step.canonical_relation_id)
        if relation_id in seen:
            continue
        seen.add(relation_id)
        ordered.append(relation_id)
    for claim in claims:
        if claim.linked_relation_id is None:
            continue
        relation_id = str(claim.linked_relation_id)
        if relation_id in seen:
            continue
        seen.add(relation_id)
        ordered.append(relation_id)
    return ordered


__all__ = [
    "KernelMechanismPathCandidate",
    "KernelReasoningPathDetail",
    "ReasoningPathListResult",
    "ReasoningPathRebuildSummary",
    "build_adjacency",
    "build_bundle",
    "build_signature_hash",
    "collect_paths_from_root",
    "resolve_ordered_canonical_relation_ids",
    "resolve_ordered_claim_ids",
    "resolve_participant_anchor_entities",
    "resolve_step_canonical_relation_id",
]
