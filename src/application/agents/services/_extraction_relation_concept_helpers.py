"""Concept-linking helper functions for extraction relation persistence."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Literal

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    default_graph_domain_context_for_source_type,
    resolve_graph_domain_context,
)

from src.domain.services.domain_context_resolver import DomainContextResolver

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import ConceptAlias, ConceptMember
    from artana_evidence_db.semantic_ports import ConceptPort

    from src.domain.agents.ports.mapping_judge_port import MappingJudgePort
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject, ResearchSpaceSettings
else:
    JSONObject = dict[str, object]  # Runtime type stub

_CONCEPT_CREATED_BY = "agent:extraction_service"
_CONCEPT_SET_SLUG_PREFIX = "pipeline"
_CONCEPT_LOOKUP_PAGE_SIZE = 500
_CONCEPT_SEMANTIC_CANDIDATE_LIMIT = 5
_CONCEPT_SEMANTIC_MATCH_THRESHOLD = 0.72
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ConceptLinkageResult:
    concept_refs: JSONObject | None = None
    members_created_count: int = 0
    aliases_created_count: int = 0
    decisions_proposed_count: int = 0
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ConceptSemanticCandidate:
    member_id: str
    display_name: str
    match_method: Literal["synonym", "fuzzy"]
    similarity_score: float
    description: str | None = None
    metadata: JSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class _ConceptCandidateInput:
    member_id: str
    display_name: str
    match_method: Literal["synonym", "fuzzy"]
    similarity_score: float
    description: str
    metadata: JSONObject


def _normalize_concept_label(raw_label: str | None) -> tuple[str, str]:
    if not isinstance(raw_label, str):
        return "", ""
    compact = " ".join(raw_label.strip().split())
    if not compact:
        return "", ""
    return compact, compact.lower()


def _normalize_sense_key(raw_value: str) -> str:
    return raw_value.strip().upper()


def _normalize_domain_context(raw_value: str | None) -> str:
    normalized = DomainContextResolver.normalize(raw_value)
    if normalized is not None:
        return normalized
    fallback = default_graph_domain_context_for_source_type(
        None,
        domain_context_policy=create_graph_domain_context_policy(),
        fallback=DomainContextResolver.GENERAL_DEFAULT_DOMAIN,
    )
    return fallback or DomainContextResolver.GENERAL_DEFAULT_DOMAIN


def _build_concept_set_slug(domain_context: str) -> str:
    token = domain_context.strip().lower()
    token = token.replace("_", "-")
    token = re.sub(r"[^a-z0-9-]+", "-", token)
    token = re.sub(r"-+", "-", token).strip("-")
    if not token:
        token = DomainContextResolver.GENERAL_DEFAULT_DOMAIN
    return f"{_CONCEPT_SET_SLUG_PREFIX}-{token}"


def _resolve_document_domain_context(document: SourceDocument) -> str:
    resolved = resolve_graph_domain_context(
        domain_context_policy=create_graph_domain_context_policy(),
        metadata=document.metadata,
        source_type=document.source_type.value,
        fallback=DomainContextResolver.GENERAL_DEFAULT_DOMAIN,
    )
    return _normalize_domain_context(resolved)


def _resolve_or_create_concept_set(  # noqa: C901, PLR0911, TRY300
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    domain_context: str,
    source_ref: str,
    cache: dict[tuple[str, str], str],
) -> str | None:
    cache_key = (research_space_id, domain_context)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    slug = _build_concept_set_slug(domain_context)
    try:
        existing_sets = concept_service.list_concept_sets(
            research_space_id=research_space_id,
            include_inactive=False,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
        logger.warning(
            "Concept set listing failed",
            extra={
                "research_space_id": research_space_id,
                "domain_context": domain_context,
                "error": str(exc),
            },
        )
        return None
    for concept_set in existing_sets:
        if concept_set.slug == slug and concept_set.domain_context == domain_context:
            cache[cache_key] = concept_set.id
            return concept_set.id
    for concept_set in existing_sets:
        if concept_set.domain_context == domain_context:
            cache[cache_key] = concept_set.id
            return concept_set.id

    try:
        created_set = concept_service.create_concept_set(
            research_space_id=research_space_id,
            name=f"{domain_context.upper()} Pipeline Concepts",
            slug=slug,
            domain_context=domain_context,
            description=(
                "System-managed concept set for extraction-stage concept linking."
            ),
            created_by=_CONCEPT_CREATED_BY,
            source_ref=source_ref,
        )
        cache[cache_key] = created_set.id
        return created_set.id  # noqa: TRY300
    except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
        logger.warning(
            "Concept set ensure failed",
            extra={
                "research_space_id": research_space_id,
                "domain_context": domain_context,
                "error": str(exc),
            },
        )
    try:
        reloaded_sets = concept_service.list_concept_sets(
            research_space_id=research_space_id,
            include_inactive=False,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
        logger.warning(
            "Concept set reload failed",
            extra={
                "research_space_id": research_space_id,
                "domain_context": domain_context,
                "error": str(exc),
            },
        )
        return None
    for concept_set in reloaded_sets:
        if concept_set.slug == slug and concept_set.domain_context == domain_context:
            cache[cache_key] = concept_set.id
            return concept_set.id
    return None


def _find_existing_member_id(  # noqa: PLR0913
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    concept_set_id: str,
    domain_context: str,
    normalized_label: str,
    sense_key: str,
    cache: dict[tuple[str, str, str], str],
) -> str | None:
    cache_key = (concept_set_id, normalized_label, sense_key)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    offset = 0
    while True:
        try:
            members = concept_service.list_concept_members(
                research_space_id=research_space_id,
                concept_set_id=concept_set_id,
                include_inactive=False,
                offset=offset,
                limit=_CONCEPT_LOOKUP_PAGE_SIZE,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            logger.warning(
                "Concept member listing failed",
                extra={
                    "research_space_id": research_space_id,
                    "concept_set_id": concept_set_id,
                    "domain_context": domain_context,
                    "error": str(exc),
                },
            )
            return None
        if not members:
            break
        for member in members:
            if member.domain_context != domain_context:
                continue
            if member.normalized_label != normalized_label:
                continue
            if member.sense_key != sense_key:
                continue
            cache[cache_key] = member.id
            return member.id
        if len(members) < _CONCEPT_LOOKUP_PAGE_SIZE:
            break
        offset += _CONCEPT_LOOKUP_PAGE_SIZE
    return None


def _list_concept_members_in_scope(  # noqa: PLR0913
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    concept_set_id: str,
    domain_context: str,
    sense_key: str,
) -> list[ConceptMember]:
    matched_members: list[ConceptMember] = []
    offset = 0
    while True:
        try:
            members = concept_service.list_concept_members(
                research_space_id=research_space_id,
                concept_set_id=concept_set_id,
                include_inactive=False,
                offset=offset,
                limit=_CONCEPT_LOOKUP_PAGE_SIZE,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            logger.warning(
                "Concept member scope listing failed",
                extra={
                    "research_space_id": research_space_id,
                    "concept_set_id": concept_set_id,
                    "domain_context": domain_context,
                    "sense_key": sense_key,
                    "error": str(exc),
                },
            )
            return []
        if not members:
            break
        matched_members.extend(
            member
            for member in members
            if member.domain_context == domain_context and member.sense_key == sense_key
        )
        if len(members) < _CONCEPT_LOOKUP_PAGE_SIZE:
            break
        offset += _CONCEPT_LOOKUP_PAGE_SIZE
    return matched_members


def _list_concept_aliases_in_scope(
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    domain_context: str,
) -> list[ConceptAlias]:
    matched_aliases: list[ConceptAlias] = []
    offset = 0
    while True:
        try:
            aliases = concept_service.list_concept_aliases(
                research_space_id=research_space_id,
                include_inactive=False,
                offset=offset,
                limit=_CONCEPT_LOOKUP_PAGE_SIZE,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            logger.warning(
                "Concept alias scope listing failed",
                extra={
                    "research_space_id": research_space_id,
                    "domain_context": domain_context,
                    "error": str(exc),
                },
            )
            return []
        if not aliases:
            break
        matched_aliases.extend(
            alias for alias in aliases if alias.domain_context == domain_context
        )
        if len(aliases) < _CONCEPT_LOOKUP_PAGE_SIZE:
            break
        offset += _CONCEPT_LOOKUP_PAGE_SIZE
    return matched_aliases


def _score_concept_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = {token for token in left.split() if token}
    right_tokens = {token for token in right.split() if token}
    union_tokens = left_tokens | right_tokens
    overlap = (
        len(left_tokens & right_tokens) / len(union_tokens) if union_tokens else 0.0
    )
    containment = (
        0.9
        if left_tokens
        and right_tokens
        and (left_tokens <= right_tokens or right_tokens <= left_tokens)
        else 0.0
    )
    sequence = SequenceMatcher(a=left, b=right).ratio()
    return max(sequence, overlap, containment)


def _build_semantic_candidates(  # noqa: PLR0913
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    concept_set_id: str,
    domain_context: str,
    normalized_label: str,
    sense_key: str,
) -> list[_ConceptSemanticCandidate]:
    members = _list_concept_members_in_scope(
        concept_service=concept_service,
        research_space_id=research_space_id,
        concept_set_id=concept_set_id,
        domain_context=domain_context,
        sense_key=sense_key,
    )
    if not members:
        return []

    member_by_id = {member.id: member for member in members}
    candidates_by_member: dict[str, _ConceptSemanticCandidate] = {}

    def record_candidate(candidate_input: _ConceptCandidateInput) -> None:
        if candidate_input.similarity_score < _CONCEPT_SEMANTIC_MATCH_THRESHOLD:
            return
        existing = candidates_by_member.get(candidate_input.member_id)
        if (
            existing is not None
            and existing.similarity_score >= candidate_input.similarity_score
        ):
            return
        candidates_by_member[candidate_input.member_id] = _ConceptSemanticCandidate(
            member_id=candidate_input.member_id,
            display_name=candidate_input.display_name,
            match_method=candidate_input.match_method,
            similarity_score=min(candidate_input.similarity_score, 1.0),
            description=candidate_input.description,
            metadata=candidate_input.metadata,
        )

    for member in members:
        canonical_score = _score_concept_similarity(
            normalized_label,
            member.canonical_label.casefold(),
        )
        normalized_score = _score_concept_similarity(
            normalized_label,
            member.normalized_label,
        )
        best_score = max(canonical_score, normalized_score)
        record_candidate(
            _ConceptCandidateInput(
                member_id=member.id,
                display_name=member.canonical_label,
                match_method="fuzzy",
                similarity_score=best_score,
                description="Existing concept member with a similar canonical label.",
                metadata={
                    "sense_key": member.sense_key,
                    "domain_context": member.domain_context,
                    "normalized_label": member.normalized_label,
                },
            ),
        )

    aliases = _list_concept_aliases_in_scope(
        concept_service=concept_service,
        research_space_id=research_space_id,
        domain_context=domain_context,
    )
    for alias in aliases:
        alias_owner_member = member_by_id.get(alias.concept_member_id)
        if alias_owner_member is None:
            continue
        alias_score = _score_concept_similarity(
            normalized_label,
            alias.alias_normalized,
        )
        record_candidate(
            _ConceptCandidateInput(
                member_id=alias_owner_member.id,
                display_name=alias_owner_member.canonical_label,
                match_method="synonym",
                similarity_score=alias_score,
                description="Existing concept alias with a semantically similar label.",
                metadata={
                    "sense_key": alias_owner_member.sense_key,
                    "domain_context": alias_owner_member.domain_context,
                    "alias_label": alias.alias_label,
                    "alias_normalized": alias.alias_normalized,
                },
            ),
        )

    sorted_candidates = sorted(
        candidates_by_member.values(),
        key=lambda candidate: (
            candidate.similarity_score,
            1 if candidate.match_method == "synonym" else 0,
            candidate.display_name,
        ),
        reverse=True,
    )
    return sorted_candidates[:_CONCEPT_SEMANTIC_CANDIDATE_LIMIT]


def _reuse_member_from_alias(  # noqa: PLR0913
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    concept_set_id: str,
    domain_context: str,
    normalized_label: str,
    sense_key: str,
    alias_scope_cache: dict[tuple[str, str], str],
) -> str | None:
    try:
        member = concept_service.resolve_member_by_alias(
            research_space_id=research_space_id,
            domain_context=domain_context,
            alias_normalized=normalized_label,
            include_inactive=False,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
        logger.warning(
            "Concept alias resolution failed",
            extra={
                "research_space_id": research_space_id,
                "concept_set_id": concept_set_id,
                "domain_context": domain_context,
                "sense_key": sense_key,
                "alias_normalized": normalized_label,
                "error": str(exc),
            },
        )
        return None
    if member is None:
        return None
    if member.concept_set_id != concept_set_id:
        return None
    if member.domain_context != domain_context:
        return None
    if member.sense_key != sense_key:
        return None
    alias_scope_cache[(domain_context, normalized_label)] = member.id
    return member.id


def _suggest_concept_merge_before_create(  # noqa: PLR0913
    *,
    concept_service: ConceptPort,
    mapping_judge_agent: MappingJudgePort | None,
    research_space_id: str,
    concept_set_id: str,
    domain_context: str,
    canonical_label: str,
    normalized_label: str,
    sense_key: str,
    source_ref: str,
    semantic_candidates: list[_ConceptSemanticCandidate],
    research_space_settings: ResearchSpaceSettings,
) -> tuple[str | None, str | None]:
    if not semantic_candidates:
        return None, None

    judge_outcome: str | None = None
    judge_rationale: str | None = None
    selected_member_id: str | None = None
    if mapping_judge_agent is not None:
        try:
            from src.domain.agents.contexts.mapping_judge_context import (
                MappingJudgeContext,
            )
            from src.domain.agents.contracts.mapping_judge import MappingJudgeCandidate

            contract = mapping_judge_agent.judge(
                MappingJudgeContext(
                    field_key=f"{sense_key}:concept_member",
                    field_value_preview=canonical_label[:2000],
                    source_id=concept_set_id[:128],
                    source_type="concept_merge",
                    domain_context=domain_context,
                    record_metadata={
                        "concept_set_id": concept_set_id,
                        "candidate_label": canonical_label,
                        "normalized_label": normalized_label,
                        "sense_key": sense_key,
                        "source_ref": source_ref,
                    },
                    candidates=[
                        MappingJudgeCandidate(
                            variable_id=candidate.member_id,
                            display_name=candidate.display_name,
                            match_method=candidate.match_method,
                            similarity_score=candidate.similarity_score,
                            description=candidate.description,
                            metadata=candidate.metadata,
                        )
                        for candidate in semantic_candidates
                    ],
                ),
            )
            judge_outcome = contract.decision
            judge_rationale = contract.selection_rationale
            selected_variable_id = (
                contract.selected_variable_id.strip()
                if isinstance(contract.selected_variable_id, str)
                else ""
            )
            candidate_ids = {candidate.member_id for candidate in semantic_candidates}
            if (
                contract.decision == "matched"
                and selected_variable_id
                and selected_variable_id in candidate_ids
            ):
                selected_member_id = selected_variable_id
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            logger.warning(
                "Concept merge judge failed",
                extra={
                    "research_space_id": research_space_id,
                    "concept_set_id": concept_set_id,
                    "domain_context": domain_context,
                    "sense_key": sense_key,
                    "candidate_label": canonical_label,
                    "error": str(exc),
                },
            )
            judge_outcome = "judge_failed"
            judge_rationale = type(exc).__name__
    else:
        judge_outcome = "judge_unavailable"

    if selected_member_id is not None:
        return selected_member_id, None

    decision_id = _propose_concept_mapping_decision(
        concept_service=concept_service,
        research_space_id=research_space_id,
        concept_set_id=concept_set_id,
        decision_payload={
            "conflict_kind": "concept_semantic_merge_candidate",
            "canonical_label": canonical_label,
            "normalized_label": normalized_label,
            "sense_key": sense_key,
            "judge_outcome": judge_outcome,
            "judge_rationale": judge_rationale,
            "semantic_candidates": [
                {
                    "concept_member_id": candidate.member_id,
                    "display_name": candidate.display_name,
                    "match_method": candidate.match_method,
                    "similarity_score": candidate.similarity_score,
                }
                for candidate in semantic_candidates
            ],
        },
        evidence_payload={
            "source_ref": source_ref,
            "domain_context": domain_context,
        },
        confidence=(
            max(candidate.similarity_score for candidate in semantic_candidates)
            if semantic_candidates
            else 0.5
        ),
        rationale=(
            "Semantic concept candidates were detected before provisional concept "
            "creation and require review."
        ),
        research_space_settings=research_space_settings,
    )
    return None, decision_id


def _propose_concept_mapping_decision(  # noqa: PLR0913
    *,
    concept_service: ConceptPort,
    research_space_id: str,
    concept_set_id: str | None,
    decision_payload: JSONObject,
    evidence_payload: JSONObject,
    confidence: float,
    rationale: str,
    research_space_settings: ResearchSpaceSettings,
) -> str | None:
    try:
        decision = concept_service.propose_decision(
            research_space_id=research_space_id,
            decision_type="MAP",
            proposed_by=_CONCEPT_CREATED_BY,
            decision_payload=decision_payload,
            evidence_payload=evidence_payload,
            confidence=confidence,
            rationale=rationale,
            concept_set_id=concept_set_id,
            research_space_settings=research_space_settings,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
        logger.warning(
            "Concept decision proposal failed",
            extra={
                "research_space_id": research_space_id,
                "concept_set_id": concept_set_id,
                "error": str(exc),
            },
        )
        return None
    return decision.id


def _ensure_concept_member(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    concept_service: ConceptPort,
    concept_set_id: str,
    research_space_id: str,
    domain_context: str,
    candidate_label: str | None,
    sense_key: str,
    source_ref: str,
    alias_source: str,
    research_space_settings: ResearchSpaceSettings,
    member_cache: dict[tuple[str, str, str], str],
    alias_cache: set[tuple[str, str, str]],
    alias_scope_cache: dict[tuple[str, str], str],
    mapping_judge_agent: MappingJudgePort | None,
) -> _ConceptLinkageResult:
    canonical_label, normalized_label = _normalize_concept_label(candidate_label)
    if not canonical_label or not normalized_label:
        return _ConceptLinkageResult()

    existing_member_id = _find_existing_member_id(
        concept_service=concept_service,
        research_space_id=research_space_id,
        concept_set_id=concept_set_id,
        domain_context=domain_context,
        normalized_label=normalized_label,
        sense_key=sense_key,
        cache=member_cache,
    )
    members_created_count = 0
    decision_ids: list[str] = []
    member_id = existing_member_id
    if member_id is None:
        member_id = _reuse_member_from_alias(
            concept_service=concept_service,
            research_space_id=research_space_id,
            concept_set_id=concept_set_id,
            domain_context=domain_context,
            normalized_label=normalized_label,
            sense_key=sense_key,
            alias_scope_cache=alias_scope_cache,
        )
    if member_id is None:
        semantic_candidates = _build_semantic_candidates(
            concept_service=concept_service,
            research_space_id=research_space_id,
            concept_set_id=concept_set_id,
            domain_context=domain_context,
            normalized_label=normalized_label,
            sense_key=sense_key,
        )
        member_id, decision_id = _suggest_concept_merge_before_create(
            concept_service=concept_service,
            mapping_judge_agent=mapping_judge_agent,
            research_space_id=research_space_id,
            concept_set_id=concept_set_id,
            domain_context=domain_context,
            canonical_label=canonical_label,
            normalized_label=normalized_label,
            sense_key=sense_key,
            source_ref=source_ref,
            semantic_candidates=semantic_candidates,
            research_space_settings=research_space_settings,
        )
        if decision_id is not None:
            decision_ids.append(decision_id)
    if member_id is None:
        try:
            created_member = concept_service.create_concept_member(
                concept_set_id=concept_set_id,
                research_space_id=research_space_id,
                domain_context=domain_context,
                canonical_label=canonical_label,
                normalized_label=normalized_label,
                sense_key=sense_key,
                is_provisional=True,
                metadata_payload={
                    "source": "extraction_pipeline",
                    "source_ref": source_ref,
                },
                created_by=_CONCEPT_CREATED_BY,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            member_id = created_member.id
            members_created_count = 1
            member_cache[(concept_set_id, normalized_label, sense_key)] = member_id
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            member_id = _find_existing_member_id(
                concept_service=concept_service,
                research_space_id=research_space_id,
                concept_set_id=concept_set_id,
                domain_context=domain_context,
                normalized_label=normalized_label,
                sense_key=sense_key,
                cache=member_cache,
            )
            if member_id is None:
                decision_id = _propose_concept_mapping_decision(
                    concept_service=concept_service,
                    research_space_id=research_space_id,
                    concept_set_id=concept_set_id,
                    decision_payload={
                        "conflict_kind": "concept_member_create_failed",
                        "canonical_label": canonical_label,
                        "normalized_label": normalized_label,
                        "sense_key": sense_key,
                        "error": str(exc),
                    },
                    evidence_payload={"source_ref": source_ref},
                    confidence=0.5,
                    rationale=(
                        "Concept member creation failed and no existing provisional "
                        "member could be resolved."
                    ),
                    research_space_settings=research_space_settings,
                )
                if decision_id is not None:
                    decision_ids.append(decision_id)
                return _ConceptLinkageResult(
                    decisions_proposed_count=1 if decision_id is not None else 0,
                    errors=("concept_member_create_failed",),
                )

    alias_key = (member_id, domain_context, normalized_label)
    aliases_created_count = 0
    alias_scope_key = (domain_context, normalized_label)
    existing_alias_owner = alias_scope_cache.get(alias_scope_key)
    if existing_alias_owner is None:
        existing_alias_owner = ""
        offset = 0
        try:
            while True:
                aliases = concept_service.list_concept_aliases(
                    research_space_id=research_space_id,
                    include_inactive=False,
                    offset=offset,
                    limit=_CONCEPT_LOOKUP_PAGE_SIZE,
                )
                if not aliases:
                    break
                for alias in aliases:
                    if alias.domain_context != domain_context:
                        continue
                    if alias.alias_normalized != normalized_label:
                        continue
                    existing_alias_owner = alias.concept_member_id
                    break
                if existing_alias_owner:
                    break
                if len(aliases) < _CONCEPT_LOOKUP_PAGE_SIZE:
                    break
                offset += _CONCEPT_LOOKUP_PAGE_SIZE
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            logger.warning(
                "Concept alias pre-check failed",
                extra={
                    "research_space_id": research_space_id,
                    "domain_context": domain_context,
                    "alias_normalized": normalized_label,
                    "error": str(exc),
                },
            )
        alias_scope_cache[alias_scope_key] = existing_alias_owner

    if existing_alias_owner and existing_alias_owner != member_id:
        decision_id = _propose_concept_mapping_decision(
            concept_service=concept_service,
            research_space_id=research_space_id,
            concept_set_id=concept_set_id,
            decision_payload={
                "conflict_kind": "concept_alias_conflict_existing_owner",
                "concept_member_id": member_id,
                "existing_owner_member_id": existing_alias_owner,
                "alias_normalized": normalized_label,
            },
            evidence_payload={"source_ref": source_ref},
            confidence=0.6,
            rationale=(
                "Alias already belongs to a different concept member in this "
                "domain context."
            ),
            research_space_settings=research_space_settings,
        )
        if decision_id is not None:
            decision_ids.append(decision_id)
        return _ConceptLinkageResult(
            concept_refs={"concept_member_id": member_id, "decision_ids": decision_ids},
            members_created_count=members_created_count,
            aliases_created_count=0,
            decisions_proposed_count=len(decision_ids),
        )

    if existing_alias_owner == member_id:
        alias_cache.add(alias_key)

    if alias_key not in alias_cache:
        try:
            concept_service.create_concept_alias(
                concept_member_id=member_id,
                research_space_id=research_space_id,
                domain_context=domain_context,
                alias_label=canonical_label,
                alias_normalized=normalized_label,
                source=alias_source,
                created_by=_CONCEPT_CREATED_BY,
                source_ref=source_ref,
            )
            alias_cache.add(alias_key)
            alias_scope_cache[alias_scope_key] = member_id
            aliases_created_count = 1
        except Exception as exc:  # noqa: BLE001 - fail-open for extraction persistence
            try:
                aliases = concept_service.list_concept_aliases(
                    research_space_id=research_space_id,
                    concept_member_id=member_id,
                    include_inactive=False,
                    offset=0,
                    limit=200,
                )
                if any(alias.alias_normalized == normalized_label for alias in aliases):
                    alias_cache.add(alias_key)
                else:
                    decision_id = _propose_concept_mapping_decision(
                        concept_service=concept_service,
                        research_space_id=research_space_id,
                        concept_set_id=concept_set_id,
                        decision_payload={
                            "conflict_kind": "concept_alias_create_failed",
                            "concept_member_id": member_id,
                            "alias_normalized": normalized_label,
                            "error": str(exc),
                        },
                        evidence_payload={"source_ref": source_ref},
                        confidence=0.5,
                        rationale=(
                            "Concept alias creation failed and no matching alias exists "
                            "for the target concept member."
                        ),
                        research_space_settings=research_space_settings,
                    )
                    if decision_id is not None:
                        decision_ids.append(decision_id)
            except Exception as list_exc:  # noqa: BLE001 - fail-open
                logger.warning(
                    "Concept alias listing failed",
                    extra={
                        "research_space_id": research_space_id,
                        "concept_member_id": member_id,
                        "error": str(list_exc),
                    },
                )

    concept_refs: JSONObject = {"concept_member_id": member_id}
    if decision_ids:
        concept_refs["decision_ids"] = decision_ids
    return _ConceptLinkageResult(
        concept_refs=concept_refs,
        members_created_count=members_created_count,
        aliases_created_count=aliases_created_count,
        decisions_proposed_count=len(decision_ids),
    )


__all__ = [
    "_ConceptLinkageResult",
    "_ensure_concept_member",
    "_normalize_sense_key",
    "_resolve_document_domain_context",
    "_resolve_or_create_concept_set",
]
