"""Application service for derived reasoning paths."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from artana_evidence_db.claim_relation_models import (
    ClaimRelationReviewStatus,
    ClaimRelationType,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.read_model_support import (
    GraphReadModelTrigger,
    GraphReadModelUpdate,
    GraphReadModelUpdateDispatcher,
)
from artana_evidence_db.read_models import EntityMechanismPathModel
from artana_evidence_db.reasoning_path_models import (
    ReasoningPathKind,
    ReasoningPathStatus,
)
from artana_evidence_db.reasoning_path_support import (
    KernelMechanismPathCandidate,
    KernelReasoningPathDetail,
    ReasoningPathListResult,
    ReasoningPathRebuildSummary,
    build_adjacency,
    collect_paths_from_root,
    resolve_ordered_canonical_relation_ids,
    resolve_ordered_claim_ids,
    resolve_participant_anchor_entities,
)
from artana_evidence_db.relation_claim_models import (
    RelationClaimPersistability,
    RelationClaimPolarity,
    RelationClaimStatus,
    RelationClaimValidationState,
)
from sqlalchemy import select
from sqlalchemy.orm import aliased

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import (
        KernelClaimEvidence,
        KernelClaimParticipant,
        KernelClaimRelation,
        KernelReasoningPath,
        KernelReasoningPathStep,
        KernelRelation,
        KernelRelationClaim,
    )
    from artana_evidence_db.kernel_domain_ports import ReasoningPathWriteBundle
    from artana_evidence_db.ports import SpaceRegistryPort
    from sqlalchemy.orm import Session


class ReasoningPathRepositoryLike(Protocol):
    """Minimal repository surface needed by reasoning-path orchestration."""

    def replace_for_space(
        self,
        *,
        research_space_id: str,
        bundles: list[ReasoningPathWriteBundle],
        replace_existing: bool,
    ) -> list[KernelReasoningPath]: ...

    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReasoningPath]: ...

    def count_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
    ) -> int: ...

    def get_path(
        self,
        *,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPath | None: ...

    def list_steps_for_path_ids(
        self,
        *,
        path_ids: list[str],
    ) -> dict[str, list[KernelReasoningPathStep]]: ...

    def mark_stale_for_claim_ids(
        self,
        *,
        research_space_id: str,
        claim_ids: list[str],
    ) -> int: ...

    def mark_stale_for_claim_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> int: ...


class RelationClaimServiceLike(Protocol):
    """Minimal claim service surface needed by reasoning-path orchestration."""

    def list_by_research_space(
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
        certainty_band: Literal["HIGH", "MEDIUM", "LOW"] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelationClaim]: ...

    def list_claims_by_ids(
        self,
        claim_ids: list[str],
    ) -> list[KernelRelationClaim]: ...


class ClaimParticipantServiceLike(Protocol):
    """Minimal participant service surface needed by reasoning-path orchestration."""

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]: ...


class ClaimEvidenceServiceLike(Protocol):
    """Minimal evidence service surface needed by reasoning-path orchestration."""

    def list_for_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimEvidence]]: ...


class ClaimRelationServiceLike(Protocol):
    """Minimal claim-relation service surface needed by reasoning-path orchestration."""

    def list_by_research_space(
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimRelation]: ...

    def get_claim_relation(self, relation_id: str) -> KernelClaimRelation | None: ...


class RelationServiceLike(Protocol):
    """Minimal canonical relation service surface needed by reasoning-path reads."""

    def get_relation(
        self,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None: ...


_ALLOWED_PATH_RELATION_TYPES = frozenset(
    {
        "CAUSES",
        "UPSTREAM_OF",
        "DOWNSTREAM_OF",
        "REFINES",
        "SUPPORTS",
        "GENERALIZES",
        "INSTANCE_OF",
    },
)


class KernelReasoningPathService:
    """Build and serve derived mechanism paths from grounded claim chains."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        reasoning_path_repo: ReasoningPathRepositoryLike,
        relation_claim_service: RelationClaimServiceLike,
        claim_participant_service: ClaimParticipantServiceLike,
        claim_evidence_service: ClaimEvidenceServiceLike,
        claim_relation_service: ClaimRelationServiceLike,
        relation_service: RelationServiceLike,
        read_model_update_dispatcher: GraphReadModelUpdateDispatcher,
        session: Session | None = None,
        space_registry_port: SpaceRegistryPort | None = None,
    ) -> None:
        self._paths = reasoning_path_repo
        self._claims = relation_claim_service
        self._participants = claim_participant_service
        self._evidence = claim_evidence_service
        self._claim_relations = claim_relation_service
        self._relations = relation_service
        self._read_model_update_dispatcher = read_model_update_dispatcher
        self._session = session
        self._space_registry = space_registry_port

    def rebuild_for_space(
        self,
        research_space_id: str,
        *,
        max_depth: int = 4,
        replace_existing: bool = True,
    ) -> ReasoningPathRebuildSummary:
        grounded_claims = self._claims.list_by_research_space(
            research_space_id,
            claim_status="RESOLVED",
            persistability="PERSISTABLE",
            polarity="SUPPORT",
        )
        claim_ids = [str(claim.id) for claim in grounded_claims]
        participant_map = self._participants.list_for_claim_ids(claim_ids)
        evidence_map = self._evidence.list_for_claim_ids(claim_ids)

        eligible_claim_map: dict[str, KernelRelationClaim] = {}
        participant_anchor_map: dict[str, tuple[str, str]] = {}
        for claim in grounded_claims:
            claim_id = str(claim.id)
            participants = participant_map.get(claim_id, [])
            anchors = resolve_participant_anchor_entities(participants)
            if anchors is None or not evidence_map.get(claim_id):
                continue
            eligible_claim_map[claim_id] = claim
            participant_anchor_map[claim_id] = anchors

        accepted_relations = [
            relation
            for relation in self._claim_relations.list_by_research_space(
                research_space_id,
                review_status="ACCEPTED",
            )
            if relation.relation_type in _ALLOWED_PATH_RELATION_TYPES
            and str(relation.source_claim_id) in eligible_claim_map
            and str(relation.target_claim_id) in eligible_claim_map
        ]
        adjacency = build_adjacency(accepted_relations)

        bundles_by_signature: dict[str, ReasoningPathWriteBundle] = {}
        normalized_depth = max(1, min(4, int(max_depth)))
        for root_claim_id in sorted(eligible_claim_map):
            collect_paths_from_root(
                research_space_id=research_space_id,
                root_claim_id=root_claim_id,
                eligible_claim_map=eligible_claim_map,
                participant_anchor_map=participant_anchor_map,
                adjacency=adjacency,
                max_depth=normalized_depth,
                bundles_by_signature=bundles_by_signature,
            )

        persisted = self._paths.replace_for_space(
            research_space_id=research_space_id,
            bundles=list(bundles_by_signature.values()),
            replace_existing=replace_existing,
        )
        self._read_model_update_dispatcher.dispatch(
            GraphReadModelUpdate(
                model_name="entity_mechanism_paths",
                trigger=GraphReadModelTrigger.FULL_REBUILD,
                space_id=research_space_id,
            ),
        )
        return ReasoningPathRebuildSummary(
            research_space_id=research_space_id,
            eligible_claims=len(eligible_claim_map),
            accepted_claim_relations=len(accepted_relations),
            rebuilt_paths=len(persisted),
            max_depth=normalized_depth,
        )

    def rebuild_global(
        self,
        *,
        max_depth: int = 4,
    ) -> list[ReasoningPathRebuildSummary]:
        if self._space_registry is None:
            msg = "Space-registry-backed global rebuild is unavailable"
            raise ValueError(msg)
        return [
            self.rebuild_for_space(
                str(space_id),
                max_depth=max_depth,
                replace_existing=True,
            )
            for space_id in self._space_registry.list_space_ids()
        ]

    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ReasoningPathListResult:
        normalized_limit = max(1, min(200, int(limit)))
        normalized_offset = max(0, int(offset))
        paths = self._paths.list_paths(
            research_space_id=research_space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
            limit=normalized_limit,
            offset=normalized_offset,
        )
        total = self._paths.count_paths(
            research_space_id=research_space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
        )
        return ReasoningPathListResult(
            paths=tuple(paths),
            total=total,
            offset=normalized_offset,
            limit=normalized_limit,
        )

    def get_path(
        self,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPathDetail | None:
        path = self._paths.get_path(
            path_id=path_id,
            research_space_id=research_space_id,
        )
        if path is None:
            return None

        steps = self._paths.list_steps_for_path_ids(path_ids=[str(path.id)]).get(
            str(path.id),
            [],
        )
        ordered_claim_ids = resolve_ordered_claim_ids(path=path, steps=steps)
        claims = self._claims.list_claims_by_ids(ordered_claim_ids)
        claims_by_id = {str(claim.id): claim for claim in claims}
        ordered_claims = tuple(
            claims_by_id[claim_id]
            for claim_id in ordered_claim_ids
            if claim_id in claims_by_id
        )

        claim_relations = tuple(
            relation
            for step in steps
            if (
                relation := self._claim_relations.get_claim_relation(
                    str(step.claim_relation_id),
                )
            )
            is not None
        )
        participant_map = self._participants.list_for_claim_ids(ordered_claim_ids)
        evidence_map = self._evidence.list_for_claim_ids(ordered_claim_ids)
        participants = tuple(
            participant
            for claim_id in ordered_claim_ids
            for participant in participant_map.get(claim_id, [])
        )
        evidence = tuple(
            evidence_row
            for claim_id in ordered_claim_ids
            for evidence_row in evidence_map.get(claim_id, [])
        )
        canonical_relations_list = []
        for relation_id in resolve_ordered_canonical_relation_ids(
            steps=steps,
            claims=ordered_claims,
        ):
            canonical_relation = self._relations.get_relation(
                relation_id,
                claim_backed_only=True,
            )
            if canonical_relation is not None:
                canonical_relations_list.append(canonical_relation)
        canonical_relations = tuple(canonical_relations_list)

        return KernelReasoningPathDetail(
            path=path,
            steps=tuple(steps),
            claims=ordered_claims,
            claim_relations=claim_relations,
            canonical_relations=canonical_relations,
            participants=participants,
            evidence=evidence,
        )

    def list_mechanism_candidates(
        self,
        *,
        research_space_id: str,
        start_entity_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[KernelMechanismPathCandidate, ...]:
        if self._session is None:
            msg = "Session-backed mechanism candidate reads are unavailable"
            raise ValueError(msg)

        normalized_limit = max(1, min(200, int(limit)))
        normalized_offset = max(0, int(offset))
        start_entity_alias = aliased(EntityModel)
        end_entity_alias = aliased(EntityModel)
        stmt = (
            select(
                EntityMechanismPathModel,
                start_entity_alias,
                end_entity_alias,
            )
            .join(
                start_entity_alias,
                start_entity_alias.id == EntityMechanismPathModel.seed_entity_id,
            )
            .join(
                end_entity_alias,
                end_entity_alias.id == EntityMechanismPathModel.end_entity_id,
            )
            .where(
                EntityMechanismPathModel.research_space_id == UUID(research_space_id),
                EntityMechanismPathModel.seed_entity_id == UUID(start_entity_id),
                start_entity_alias.research_space_id == UUID(research_space_id),
                end_entity_alias.research_space_id == UUID(research_space_id),
            )
            .order_by(
                EntityMechanismPathModel.confidence.desc(),
                EntityMechanismPathModel.path_length.asc(),
                EntityMechanismPathModel.path_updated_at.desc(),
                EntityMechanismPathModel.path_id.asc(),
            )
            .offset(normalized_offset)
            .limit(normalized_limit)
        )
        rows = self._session.execute(stmt).all()
        return tuple(
            KernelMechanismPathCandidate(
                reasoning_path_id=str(index_row.path_id),
                start_entity_id=str(index_row.seed_entity_id),
                end_entity_id=str(index_row.end_entity_id),
                source_type=start_entity.entity_type.strip().upper(),
                target_type=end_entity.entity_type.strip().upper(),
                relation_type=str(index_row.relation_type),
                source_label=start_entity.display_label,
                target_label=end_entity.display_label,
                confidence=float(index_row.confidence),
                path_length=int(index_row.path_length),
                supporting_claim_ids=(
                    tuple(
                        value
                        for value in index_row.supporting_claim_ids
                        if isinstance(value, str)
                    )
                    if isinstance(index_row.supporting_claim_ids, list)
                    else ()
                ),
            )
            for index_row, start_entity, end_entity in rows
        )

    def mark_stale_for_claim_ids(
        self,
        claim_ids: list[str],
        research_space_id: str,
    ) -> int:
        stale_count = self._paths.mark_stale_for_claim_ids(
            research_space_id=research_space_id,
            claim_ids=claim_ids,
        )
        self._read_model_update_dispatcher.dispatch(
            GraphReadModelUpdate(
                model_name="entity_mechanism_paths",
                trigger=GraphReadModelTrigger.CLAIM_CHANGE,
                claim_ids=tuple(claim_ids),
                space_id=research_space_id,
            ),
        )
        return stale_count

    def mark_stale_for_claim_relation_ids(
        self,
        relation_ids: list[str],
        research_space_id: str,
    ) -> int:
        stale_count = self._paths.mark_stale_for_claim_relation_ids(
            research_space_id=research_space_id,
            relation_ids=relation_ids,
        )
        self._read_model_update_dispatcher.dispatch(
            GraphReadModelUpdate(
                model_name="entity_mechanism_paths",
                trigger=GraphReadModelTrigger.PROJECTION_CHANGE,
                relation_ids=tuple(relation_ids),
                space_id=research_space_id,
            ),
        )
        return stale_count


__all__ = [
    "KernelReasoningPathDetail",
    "KernelReasoningPathService",
    "ReasoningPathListResult",
    "ReasoningPathRebuildSummary",
]
