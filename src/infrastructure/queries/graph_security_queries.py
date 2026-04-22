"""Allowed graph-query helpers for legacy platform security operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.entity_lookup_models import EntityIdentifierModel
from sqlalchemy import not_, or_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_BACKFILL_CIPHERTEXT_PREFIX = "artanaphi:%"


def load_phi_identifier_backfill_batch(
    session: Session,
    *,
    last_seen_id: int,
    limit: int,
) -> list[object]:
    candidate_conditions = or_(
        EntityIdentifierModel.identifier_blind_index.is_(None),
        EntityIdentifierModel.encryption_key_version.is_(None),
        EntityIdentifierModel.blind_index_version.is_(None),
        not_(
            EntityIdentifierModel.identifier_value.like(
                _BACKFILL_CIPHERTEXT_PREFIX,
            ),
        ),
    )
    statement = (
        select(EntityIdentifierModel)
        .where(
            EntityIdentifierModel.id > last_seen_id,
            EntityIdentifierModel.sensitivity == "PHI",
            candidate_conditions,
        )
        .order_by(EntityIdentifierModel.id.asc())
        .limit(limit)
    )
    return list(session.scalars(statement).all())


__all__ = ["load_phi_identifier_backfill_batch"]
