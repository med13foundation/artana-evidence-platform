"""Read-side graph view service for domain views and mechanism chains."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.graph_view_support import (
    ClaimBundle,
    GraphDomainViewType,
    KernelClaimMechanismChain,
    KernelGraphDomainView,
    KernelGraphViewNotFoundError,
    KernelGraphViewServiceDependencies,
    KernelGraphViewValidationError,
    dedupe_relations,
    flatten_evidence,
    flatten_participants,
    normalize_ids,
    sort_claim_relations,
    sort_claims,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import (
        KernelClaimRelation,
        KernelRelation,
        KernelRelationClaim,
    )


class KernelGraphViewService:
    """Build read-only domain views and mechanism claim chains."""

    def __init__(self, dependencies: KernelGraphViewServiceDependencies) -> None:
        self._entities = dependencies.entity_service
        self._relations = dependencies.relation_service
        self._claims = dependencies.relation_claim_service
        self._claim_participants = dependencies.claim_participant_service
        self._claim_relations = dependencies.claim_relation_service
        self._claim_evidence = dependencies.claim_evidence_service
        self._source_document_lookup = dependencies.source_document_lookup
        self._view_extension = dependencies.view_extension

    def build_domain_view(
        self,
        *,
        research_space_id: str,
        view_type: GraphDomainViewType,
        resource_id: str,
        claim_limit: int = 50,
        relation_limit: int = 50,
    ) -> KernelGraphDomainView:
        """Build a graph view for one entity, claim, or source document."""
        if self._view_extension.is_entity_view(view_type):
            return self._build_entity_view(
                research_space_id=research_space_id,
                view_type=view_type,
                entity_id=resource_id,
                claim_limit=claim_limit,
                relation_limit=relation_limit,
            )
        if self._view_extension.is_claim_view(view_type):
            return self._build_claim_view(
                research_space_id=research_space_id,
                claim_id=resource_id,
            )
        if self._view_extension.is_document_view(view_type):
            return self._build_paper_view(
                research_space_id=research_space_id,
                source_document_id=resource_id,
                claim_limit=claim_limit,
            )
        msg = f"Unsupported graph view type: {view_type}"
        raise KernelGraphViewValidationError(msg)

    def build_mechanism_chain(
        self,
        *,
        research_space_id: str,
        claim_id: str,
        max_depth: int = 3,
    ) -> KernelClaimMechanismChain:
        """Traverse mechanism-style claim relations from one root claim."""
        if max_depth < 1:
            msg = "max_depth must be at least 1"
            raise KernelGraphViewValidationError(msg)
        root_claim = self._claims.get_claim(claim_id)
        if root_claim is None or str(root_claim.research_space_id) != research_space_id:
            msg = f"Claim {claim_id} not found in research space {research_space_id}"
            raise KernelGraphViewNotFoundError(msg)

        visited_claim_ids, claim_relations = self._collect_mechanism_relations(
            research_space_id=research_space_id,
            root_claim_id=str(root_claim.id),
            max_depth=max_depth,
        )
        bundle = self._build_claim_bundle(
            research_space_id=research_space_id,
            claim_ids=list(visited_claim_ids),
            preloaded_claim_relations=claim_relations,
        )
        return KernelClaimMechanismChain(
            root_claim=root_claim,
            max_depth=max_depth,
            canonical_relations=bundle.canonical_relations,
            claims=bundle.claims,
            claim_relations=bundle.claim_relations,
            participants=bundle.participants,
            evidence=bundle.evidence,
        )

    def _collect_mechanism_relations(
        self,
        *,
        research_space_id: str,
        root_claim_id: str,
        max_depth: int,
    ) -> tuple[set[str], list[KernelClaimRelation]]:
        visited_claim_ids: set[str] = {root_claim_id}
        frontier: set[str] = {root_claim_id}
        claim_relations: list[KernelClaimRelation] = []
        seen_relation_ids: set[str] = set()

        for _ in range(max_depth):
            if not frontier:
                break
            step_relations = self._claim_relations.list_by_claim_ids(
                research_space_id,
                list(frontier),
            )
            frontier = self._expand_mechanism_frontier(
                step_relations=step_relations,
                visited_claim_ids=visited_claim_ids,
                seen_relation_ids=seen_relation_ids,
                collected_relations=claim_relations,
            )
        return visited_claim_ids, claim_relations

    def _expand_mechanism_frontier(
        self,
        *,
        step_relations: list[KernelClaimRelation],
        visited_claim_ids: set[str],
        seen_relation_ids: set[str],
        collected_relations: list[KernelClaimRelation],
    ) -> set[str]:
        next_frontier: set[str] = set()
        for relation in step_relations:
            if relation.review_status == "REJECTED":
                continue
            if (
                relation.relation_type
                not in self._view_extension.mechanism_relation_types
            ):
                continue
            relation_id = str(relation.id)
            if relation_id not in seen_relation_ids:
                seen_relation_ids.add(relation_id)
                collected_relations.append(relation)

            source_claim_id = str(relation.source_claim_id)
            target_claim_id = str(relation.target_claim_id)
            if source_claim_id not in visited_claim_ids:
                visited_claim_ids.add(source_claim_id)
                next_frontier.add(source_claim_id)
            if target_claim_id not in visited_claim_ids:
                visited_claim_ids.add(target_claim_id)
                next_frontier.add(target_claim_id)
        return next_frontier

    def _build_entity_view(
        self,
        *,
        research_space_id: str,
        view_type: GraphDomainViewType,
        entity_id: str,
        claim_limit: int,
        relation_limit: int,
    ) -> KernelGraphDomainView:
        entity = self._entities.get_entity(entity_id)
        if entity is None or str(entity.research_space_id) != research_space_id:
            msg = f"Entity {entity_id} not found in research space {research_space_id}"
            raise KernelGraphViewNotFoundError(msg)
        expected_entity_type = self._view_extension.entity_view_types[view_type]
        if entity.entity_type != expected_entity_type:
            msg = (
                f"Graph view '{view_type}' requires entity_type "
                f"'{expected_entity_type}', got '{entity.entity_type}'"
            )
            raise KernelGraphViewValidationError(msg)

        claim_ids = self._claim_participants.list_claim_ids_by_entity(
            research_space_id=research_space_id,
            entity_id=entity_id,
            limit=claim_limit,
            offset=0,
        )
        claim_bundle = self._build_claim_bundle(
            research_space_id=research_space_id,
            claim_ids=claim_ids,
        )
        neighborhood_relations = self._relations.get_neighborhood_in_space(
            research_space_id,
            entity_id,
            depth=1,
            claim_backed_only=True,
            limit=relation_limit,
        )
        canonical_relations = dedupe_relations(
            list(neighborhood_relations) + list(claim_bundle.canonical_relations),
        )
        return KernelGraphDomainView(
            view_type=view_type,
            resource_id=entity_id,
            entity=entity,
            claim=None,
            paper=None,
            canonical_relations=tuple(canonical_relations),
            claims=claim_bundle.claims,
            claim_relations=claim_bundle.claim_relations,
            participants=claim_bundle.participants,
            evidence=claim_bundle.evidence,
        )

    def _build_claim_view(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> KernelGraphDomainView:
        claim = self._claims.get_claim(claim_id)
        if claim is None or str(claim.research_space_id) != research_space_id:
            msg = f"Claim {claim_id} not found in research space {research_space_id}"
            raise KernelGraphViewNotFoundError(msg)
        claim_bundle = self._build_claim_bundle(
            research_space_id=research_space_id,
            claim_ids=[claim_id],
        )
        return KernelGraphDomainView(
            view_type="claim",
            resource_id=claim_id,
            entity=None,
            claim=claim,
            paper=None,
            canonical_relations=claim_bundle.canonical_relations,
            claims=claim_bundle.claims,
            claim_relations=claim_bundle.claim_relations,
            participants=claim_bundle.participants,
            evidence=claim_bundle.evidence,
        )

    def _build_paper_view(
        self,
        *,
        research_space_id: str,
        source_document_id: str,
        claim_limit: int,
    ) -> KernelGraphDomainView:
        document = self._source_document_lookup.get_by_id(UUID(source_document_id))
        if document is None:
            msg = f"Source document {source_document_id} not found"
            raise KernelGraphViewNotFoundError(msg)
        if (
            document.research_space_id is not None
            and str(document.research_space_id) != research_space_id
        ):
            msg = (
                f"Source document {source_document_id} not found in "
                f"research space {research_space_id}"
            )
            raise KernelGraphViewNotFoundError(msg)

        claims = self._claims.list_by_research_space(
            research_space_id,
            source_document_id=source_document_id,
            limit=claim_limit,
            offset=0,
        )
        claim_bundle = self._build_claim_bundle(
            research_space_id=research_space_id,
            claim_ids=[str(claim.id) for claim in claims],
            preloaded_claims=claims,
        )
        return KernelGraphDomainView(
            view_type="paper",
            resource_id=source_document_id,
            entity=None,
            claim=None,
            paper=document,
            canonical_relations=claim_bundle.canonical_relations,
            claims=claim_bundle.claims,
            claim_relations=claim_bundle.claim_relations,
            participants=claim_bundle.participants,
            evidence=claim_bundle.evidence,
        )

    def _build_claim_bundle(
        self,
        *,
        research_space_id: str,
        claim_ids: list[str],
        preloaded_claims: list[KernelRelationClaim] | None = None,
        preloaded_claim_relations: list[KernelClaimRelation] | None = None,
    ) -> ClaimBundle:
        normalized_claim_ids = normalize_ids(claim_ids)
        if not normalized_claim_ids:
            return ClaimBundle(
                claims=(),
                claim_relations=(),
                participants=(),
                evidence=(),
                canonical_relations=(),
            )

        claims = (
            sort_claims(preloaded_claims)
            if preloaded_claims is not None
            else sort_claims(self._claims.list_claims_by_ids(normalized_claim_ids))
        )
        normalized_claim_id_set = set(normalized_claim_ids)
        filtered_claims = tuple(
            claim
            for claim in claims
            if str(claim.research_space_id) == research_space_id
            and str(claim.id) in normalized_claim_id_set
        )
        if not filtered_claims:
            return ClaimBundle(
                claims=(),
                claim_relations=(),
                participants=(),
                evidence=(),
                canonical_relations=(),
            )

        filtered_claim_ids = [str(claim.id) for claim in filtered_claims]
        participants_by_claim_id = self._claim_participants.list_for_claim_ids(
            filtered_claim_ids,
        )
        evidence_by_claim_id = self._claim_evidence.list_for_claim_ids(
            filtered_claim_ids,
        )
        claim_relations = (
            sort_claim_relations(preloaded_claim_relations)
            if preloaded_claim_relations is not None
            else sort_claim_relations(
                self._claim_relations.list_by_claim_ids(
                    research_space_id,
                    filtered_claim_ids,
                ),
            )
        )
        participants = flatten_participants(
            filtered_claim_ids,
            participants_by_claim_id,
        )
        evidence = flatten_evidence(filtered_claim_ids, evidence_by_claim_id)
        canonical_relations = self._load_linked_canonical_relations(
            research_space_id=research_space_id,
            claims=filtered_claims,
        )
        return ClaimBundle(
            claims=filtered_claims,
            claim_relations=tuple(claim_relations),
            participants=tuple(participants),
            evidence=tuple(evidence),
            canonical_relations=tuple(canonical_relations),
        )

    def _load_linked_canonical_relations(
        self,
        *,
        research_space_id: str,
        claims: tuple[KernelRelationClaim, ...],
    ) -> list[KernelRelation]:
        relations: list[KernelRelation] = []
        seen_relation_ids: set[str] = set()
        for claim in claims:
            if claim.linked_relation_id is None:
                continue
            relation_id = str(claim.linked_relation_id)
            if relation_id in seen_relation_ids:
                continue
            seen_relation_ids.add(relation_id)
            relation = self._relations.get_relation(
                relation_id,
                claim_backed_only=True,
            )
            if relation is None:
                continue
            if str(relation.research_space_id) != research_space_id:
                continue
            relations.append(relation)
        return dedupe_relations(relations)


__all__ = [
    "GraphDomainViewType",
    "KernelClaimMechanismChain",
    "KernelGraphDomainView",
    "KernelGraphViewNotFoundError",
    "KernelGraphViewService",
    "KernelGraphViewServiceDependencies",
    "KernelGraphViewValidationError",
]
