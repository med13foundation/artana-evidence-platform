"""Support types and pure helpers for hypothesis generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Literal
from uuid import UUID  # noqa: TC003

from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from artana_evidence_db.kernel_domain_models import (
        KernelClaimParticipant,
        KernelRelationClaim,
    )
    from artana_evidence_db.kernel_services import (
        KernelReasoningPathService,
    )
    from artana_evidence_db.reasoning_path_support import (
        KernelMechanismPathCandidate,
    )

_GRAPH_SCORE_WEIGHT_CONFIDENCE = 0.50
_GRAPH_SCORE_WEIGHT_EVIDENCE = 0.20
_GRAPH_SCORE_WEIGHT_NOVELTY = 0.20
_GRAPH_SCORE_WEIGHT_DIVERSITY = 0.10


@dataclass(frozen=True)
class RawCandidate:
    seed_entity_id: str
    source_entity_id: str
    target_entity_id: str
    source_type: str
    target_type: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    relation_confidence: float
    evidence_density: float
    novelty: float
    relation_allowed: bool
    self_loop: bool
    supporting_provenance_ids: tuple[str, ...]
    supporting_document_count: int
    evidence_summary: str
    reasoning: str
    graph_agent_run_id: str | None


@dataclass(frozen=True)
class ScoredCandidate:
    raw: RawCandidate
    relation_diversity: float
    score: float


@dataclass(frozen=True)
class PathCandidate:
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


@dataclass(frozen=True)
class TransferCandidate:
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
    direct_supporting_claim_ids: tuple[str, ...]
    transferred_supporting_claim_ids: tuple[str, ...]
    transferred_from_entity_ids: tuple[str, ...]
    transferred_from_entity_labels: tuple[str, ...]
    transfer_basis: tuple[str, ...]
    contradiction_claim_ids: tuple[str, ...]
    explanation: str
    candidate_score: float
    direct_support_score: float
    transfer_support_score: float
    phenotype_overlap_score: float
    pathway_overlap_score: float
    contradiction_penalty: float


def normalize_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for value in seed_entity_ids:
        normalized = normalize_optional_text(value)
        if normalized is None:
            continue
        try:
            canonical = str(UUID(normalized))
        except ValueError:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized_ids.append(canonical)
    return normalized_ids


def normalize_relation_types(
    relation_types: list[str] | None,
) -> list[str] | None:
    if relation_types is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for value in relation_types:
        relation_type = normalize_relation_type(value)
        if not relation_type or relation_type in seen:
            continue
        seen.add(relation_type)
        normalized.append(relation_type)
    return normalized or None


def normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def normalize_metadata_relation_type(value: object) -> str | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    return normalize_relation_type(normalized)


def normalize_metadata_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(normalize_string_iterable(value))


def normalize_string_iterable(values: Iterable[object]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return tuple(normalized)


def resolve_evidence_density(
    *,
    supporting_provenance_ids: Iterable[str],
    supporting_document_count: int,
) -> float:
    provenance_count = len(
        [value for value in supporting_provenance_ids if value.strip()],
    )
    strongest_signal = max(provenance_count, 0, supporting_document_count)
    return max(0.0, min(1.0, strongest_signal / 5.0))


def build_fingerprint(
    *,
    source_entity_id: str,
    relation_type: str,
    target_entity_id: str,
    origin: str,
) -> str:
    return f"{source_entity_id}|{relation_type}|{target_entity_id}|{origin}"


def resolve_validation_state(
    *,
    relation_allowed: bool,
    self_loop: bool,
) -> tuple[
    Literal["ALLOWED", "FORBIDDEN", "SELF_LOOP"],
    str,
    Literal["PERSISTABLE", "NON_PERSISTABLE"],
]:
    if self_loop:
        return "SELF_LOOP", "self_loop_hypothesis_candidate", "NON_PERSISTABLE"
    if relation_allowed:
        return "ALLOWED", "dictionary_allowed_hypothesis_candidate", "PERSISTABLE"
    return "FORBIDDEN", "dictionary_forbidden_hypothesis_candidate", "NON_PERSISTABLE"


def resolve_object_entity_id(
    *,
    claim: KernelRelationClaim,
    participants: Sequence[KernelClaimParticipant] | Sequence[object],
) -> str | None:
    for participant in participants:
        role = getattr(participant, "role", None)
        entity_id = getattr(participant, "entity_id", None)
        if str(role) != "OBJECT" or entity_id is None:
            continue
        return str(entity_id)
    metadata_object_entity_id = (
        claim.metadata_payload.get("target_entity_id")
        if isinstance(claim.metadata_payload, dict)
        else None
    )
    return normalize_optional_text(metadata_object_entity_id)


def resolve_object_label(
    *,
    claim: KernelRelationClaim,
    participants: Sequence[KernelClaimParticipant] | Sequence[object],
) -> str | None:
    for participant in participants:
        role = getattr(participant, "role", None)
        label = getattr(participant, "label", None)
        if str(role) != "OBJECT":
            continue
        normalized = normalize_optional_text(label)
        if normalized is not None:
            return normalized
    return normalize_optional_text(claim.target_label)


def claim_targets_transfer_endpoint(
    *,
    claim: KernelRelationClaim,
    path_candidate: PathCandidate,
    overlap_threshold: float,
    label_overlap_fn: Callable[[str | None, str | None], float],
) -> bool:
    metadata_payload = (
        claim.metadata_payload if isinstance(claim.metadata_payload, dict) else {}
    )
    target_entity_id = normalize_optional_text(metadata_payload.get("target_entity_id"))
    if target_entity_id == path_candidate.end_entity_id:
        return True
    return (
        label_overlap_fn(
            normalize_optional_text(claim.target_label),
            path_candidate.target_label,
        )
        >= overlap_threshold
    )


def dedupe_strings(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def datetime_to_epoch_seconds(value: datetime) -> float:
    return value.timestamp()


def score_candidates(candidates: list[RawCandidate]) -> list[ScoredCandidate]:
    relation_type_counts: dict[str, int] = {}
    for candidate in candidates:
        relation_type_counts[candidate.relation_type] = (
            relation_type_counts.get(candidate.relation_type, 0) + 1
        )

    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        relation_count = max(
            1,
            relation_type_counts.get(candidate.relation_type, 1),
        )
        relation_diversity = max(0.2, 1.0 / float(relation_count))
        score = (
            (_GRAPH_SCORE_WEIGHT_CONFIDENCE * candidate.relation_confidence)
            + (_GRAPH_SCORE_WEIGHT_EVIDENCE * candidate.evidence_density)
            + (_GRAPH_SCORE_WEIGHT_NOVELTY * candidate.novelty)
            + (_GRAPH_SCORE_WEIGHT_DIVERSITY * relation_diversity)
        )
        scored.append(
            ScoredCandidate(
                raw=candidate,
                relation_diversity=max(0.0, min(1.0, relation_diversity)),
                score=max(0.0, min(1.0, score)),
            ),
        )
    return scored


def load_reasoning_path_candidates(
    *,
    reasoning_path_service: KernelReasoningPathService | None,
    research_space_id: str,
    seed_entity_ids: list[str],
    max_hypotheses: int,
) -> tuple[list[PathCandidate], list[str]]:
    if reasoning_path_service is None:
        return [], []
    candidates: list[PathCandidate] = []
    errors: list[str] = []
    seen_path_ids: set[str] = set()
    for seed_entity_id in seed_entity_ids:
        path_candidates = reasoning_path_service.list_mechanism_candidates(
            research_space_id=research_space_id,
            start_entity_id=seed_entity_id,
            limit=max(5, max_hypotheses * 3),
            offset=0,
        )
        for mechanism_candidate in path_candidates:
            path_id = mechanism_candidate.reasoning_path_id
            if path_id in seen_path_ids:
                continue
            seen_path_ids.add(path_id)
            candidates.append(
                _build_path_candidate(mechanism_candidate),
            )
    candidates.sort(
        key=lambda item: (
            -item.confidence,
            item.path_length,
            item.reasoning_path_id,
        ),
    )
    return candidates, errors


def _build_path_candidate(
    mechanism_candidate: KernelMechanismPathCandidate,
) -> PathCandidate:
    return PathCandidate(
        reasoning_path_id=mechanism_candidate.reasoning_path_id,
        start_entity_id=mechanism_candidate.start_entity_id,
        end_entity_id=mechanism_candidate.end_entity_id,
        source_type=mechanism_candidate.source_type,
        target_type=mechanism_candidate.target_type,
        relation_type=mechanism_candidate.relation_type,
        source_label=normalize_optional_text(mechanism_candidate.source_label),
        target_label=normalize_optional_text(mechanism_candidate.target_label),
        confidence=max(0.0, min(1.0, float(mechanism_candidate.confidence))),
        path_length=int(mechanism_candidate.path_length),
        supporting_claim_ids=mechanism_candidate.supporting_claim_ids,
    )


__all__ = [
    "PathCandidate",
    "RawCandidate",
    "ScoredCandidate",
    "TransferCandidate",
    "build_fingerprint",
    "claim_targets_transfer_endpoint",
    "datetime_to_epoch_seconds",
    "dedupe_strings",
    "load_reasoning_path_candidates",
    "normalize_metadata_relation_type",
    "normalize_metadata_string_tuple",
    "normalize_optional_text",
    "normalize_relation_types",
    "normalize_seed_entity_ids",
    "normalize_string_iterable",
    "resolve_evidence_density",
    "resolve_object_entity_id",
    "resolve_object_label",
    "resolve_validation_state",
    "score_candidates",
]
