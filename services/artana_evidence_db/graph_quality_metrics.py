"""Graph quality observability helpers.

Pure query functions that compute quality metrics for a research space.
No endpoints — these are intended for observability dashboards, health
checks, and operational tooling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.kernel_claim_models import RelationClaimModel
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from sqlalchemy import distinct, func, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def claim_to_canonical_projection_rate(
    session: Session,
    space_id: str | UUID,
) -> float:
    """Ratio of resolved claims linked to a canonical relation.

    Returns 0.0 when there are no resolved claims.
    """
    sid = _as_uuid(space_id)
    resolved_count = (
        session.scalar(
            select(func.count()).select_from(
                select(RelationClaimModel.id)
                .where(
                    RelationClaimModel.research_space_id == sid,
                    RelationClaimModel.claim_status == "RESOLVED",
                )
                .subquery(),
            ),
        )
        or 0
    )
    if resolved_count == 0:
        return 0.0
    linked_count = (
        session.scalar(
            select(func.count()).select_from(
                select(RelationClaimModel.id)
                .where(
                    RelationClaimModel.research_space_id == sid,
                    RelationClaimModel.claim_status == "RESOLVED",
                    RelationClaimModel.linked_relation_id.is_not(None),
                )
                .subquery(),
            ),
        )
        or 0
    )
    return float(linked_count) / float(resolved_count)


def computational_only_relation_count(
    session: Session,
    space_id: str | UUID,
) -> int:
    """Count of relations where all evidence is COMPUTATIONAL tier."""
    sid = _as_uuid(space_id)
    # Relations in this space that have at least one evidence row
    relations_with_evidence = (
        select(RelationModel.id)
        .join(
            RelationEvidenceModel,
            RelationEvidenceModel.relation_id == RelationModel.id,
        )
        .where(RelationModel.research_space_id == sid)
        .group_by(RelationModel.id)
        .subquery()
    )
    # Relations that have at least one non-COMPUTATIONAL evidence row
    relations_with_non_computational = (
        select(distinct(RelationEvidenceModel.relation_id))
        .join(
            RelationModel,
            RelationModel.id == RelationEvidenceModel.relation_id,
        )
        .where(
            RelationModel.research_space_id == sid,
            RelationEvidenceModel.evidence_tier != "COMPUTATIONAL",
        )
        .subquery()
    )
    count = session.scalar(
        select(func.count()).select_from(
            select(relations_with_evidence.c.id)
            .where(
                relations_with_evidence.c.id.not_in(
                    select(relations_with_non_computational),
                ),
            )
            .subquery(),
        ),
    )
    return int(count or 0)


def contradiction_count(
    session: Session,
    space_id: str | UUID,
) -> int:
    """Count of relations with both SUPPORT and REFUTE claims."""
    sid = _as_uuid(space_id)
    support_relation_ids = (
        select(distinct(RelationClaimModel.linked_relation_id))
        .where(
            RelationClaimModel.research_space_id == sid,
            RelationClaimModel.linked_relation_id.is_not(None),
            RelationClaimModel.polarity == "SUPPORT",
            RelationClaimModel.claim_status != "REJECTED",
        )
        .subquery()
    )
    refute_relation_ids = (
        select(distinct(RelationClaimModel.linked_relation_id))
        .where(
            RelationClaimModel.research_space_id == sid,
            RelationClaimModel.linked_relation_id.is_not(None),
            RelationClaimModel.polarity == "REFUTE",
            RelationClaimModel.claim_status != "REJECTED",
        )
        .subquery()
    )
    count = session.scalar(
        select(func.count()).select_from(
            select(support_relation_ids.c.linked_relation_id)
            .where(
                support_relation_ids.c.linked_relation_id.in_(
                    select(refute_relation_ids),
                ),
            )
            .subquery(),
        ),
    )
    return int(count or 0)


def unresolved_review_queue_size(
    session: Session,
    space_id: str | UUID,
) -> int:
    """Count of OPEN claims pending review."""
    sid = _as_uuid(space_id)
    count = session.scalar(
        select(func.count()).select_from(
            select(RelationClaimModel.id)
            .where(
                RelationClaimModel.research_space_id == sid,
                RelationClaimModel.claim_status == "OPEN",
            )
            .subquery(),
        ),
    )
    return int(count or 0)


def relation_family_coverage(
    session: Session,
    space_id: str | UUID,
) -> dict[str, int]:
    """Count of canonical relations by relation type.

    Returns a dict mapping relation_type -> count, sorted by count descending.
    """
    sid = _as_uuid(space_id)
    rows = session.execute(
        select(
            RelationModel.relation_type,
            func.count(RelationModel.id).label("cnt"),
        )
        .where(RelationModel.research_space_id == sid)
        .group_by(RelationModel.relation_type)
        .order_by(func.count(RelationModel.id).desc()),
    ).all()
    return {row[0]: int(row[1]) for row in rows}


__all__ = [
    "claim_to_canonical_projection_rate",
    "computational_only_relation_count",
    "contradiction_count",
    "relation_family_coverage",
    "unresolved_review_queue_size",
]
