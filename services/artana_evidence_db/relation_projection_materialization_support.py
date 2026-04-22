"""Helper types and pure functions for relation projection materialization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import Sequence

    from artana_evidence_db.graph_core_models import (
        KernelRelation,
        KernelRelationEvidence,
    )
    from artana_evidence_db.kernel_domain_models import (
        KernelClaimEvidence,
        KernelClaimParticipant,
        KernelRelationClaim,
    )


class ClaimEvidenceRepositoryLike(Protocol):
    """Minimal claim-evidence write surface needed for evidence backfill."""

    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        sentence: str | None,
        sentence_source: str | None,
        sentence_confidence: str | None,
        sentence_rationale: str | None,
        figure_reference: str | None,
        table_reference: str | None,
        confidence: float,
        source_document_ref: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> object: ...


class RelationProjectionMaterializationError(ValueError):
    """Raised when a claim cannot be materialized into a canonical relation."""


@dataclass(frozen=True)
class RelationProjectionMaterializationResult:
    """Outcome of one projection materialization or rebuild operation."""

    relation: KernelRelation | None
    rebuilt_relation_ids: tuple[str, ...] = ()
    deleted_relation_ids: tuple[str, ...] = ()
    derived_evidence_rows: int = 0


@dataclass(frozen=True)
class ProjectionEndpoints:
    """Normalized canonical triple resolved from one support claim."""

    source_id: str
    source_label: str | None
    source_type: str
    relation_type: str
    target_id: str
    target_label: str | None
    target_type: str
    entity_ids: tuple[str, ...]


def participant_for_role(
    participants: list[KernelClaimParticipant],
    *,
    role: str,
) -> KernelClaimParticipant | None:
    matching_participants = participants_for_role(participants, role=role)
    return matching_participants[0] if matching_participants else None


def participants_for_role(
    participants: list[KernelClaimParticipant],
    *,
    role: str,
) -> list[KernelClaimParticipant]:
    normalized_role = role.strip().upper()
    return sorted(
        [
            participant
            for participant in participants
            if participant.role == normalized_role
        ],
        key=_participant_order_key,
    )


def _participant_order_key(
    participant: KernelClaimParticipant,
) -> tuple[bool, int, str]:
    position = getattr(participant, "position", None)
    normalized_position = position if isinstance(position, int) else 0
    return (
        position is None,
        normalized_position,
        _participant_anchor(participant),
    )


def _participant_anchor(participant: KernelClaimParticipant) -> str:
    entity_id = getattr(participant, "entity_id", None)
    if entity_id is not None:
        return f"entity:{entity_id}"
    label = getattr(participant, "label", None)
    if isinstance(label, str) and label.strip():
        normalized_label = " ".join(label.split()).casefold()
        return f"label:{normalized_label}"
    participant_id = getattr(participant, "id", None)
    return f"participant:{participant_id}"


def _endpoint_participant_sets(
    participants: list[KernelClaimParticipant],
) -> dict[str, list[str]]:
    participant_sets: dict[str, list[str]] = {}
    for role in ("SUBJECT", "OBJECT"):
        role_participants = participants_for_role(participants, role=role)
        if len(role_participants) > 1:
            participant_sets[role] = [
                _participant_anchor(participant) for participant in role_participants
            ]
    return participant_sets


def extract_scoping_qualifier_fingerprint(
    participants: list[KernelClaimParticipant],
) -> dict[str, object]:
    """Extract scoping context from claim participants for canonicalization.

    Includes:
    - CONTEXT participant entity anchors (label or entity_id)
    - Scoping qualifier key-value pairs from all participants
    - Ordered SUBJECT/OBJECT participant sets for multi-endpoint claims

    Returns a sorted dict that forms part of the canonicalization
    fingerprint.  Non-scoping qualifiers and non-CONTEXT participant
    anchors are excluded to avoid unnecessary relation splitting.
    """
    from artana_evidence_db.qualifier_registry import is_scoping_qualifier

    scoping: dict[str, object] = {}

    # Include CONTEXT participant anchors
    context_labels: list[str] = []
    for participant in participants:
        role = getattr(participant, "role", "")
        if role == "CONTEXT":
            label = getattr(participant, "label", None)
            entity_id = getattr(participant, "entity_id", None)
            anchor = str(label or entity_id or "")
            if anchor:
                context_labels.append(anchor)
    if context_labels:
        scoping["_context_anchors"] = sorted(context_labels)

    participant_sets = _endpoint_participant_sets(participants)
    if participant_sets:
        scoping["_participant_sets"] = participant_sets

    # Include scoping qualifiers from all participants
    for participant in participants:
        qualifiers = getattr(participant, "qualifiers", None)
        if not isinstance(qualifiers, dict):
            continue
        scoping.update(
            {
                key: value
                for key, value in qualifiers.items()
                if is_scoping_qualifier(key)
            },
        )

    return dict(sorted(scoping.items()))


def is_active_support_claim(claim: KernelRelationClaim) -> bool:
    if claim.polarity != "SUPPORT":
        return False
    if claim.claim_status != "RESOLVED":
        return False
    if claim.persistability != "PERSISTABLE":
        return False
    assertion_class = getattr(claim, "assertion_class", "SOURCE_BACKED")
    return assertion_class != "COMPUTATIONAL"


def claim_evidence_summary(
    *,
    claim: KernelRelationClaim,
    evidence: KernelClaimEvidence,
) -> str | None:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        raw_summary = metadata.get("evidence_summary")
        if isinstance(raw_summary, str) and raw_summary.strip():
            return raw_summary.strip()[:2000]
    if isinstance(claim.claim_text, str) and claim.claim_text.strip():
        return claim.claim_text.strip()[:2000]
    return None


def claim_evidence_tier(evidence: KernelClaimEvidence) -> str:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        raw_tier = metadata.get("evidence_tier")
        if isinstance(raw_tier, str) and raw_tier.strip():
            return raw_tier.strip().upper()[:32]
    return "COMPUTATIONAL"


def claim_evidence_provenance_id(
    evidence: KernelClaimEvidence,
) -> UUID | None:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        raw_provenance_id = metadata.get("provenance_id")
        if isinstance(raw_provenance_id, str):
            normalized = raw_provenance_id.strip()
            if normalized:
                try:
                    return UUID(normalized)
                except ValueError:
                    return None
    return None


def relation_provenance_id(
    *,
    claim: KernelRelationClaim,
    evidences: Sequence[KernelClaimEvidence],
) -> str | None:
    claim_metadata = claim.metadata_payload
    if isinstance(claim_metadata, dict):
        raw_provenance_id = claim_metadata.get("provenance_id")
        if isinstance(raw_provenance_id, str) and raw_provenance_id.strip():
            return raw_provenance_id.strip()
        supporting_provenance_ids = claim_metadata.get("supporting_provenance_ids")
        if isinstance(supporting_provenance_ids, list):
            for provenance_id in supporting_provenance_ids:
                if isinstance(provenance_id, str) and provenance_id.strip():
                    return provenance_id.strip()
    for evidence in evidences:
        provenance_id = claim_evidence_provenance_id(evidence)
        if provenance_id is not None:
            return str(provenance_id)
    return None


def dedupe_relation_ids(relation_ids: list[str]) -> list[str]:
    deduped: list[str] = []
    for relation_id in relation_ids:
        normalized = relation_id.strip()
        if not normalized or normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped


def backfill_claim_evidence_from_relation_cache(
    *,
    claim_evidence_repo: ClaimEvidenceRepositoryLike,
    claim_id: str,
    claim: KernelRelationClaim,
    current_evidence: list[KernelRelationEvidence],
) -> None:
    for evidence in current_evidence:
        claim_evidence_repo.create(
            claim_id=claim_id,
            source_document_id=(
                str(evidence.source_document_id)
                if evidence.source_document_id is not None
                else None
            ),
            source_document_ref=evidence.source_document_ref,
            agent_run_id=evidence.agent_run_id or claim.agent_run_id,
            sentence=evidence.evidence_sentence,
            sentence_source=evidence.evidence_sentence_source,
            sentence_confidence=evidence.evidence_sentence_confidence,
            sentence_rationale=evidence.evidence_sentence_rationale,
            figure_reference=None,
            table_reference=None,
            confidence=float(evidence.confidence),
            metadata={
                "origin": "relation_evidence_backfill",
                "evidence_summary": evidence.evidence_summary,
                "evidence_tier": evidence.evidence_tier,
                "provenance_id": (
                    str(evidence.provenance_id)
                    if evidence.provenance_id is not None
                    else None
                ),
            },
        )


__all__ = [
    "ProjectionEndpoints",
    "RelationProjectionMaterializationError",
    "RelationProjectionMaterializationResult",
    "backfill_claim_evidence_from_relation_cache",
    "claim_evidence_provenance_id",
    "claim_evidence_summary",
    "claim_evidence_tier",
    "dedupe_relation_ids",
    "extract_scoping_qualifier_fingerprint",
    "is_active_support_claim",
    "participant_for_role",
    "participants_for_role",
    "relation_provenance_id",
]
