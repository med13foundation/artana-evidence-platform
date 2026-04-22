"""Service-local support types and query helpers for claim projection readiness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    ClaimParticipantModel,
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from sqlalchemy import and_, or_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class ClaimParticipantBackfillGlobalSummaryLike(Protocol):
    """Minimal global backfill summary shape used by readiness repair output."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    research_spaces: int
    dry_run: bool


@dataclass(frozen=True)
class ClaimProjectionReadinessSample:
    """One sampled unresolved readiness issue."""

    research_space_id: str
    claim_id: str | None
    relation_id: str | None
    detail: str


@dataclass(frozen=True)
class ClaimProjectionReadinessIssue:
    """Aggregate count plus sampled rows for one readiness category."""

    count: int
    samples: tuple[ClaimProjectionReadinessSample, ...]


@dataclass(frozen=True)
class ClaimProjectionReadinessReport:
    """Global readiness report for claim-backed canonical projections."""

    orphan_relations: ClaimProjectionReadinessIssue
    missing_claim_participants: ClaimProjectionReadinessIssue
    missing_claim_evidence: ClaimProjectionReadinessIssue
    linked_relation_mismatches: ClaimProjectionReadinessIssue
    invalid_projection_relations: ClaimProjectionReadinessIssue
    ready: bool


@dataclass(frozen=True)
class ClaimProjectionRepairSummary:
    """Result of global repair attempts for projection-related claim state."""

    participant_backfill: ClaimParticipantBackfillGlobalSummaryLike
    materialized_claims: int
    detached_claims: int
    unresolved_claims: int
    dry_run: bool


def load_projection_relevant_support_claims(
    session: Session,
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
    )
    return list(session.scalars(stmt).all())


def load_projection_rows(
    session: Session,
) -> list[RelationProjectionSourceModel]:
    stmt = select(RelationProjectionSourceModel).order_by(
        RelationProjectionSourceModel.created_at.asc(),
        RelationProjectionSourceModel.id.asc(),
    )
    return list(session.scalars(stmt).all())


def load_claims_by_ids(
    session: Session,
    *,
    claim_ids: list[str],
) -> dict[str, RelationClaimModel]:
    normalized_ids = _normalize_uuid_strings(claim_ids)
    if not normalized_ids:
        return {}
    stmt = select(RelationClaimModel).where(
        RelationClaimModel.id.in_([UUID(claim_id) for claim_id in normalized_ids]),
    )
    models = session.scalars(stmt).all()
    return {str(model.id): model for model in models}


def load_participants_by_claim_id(
    session: Session,
    *,
    claim_ids: list[str],
) -> dict[str, list[ClaimParticipantModel]]:
    normalized_ids = _normalize_uuid_strings(claim_ids)
    if not normalized_ids:
        return {}
    stmt = (
        select(ClaimParticipantModel)
        .where(
            ClaimParticipantModel.claim_id.in_(
                [UUID(claim_id) for claim_id in normalized_ids],
            ),
        )
        .order_by(
            ClaimParticipantModel.claim_id.asc(),
            ClaimParticipantModel.position.asc().nulls_last(),
            ClaimParticipantModel.created_at.asc(),
        )
    )
    grouped: dict[str, list[ClaimParticipantModel]] = {}
    for model in session.scalars(stmt).all():
        grouped.setdefault(str(model.claim_id), []).append(model)
    return grouped


def load_evidence_by_claim_id(
    session: Session,
    *,
    claim_ids: list[str],
) -> dict[str, list[ClaimEvidenceModel]]:
    normalized_ids = _normalize_uuid_strings(claim_ids)
    if not normalized_ids:
        return {}
    stmt = (
        select(ClaimEvidenceModel)
        .where(
            ClaimEvidenceModel.claim_id.in_(
                [UUID(claim_id) for claim_id in normalized_ids],
            ),
        )
        .order_by(
            ClaimEvidenceModel.claim_id.asc(),
            ClaimEvidenceModel.created_at.desc(),
        )
    )
    grouped: dict[str, list[ClaimEvidenceModel]] = {}
    for model in session.scalars(stmt).all():
        grouped.setdefault(str(model.claim_id), []).append(model)
    return grouped


def group_projection_rows_by_claim_id(
    projection_rows: list[RelationProjectionSourceModel],
) -> dict[str, list[RelationProjectionSourceModel]]:
    grouped: dict[str, list[RelationProjectionSourceModel]] = {}
    for row in projection_rows:
        grouped.setdefault(str(row.claim_id), []).append(row)
    return grouped


def has_role_anchor(
    participants: list[ClaimParticipantModel],
    *,
    role: str,
) -> bool:
    for participant in participants:
        if participant.role == role and participant.entity_id is not None:
            return True
    return False


def has_required_projection_participants(
    participants: list[ClaimParticipantModel],
) -> bool:
    return has_role_anchor(participants, role="SUBJECT") and has_role_anchor(
        participants,
        role="OBJECT",
    )


def has_usable_claim_evidence(evidences: list[ClaimEvidenceModel]) -> bool:
    return bool(evidences)


def is_active_support_claim(claim: RelationClaimModel) -> bool:
    return (
        claim.polarity == "SUPPORT"
        and claim.claim_status == "RESOLVED"
        and claim.persistability == "PERSISTABLE"
    )


def _normalize_uuid_strings(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        try:
            normalized_value = str(UUID(value))
        except ValueError:
            continue
        if normalized_value in seen:
            continue
        seen.add(normalized_value)
        normalized.append(normalized_value)
    return normalized


__all__ = [
    "ClaimParticipantBackfillGlobalSummaryLike",
    "ClaimProjectionReadinessIssue",
    "ClaimProjectionReadinessReport",
    "ClaimProjectionReadinessSample",
    "ClaimProjectionRepairSummary",
    "group_projection_rows_by_claim_id",
    "has_required_projection_participants",
    "has_usable_claim_evidence",
    "has_role_anchor",
    "is_active_support_claim",
    "load_claims_by_ids",
    "load_evidence_by_claim_id",
    "load_participants_by_claim_id",
    "load_projection_relevant_support_claims",
    "load_projection_rows",
]
