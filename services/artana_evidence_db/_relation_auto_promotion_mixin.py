"""Auto-promotion mixin for service-local relation repositories."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.kernel_claim_models import RelationClaimModel
from artana_evidence_db.kernel_dictionary_models import RelationConstraintModel
from artana_evidence_db.kernel_entity_models import GraphEntityModel
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from artana_evidence_db.relation_autopromotion_policy import (
    DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER,
    PROMOTABLE_RELATION_CURATION_STATUSES,
    RELATION_AUTOPROMOTION_SPACE_POLICY_CUSTOM_PREFIX,
    RELATION_AUTOPROMOTION_SPACE_POLICY_SETTINGS_KEY,
    AutoPromotionDecision,
    AutoPromotionPolicy,
    normalize_relation_autopromotion_tier,
    normalize_relation_evidence_tier,
    parse_relation_autopromotion_bool,
    parse_relation_autopromotion_float,
    parse_relation_autopromotion_int,
    relation_evidence_tier_rank,
)
from artana_evidence_db.space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class _KernelRelationAutoPromotionMixin:
    """Mixins for relation auto-promotion policy resolution and evaluation."""

    _session: Session
    _auto_promotion_policy: AutoPromotionPolicy

    @staticmethod
    def _log_auto_promotion_decision(
        *,
        relation: RelationModel,
        decision: AutoPromotionDecision,
    ) -> None:
        logger.info(
            "Relation auto-promotion evaluated",
            extra={
                "event": "relation_auto_promotion",
                "relation_id": str(relation.id),
                "research_space_id": str(relation.research_space_id),
                "source_id": str(relation.source_id),
                "target_id": str(relation.target_id),
                "relation_type": relation.relation_type,
                "auto_promotion_outcome": decision.outcome,
                "auto_promotion_reason": decision.reason,
                "auto_promotion_previous_status": decision.previous_status,
                "auto_promotion_current_status": decision.current_status,
                "auto_promotion_all_computational": decision.all_computational,
                "auto_promotion_required_sources": decision.required_sources,
                "auto_promotion_required_confidence": decision.required_confidence,
                "auto_promotion_distinct_source_count": decision.distinct_source_count,
                "auto_promotion_distinct_document_count": decision.distinct_document_count,
                "auto_promotion_distinct_run_count": decision.distinct_run_count,
                "aggregate_confidence": decision.aggregate_confidence,
                "highest_evidence_tier": decision.highest_evidence_tier,
            },
        )

    def _resolve_auto_promotion_policy(
        self,
        *,
        research_space_id: UUID,
    ) -> AutoPromotionPolicy:
        default_policy = self._auto_promotion_policy
        settings_payload = self._extract_space_policy_settings(
            research_space_id=research_space_id,
        )
        if not settings_payload:
            return default_policy

        return AutoPromotionPolicy(
            enabled=parse_relation_autopromotion_bool(
                settings_payload.get("enabled"),
                default=default_policy.enabled,
            ),
            min_distinct_sources=parse_relation_autopromotion_int(
                settings_payload.get("min_distinct_sources"),
                default=default_policy.min_distinct_sources,
                minimum=1,
            ),
            min_aggregate_confidence=parse_relation_autopromotion_float(
                settings_payload.get("min_aggregate_confidence"),
                default=default_policy.min_aggregate_confidence,
            ),
            require_distinct_documents=parse_relation_autopromotion_bool(
                settings_payload.get("require_distinct_documents"),
                default=default_policy.require_distinct_documents,
            ),
            require_distinct_runs=parse_relation_autopromotion_bool(
                settings_payload.get("require_distinct_runs"),
                default=default_policy.require_distinct_runs,
            ),
            block_if_conflicting_evidence=parse_relation_autopromotion_bool(
                settings_payload.get("block_if_conflicting_evidence"),
                default=default_policy.block_if_conflicting_evidence,
            ),
            min_evidence_tier=normalize_relation_autopromotion_tier(
                settings_payload.get("min_evidence_tier"),
                default=default_policy.min_evidence_tier,
            ),
            conflicting_confidence_threshold=parse_relation_autopromotion_float(
                settings_payload.get("conflicting_confidence_threshold"),
                default=default_policy.conflicting_confidence_threshold,
            ),
        )

    def _extract_space_policy_settings(
        self,
        *,
        research_space_id: UUID,
    ) -> dict[str, object]:
        space = SqlAlchemyKernelSpaceRegistryRepository(self._session).get_by_id(
            research_space_id,
        )
        if space is None:
            return {}

        settings_payload: dict[str, object] = {}
        raw_policy = space.settings.get(
            RELATION_AUTOPROMOTION_SPACE_POLICY_SETTINGS_KEY,
        )
        if isinstance(raw_policy, dict):
            for key, value in raw_policy.items():
                settings_payload[str(key)] = value

        custom_settings = space.settings.get("custom")
        if isinstance(custom_settings, dict):
            for key, value in custom_settings.items():
                if not key.startswith(
                    RELATION_AUTOPROMOTION_SPACE_POLICY_CUSTOM_PREFIX,
                ):
                    continue
                normalized_key = key.removeprefix(
                    RELATION_AUTOPROMOTION_SPACE_POLICY_CUSTOM_PREFIX,
                )
                if normalized_key:
                    settings_payload[normalized_key] = value

        return settings_payload

    def _apply_auto_promotion(  # noqa: C901, PLR0911, PLR0912
        self,
        relation_id: UUID,
    ) -> AutoPromotionDecision:
        relation_model = self._session.get(RelationModel, relation_id)
        if relation_model is None:
            return AutoPromotionDecision(
                outcome="kept",
                reason="relation_not_found",
                previous_status="UNKNOWN",
                current_status="UNKNOWN",
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=0.0,
                highest_evidence_tier=None,
            )

        policy = self._resolve_auto_promotion_policy(
            research_space_id=relation_model.research_space_id,
        )
        if not policy.enabled:
            normalized_status = relation_model.curation_status.strip().upper()
            return AutoPromotionDecision(
                outcome="kept",
                reason="policy_disabled",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        normalized_status = relation_model.curation_status.strip().upper()
        if normalized_status not in PROMOTABLE_RELATION_CURATION_STATUSES:
            return AutoPromotionDecision(
                outcome="kept",
                reason="status_not_promotable",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        evidences = self._list_relation_evidences(relation_id)
        if not evidences:
            return AutoPromotionDecision(
                outcome="kept",
                reason="no_evidence",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=False,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=0,
                distinct_document_count=0,
                distinct_run_count=0,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        all_computational = self._all_evidence_is_computational(evidences)
        required_sources = policy.min_distinct_sources
        required_confidence = policy.min_aggregate_confidence

        if self._is_review_only_constraint(relation_model):
            return AutoPromotionDecision(
                outcome="kept",
                reason="review_only_constraint",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=self._count_distinct_sources(evidences),
                distinct_document_count=self._count_distinct_documents(evidences),
                distinct_run_count=self._count_distinct_runs(evidences),
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if all_computational:
            return AutoPromotionDecision(
                outcome="kept",
                reason="computational_only_not_promotable",
                previous_status=relation_model.curation_status,
                current_status=relation_model.curation_status,
                all_computational=True,
                required_sources=0,
                required_confidence=0.0,
                distinct_source_count=self._count_distinct_sources(evidences),
                distinct_document_count=self._count_distinct_documents(evidences),
                distinct_run_count=self._count_distinct_runs(evidences),
                aggregate_confidence=float(
                    relation_model.aggregate_confidence or 0.0,
                ),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        distinct_source_count = self._count_distinct_sources(evidences)
        distinct_document_count = self._count_distinct_documents(evidences)
        distinct_run_count = self._count_distinct_runs(evidences)

        if not all_computational and relation_evidence_tier_rank(
            relation_model.highest_evidence_tier,
        ) < relation_evidence_tier_rank(policy.min_evidence_tier):
            return AutoPromotionDecision(
                outcome="kept",
                reason="tier_below_threshold",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if policy.block_if_conflicting_evidence and self._has_linked_refute_claim(
            relation_model,
        ):
            return AutoPromotionDecision(
                outcome="kept",
                reason="conflicting_evidence_detected",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if distinct_source_count < required_sources:
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_distinct_sources",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if (
            policy.require_distinct_documents
            and 0 < distinct_document_count < required_sources
        ):
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_distinct_documents",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if policy.require_distinct_runs and 0 < distinct_run_count < required_sources:
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_distinct_runs",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        if relation_model.aggregate_confidence < required_confidence:
            return AutoPromotionDecision(
                outcome="kept",
                reason="insufficient_aggregate_confidence",
                previous_status=normalized_status,
                current_status=normalized_status,
                all_computational=all_computational,
                required_sources=required_sources,
                required_confidence=required_confidence,
                distinct_source_count=distinct_source_count,
                distinct_document_count=distinct_document_count,
                distinct_run_count=distinct_run_count,
                aggregate_confidence=float(relation_model.aggregate_confidence),
                highest_evidence_tier=relation_model.highest_evidence_tier,
            )

        relation_model.curation_status = "APPROVED"
        relation_model.reviewed_at = datetime.now(UTC)
        return AutoPromotionDecision(
            outcome="promoted",
            reason="thresholds_met",
            previous_status=normalized_status,
            current_status=relation_model.curation_status,
            all_computational=all_computational,
            required_sources=required_sources,
            required_confidence=required_confidence,
            distinct_source_count=distinct_source_count,
            distinct_document_count=distinct_document_count,
            distinct_run_count=distinct_run_count,
            aggregate_confidence=float(relation_model.aggregate_confidence),
            highest_evidence_tier=relation_model.highest_evidence_tier,
        )

    def _list_relation_evidences(
        self,
        relation_id: UUID,
    ) -> list[RelationEvidenceModel]:
        stmt = select(RelationEvidenceModel).where(
            RelationEvidenceModel.relation_id == relation_id,
        )
        return list(self._session.scalars(stmt).all())

    @staticmethod
    def _count_distinct_sources(evidences: list[RelationEvidenceModel]) -> int:
        distinct_sources: set[str] = set()
        for evidence in evidences:
            if evidence.provenance_id is not None:
                distinct_sources.add(f"provenance:{evidence.provenance_id}")
            elif evidence.source_document_id is not None:
                distinct_sources.add(f"document:{evidence.source_document_id}")
            elif evidence.source_document_ref is not None:
                distinct_sources.add(f"document_ref:{evidence.source_document_ref}")
            elif evidence.agent_run_id is not None:
                distinct_sources.add(f"run:{evidence.agent_run_id}")
            else:
                distinct_sources.add(f"evidence:{evidence.id}")
        return len(distinct_sources)

    @staticmethod
    def _count_distinct_documents(evidences: list[RelationEvidenceModel]) -> int:
        distinct_documents: set[str] = set()
        for evidence in evidences:
            if evidence.source_document_id is not None:
                distinct_documents.add(f"id:{evidence.source_document_id}")
            elif evidence.source_document_ref is not None:
                distinct_documents.add(f"ref:{evidence.source_document_ref}")
        return len(distinct_documents)

    @staticmethod
    def _count_distinct_runs(evidences: list[RelationEvidenceModel]) -> int:
        distinct_runs = {
            evidence.agent_run_id
            for evidence in evidences
            if evidence.agent_run_id is not None
        }
        return len(distinct_runs)

    @staticmethod
    def _all_evidence_is_computational(evidences: list[RelationEvidenceModel]) -> bool:
        if not evidences:
            return False
        return all(
            normalize_relation_evidence_tier(evidence.evidence_tier)
            == DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
            for evidence in evidences
        )

    def _is_review_only_constraint(
        self,
        relation_model: RelationModel,
    ) -> bool:
        """Check if the relation's triple matches a REVIEW_ONLY constraint."""
        source_entity = self._session.get(GraphEntityModel, relation_model.source_id)
        target_entity = self._session.get(GraphEntityModel, relation_model.target_id)
        if source_entity is None or target_entity is None:
            return False
        stmt = select(RelationConstraintModel).where(
            RelationConstraintModel.source_type == source_entity.entity_type,
            RelationConstraintModel.relation_type == relation_model.relation_type,
            RelationConstraintModel.target_type == target_entity.entity_type,
            RelationConstraintModel.review_status == "ACTIVE",
            RelationConstraintModel.is_active.is_(True),
        )
        constraint = self._session.scalars(stmt).first()
        if constraint is None:
            return False
        return getattr(constraint, "profile", "ALLOWED") == "REVIEW_ONLY"

    def _has_linked_refute_claim(
        self,
        relation_model: RelationModel,
    ) -> bool:
        refute_claim_id = self._session.scalar(
            select(RelationClaimModel.id)
            .where(
                RelationClaimModel.research_space_id
                == relation_model.research_space_id,
                RelationClaimModel.linked_relation_id == relation_model.id,
                RelationClaimModel.claim_status != "REJECTED",
                RelationClaimModel.polarity == "REFUTE",
                RelationClaimModel.assertion_class != "COMPUTATIONAL",
            )
            .limit(1),
        )
        return refute_claim_id is not None
