"""Application service for graph-connection agent orchestration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from src.application.agents.services._fact_assessment_scoring import (
    fact_evidence_weight,
    run_confidence_from_assessments,
)
from src.application.agents.services._graph_connection_fallback_helpers import (
    build_seed_neighbourhood_fallback_relations,
    resolve_relations_for_persistence,
)
from src.application.agents.services.governance_service import (
    GovernanceDecision,
    GovernanceService,
)
from src.domain.agents.contexts.graph_connection_context import GraphConnectionContext
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.claim_participant_service import (
        KernelClaimParticipantService,
    )
    from artana_evidence_db.kernel_repositories import (
        KernelClaimEvidenceRepository,
        KernelClaimParticipantRepository,
        KernelEntityRepository,
        KernelRelationClaimRepository,
        KernelRelationProjectionSourceRepository,
        KernelRelationRepository,
    )
    from artana_evidence_db.kernel_services import (
        KernelRelationProjectionMaterializationService,
    )
    from artana_evidence_db.ports import SpaceSettingsPort

    from src.domain.agents.contracts.graph_connection import (
        GraphConnectionContract,
        ProposedRelation,
    )
    from src.domain.agents.graph_domain_ai_contracts import GraphConnectorExtension
    from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
    from src.type_definitions.common import ResearchSpaceSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GraphConnectionServiceDependencies:
    """Dependencies required by graph-connection orchestration."""

    graph_connection_agent: GraphConnectionPort
    graph_connection_prompt: GraphConnectorExtension
    relation_repository: KernelRelationRepository
    entity_repository: KernelEntityRepository | None = None
    relation_claim_repository: KernelRelationClaimRepository | None = None
    claim_participant_repository: KernelClaimParticipantRepository | None = None
    claim_participant_service: KernelClaimParticipantService | None = None
    claim_evidence_repository: KernelClaimEvidenceRepository | None = None
    relation_projection_source_repository: (
        KernelRelationProjectionSourceRepository | None
    ) = None
    relation_projection_materialization_service: (
        KernelRelationProjectionMaterializationService | None
    ) = None
    governance_service: GovernanceService | None = None
    space_settings_port: SpaceSettingsPort | None = None
    review_queue_submitter: Callable[[str, str, str | None, str], None] | None = None
    rollback_on_error: Callable[[], None] | None = None


@dataclass(frozen=True)
class GraphConnectionOutcome:
    """Outcome of one graph-connection discovery run."""

    seed_entity_id: str
    research_space_id: str
    status: Literal["discovered", "failed"]
    reason: str
    review_required: bool
    shadow_mode: bool
    wrote_to_graph: bool
    run_id: str | None = None
    proposed_relations_count: int = 0
    persisted_relations_count: int = 0
    rejected_candidates_count: int = 0
    errors: tuple[str, ...] = ()


class GraphConnectionService:
    """Coordinate Graph Connection Agent -> Governance -> relation upsert."""

    def __init__(self, dependencies: GraphConnectionServiceDependencies) -> None:
        self._agent = dependencies.graph_connection_agent
        self._graph_connection_prompt = dependencies.graph_connection_prompt
        self._relations = dependencies.relation_repository
        self._entities = dependencies.entity_repository
        self._relation_claims = dependencies.relation_claim_repository
        self._claim_participants = dependencies.claim_participant_repository
        self._claim_participant_service = dependencies.claim_participant_service
        self._claim_evidence = dependencies.claim_evidence_repository
        self._relation_projection_sources = (
            dependencies.relation_projection_source_repository
        )
        self._materializer = dependencies.relation_projection_materialization_service
        self._governance = dependencies.governance_service or GovernanceService()
        self._space_settings = dependencies.space_settings_port
        self._review_queue_submitter = dependencies.review_queue_submitter
        self._rollback_on_error = dependencies.rollback_on_error

    async def discover_connections_for_seed(  # noqa: PLR0913, C901, PLR0912, PLR0915
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        source_id: str | None = None,
        source_type: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
        model_id: str | None = None,
        relation_types: list[str] | None = None,
        max_depth: int = 2,
        shadow_mode: bool | None = None,
        pipeline_run_id: str | None = None,
        fallback_relations: tuple[ProposedRelation, ...] | None = None,
    ) -> GraphConnectionOutcome:
        """Run one graph-connection discovery pass for a seed entity."""
        resolved_research_space_id = research_space_id.strip()
        resolved_seed_entity_id = seed_entity_id.strip()
        resolved_settings = self._resolve_research_space_settings(
            research_space_id=resolved_research_space_id,
            provided_settings=research_space_settings,
        )
        resolved_source_type = self._graph_connection_prompt.resolve_source_type(
            source_type,
        )
        requested_shadow_mode = shadow_mode if isinstance(shadow_mode, bool) else False
        context = GraphConnectionContext(
            seed_entity_id=resolved_seed_entity_id,
            source_type=resolved_source_type,
            research_space_id=resolved_research_space_id,
            source_id=(
                source_id.strip()
                if isinstance(source_id, str) and source_id.strip()
                else None
            ),
            pipeline_run_id=(
                pipeline_run_id.strip()
                if isinstance(pipeline_run_id, str) and pipeline_run_id.strip()
                else None
            ),
            research_space_settings=resolved_settings or {},
            relation_types=relation_types,
            max_depth=max_depth,
            shadow_mode=requested_shadow_mode,
        )
        contract = await self._agent.discover(context, model_id=model_id)
        run_id = self._resolve_run_id(contract)
        assessment_scores = tuple(
            fact_evidence_weight(relation)
            for relation in (
                *contract.proposed_relations,
                *contract.rejected_candidates,
            )
        )
        effective_run_confidence = run_confidence_from_assessments(
            assessment_scores,
        )
        governance = self._governance.evaluate(
            confidence_score=effective_run_confidence,
            assessment_scores=assessment_scores,
            evidence_count=len(contract.evidence),
            decision=contract.decision,
            requested_shadow_mode=requested_shadow_mode,
            research_space_settings=resolved_settings,
            relation_types=self._resolve_relation_types(contract),
        )
        logger.info(
            "Graph connection governance decision evaluated",
            extra={
                "research_space_id": resolved_research_space_id,
                "seed_entity_id": resolved_seed_entity_id,
                "run_id": run_id,
                "decision": contract.decision,
                "derived_confidence_score": effective_run_confidence,
                "effective_run_confidence": effective_run_confidence,
                "requires_review": governance.requires_review,
                "reason": governance.reason,
            },
        )
        if governance.requires_review:
            self._submit_review_item(
                research_space_id=resolved_research_space_id,
                seed_entity_id=resolved_seed_entity_id,
                reason=governance.reason,
            )

        if governance.shadow_mode:
            return self._build_outcome(
                contract=contract,
                governance=governance,
                research_space_id=resolved_research_space_id,
                seed_entity_id=resolved_seed_entity_id,
                run_id=run_id,
                wrote_to_graph=False,
                reason="shadow_mode_enabled",
                review_required=governance.requires_review,
            )

        external_fallback_relations = tuple(fallback_relations or ())
        allow_write = governance.allow_write or bool(external_fallback_relations)
        if not allow_write:
            return self._build_outcome(
                contract=contract,
                governance=governance,
                research_space_id=resolved_research_space_id,
                seed_entity_id=resolved_seed_entity_id,
                run_id=run_id,
                wrote_to_graph=False,
                reason=governance.reason,
                review_required=governance.requires_review,
                errors=(governance.reason,),
            )

        (
            relations_for_persistence,
            promoted_rejected_count,
            extraction_fallback_count,
        ) = resolve_relations_for_persistence(
            tuple(contract.proposed_relations),
            tuple(contract.rejected_candidates),
        )
        if external_fallback_relations:
            (
                relations_for_persistence,
                promoted_rejected_count,
                extraction_fallback_count,
            ) = resolve_relations_for_persistence(
                tuple(contract.proposed_relations),
                tuple(contract.rejected_candidates),
                fallback_relations=external_fallback_relations,
                prefer_fallback=not governance.allow_write,
            )
        used_neighbourhood_fallback = False
        used_extraction_fallback = extraction_fallback_count > 0
        if not relations_for_persistence:
            relations_for_persistence = build_seed_neighbourhood_fallback_relations(
                self._relations,
                seed_entity_id=contract.seed_entity_id,
            )
            used_neighbourhood_fallback = bool(relations_for_persistence)

        fallback_requires_pending_review = (
            promoted_rejected_count > 0
            or used_neighbourhood_fallback
            or used_extraction_fallback
            or not governance.allow_write
        )
        review_required = governance.requires_review or fallback_requires_pending_review
        if promoted_rejected_count > 0 and not governance.requires_review:
            self._submit_review_item(
                research_space_id=resolved_research_space_id,
                seed_entity_id=resolved_seed_entity_id,
                reason="promoted_rejected_candidates",
            )
        if used_extraction_fallback and not governance.requires_review:
            self._submit_review_item(
                research_space_id=resolved_research_space_id,
                seed_entity_id=resolved_seed_entity_id,
                reason="extraction_relation_fallback",
            )
        if used_neighbourhood_fallback and not governance.requires_review:
            self._submit_review_item(
                research_space_id=resolved_research_space_id,
                seed_entity_id=resolved_seed_entity_id,
                reason="seed_neighbourhood_fallback",
            )

        persisted_count = 0
        persistence_errors: list[str] = []
        for relation in relations_for_persistence:
            normalized_relation_type = normalize_relation_type(relation.relation_type)
            if not normalized_relation_type:
                persistence_errors.append("relation_type_missing")
                continue
            try:
                materialized_relation_id = self._record_claim_backed_projection(
                    research_space_id=resolved_research_space_id,
                    relation=relation,
                    normalized_relation_type=normalized_relation_type,
                    run_id=run_id,
                )
                if materialized_relation_id is not None:
                    self._enqueue_relation_review_item(
                        relation_id=materialized_relation_id,
                        research_space_id=resolved_research_space_id,
                        fallback_requires_pending_review=fallback_requires_pending_review,
                    )
                persisted_count += 1
                logger.info(
                    "Graph relation persisted from connection discovery",
                    extra={
                        "research_space_id": research_space_id,
                        "seed_entity_id": resolved_seed_entity_id,
                        "pipeline_run_id": pipeline_run_id,
                        "graph_connection_run_id": run_id,
                        "relation_type": normalized_relation_type,
                        "relation_source_id": relation.source_id,
                        "relation_target_id": relation.target_id,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                self._rollback_relation_write(context="graph_connection_persist")
                persistence_errors.append(
                    self._map_relation_persistence_error_code(exc),
                )
                logger.warning(
                    "Graph relation persistence failed",
                    extra={
                        "research_space_id": research_space_id,
                        "seed_entity_id": resolved_seed_entity_id,
                        "pipeline_run_id": pipeline_run_id,
                        "graph_connection_run_id": run_id,
                        "relation_type": normalized_relation_type,
                        "relation_source_id": relation.source_id,
                        "relation_target_id": relation.target_id,
                        "error_code": self._map_relation_persistence_error_code(exc),
                        "error": str(exc),
                    },
                )

        wrote_to_graph = persisted_count > 0
        reason = "processed" if wrote_to_graph else "no_relations_persisted"
        if wrote_to_graph and used_extraction_fallback:
            reason = "processed_extraction_relation_fallback"
        elif wrote_to_graph and promoted_rejected_count > 0:
            reason = "processed_promoted_rejected_candidates"
        elif wrote_to_graph and used_neighbourhood_fallback:
            reason = "processed_seed_neighbourhood_fallback"
        if persistence_errors and not wrote_to_graph:
            reason = "relation_persistence_failed"

        return self._build_outcome(
            contract=contract,
            governance=governance,
            research_space_id=resolved_research_space_id,
            seed_entity_id=resolved_seed_entity_id,
            run_id=run_id,
            wrote_to_graph=wrote_to_graph,
            reason=reason,
            review_required=review_required,
            persisted_relations_count=persisted_count,
            errors=tuple(persistence_errors),
        )

    def _record_claim_backed_projection(
        self,
        *,
        research_space_id: str,
        relation: ProposedRelation,
        normalized_relation_type: str,
        run_id: str | None,
    ) -> str | None:
        if (
            self._entities is None
            or self._relation_claims is None
            or self._claim_participants is None
            or self._claim_evidence is None
            or self._materializer is None
        ):
            msg = (
                "Graph connection persistence requires claim-backed projection "
                "dependencies"
            )
            raise ValueError(msg)
        source_entity = self._entities.get_by_id(relation.source_id)
        target_entity = self._entities.get_by_id(relation.target_id)
        if source_entity is None or target_entity is None:
            msg = "Graph connection relation endpoints must exist before projection"
            raise ValueError(msg)
        claim = self._relation_claims.create(
            research_space_id=research_space_id,
            source_document_id=None,
            agent_run_id=run_id,
            source_type=source_entity.entity_type,
            relation_type=normalized_relation_type,
            target_type=target_entity.entity_type,
            source_label=source_entity.display_label,
            target_label=target_entity.display_label,
            confidence=relation.confidence,
            validation_state="ALLOWED",
            validation_reason="Created via graph connection projection",
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text=relation.evidence_summary,
            claim_section=None,
            linked_relation_id=None,
            metadata={
                "origin": "graph_connection",
                "reasoning": relation.reasoning,
                "supporting_provenance_ids": relation.supporting_provenance_ids,
                "supporting_document_count": relation.supporting_document_count,
                "source_entity_id": relation.source_id,
                "target_entity_id": relation.target_id,
            },
        )
        if self._claim_participant_service is not None:
            self._claim_participant_service.create_participant(
                claim_id=str(claim.id),
                research_space_id=research_space_id,
                role="SUBJECT",
                label=source_entity.display_label,
                entity_id=str(source_entity.id),
                position=0,
                qualifiers={"origin": "graph_connection"},
            )
            self._claim_participant_service.create_participant(
                claim_id=str(claim.id),
                research_space_id=research_space_id,
                role="OBJECT",
                label=target_entity.display_label,
                entity_id=str(target_entity.id),
                position=1,
                qualifiers={"origin": "graph_connection"},
            )
        elif self._claim_participants is not None:
            self._claim_participants.create(
                claim_id=str(claim.id),
                research_space_id=research_space_id,
                role="SUBJECT",
                label=source_entity.display_label,
                entity_id=str(source_entity.id),
                position=0,
                qualifiers={"origin": "graph_connection"},
            )
            self._claim_participants.create(
                claim_id=str(claim.id),
                research_space_id=research_space_id,
                role="OBJECT",
                label=target_entity.display_label,
                entity_id=str(target_entity.id),
                position=1,
                qualifiers={"origin": "graph_connection"},
            )
        self._claim_evidence.create(
            claim_id=str(claim.id),
            source_document_id=None,
            agent_run_id=run_id,
            sentence=None,
            sentence_source=None,
            sentence_confidence=None,
            sentence_rationale=None,
            figure_reference=None,
            table_reference=None,
            confidence=relation.confidence,
            metadata={
                "origin": "graph_connection",
                "evidence_summary": relation.evidence_summary,
                "evidence_tier": relation.evidence_tier,
                "supporting_provenance_ids": relation.supporting_provenance_ids,
                "provenance_id": (
                    relation.supporting_provenance_ids[0]
                    if relation.supporting_provenance_ids
                    else None
                ),
                "reasoning": relation.reasoning,
            },
        )
        materialized = self._materializer.materialize_support_claim(
            claim_id=str(claim.id),
            research_space_id=research_space_id,
            projection_origin="GRAPH_CONNECTION",
        )
        if materialized.relation is None:
            return None
        return str(materialized.relation.id)

    def _rollback_relation_write(self, *, context: str) -> None:
        rollback = self._rollback_on_error
        if rollback is None:
            return
        try:
            rollback()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Graph connection rollback failed (context=%s): %s",
                context,
                exc,
            )

    async def close(self) -> None:
        """Release resources held by the underlying graph-connection adapter."""
        await self._agent.close()

    def _resolve_research_space_settings(
        self,
        *,
        research_space_id: str,
        provided_settings: ResearchSpaceSettings | None,
    ) -> ResearchSpaceSettings | None:
        if provided_settings is not None:
            return provided_settings
        if self._space_settings is None:
            return None
        try:
            space_uuid = UUID(research_space_id)
        except ValueError:
            return None
        settings = self._space_settings.get_settings(space_uuid)
        if settings is None:
            return None
        return self._normalize_research_space_settings(settings)

    @staticmethod
    def _normalize_research_space_settings(  # noqa: C901
        raw_settings: Mapping[str, object],
    ) -> ResearchSpaceSettings:
        settings: ResearchSpaceSettings = {}

        auto_approve = raw_settings.get("auto_approve")
        if isinstance(auto_approve, bool):
            settings["auto_approve"] = auto_approve

        require_review = raw_settings.get("require_review")
        if isinstance(require_review, bool):
            settings["require_review"] = require_review

        review_threshold = raw_settings.get("review_threshold")
        if isinstance(review_threshold, float | int):
            settings["review_threshold"] = max(0.0, min(float(review_threshold), 1.0))

        relation_default_review_threshold = raw_settings.get(
            "relation_default_review_threshold",
        )
        if isinstance(relation_default_review_threshold, float | int):
            settings["relation_default_review_threshold"] = max(
                0.0,
                min(float(relation_default_review_threshold), 1.0),
            )

        raw_relation_thresholds = raw_settings.get("relation_review_thresholds")
        if isinstance(raw_relation_thresholds, Mapping):
            relation_thresholds: dict[str, float] = {}
            for raw_relation_type, raw_threshold in raw_relation_thresholds.items():
                if not isinstance(raw_relation_type, str):
                    continue
                normalized_relation_type = raw_relation_type.strip().upper()
                if not normalized_relation_type:
                    continue
                if isinstance(raw_threshold, float | int):
                    relation_thresholds[normalized_relation_type] = max(
                        0.0,
                        min(float(raw_threshold), 1.0),
                    )
            if relation_thresholds:
                settings["relation_review_thresholds"] = relation_thresholds

        return settings

    @staticmethod
    def _resolve_relation_types(
        contract: GraphConnectionContract,
    ) -> tuple[str, ...] | None:
        relation_types: list[str] = []
        for relation in contract.proposed_relations:
            normalized = normalize_relation_type(relation.relation_type)
            if not normalized or normalized in relation_types:
                continue
            relation_types.append(normalized)
        return tuple(relation_types) if relation_types else None

    @staticmethod
    def _map_relation_persistence_error_code(  # noqa: C901, PLR0911
        exc: Exception,
    ) -> str:
        message = str(exc)
        if isinstance(exc, IntegrityError) and exc.orig is not None:
            message = str(exc.orig)
        normalized = message.strip().lower()

        if "requires evidence but none exists at commit" in normalized:
            return "relation_requires_evidence"
        if "not allowed by active relation constraints" in normalized:
            return "relation_triple_not_allowed"
        if (
            "fk_relations_source_space_entities" in normalized
            or "source_id" in normalized
            and "does not belong to research_space_id" in normalized
        ):
            return "relation_source_cross_space"
        if (
            "fk_relations_target_space_entities" in normalized
            or "target_id" in normalized
            and "does not belong to research_space_id" in normalized
        ):
            return "relation_target_cross_space"
        if (
            "fk_relations_relation_type_dictionary" in normalized
            or "active dictionary_relation_type" in normalized
        ):
            return "relation_type_invalid_or_inactive"
        if (
            "fk_entities_entity_type_dictionary" in normalized
            or "active dictionary_entity_type" in normalized
        ):
            return "entity_type_invalid_or_inactive"
        if "uq_relations_canonical_edge" in normalized:
            return "relation_edge_duplicate"
        if "foreign key" in normalized:
            return "relation_foreign_key_violation"
        if isinstance(exc, ValueError | TypeError):
            return "relation_payload_invalid"
        if isinstance(exc, IntegrityError):
            return "relation_integrity_violation"
        return "relation_persistence_failed"

    def _submit_review_item(
        self,
        *,
        research_space_id: str,
        seed_entity_id: str,
        reason: str,
    ) -> None:
        submitter = self._review_queue_submitter
        if submitter is None:
            return
        try:
            submitter(
                "graph_connection_seed",
                seed_entity_id,
                research_space_id,
                self._review_priority_for_reason(reason),
            )
        except Exception as exc:  # noqa: BLE001 - do not block graph writes
            logger.warning(
                "Failed to enqueue graph-connection review item for seed=%s: %s",
                seed_entity_id,
                exc,
            )

    def _enqueue_relation_review_item(
        self,
        *,
        relation_id: str,
        research_space_id: str,
        fallback_requires_pending_review: bool,
    ) -> None:
        submitter = self._review_queue_submitter
        if submitter is None:
            return
        try:
            submitter(
                "relation",
                relation_id,
                research_space_id,
                "medium" if fallback_requires_pending_review else "low",
            )
        except Exception as exc:  # noqa: BLE001 - do not block graph writes
            logger.warning(
                "Failed to enqueue graph-connection relation review item for relation=%s: %s",
                relation_id,
                exc,
            )

    @staticmethod
    def _review_priority_for_reason(reason: str) -> str:
        if reason in {"agent_requested_escalation", "evidence_required"}:
            return "high"
        if reason in {
            "confidence_below_threshold",
            "promoted_rejected_candidates",
            "extraction_relation_fallback",
            "seed_neighbourhood_fallback",
        }:
            return "medium"
        return "low"

    @staticmethod
    def _resolve_run_id(contract: GraphConnectionContract) -> str | None:
        run_id = contract.agent_run_id
        if not isinstance(run_id, str):
            return None
        normalized = run_id.strip()
        return normalized or None

    @staticmethod
    def _build_outcome(  # noqa: PLR0913
        *,
        contract: GraphConnectionContract,
        governance: GovernanceDecision,
        research_space_id: str,
        seed_entity_id: str,
        run_id: str | None,
        wrote_to_graph: bool,
        reason: str,
        review_required: bool,
        persisted_relations_count: int = 0,
        errors: tuple[str, ...] = (),
    ) -> GraphConnectionOutcome:
        status: Literal["discovered", "failed"] = (
            "discovered" if wrote_to_graph or governance.shadow_mode else "failed"
        )
        return GraphConnectionOutcome(
            seed_entity_id=seed_entity_id,
            research_space_id=research_space_id,
            status=status,
            reason=reason,
            review_required=review_required,
            shadow_mode=governance.shadow_mode,
            wrote_to_graph=wrote_to_graph,
            run_id=run_id,
            proposed_relations_count=len(contract.proposed_relations),
            persisted_relations_count=persisted_relations_count,
            rejected_candidates_count=len(contract.rejected_candidates),
            errors=errors,
        )


__all__ = [
    "GraphConnectionOutcome",
    "GraphConnectionService",
    "GraphConnectionServiceDependencies",
]
