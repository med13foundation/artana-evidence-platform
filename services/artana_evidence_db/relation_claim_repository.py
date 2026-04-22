"""Service-local SQLAlchemy repository for relation claim ledger rows."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID, uuid4

from artana_evidence_db._relation_repository_shared import (
    _claim_source_family_key,
    _clamp_confidence,
    _diminishing_confidence,
    _source_family_key,
)
from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    RelationClaimModel,
)
from artana_evidence_db.kernel_relation_models import RelationModel
from artana_evidence_db.relation_claim_models import (
    KernelRelationClaim,
    KernelRelationConflictSummary,
    RelationClaimPersistability,
    RelationClaimPolarity,
    RelationClaimStatus,
    RelationClaimValidationState,
)
from sqlalchemy import false, func, select

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import Select

CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class SqlAlchemyKernelRelationClaimRepository:
    """SQLAlchemy implementation of relation claim ledger repository."""

    _HIGH_CONFIDENCE_THRESHOLD = 0.8
    _MEDIUM_CONFIDENCE_THRESHOLD = 0.6

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_type: str,
        relation_type: str,
        target_type: str,
        source_label: str | None,
        target_label: str | None,
        confidence: float,
        validation_state: RelationClaimValidationState,
        validation_reason: str | None,
        persistability: RelationClaimPersistability,
        assertion_class: str = "SOURCE_BACKED",
        claim_status: RelationClaimStatus = "OPEN",
        polarity: RelationClaimPolarity = "UNCERTAIN",
        claim_text: str | None = None,
        claim_section: str | None = None,
        linked_relation_id: str | None = None,
        source_document_ref: str | None = None,
        source_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationClaim:
        model = RelationClaimModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            source_document_id=_try_as_uuid(source_document_id),
            source_document_ref=_normalize_optional_text(source_document_ref),
            source_ref=_normalize_optional_text(source_ref),
            agent_run_id=agent_run_id,
            source_type=source_type,
            relation_type=relation_type,
            target_type=target_type,
            source_label=source_label,
            target_label=target_label,
            confidence=float(confidence),
            validation_state=validation_state,
            validation_reason=validation_reason,
            persistability=persistability,
            assertion_class=assertion_class,
            claim_status=claim_status,
            polarity=polarity,
            claim_text=claim_text,
            claim_section=claim_section,
            linked_relation_id=_try_as_uuid(linked_relation_id),
            metadata_payload=metadata or {},
        )
        self._session.add(model)
        self._session.flush()
        return KernelRelationClaim.model_validate(model)

    def get_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str,
    ) -> KernelRelationClaim | None:
        normalized_source_ref = _normalize_optional_text(source_ref)
        if normalized_source_ref is None:
            return None
        model = self._session.scalar(
            select(RelationClaimModel).where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.source_ref == normalized_source_ref,
            ),
        )
        if model is None:
            return None
        return KernelRelationClaim.model_validate(model)

    def get_by_id(self, claim_id: str) -> KernelRelationClaim | None:
        model = self._session.get(RelationClaimModel, _as_uuid(claim_id))
        if model is None:
            return None
        return KernelRelationClaim.model_validate(model)

    def list_by_ids(self, claim_ids: list[str]) -> list[KernelRelationClaim]:
        if not claim_ids:
            return []

        normalized_ids: list[str] = []
        uuids: list[UUID] = []
        seen: set[str] = set()
        for claim_id in claim_ids:
            normalized_uuid = _try_as_uuid(claim_id)
            if normalized_uuid is None:
                continue
            normalized_id = str(normalized_uuid)
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            normalized_ids.append(normalized_id)
            uuids.append(normalized_uuid)

        if not uuids:
            return []

        models = self._session.scalars(
            select(RelationClaimModel).where(RelationClaimModel.id.in_(uuids)),
        ).all()
        indexed = {str(model.id): model for model in models}
        return [
            KernelRelationClaim.model_validate(indexed[claim_id])
            for claim_id in normalized_ids
            if claim_id in indexed
        ]

    def find_by_linked_relation_ids(
        self,
        *,
        research_space_id: str,
        linked_relation_ids: list[str],
    ) -> list[KernelRelationClaim]:
        normalized_relation_ids: list[str] = []
        relation_uuids: list[UUID] = []
        seen: set[str] = set()
        for relation_id in linked_relation_ids:
            normalized_uuid = _try_as_uuid(relation_id)
            if normalized_uuid is None:
                continue
            normalized_id = str(normalized_uuid)
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            normalized_relation_ids.append(normalized_id)
            relation_uuids.append(normalized_uuid)

        if not relation_uuids:
            return []

        stmt = (
            select(RelationClaimModel)
            .where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.linked_relation_id.in_(relation_uuids),
            )
            .order_by(
                RelationClaimModel.linked_relation_id.asc(),
                RelationClaimModel.created_at.desc(),
            )
        )
        return [
            KernelRelationClaim.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationClaim]:
        stmt = self._build_filtered_stmt(
            research_space_id=research_space_id,
            claim_status=claim_status,
            assertion_class=assertion_class,
            validation_state=validation_state,
            persistability=persistability,
            polarity=polarity,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
        ).order_by(RelationClaimModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelationClaim.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        claim_status: RelationClaimStatus | None = None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None = None,
        persistability: RelationClaimPersistability | None = None,
        polarity: RelationClaimPolarity | None = None,
        source_document_id: str | None = None,
        relation_type: str | None = None,
        linked_relation_id: str | None = None,
        certainty_band: CertaintyBand | None = None,
    ) -> int:
        stmt = self._build_filtered_stmt(
            research_space_id=research_space_id,
            claim_status=claim_status,
            assertion_class=assertion_class,
            validation_state=validation_state,
            persistability=persistability,
            polarity=polarity,
            source_document_id=source_document_id,
            relation_type=relation_type,
            linked_relation_id=linked_relation_id,
            certainty_band=certainty_band,
        ).subquery()
        return int(
            self._session.execute(
                select(func.count()).select_from(stmt),
            ).scalar_one(),
        )

    def update_triage_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
        triaged_by: str,
    ) -> KernelRelationClaim:
        model = self._session.get(RelationClaimModel, _as_uuid(claim_id))
        if model is None:
            msg = f"Relation claim {claim_id} not found"
            raise ValueError(msg)
        model.claim_status = claim_status
        model.triaged_by = _as_uuid(triaged_by)
        model.triaged_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return KernelRelationClaim.model_validate(model)

    def link_relation(
        self,
        claim_id: str,
        *,
        linked_relation_id: str,
    ) -> KernelRelationClaim:
        model = self._session.get(RelationClaimModel, _as_uuid(claim_id))
        if model is None:
            msg = f"Relation claim {claim_id} not found"
            raise ValueError(msg)
        model.linked_relation_id = _as_uuid(linked_relation_id)
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return KernelRelationClaim.model_validate(model)

    def clear_relation_link(
        self,
        claim_id: str,
    ) -> KernelRelationClaim:
        model = self._session.get(RelationClaimModel, _as_uuid(claim_id))
        if model is None:
            msg = f"Relation claim {claim_id} not found"
            raise ValueError(msg)
        model.linked_relation_id = None
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return KernelRelationClaim.model_validate(model)

    def set_system_status(
        self,
        claim_id: str,
        *,
        claim_status: RelationClaimStatus,
    ) -> KernelRelationClaim:
        model = self._session.get(RelationClaimModel, _as_uuid(claim_id))
        if model is None:
            msg = f"Relation claim {claim_id} not found"
            raise ValueError(msg)
        model.claim_status = claim_status
        model.triaged_by = None
        model.triaged_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        self._session.flush()
        return KernelRelationClaim.model_validate(model)

    def find_conflicts_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationConflictSummary]:
        rows = self._session.scalars(
            select(RelationClaimModel).where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.linked_relation_id.is_not(None),
                RelationClaimModel.claim_status != "REJECTED",
                RelationClaimModel.polarity.in_(("SUPPORT", "REFUTE")),
            ),
        ).all()

        grouped_support: dict[UUID, list[RelationClaimModel]] = defaultdict(list)
        grouped_refute: dict[UUID, list[RelationClaimModel]] = defaultdict(list)
        for row in rows:
            relation_id = row.linked_relation_id
            if relation_id is None:
                continue
            if row.polarity == "SUPPORT":
                grouped_support[relation_id].append(row)
            elif row.polarity == "REFUTE":
                grouped_refute[relation_id].append(row)

        conflicts: list[KernelRelationConflictSummary] = []
        relation_ids = set(grouped_support).intersection(set(grouped_refute))
        for relation_id in relation_ids:
            support_claims = grouped_support[relation_id]
            refute_claims = grouped_refute[relation_id]
            support_ids = tuple(claim.id for claim in support_claims)
            refute_ids = tuple(claim.id for claim in refute_claims)
            relation_model = self._session.get(RelationModel, relation_id)
            conflicts.append(
                KernelRelationConflictSummary(
                    relation_id=relation_id,
                    support_count=len(support_ids),
                    refute_count=len(refute_ids),
                    support_claim_ids=support_ids,
                    refute_claim_ids=refute_ids,
                    support_confidence=self._aggregate_claim_polarity_confidence(
                        support_claims,
                    ),
                    refute_confidence=self._aggregate_claim_polarity_confidence(
                        refute_claims,
                    ),
                    relation_type=(
                        relation_model.relation_type
                        if relation_model is not None
                        else None
                    ),
                ),
            )

        conflicts.sort(
            key=lambda conflict: (
                -(conflict.support_count + conflict.refute_count),
                str(conflict.relation_id),
            ),
        )
        start = max(offset or 0, 0)
        if limit is None:
            return conflicts[start:]
        return conflicts[start : start + max(limit, 0)]

    def count_conflicts_by_research_space(
        self,
        research_space_id: str,
    ) -> int:
        return len(
            self.find_conflicts_by_research_space(
                research_space_id,
            ),
        )

    def _aggregate_claim_polarity_confidence(
        self,
        claims: list[RelationClaimModel],
    ) -> float:
        active_claims = [
            claim for claim in claims if claim.assertion_class != "COMPUTATIONAL"
        ]
        if not active_claims:
            return 0.0

        claim_ids = [claim.id for claim in active_claims]
        evidence_rows = list(
            self._session.scalars(
                select(ClaimEvidenceModel).where(
                    ClaimEvidenceModel.claim_id.in_(claim_ids),
                ),
            ).all(),
        )
        evidence_by_claim_id: dict[UUID, list[ClaimEvidenceModel]] = defaultdict(list)
        for evidence in evidence_rows:
            evidence_by_claim_id[evidence.claim_id].append(evidence)

        units: dict[str, float] = {}
        for claim in active_claims:
            claim_evidences = evidence_by_claim_id.get(claim.id, [])
            if not claim_evidences:
                family_key = _claim_source_family_key(claim)
                units[family_key] = max(
                    units.get(family_key, 0.0),
                    _clamp_confidence(float(claim.confidence)),
                )
                continue
            for evidence in claim_evidences:
                family_key = _source_family_key(evidence)
                units[family_key] = max(
                    units.get(family_key, 0.0),
                    _clamp_confidence(float(evidence.confidence)),
                )
        return _diminishing_confidence(units.values())

    def _build_filtered_stmt(  # noqa: C901, PLR0912, PLR0913
        self,
        *,
        research_space_id: str,
        claim_status: RelationClaimStatus | None,
        assertion_class: str | None = None,
        validation_state: RelationClaimValidationState | None,
        persistability: RelationClaimPersistability | None,
        polarity: RelationClaimPolarity | None,
        source_document_id: str | None,
        relation_type: str | None,
        linked_relation_id: str | None,
        certainty_band: CertaintyBand | None,
    ) -> Select[tuple[RelationClaimModel]]:
        stmt = select(RelationClaimModel).where(
            RelationClaimModel.research_space_id == _as_uuid(research_space_id),
        )
        if claim_status is not None:
            stmt = stmt.where(RelationClaimModel.claim_status == claim_status)
        if assertion_class is not None:
            stmt = stmt.where(RelationClaimModel.assertion_class == assertion_class)
        if validation_state is not None:
            stmt = stmt.where(RelationClaimModel.validation_state == validation_state)
        if persistability is not None:
            stmt = stmt.where(RelationClaimModel.persistability == persistability)
        if polarity is not None:
            stmt = stmt.where(RelationClaimModel.polarity == polarity)
        if relation_type is not None:
            stmt = stmt.where(RelationClaimModel.relation_type == relation_type)
        source_document_uuid = _try_as_uuid(source_document_id)
        if source_document_id is not None:
            if source_document_uuid is None:
                return stmt.where(false())
            stmt = stmt.where(
                RelationClaimModel.source_document_id == source_document_uuid,
            )
        linked_relation_uuid = _try_as_uuid(linked_relation_id)
        if linked_relation_id is not None:
            if linked_relation_uuid is None:
                return stmt.where(false())
            stmt = stmt.where(
                RelationClaimModel.linked_relation_id == linked_relation_uuid,
            )
        if certainty_band == "HIGH":
            stmt = stmt.where(
                RelationClaimModel.confidence >= self._HIGH_CONFIDENCE_THRESHOLD,
            )
        elif certainty_band == "MEDIUM":
            stmt = stmt.where(
                RelationClaimModel.confidence >= self._MEDIUM_CONFIDENCE_THRESHOLD,
                RelationClaimModel.confidence < self._HIGH_CONFIDENCE_THRESHOLD,
            )
        elif certainty_band == "LOW":
            stmt = stmt.where(
                RelationClaimModel.confidence < self._MEDIUM_CONFIDENCE_THRESHOLD,
            )
        return stmt


__all__ = [
    "CertaintyBand",
    "SqlAlchemyKernelRelationClaimRepository",
]
