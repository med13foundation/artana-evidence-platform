"""One implementation of relation aggregate recomputation.

There were two.  The curation path filtered evidence for eligibility and wrote
six derived fields; the dictionary relation-type merge path filtered nothing and
wrote three, leaving `support_confidence`, `refute_confidence`, and
`distinct_source_family_count` holding pre-merge values.  Those fields are
query-filterable and API-exposed, so a merged relation reported stale
confidence indefinitely.

`source_count` also counted evidence *rows* in both.  It is rendered to users as
"sources", so three spans quoted from one paper read as three sources.  It now
counts distinct source documents (§5.6).

Deliberately not called "independent source count".  A preprint and its
publication, two papers from one study, or a review citing an original are
distinct documents and not independent evidence.  Establishing independence is a
later, explicit classification.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db._relation_repository_shared import (
    _clamp_confidence,
    _diminishing_confidence,
    _normalize_evidence_tier,
    _source_family_key,
    _tier_rank,
)
from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    RelationClaimModel,
)
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from artana_evidence_db.source_provenance.eligibility import (
    ClaimEvidenceEligibilityService,
)
from sqlalchemy import select

if TYPE_CHECKING:

    from sqlalchemy.orm import Session

_COMPUTATIONAL_TIER = "COMPUTATIONAL"


def distinct_document_count(evidences: list[RelationEvidenceModel]) -> int:
    """Count distinct source documents behind a relation's evidence.

    Evidence with no `source_document_id` counts as its own document rather
    than collapsing with other unattributed rows: absent provenance could be
    one document or several, and assuming one understates the count.  Missing
    is not equal (invariant 8).
    """

    identified: set[str] = set()
    unattributed = 0
    for evidence in evidences:
        document_id = getattr(evidence, "source_document_id", None)
        if document_id is None or str(document_id).strip() == "":
            unattributed += 1
            continue
        identified.add(str(document_id))
    return len(identified) + unattributed


def recompute_relation_aggregate(session: Session, relation_id: UUID) -> None:
    """Recompute every evidence-derived field on one relation.

    Both the curation path and the dictionary relation-type merge path call
    this, so a merge can no longer leave a subset of the fields behind.
    """

    relation_model = session.get(RelationModel, relation_id)
    if relation_model is None:
        return

    evidences = list(
        session.scalars(
            select(RelationEvidenceModel).where(
                RelationEvidenceModel.relation_id == relation_id,
            ),
        ).all(),
    )
    eligible_snapshot_ids = ClaimEvidenceEligibilityService(
        session,
    ).eligible_snapshot_ids_for_relation(
        relation_id=relation_id,
        research_space_id=relation_model.research_space_id,
    )
    evidences = [
        evidence
        for evidence in evidences
        if evidence.source_snapshot_id in eligible_snapshot_ids
    ]
    if not evidences:
        _reset(relation_model)
        return

    support_units: dict[str, float] = {}
    source_families: set[str] = set()
    highest_tier: str | None = None
    highest_rank = -1
    all_product = 1.0

    for evidence in evidences:
        confidence = _clamp_confidence(float(evidence.confidence))
        all_product *= 1.0 - confidence
        tier = _normalize_evidence_tier(evidence.evidence_tier)
        rank = _tier_rank(tier)
        if rank > highest_rank:
            highest_rank = rank
            highest_tier = tier

        family_key = _source_family_key(evidence)
        if family_key is None:
            continue
        source_families.add(family_key)
        if tier == _COMPUTATIONAL_TIER:
            continue
        support_units[family_key] = max(
            support_units.get(family_key, 0.0),
            confidence,
        )

    relation_model.aggregate_confidence = _clamp_confidence(1.0 - all_product)
    relation_model.source_count = distinct_document_count(evidences)
    relation_model.highest_evidence_tier = highest_tier
    relation_model.support_confidence = _diminishing_confidence(support_units.values())
    relation_model.refute_confidence = _diminishing_confidence(
        _linked_refute_claim_units(session, relation_model).values(),
    )
    relation_model.distinct_source_family_count = len(source_families)
    relation_model.updated_at = datetime.now(UTC)


def _reset(relation_model: RelationModel) -> None:
    relation_model.aggregate_confidence = 0.0
    relation_model.source_count = 0
    relation_model.highest_evidence_tier = None
    relation_model.support_confidence = 0.0
    relation_model.refute_confidence = 0.0
    relation_model.distinct_source_family_count = 0
    relation_model.updated_at = datetime.now(UTC)


def _linked_refute_claim_units(
    session: Session,
    relation_model: RelationModel,
) -> dict[str, float]:
    """Return REFUTE confidence units linked to a canonical relation."""

    refute_claims = list(
        session.scalars(
            select(RelationClaimModel).where(
                RelationClaimModel.research_space_id
                == relation_model.research_space_id,
                RelationClaimModel.linked_relation_id == relation_model.id,
                RelationClaimModel.claim_status != "REJECTED",
                RelationClaimModel.polarity == "REFUTE",
                RelationClaimModel.assertion_class != _COMPUTATIONAL_TIER,
            ),
        ).all(),
    )
    if not refute_claims:
        return {}

    claim_evidence_rows = list(
        session.scalars(
            select(ClaimEvidenceModel).where(
                ClaimEvidenceModel.claim_id.in_([claim.id for claim in refute_claims]),
            ),
        ).all(),
    )
    evidence_by_claim_id: dict[UUID, list[ClaimEvidenceModel]] = {}
    for evidence in claim_evidence_rows:
        evidence_by_claim_id.setdefault(evidence.claim_id, []).append(evidence)

    eligibility = ClaimEvidenceEligibilityService(session)
    refute_units: dict[str, float] = {}
    for claim in refute_claims:
        for evidence in evidence_by_claim_id.get(claim.id, []):
            if not eligibility.evaluate(
                evidence,
                research_space_id=relation_model.research_space_id,
            ).eligible:
                continue
            family_key = _source_family_key(evidence)
            if family_key is None:
                continue
            refute_units[family_key] = max(
                refute_units.get(family_key, 0.0),
                _clamp_confidence(float(evidence.confidence)),
            )
    return refute_units


__all__ = [
    "distinct_document_count",
    "recompute_relation_aggregate",
]
