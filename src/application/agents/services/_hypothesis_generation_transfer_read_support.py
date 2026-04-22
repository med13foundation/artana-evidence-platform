"""Transfer-specific read helpers for hypothesis generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.agents.services._hypothesis_generation_support import (
    PathCandidate,
    TransferCandidate,
    claim_targets_transfer_endpoint,
    dedupe_strings,
    normalize_optional_text,
    resolve_object_entity_id,
    resolve_object_label,
)
from src.application.agents.services._hypothesis_transfer_support import (
    _TRANSFER_SCORE_THRESHOLD,
    build_transfer_explanation,
    label_overlap_score,
    relation_types_are_transfer_compatible,
    score_transfer_candidate,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import KernelRelationClaim
    from artana_evidence_db.kernel_repositories import (
        KernelEntityRepository,
        KernelRelationRepository,
    )
    from artana_evidence_db.kernel_services import (
        KernelClaimEvidenceService,
        KernelClaimParticipantService,
        KernelReasoningPathService,
        KernelRelationClaimService,
    )


_PHENOTYPE_OVERLAP_THRESHOLD = 0.34


def load_transfer_candidates(  # noqa: PLR0913
    *,
    reasoning_path_service: KernelReasoningPathService | None,
    relation_repository: KernelRelationRepository,
    relation_claim_service: KernelRelationClaimService,
    claim_participant_service: KernelClaimParticipantService,
    claim_evidence_service: KernelClaimEvidenceService,
    entity_repository: KernelEntityRepository,
    research_space_id: str,
    seed_entity_ids: list[str],
    path_candidates: list[PathCandidate],
    max_hypotheses: int,
) -> tuple[list[TransferCandidate], list[str]]:
    if reasoning_path_service is None:
        return [], []

    path_candidates_by_seed: dict[str, list[PathCandidate]] = {}
    for path_candidate in path_candidates:
        path_candidates_by_seed.setdefault(
            path_candidate.start_entity_id,
            [],
        ).append(path_candidate)

    candidates: list[TransferCandidate] = []
    errors: list[str] = []
    for seed_entity_id in seed_entity_ids:
        seed_paths = path_candidates_by_seed.get(seed_entity_id, [])
        if not seed_paths:
            continue
        neighboring_relation_types = load_neighboring_relation_types(
            relation_repository=relation_repository,
            research_space_id=research_space_id,
            seed_entity_id=seed_entity_id,
            limit=max(20, max_hypotheses * 12),
        )
        if not neighboring_relation_types:
            continue

        support_claims_by_entity, contradiction_claims = (
            load_neighboring_transfer_support(
                relation_claim_service=relation_claim_service,
                claim_participant_service=claim_participant_service,
                claim_evidence_service=claim_evidence_service,
                research_space_id=research_space_id,
                neighboring_entity_ids=list(neighboring_relation_types),
                seed_entity_id=seed_entity_id,
                limit=max(20, max_hypotheses * 12),
            )
        )
        for path_candidate in seed_paths:
            candidate = build_transfer_candidate_for_path(
                entity_repository=entity_repository,
                path_candidate=path_candidate,
                neighboring_relation_types=neighboring_relation_types,
                support_claims_by_entity=support_claims_by_entity,
                contradiction_claims=contradiction_claims,
            )
            if candidate is None:
                continue
            if candidate.candidate_score < _TRANSFER_SCORE_THRESHOLD:
                errors.append(
                    "transfer_candidate_below_threshold:"
                    f"{candidate.reasoning_path_id}",
                )
                continue
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -item.candidate_score,
            -item.confidence,
            item.path_length,
            item.reasoning_path_id,
        ),
    )
    return candidates, errors


def load_neighboring_relation_types(
    *,
    relation_repository: KernelRelationRepository,
    research_space_id: str,
    seed_entity_id: str,
    limit: int,
) -> dict[str, tuple[str, ...]]:
    relation_rows = relation_repository.find_by_research_space(
        research_space_id,
        node_ids=[seed_entity_id],
        claim_backed_only=True,
        limit=limit,
        offset=0,
    )
    neighboring: dict[str, set[str]] = {}
    for relation in relation_rows:
        relation_source_id = str(relation.source_id)
        relation_target_id = str(relation.target_id)
        if relation_source_id == seed_entity_id:
            neighboring_entity_id = relation_target_id
        elif relation_target_id == seed_entity_id:
            neighboring_entity_id = relation_source_id
        else:
            continue
        if neighboring_entity_id == seed_entity_id:
            continue
        neighboring.setdefault(neighboring_entity_id, set()).add(
            str(relation.relation_type),
        )
    return {
        entity_id: tuple(sorted(relation_types))
        for entity_id, relation_types in neighboring.items()
    }


def load_neighboring_transfer_support(  # noqa: PLR0913
    *,
    relation_claim_service: KernelRelationClaimService,
    claim_participant_service: KernelClaimParticipantService,
    claim_evidence_service: KernelClaimEvidenceService,
    research_space_id: str,
    neighboring_entity_ids: list[str],
    seed_entity_id: str,
    limit: int,
) -> tuple[
    dict[str, tuple[tuple[KernelRelationClaim, str | None, str | None], ...]],
    tuple[KernelRelationClaim, ...],
]:
    support_claims_by_entity: dict[
        str,
        tuple[tuple[KernelRelationClaim, str | None, str | None], ...],
    ] = {}
    contradiction_claims: list[KernelRelationClaim] = []
    contradiction_seen: set[str] = set()
    for entity_id in neighboring_entity_ids:
        claim_ids = claim_participant_service.list_claim_ids_by_entity(
            research_space_id=research_space_id,
            entity_id=entity_id,
            limit=limit,
            offset=0,
        )
        if not claim_ids:
            continue
        claims = relation_claim_service.list_claims_by_ids(claim_ids)
        participants_by_claim = claim_participant_service.list_for_claim_ids(claim_ids)
        evidence_by_claim = claim_evidence_service.list_for_claim_ids(claim_ids)

        support_rows: list[tuple[KernelRelationClaim, str | None, str | None]] = []
        for claim in claims:
            claim_id = str(claim.id)
            participants = participants_by_claim.get(claim_id, [])
            object_entity_id = resolve_object_entity_id(
                claim=claim,
                participants=participants,
            )
            object_label = resolve_object_label(
                claim=claim,
                participants=participants,
            )
            if (
                claim.polarity == "SUPPORT"
                and claim.claim_status == "RESOLVED"
                and claim.persistability == "PERSISTABLE"
                and evidence_by_claim.get(claim_id)
            ):
                support_rows.append((claim, object_entity_id, object_label))
                continue
            if (
                claim.polarity in {"REFUTE", "UNCERTAIN"}
                and claim_id not in contradiction_seen
            ):
                contradiction_seen.add(claim_id)
                contradiction_claims.append(claim)

        if support_rows:
            support_claims_by_entity[entity_id] = tuple(support_rows)

    support_claims_by_entity.pop(seed_entity_id, None)
    return support_claims_by_entity, tuple(contradiction_claims)


def build_transfer_candidate_for_path(
    *,
    entity_repository: KernelEntityRepository,
    path_candidate: PathCandidate,
    neighboring_relation_types: dict[str, tuple[str, ...]],
    support_claims_by_entity: dict[
        str,
        tuple[tuple[KernelRelationClaim, str | None, str | None], ...],
    ],
    contradiction_claims: tuple[KernelRelationClaim, ...],
) -> TransferCandidate | None:
    transferred_supporting_claim_ids: list[str] = []
    transferred_from_entity_ids: list[str] = []
    transferred_from_entity_labels: list[str] = []
    transfer_basis: set[str] = set()
    matched_claim_confidences: list[float] = []
    best_phenotype_overlap = 0.0

    for neighboring_entity_id, relation_types in neighboring_relation_types.items():
        support_rows = support_claims_by_entity.get(neighboring_entity_id, ())
        if not support_rows:
            continue
        neighboring_entity = entity_repository.get_by_id(neighboring_entity_id)
        neighboring_label = (
            normalize_optional_text(neighboring_entity.display_label)
            if neighboring_entity is not None
            else None
        )
        matched_claim_ids_for_entity: list[str] = []
        entity_best_overlap = 0.0
        for claim, object_entity_id, object_label in support_rows:
            if not relation_types_are_transfer_compatible(
                path_candidate.relation_type,
                str(claim.relation_type),
            ):
                continue
            exact_end_match = object_entity_id == path_candidate.end_entity_id
            phenotype_overlap = (
                1.0
                if exact_end_match
                else label_overlap_score(object_label, path_candidate.target_label)
            )
            if phenotype_overlap < _PHENOTYPE_OVERLAP_THRESHOLD:
                continue
            matched_claim_ids_for_entity.append(str(claim.id))
            matched_claim_confidences.append(float(claim.confidence))
            entity_best_overlap = max(entity_best_overlap, phenotype_overlap)
            transfer_basis.add(
                "shared_end_entity" if exact_end_match else "phenotype_overlap",
            )
            transfer_basis.add("relation_family_overlap")

        if not matched_claim_ids_for_entity:
            continue
        best_phenotype_overlap = max(best_phenotype_overlap, entity_best_overlap)
        transferred_supporting_claim_ids.extend(matched_claim_ids_for_entity)
        transferred_from_entity_ids.append(neighboring_entity_id)
        transferred_from_entity_labels.append(
            neighboring_label or neighboring_entity_id,
        )
        for relation_type in relation_types:
            transfer_basis.add(f"neighbor_via_{relation_type.lower()}")

    if not transferred_supporting_claim_ids:
        return None

    contradiction_ids = [
        str(claim.id)
        for claim in contradiction_claims
        if relation_types_are_transfer_compatible(
            path_candidate.relation_type,
            str(claim.relation_type),
        )
        and claim_targets_transfer_endpoint(
            claim=claim,
            path_candidate=path_candidate,
            overlap_threshold=_PHENOTYPE_OVERLAP_THRESHOLD,
            label_overlap_fn=label_overlap_score,
        )
    ]
    score_breakdown = score_transfer_candidate(
        direct_path_confidence=path_candidate.confidence,
        average_transfer_confidence=(
            sum(matched_claim_confidences) / float(len(matched_claim_confidences))
        ),
        phenotype_overlap=best_phenotype_overlap,
        transferred_entity_count=len(transferred_from_entity_ids),
        contradiction_count=len(contradiction_ids),
    )
    return TransferCandidate(
        reasoning_path_id=path_candidate.reasoning_path_id,
        start_entity_id=path_candidate.start_entity_id,
        end_entity_id=path_candidate.end_entity_id,
        source_type=path_candidate.source_type,
        target_type=path_candidate.target_type,
        relation_type=path_candidate.relation_type,
        source_label=path_candidate.source_label,
        target_label=path_candidate.target_label,
        confidence=path_candidate.confidence,
        path_length=path_candidate.path_length,
        direct_supporting_claim_ids=path_candidate.supporting_claim_ids,
        transferred_supporting_claim_ids=tuple(
            dedupe_strings(transferred_supporting_claim_ids),
        ),
        transferred_from_entity_ids=tuple(dedupe_strings(transferred_from_entity_ids)),
        transferred_from_entity_labels=tuple(
            dedupe_strings(transferred_from_entity_labels),
        ),
        transfer_basis=tuple(sorted(transfer_basis)),
        contradiction_claim_ids=tuple(dedupe_strings(contradiction_ids)),
        explanation=build_transfer_explanation(
            source_label=path_candidate.source_label or path_candidate.start_entity_id,
            target_label=path_candidate.target_label or path_candidate.end_entity_id,
            transferred_entity_labels=tuple(transferred_from_entity_labels),
            direct_supporting_claim_count=len(path_candidate.supporting_claim_ids),
            transferred_supporting_claim_count=len(transferred_supporting_claim_ids),
            contradiction_count=len(contradiction_ids),
        ),
        candidate_score=score_breakdown.score,
        direct_support_score=score_breakdown.direct_support_score,
        transfer_support_score=score_breakdown.transfer_support_score,
        phenotype_overlap_score=score_breakdown.phenotype_overlap_score,
        pathway_overlap_score=score_breakdown.pathway_overlap_score,
        contradiction_penalty=score_breakdown.contradiction_penalty,
    )


__all__ = ["load_transfer_candidates"]
