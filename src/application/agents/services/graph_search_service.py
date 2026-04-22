"""Application service for read-only graph search orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.application.agents.services.governance_service import GovernanceService
from src.domain.agents.contexts.graph_search_context import GraphSearchContext
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_search import (
    EvidenceChainItem,
    GraphSearchContract,
    GraphSearchResultEntry,
)
from src.domain.agents.contracts.graph_search_assessment import (
    GraphSearchAssessment,
    GraphSearchGroundingLevel,
    build_graph_search_assessment_from_confidence,
    graph_search_assessment_confidence,
    graph_search_grounding_level_from_counts,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import (
        KernelEntity,
        KernelObservation,
        KernelRelation,
    )
    from artana_evidence_db.query_ports import GraphQueryPort, ResearchQueryPort
    from artana_evidence_db.research_query_models import ResearchQueryPlan

    from src.domain.agents.ports.graph_search_port import GraphSearchPort

_EVIDENCE_TIER_RANK = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}


@dataclass(frozen=True)
class GraphSearchServiceDependencies:
    """Dependencies required by graph search orchestration."""

    research_query_service: ResearchQueryPort
    graph_query_service: GraphQueryPort
    graph_search_agent: GraphSearchPort | None = None
    governance_service: GovernanceService | None = None


class GraphSearchService:
    """Deterministic-first graph search with optional agent fallback."""

    def __init__(self, dependencies: GraphSearchServiceDependencies) -> None:
        self._research_query_service = dependencies.research_query_service
        self._graph_query_service = dependencies.graph_query_service
        self._graph_search_agent = dependencies.graph_search_agent
        self._governance_service = (
            dependencies.governance_service or GovernanceService()
        )

    async def search(  # noqa: PLR0913
        self,
        *,
        question: str,
        research_space_id: str,
        max_depth: int = 2,
        top_k: int = 25,
        curation_statuses: list[str] | None = None,
        include_evidence_chains: bool = True,
        force_agent: bool = False,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        """Execute graph search for one question in a research space."""
        context = GraphSearchContext(
            question=question,
            research_space_id=research_space_id,
            max_depth=max_depth,
            top_k=top_k,
            curation_statuses=_normalize_curation_statuses(curation_statuses),
            include_evidence_chains=include_evidence_chains,
            force_agent=force_agent,
        )

        if force_agent:
            agent_contract = await self._search_with_agent(context, model_id=model_id)
            if agent_contract is not None and agent_contract.results:
                return agent_contract

            fallback = self._search_deterministic(context)
            fallback.executed_path = "agent_fallback"
            if agent_contract is None:
                fallback.warnings.append(
                    "force_agent was requested but no graph search agent is configured.",
                )
            else:
                fallback.warnings.append(
                    "force_agent was requested but the agent returned no ranked results.",
                )
            return fallback

        deterministic = self._search_deterministic(context)
        if deterministic.results:
            return deterministic

        agent_contract = await self._search_with_agent(context, model_id=model_id)
        if agent_contract is not None and agent_contract.results:
            return agent_contract
        return deterministic

    async def close(self) -> None:
        """Release resources held by the optional graph-search adapter."""
        if self._graph_search_agent is None:
            return
        await self._graph_search_agent.close()

    async def _search_with_agent(
        self,
        context: GraphSearchContext,
        *,
        model_id: str | None,
    ) -> GraphSearchContract | None:
        if self._graph_search_agent is None:
            return None
        contract = await self._graph_search_agent.search(context, model_id=model_id)
        if context.curation_statuses:
            contract = self._apply_agent_status_filter(
                contract=contract,
                context=context,
            )
        contract = self._normalize_search_contract(contract)
        contract.executed_path = "agent"
        return contract

    def _apply_agent_status_filter(
        self,
        *,
        contract: GraphSearchContract,
        context: GraphSearchContext,
    ) -> GraphSearchContract:
        allowed_statuses = _normalize_curation_statuses(context.curation_statuses)
        if not allowed_statuses:
            return contract

        filtered_results: list[GraphSearchResultEntry] = []
        warnings = list(contract.warnings)
        for result in contract.results:
            allowed_relation_ids = {
                str(relation.id)
                for relation in self._graph_query_service.graph_query_relations(
                    research_space_id=context.research_space_id,
                    entity_id=result.entity_id,
                    relation_types=None,
                    curation_statuses=allowed_statuses,
                    direction="both",
                    depth=context.max_depth,
                    limit=500,
                )
            }
            filtered_relation_ids = [
                relation_id
                for relation_id in result.matching_relation_ids
                if relation_id in allowed_relation_ids
            ]
            filtered_chain = [
                item
                for item in result.evidence_chain
                if item.relation_id is None or item.relation_id in allowed_relation_ids
            ]
            if not filtered_relation_ids and result.matching_relation_ids:
                warnings.append(
                    (
                        "Agent result relation set was filtered by selected trust "
                        f"statuses for entity {result.entity_id}."
                    ),
                )
            filtered_results.append(
                result.model_copy(
                    update={
                        "matching_relation_ids": filtered_relation_ids,
                        "evidence_chain": filtered_chain,
                    },
                ),
            )

        return contract.model_copy(
            update={
                "results": filtered_results,
                "total_results": len(filtered_results),
                "warnings": _dedupe(warnings),
            },
        )

    def _search_deterministic(
        self,
        context: GraphSearchContext,
    ) -> GraphSearchContract:
        intent = self._research_query_service.parse_intent(
            question=context.question,
            research_space_id=context.research_space_id,
        )
        plan = self._research_query_service.build_query_plan(
            intent=intent,
            max_depth=context.max_depth,
            top_k=context.top_k,
        )
        candidates = self._collect_candidate_entities(
            research_space_id=context.research_space_id,
            plan=plan,
        )
        results: list[GraphSearchResultEntry] = []
        warnings = list(intent.notes)
        for entity in candidates:
            result, result_warnings = self._build_result_entry(
                research_space_id=context.research_space_id,
                entity=entity,
                plan=plan,
                curation_statuses=context.curation_statuses,
                include_evidence_chains=context.include_evidence_chains,
            )
            warnings.extend(result_warnings)
            if result is not None:
                results.append(result)

        results.sort(key=lambda item: item.relevance_score, reverse=True)
        ranked_results = results[: plan.top_k]
        average_relevance_score = (
            sum(item.relevance_score for item in ranked_results) / len(ranked_results)
            if ranked_results
            else 0.25
        )
        search_assessment = build_graph_search_assessment_from_confidence(
            average_relevance_score,
            confidence_rationale=(
                f"Derived from {len(ranked_results)} ranked result(s) and "
                f"mean relevance {average_relevance_score:.2f}."
            ),
            grounding_level=(
                GraphSearchGroundingLevel.AGGREGATED
                if ranked_results
                else GraphSearchGroundingLevel.NONE
            ),
        )
        support_label = _support_label_for_band(search_assessment.support_band)
        if (
            ranked_results
            and self._governance_service.evaluate(
                confidence_score=_clamp(
                    graph_search_assessment_confidence(search_assessment),
                ),
                evidence_count=len(ranked_results),
                decision="generated",
                requested_shadow_mode=False,
                research_space_settings=None,
            ).requires_review
        ):
            support_label = f"{support_label}; review recommended"
        summary_excerpt = (
            f"Deterministic graph search produced {len(ranked_results)} results."
            if ranked_results
            else "Deterministic graph search produced no ranked results."
        )
        decision: Literal["generated", "fallback"] = (
            "generated" if ranked_results else "fallback"
        )
        rationale = (
            f"Deterministic-first graph search completed with {support_label} evidence."
            if ranked_results
            else "Deterministic-first graph search could not find enough evidence."
        )

        return GraphSearchContract(
            decision=decision,
            assessment=search_assessment,
            confidence_score=_clamp(
                graph_search_assessment_confidence(search_assessment),
            ),
            rationale=rationale,
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"research_space:{context.research_space_id}",
                    excerpt=summary_excerpt,
                    relevance=_clamp(
                        (
                            graph_search_assessment_confidence(search_assessment)
                            if ranked_results
                            else 0.35
                        ),
                    ),
                ),
            ],
            research_space_id=context.research_space_id,
            original_query=context.question,
            interpreted_intent=(
                ", ".join(intent.normalized_terms)
                if intent.normalized_terms
                else context.question
            ),
            query_plan_summary=plan.plan_summary,
            total_results=len(ranked_results),
            results=ranked_results,
            executed_path="deterministic",
            warnings=_dedupe(warnings),
        )

    def _collect_candidate_entities(
        self,
        *,
        research_space_id: str,
        plan: ResearchQueryPlan,
    ) -> list[KernelEntity]:
        entity_map: dict[str, KernelEntity] = {}
        for entity_type in plan.entity_types:
            entities = self._graph_query_service.graph_query_entities(
                research_space_id=research_space_id,
                entity_type=entity_type,
                query_text=None,
                limit=200,
            )
            for entity in entities:
                entity_map[str(entity.id)] = entity

        if not entity_map:
            query_text = " ".join(plan.query_terms[:4]) if plan.query_terms else None
            generic_entities = self._graph_query_service.graph_query_entities(
                research_space_id=research_space_id,
                entity_type=None,
                query_text=query_text,
                limit=200,
            )
            for entity in generic_entities:
                entity_map[str(entity.id)] = entity

        if not entity_map and plan.variable_ids:
            for variable_id in plan.variable_ids[:3]:
                entities = self._graph_query_service.graph_query_by_observation(
                    research_space_id=research_space_id,
                    variable_id=variable_id,
                    operator="eq",
                    value=None,
                    limit=200,
                )
                for entity in entities:
                    entity_map[str(entity.id)] = entity

        candidates = list(entity_map.values())
        candidates.sort(key=lambda entity: entity.created_at, reverse=True)
        return candidates[:200]

    def _build_result_entry(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity: KernelEntity,
        plan: ResearchQueryPlan,
        curation_statuses: list[str] | None,
        include_evidence_chains: bool,
    ) -> tuple[GraphSearchResultEntry | None, list[str]]:
        warnings: list[str] = []
        relations = self._graph_query_service.graph_query_relations(
            research_space_id=research_space_id,
            entity_id=str(entity.id),
            relation_types=plan.relation_types or None,
            curation_statuses=curation_statuses,
            direction="both",
            depth=plan.max_depth,
            limit=200,
        )
        if not relations and plan.relation_types:
            relations = self._graph_query_service.graph_query_relations(
                research_space_id=research_space_id,
                entity_id=str(entity.id),
                relation_types=None,
                curation_statuses=curation_statuses,
                direction="both",
                depth=plan.max_depth,
                limit=200,
            )
            if relations:
                warnings.append(
                    "Inferred relation-type filters returned no edges; broadened "
                    "relation search for deterministic fallback coverage.",
                )
        valid_relations = relations

        observations = self._graph_query_service.graph_query_observations(
            research_space_id=research_space_id,
            entity_id=str(entity.id),
            variable_ids=plan.variable_ids or None,
            limit=200,
        )
        relevance_score = self._compute_relevance_score(
            entity=entity,
            plan=plan,
            relations=valid_relations,
            observations=observations,
        )
        if relevance_score <= 0.0:
            return None, warnings

        evidence_chain = (
            self._build_evidence_chain(
                research_space_id=research_space_id,
                relations=valid_relations,
                observations=observations,
            )
            if include_evidence_chains
            else []
        )
        support_summary = self._build_support_summary(
            assessment=build_graph_search_assessment_from_confidence(
                relevance_score,
                confidence_rationale=(
                    f"Derived from relevance_score={relevance_score:.2f}."
                ),
                grounding_level=graph_search_grounding_level_from_counts(
                    relation_count=len(valid_relations),
                    observation_count=len(observations),
                ),
            ),
            evidence_chain=evidence_chain,
            relation_count=len(valid_relations),
            observation_count=len(observations),
        )
        result_assessment = build_graph_search_assessment_from_confidence(
            relevance_score,
            confidence_rationale=(
                f"Derived from relevance_score={relevance_score:.2f} and "
                f"{len(valid_relations)} relation(s) / {len(observations)} observation(s)."
            ),
            grounding_level=graph_search_grounding_level_from_counts(
                relation_count=len(valid_relations),
                observation_count=len(observations),
            ),
        )
        explanation = (
            f"Entity matched with {len(valid_relations)} relation(s) and "
            f"{len(observations)} observation(s) under the planned filters."
        )

        return (
            GraphSearchResultEntry(
                entity_id=str(entity.id),
                entity_type=entity.entity_type,
                display_label=entity.display_label,
                relevance_score=_clamp(relevance_score),
                assessment=result_assessment,
                matching_observation_ids=[
                    str(observation.id) for observation in observations
                ],
                matching_relation_ids=[
                    str(relation.id) for relation in valid_relations
                ],
                evidence_chain=evidence_chain,
                explanation=explanation,
                support_summary=support_summary,
            ),
            warnings,
        )

    def _compute_relevance_score(
        self,
        *,
        entity: KernelEntity,
        plan: ResearchQueryPlan,
        relations: list[KernelRelation],
        observations: list[KernelObservation],
    ) -> float:
        relation_score = min(len(relations), 10) / 10.0
        observation_score = min(len(observations), 10) / 10.0
        keyword_score = 0.0
        label = (entity.display_label or "").casefold()
        if label:
            matched_terms = [
                term for term in plan.query_terms if term.casefold() in label
            ]
            keyword_score = min(len(matched_terms), 3) / 3.0

        return _clamp(
            (relation_score * 0.5)
            + (observation_score * 0.35)
            + (keyword_score * 0.15),
        )

    def _build_evidence_chain(
        self,
        *,
        research_space_id: str,
        relations: list[KernelRelation],
        observations: list[KernelObservation],
    ) -> list[EvidenceChainItem]:
        chain: list[EvidenceChainItem] = []
        for relation in relations[:3]:
            relation_evidence = self._graph_query_service.graph_query_relation_evidence(
                research_space_id=research_space_id,
                relation_id=str(relation.id),
                limit=3,
            )
            if not relation_evidence:
                chain.append(
                    EvidenceChainItem(
                        provenance_id=(
                            str(relation.provenance_id)
                            if relation.provenance_id is not None
                            else None
                        ),
                        relation_id=str(relation.id),
                        observation_id=None,
                        evidence_tier=relation.highest_evidence_tier,
                        confidence=_clamp(relation.aggregate_confidence),
                        assessment=build_graph_search_assessment_from_confidence(
                            relation.aggregate_confidence,
                            confidence_rationale=(
                                f"Derived from relation aggregate_confidence="
                                f"{relation.aggregate_confidence:.2f}."
                            ),
                            grounding_level=GraphSearchGroundingLevel.RELATION,
                        ),
                        evidence_sentence=None,
                        source_ref=f"relation:{relation.id}",
                    ),
                )
                continue

            chain.extend(
                [
                    EvidenceChainItem(
                        provenance_id=(
                            str(evidence.provenance_id)
                            if evidence.provenance_id is not None
                            else None
                        ),
                        relation_id=str(relation.id),
                        observation_id=None,
                        evidence_tier=evidence.evidence_tier,
                        confidence=_clamp(float(evidence.confidence)),
                        assessment=build_graph_search_assessment_from_confidence(
                            float(evidence.confidence),
                            confidence_rationale=(
                                f"Derived from relation evidence confidence="
                                f"{float(evidence.confidence):.2f}."
                            ),
                            grounding_level=GraphSearchGroundingLevel.RELATION,
                        ),
                        evidence_sentence=(
                            evidence.evidence_sentence.strip()[:2000]
                            if isinstance(evidence.evidence_sentence, str)
                            and evidence.evidence_sentence.strip()
                            else None
                        ),
                        source_ref=(
                            str(evidence.source_document_id)
                            if evidence.source_document_id is not None
                            else None
                        ),
                    )
                    for evidence in relation_evidence
                ],
            )

        chain.extend(
            [
                EvidenceChainItem(
                    provenance_id=(
                        str(observation.provenance_id)
                        if observation.provenance_id is not None
                        else None
                    ),
                    relation_id=None,
                    observation_id=str(observation.id),
                    evidence_tier=None,
                    confidence=_clamp(observation.confidence),
                    assessment=build_graph_search_assessment_from_confidence(
                        observation.confidence,
                        confidence_rationale=(
                            f"Derived from observation confidence="
                            f"{observation.confidence:.2f}."
                        ),
                        grounding_level=GraphSearchGroundingLevel.OBSERVATION,
                    ),
                    evidence_sentence=None,
                    source_ref=f"observation:{observation.id}",
                )
                for observation in observations[:3]
            ],
        )
        return chain

    def _build_support_summary(
        self,
        *,
        assessment: GraphSearchAssessment,
        evidence_chain: list[EvidenceChainItem],
        relation_count: int,
        observation_count: int,
    ) -> str:
        governance = self._governance_service.evaluate(
            confidence_score=_clamp(graph_search_assessment_confidence(assessment)),
            evidence_count=len(evidence_chain),
            decision="generated",
            requested_shadow_mode=False,
            research_space_settings=None,
        )
        independent_sources = {
            item.provenance_id
            for item in evidence_chain
            if item.provenance_id is not None
        }
        highest_tier = _highest_evidence_tier(evidence_chain)
        is_computational_only = (highest_tier or "COMPUTATIONAL") == "COMPUTATIONAL"
        quality_label = _support_label_for_band(assessment.support_band)
        if governance.requires_review:
            quality_label = f"{quality_label}; review recommended"
        if is_computational_only:
            quality_label = f"{quality_label}; computational only"
        return (
            f"{quality_label}: relations={relation_count}, observations={observation_count}, "
            f"independent_sources={len(independent_sources)}, "
            f"highest_tier={highest_tier or 'N/A'}, "
            f"assertion_basis={'computational' if is_computational_only else 'source_backed'}, "
            f"support_band={assessment.support_band}, "
            f"grounding={assessment.grounding_level}"
        )

    def _normalize_search_contract(
        self,
        contract: GraphSearchContract,
    ) -> GraphSearchContract:
        assessment = contract.assessment
        if assessment is None:
            confidence_score = (
                contract.confidence_score
                if contract.confidence_score is not None
                else 0.25
            )
            grounding_level = (
                GraphSearchGroundingLevel.AGGREGATED
                if contract.results
                and any(result.evidence_chain for result in contract.results)
                else GraphSearchGroundingLevel.ENTITY
            )
            assessment = build_graph_search_assessment_from_confidence(
                confidence_score,
                confidence_rationale=(
                    f"Derived from {len(contract.results)} ranked result(s) with "
                    f"mean relevance {confidence_score:.2f}."
                ),
                grounding_level=grounding_level,
            )
            contract = contract.model_copy(update={"assessment": assessment})
        return contract.model_copy(
            update={
                "confidence_score": _clamp(
                    graph_search_assessment_confidence(assessment),
                ),
            },
        )


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        if normalized in deduped:
            continue
        deduped.append(normalized)
    return deduped


def _highest_evidence_tier(evidence_chain: list[EvidenceChainItem]) -> str | None:
    highest_tier: str | None = None
    highest_rank = -1
    for item in evidence_chain:
        if item.evidence_tier is None:
            continue
        rank = _EVIDENCE_TIER_RANK.get(item.evidence_tier.upper(), 0)
        if rank > highest_rank:
            highest_rank = rank
            highest_tier = item.evidence_tier
    return highest_tier


def _support_label_for_band(band: str) -> str:
    normalized_band = band.upper()
    if normalized_band == "STRONG":
        return "strongly supported"
    if normalized_band == "SUPPORTED":
        return "supported"
    if normalized_band == "TENTATIVE":
        return "tentatively supported"
    return "insufficient support"


def _normalize_curation_statuses(
    statuses: list[str] | None,
) -> list[str] | None:
    if statuses is None:
        return None
    normalized: list[str] = []
    for raw_status in statuses:
        candidate = raw_status.strip().upper()
        if not candidate:
            continue
        if candidate == "PENDING_REVIEW":
            candidate = "DRAFT"
        if candidate in normalized:
            continue
        normalized.append(candidate)
    return normalized or None


__all__ = ["GraphSearchService", "GraphSearchServiceDependencies"]
