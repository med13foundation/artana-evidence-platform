"""Curation and delete mixin for service-local relation repositories."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db._relation_repository_shared import (
    _as_uuid,
    _claim_source_family_key,
    _clamp_confidence,
    _diminishing_confidence,
    _normalize_evidence_tier,
    _source_family_key,
    _tier_rank,
)
from artana_evidence_db.graph_core_models import KernelRelation
from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    RelationClaimModel,
)
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.engine import CursorResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class _KernelRelationCurationMixin:
    """Curation lifecycle, delete, and aggregate helper methods."""

    _session: Session

    def update_curation(
        self,
        relation_id: str,
        *,
        curation_status: str,
        reviewed_by: str,
        reviewed_at: datetime | None = None,
    ) -> KernelRelation:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            msg = f"Relation {relation_id} not found"
            raise ValueError(msg)
        relation_model.curation_status = curation_status
        relation_model.reviewed_by = _as_uuid(reviewed_by)
        relation_model.reviewed_at = reviewed_at or datetime.now(UTC)
        self._session.flush()
        return KernelRelation.model_validate(relation_model)

    def delete(
        self,
        relation_id: str,
    ) -> bool:
        relation_model = self._session.get(RelationModel, _as_uuid(relation_id))
        if relation_model is None:
            return False
        self._session.delete(relation_model)
        self._session.flush()
        return True

    def delete_by_provenance(
        self,
        provenance_id: str,
    ) -> int:
        target_provenance_id = _as_uuid(provenance_id)
        relation_ids = list(
            set(
                self._session.scalars(
                    select(RelationEvidenceModel.relation_id).where(
                        RelationEvidenceModel.provenance_id == target_provenance_id,
                    ),
                ).all(),
            ),
        )
        if not relation_ids:
            return 0

        self._session.execute(
            sa_delete(RelationEvidenceModel).where(
                RelationEvidenceModel.provenance_id == target_provenance_id,
            ),
        )

        for relation_id in relation_ids:
            relation_model = self._session.get(RelationModel, relation_id)
            if relation_model is None:
                continue
            self._recompute_relation_aggregate(relation_id)

        delete_result = self._session.execute(
            sa_delete(RelationModel).where(
                RelationModel.id.in_(relation_ids),
                ~RelationModel.evidences.any(),
            ),
        )
        count = (
            int(delete_result.rowcount or 0)
            if isinstance(delete_result, CursorResult)
            else 0
        )
        self._session.flush()
        logger.info(
            "Rolled back %d relations for provenance %s",
            count,
            provenance_id,
        )
        return count

    def _recompute_relation_aggregate(
        self,
        relation_id: UUID,
    ) -> None:
        relation_model = self._session.get(RelationModel, relation_id)
        if relation_model is None:
            return

        evidences = list(
            self._session.scalars(
                select(RelationEvidenceModel).where(
                    RelationEvidenceModel.relation_id == relation_id,
                ),
            ).all(),
        )
        if not evidences:
            relation_model.aggregate_confidence = 0.0
            relation_model.source_count = 0
            relation_model.highest_evidence_tier = None
            relation_model.support_confidence = 0.0
            relation_model.refute_confidence = 0.0
            relation_model.distinct_source_family_count = 0
            relation_model.updated_at = datetime.now(UTC)
            return

        # Collapse support evidence into units keyed by source family.
        # Multiple spans from the same source document collapse into one unit.
        support_units: dict[str, float] = {}
        source_families: set[str] = set()
        highest_tier: str | None = None
        highest_rank = -1

        for evidence in evidences:
            confidence = _clamp_confidence(float(evidence.confidence))
            tier = _normalize_evidence_tier(evidence.evidence_tier)
            rank = _tier_rank(tier)
            if rank > highest_rank:
                highest_rank = rank
                highest_tier = tier

            # Determine source family key for collapsing
            family_key = _source_family_key(evidence)
            source_families.add(family_key)

            # Computational evidence does not contribute to support confidence
            if tier == "COMPUTATIONAL":
                continue

            # Relation evidence is supporting evidence. Low confidence weakens
            # support; it does not become refutation without REFUTE polarity.
            existing = support_units.get(family_key, 0.0)
            support_units[family_key] = max(existing, confidence)

        # Diminishing returns: aggregate = 1 - product(1 - unit_score)
        support_conf = _diminishing_confidence(support_units.values())

        refute_units = self._linked_refute_claim_units(relation_model)
        refute_conf = _diminishing_confidence(refute_units.values())

        # Backward-compatible aggregate uses all evidence
        all_product = 1.0
        for evidence in evidences:
            confidence = _clamp_confidence(float(evidence.confidence))
            all_product *= 1.0 - confidence

        relation_model.aggregate_confidence = _clamp_confidence(1.0 - all_product)
        relation_model.source_count = len(evidences)
        relation_model.highest_evidence_tier = highest_tier
        relation_model.support_confidence = support_conf
        relation_model.refute_confidence = refute_conf
        relation_model.distinct_source_family_count = len(source_families)
        relation_model.updated_at = datetime.now(UTC)

    def _linked_refute_claim_units(
        self,
        relation_model: RelationModel,
    ) -> dict[str, float]:
        """Return REFUTE confidence units linked to a canonical relation."""
        refute_claims = list(
            self._session.scalars(
                select(RelationClaimModel).where(
                    RelationClaimModel.research_space_id
                    == relation_model.research_space_id,
                    RelationClaimModel.linked_relation_id == relation_model.id,
                    RelationClaimModel.claim_status != "REJECTED",
                    RelationClaimModel.polarity == "REFUTE",
                    RelationClaimModel.assertion_class != "COMPUTATIONAL",
                ),
            ).all(),
        )
        if not refute_claims:
            return {}

        claim_ids = [claim.id for claim in refute_claims]
        claim_evidence_rows = list(
            self._session.scalars(
                select(ClaimEvidenceModel).where(
                    ClaimEvidenceModel.claim_id.in_(claim_ids),
                ),
            ).all(),
        )
        evidence_by_claim_id: dict[UUID, list[ClaimEvidenceModel]] = {}
        for evidence in claim_evidence_rows:
            evidence_by_claim_id.setdefault(evidence.claim_id, []).append(evidence)

        refute_units: dict[str, float] = {}
        for claim in refute_claims:
            claim_evidences = evidence_by_claim_id.get(claim.id, [])
            if not claim_evidences:
                family_key = _claim_source_family_key(claim)
                existing = refute_units.get(family_key, 0.0)
                refute_units[family_key] = max(
                    existing,
                    _clamp_confidence(float(claim.confidence)),
                )
                continue
            for evidence in claim_evidences:
                family_key = _source_family_key(evidence)
                existing = refute_units.get(family_key, 0.0)
                refute_units[family_key] = max(
                    existing,
                    _clamp_confidence(float(evidence.confidence)),
                )
        return refute_units
