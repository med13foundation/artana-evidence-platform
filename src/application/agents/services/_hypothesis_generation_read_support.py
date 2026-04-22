"""Read-side helpers for hypothesis generation orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services._hypothesis_generation_support import (
    RawCandidate,
    datetime_to_epoch_seconds,
    normalize_optional_text,
    resolve_evidence_density,
)
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from artana_evidence_db.kernel_repositories import (
        KernelEntityRepository,
        KernelRelationRepository,
    )
    from artana_evidence_db.kernel_services import (
        KernelRelationClaimService,
    )
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.agents.contracts.graph_connection import ProposedRelation


_DEFAULT_SEED_LIMIT = 40
_SEED_CLAIM_CONFIDENCE_THRESHOLD = 0.7


def resolve_seed_entity_ids(  # noqa: C901, PLR0912, PLR0913
    *,
    relation_claim_service: KernelRelationClaimService,
    relation_repository: KernelRelationRepository,
    entity_repository: KernelEntityRepository,
    research_space_id: str,
    requested_seed_entity_ids: list[str],
    max_hypotheses: int,
) -> list[str]:
    max_seed_count = max(1, min(_DEFAULT_SEED_LIMIT, max_hypotheses * 2))
    if requested_seed_entity_ids:
        return requested_seed_entity_ids[:max_seed_count]

    resolved: list[str] = []
    seen: set[str] = set()
    unresolved_claims = relation_claim_service.list_by_research_space(
        research_space_id,
        limit=300,
    )
    prioritized_claims = [
        claim
        for claim in unresolved_claims
        if claim.claim_status in {"OPEN", "NEEDS_MAPPING"}
        and float(claim.confidence) >= _SEED_CLAIM_CONFIDENCE_THRESHOLD
    ]
    prioritized_claims.sort(
        key=lambda claim: (
            -float(claim.confidence),
            -datetime_to_epoch_seconds(claim.created_at),
        ),
    )
    for claim in prioritized_claims:
        for candidate_seed in (
            normalize_optional_text(claim.metadata_payload.get("source_entity_id")),
            normalize_optional_text(claim.metadata_payload.get("target_entity_id")),
        ):
            if candidate_seed is None or candidate_seed in seen:
                continue
            seen.add(candidate_seed)
            resolved.append(candidate_seed)
            if len(resolved) >= max_seed_count:
                return resolved

    degree_counts: dict[str, int] = {}
    for relation in relation_repository.find_by_research_space(
        research_space_id,
        limit=600,
    ):
        source_id = str(relation.source_id)
        target_id = str(relation.target_id)
        degree_counts[source_id] = degree_counts.get(source_id, 0) + 1
        degree_counts[target_id] = degree_counts.get(target_id, 0) + 1
    for entity_id in sorted(
        degree_counts,
        key=lambda candidate_id: (-degree_counts[candidate_id], candidate_id),
    ):
        if entity_id in seen:
            continue
        seen.add(entity_id)
        resolved.append(entity_id)
        if len(resolved) >= max_seed_count:
            return resolved

    for entity in entity_repository.find_by_research_space(
        research_space_id,
        limit=max_seed_count,
    ):
        entity_id = str(entity.id)
        if entity_id in seen:
            continue
        seen.add(entity_id)
        resolved.append(entity_id)
        if len(resolved) >= max_seed_count:
            break
    return resolved


def load_active_hypothesis_fingerprints(
    *,
    relation_claim_service: KernelRelationClaimService,
    research_space_id: str,
) -> set[str]:
    active_fingerprints: set[str] = set()
    for claim in relation_claim_service.list_by_research_space(
        research_space_id,
        polarity="HYPOTHESIS",
    ):
        if claim.claim_status == "REJECTED":
            continue
        fingerprint = normalize_optional_text(claim.metadata_payload.get("fingerprint"))
        if fingerprint is not None:
            active_fingerprints.add(fingerprint)
    return active_fingerprints


def normalize_candidates_for_seed(  # noqa: PLR0913
    *,
    dictionary_service: DictionaryPort,
    entity_repository: KernelEntityRepository,
    relation_repository: KernelRelationRepository,
    research_space_id: str,
    seed_entity_id: str,
    candidates: list[ProposedRelation],
    graph_agent_run_id: str | None,
) -> tuple[list[RawCandidate], list[str]]:
    normalized_candidates: list[RawCandidate] = []
    errors: list[str] = []

    for candidate in candidates:
        normalized_relation_type = normalize_relation_type(candidate.relation_type)
        if not normalized_relation_type:
            errors.append("candidate_missing_relation_type")
            continue
        source_entity = entity_repository.get_by_id(candidate.source_id)
        target_entity = entity_repository.get_by_id(candidate.target_id)
        if source_entity is None or target_entity is None:
            errors.append(
                "candidate_endpoint_unresolved:"
                f"{candidate.source_id}->{candidate.target_id}:{normalized_relation_type}",
            )
            continue

        source_entity_type = source_entity.entity_type.strip().upper()
        target_entity_type = target_entity.entity_type.strip().upper()
        self_loop = str(source_entity.id) == str(target_entity.id)
        relation_allowed = False
        if not self_loop:
            try:
                relation_allowed = dictionary_service.is_relation_allowed(
                    source_entity_type,
                    normalized_relation_type,
                    target_entity_type,
                )
            except ValueError:
                relation_allowed = False

        normalized_candidates.append(
            RawCandidate(
                seed_entity_id=seed_entity_id,
                source_entity_id=str(source_entity.id),
                target_entity_id=str(target_entity.id),
                source_type=source_entity_type,
                target_type=target_entity_type,
                relation_type=normalized_relation_type,
                source_label=normalize_optional_text(source_entity.display_label),
                target_label=normalize_optional_text(target_entity.display_label),
                relation_confidence=max(0.0, min(1.0, float(candidate.confidence))),
                evidence_density=resolve_evidence_density(
                    supporting_provenance_ids=candidate.supporting_provenance_ids,
                    supporting_document_count=candidate.supporting_document_count,
                ),
                novelty=resolve_novelty(
                    relation_repository=relation_repository,
                    research_space_id=research_space_id,
                    source_entity_id=str(source_entity.id),
                    relation_type=normalized_relation_type,
                    target_entity_id=str(target_entity.id),
                ),
                relation_allowed=relation_allowed,
                self_loop=self_loop,
                supporting_provenance_ids=tuple(candidate.supporting_provenance_ids),
                supporting_document_count=max(
                    0,
                    int(candidate.supporting_document_count),
                ),
                evidence_summary=candidate.evidence_summary,
                reasoning=candidate.reasoning,
                graph_agent_run_id=graph_agent_run_id,
            ),
        )
    return normalized_candidates, errors


def resolve_novelty(
    *,
    relation_repository: KernelRelationRepository,
    research_space_id: str,
    source_entity_id: str,
    relation_type: str,
    target_entity_id: str,
) -> float:
    for relation in relation_repository.find_by_source(
        source_entity_id,
        relation_type=relation_type,
        limit=200,
    ):
        if str(relation.research_space_id) != research_space_id:
            continue
        if str(relation.target_id) != target_entity_id:
            continue
        return 0.3
    return 1.0


__all__ = [
    "load_active_hypothesis_fingerprints",
    "normalize_candidates_for_seed",
    "resolve_seed_entity_ids",
]
