"""Research-init source selection and PubMed candidate helpers."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.marrvel_enrichment import (
    prioritize_marrvel_gene_labels as _shared_prioritize_marrvel_gene_labels,
)
from artana_evidence_api.process_health import read_heartbeat
from artana_evidence_api.source_registry import (
    default_research_plan_source_preferences,
    normalize_source_key,
    research_plan_source_keys,
    unknown_source_preference_keys,
)
from artana_evidence_api.types.common import (
    ResearchSpaceSettings,
    ResearchSpaceSourcePreferences,
)
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.proposal_store import HarnessProposalStore

_SYSTEM_OWNER_ID = UUID("00000000-0000-0000-0000-000000000000")
LOGGER = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
_GENE_SYMBOL_PATTERN = re.compile(r"[A-Za-z]{2,10}[0-9]{1,5}[A-Za-z]{0,3}")
_DEFAULT_RESEARCH_INIT_SOURCES: ResearchSpaceSourcePreferences = (
    default_research_plan_source_preferences()
)
_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "based",
    "be",
    "been",
    "being",
    "between",
    "build",
    "by",
    "compare",
    "create",
    "determine",
    "distinguish",
    "evaluate",
    "examine",
    "explore",
    "for",
    "from",
    "goal",
    "goals",
    "how",
    "identify",
    "in",
    "include",
    "including",
    "investigate",
    "is",
    "it",
    "its",
    "no",
    "not",
    "of",
    "on",
    "or",
    "project",
    "question",
    "questions",
    "research",
    "role",
    "study",
    "target",
    "that",
    "the",
    "these",
    "this",
    "those",
    "to",
    "understand",
    "was",
    "were",
    "what",
    "whether",
    "with",
}
_GENERIC_SCIENCE_TERMS = {
    "activity",
    "association",
    "associations",
    "biology",
    "cancer",
    "cancers",
    "cell",
    "cells",
    "clinical",
    "cohort",
    "context",
    "data",
    "dataset",
    "datasets",
    "development",
    "disease",
    "effect",
    "effects",
    "factor",
    "factors",
    "function",
    "functions",
    "mechanism",
    "mechanisms",
    "model",
    "models",
    "molecular",
    "pathway",
    "pathways",
    "patient",
    "patients",
    "process",
    "processes",
    "regulation",
    "relationship",
    "relationships",
    "resource",
    "resources",
    "shared",
    "system",
    "systems",
    "transcriptome",
    "transcriptomes",
    "transcriptomic",
    "transcriptomics",
    "underlying",
}
_GENERIC_QUERY_SEED_TOKENS = {
    "case",
    "cases",
    "cell",
    "cells",
    "clinical",
    "condition",
    "conditions",
    "connections",
    "disease",
    "evidence",
    "feature",
    "features",
    "hidden",
    "hypothesis",
    "hypotheses",
    "management",
    "mechanism",
    "mechanisms",
    "new",
    "pathway",
    "pathways",
    "phenotype",
    "phenotypes",
    "report",
    "reports",
    "related",
    "symptom",
    "symptoms",
    "therapeutic",
    "therapy",
    "transcriptome",
    "transcriptomes",
    "transcriptomic",
    "transcriptomics",
    "treatment",
}
_MAX_QUERY_TERMS = 6
_MAX_PREVIEWS_PER_QUERY = 5
_MAX_CANDIDATES_TO_INGEST = 10
_MAX_CANDIDATES_FOR_LLM_REVIEW = 12
_MAX_LLM_CANDIDATES_PER_QUERY_FAMILY = 2
_HEURISTIC_RELEVANCE_THRESHOLD = 3
_HIGH_SPECIFICITY_QUERY_THRESHOLD = 6
_LLM_RELEVANCE_TIMEOUT_SECONDS = 20.0
_MAX_LLM_RELEVANCE_CONCURRENCY = 4
_MIN_QUERY_TOKEN_LENGTH = 2
_MEDIUM_QUERY_TOKEN_LENGTH = 5
_LONG_QUERY_TOKEN_LENGTH = 10
_HTTP_OK = 200
_WORKER_HEARTBEAT_PATH = "logs/artana-evidence-api-worker-heartbeat.json"
_WORKER_MAX_AGE_SECONDS = 120.0
_RUN_PROGRESS_PATH_TEMPLATE = "/v1/spaces/{space_id}/runs/{run_id}/progress"
ResearchInitOrchestrationMode = Literal[
    "deterministic",
    "full_ai_shadow",
    "full_ai_guarded",
]
_DEFAULT_RESEARCH_ORCHESTRATION_MODE: ResearchInitOrchestrationMode = "full_ai_guarded"
_RESEARCH_INIT_ORCHESTRATOR_PLANNER_MODES: dict[
    ResearchInitOrchestrationMode,
    FullAIOrchestratorPlannerMode | None,
] = {
    "deterministic": None,
    "full_ai_shadow": FullAIOrchestratorPlannerMode.SHADOW,
    "full_ai_guarded": FullAIOrchestratorPlannerMode.GUARDED,
}


@dataclass(frozen=True, slots=True)
class _ObjectiveQueryTerm:
    token: str
    normalized: str
    score: int
    index: int


@dataclass(slots=True)
class _PubMedCandidate:
    title: str
    text: str
    queries: list[str]
    pmid: str | None = None
    doi: str | None = None
    pmc_id: str | None = None
    journal: str | None = None


@dataclass(frozen=True, slots=True)
class _CandidateAnchorProfile:
    anchor_phrases: tuple[str, ...]
    anchor_tokens: tuple[str, ...]
    focus_phrases: tuple[str, ...]
    focus_tokens: tuple[str, ...]
    core_anchor_phrases: tuple[str, ...]
    core_anchor_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PubMedCandidateReview:
    method: Literal["heuristic", "llm"]
    label: Literal["relevant", "non_relevant"]
    confidence: float
    rationale: str
    agent_run_id: str | None = None
    signal_count: int = 0
    focus_signal_count: int = 0
    query_specificity: int = 0


@dataclass(frozen=True, slots=True)
class _AnchorMatchResult:
    score: int
    title_matches: list[str]
    text_matches: list[str]
    focus_matches: list[str]
    core_matches: list[str]


def _normalize_text_token(value: str) -> str:
    return value.strip().strip(".,;:()[]{}\"'").casefold()


def _normalize_free_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _tokenize_text(value: str) -> list[str]:
    return [match.group(0) for match in _TOKEN_PATTERN.finditer(value)]


def _normalized_tokens(value: str) -> list[str]:
    normalized_tokens: list[str] = []
    for token in _tokenize_text(value):
        normalized = _normalize_text_token(token)
        if normalized != "":
            normalized_tokens.append(normalized)
    return normalized_tokens


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        normalized = value.casefold()
        if normalized in seen:
            continue
        deduped.append(value)
        seen.add(normalized)
    return deduped


def _looks_like_gene_symbol(term: str) -> bool:
    normalized = term.strip().upper()
    if " " in normalized or normalized == "":
        return False
    return _GENE_SYMBOL_PATTERN.fullmatch(normalized) is not None


def _is_actionable_seed_term(term: str) -> bool:
    tokens = [
        _normalize_text_token(token)
        for token in _tokenize_text(term)
        if _normalize_text_token(token) != ""
    ]
    if not tokens:
        return False
    if _looks_like_gene_symbol(term):
        return True
    generic_tokens = _GENERIC_QUERY_SEED_TOKENS | _GENERIC_SCIENCE_TERMS
    return any(token not in generic_tokens for token in tokens)


def _rank_objective_query_terms(
    objective: str,
    seed_terms: list[str],
) -> list[_ObjectiveQueryTerm]:
    seed_token_set = {
        _normalize_text_token(token)
        for seed_term in seed_terms
        for token in _tokenize_text(seed_term)
        if _normalize_text_token(token) != ""
    }

    ranked_terms: list[_ObjectiveQueryTerm] = []
    for index, raw_token in enumerate(_tokenize_text(objective)):
        normalized = _normalize_text_token(raw_token)
        if len(normalized) < _MIN_QUERY_TOKEN_LENGTH or normalized in _QUERY_STOPWORDS:
            continue
        if raw_token.isdigit():
            continue

        score = 0
        if any(character.isdigit() for character in raw_token):
            score += 4
        if normalized in seed_token_set:
            score += 3
        if len(normalized) >= _LONG_QUERY_TOKEN_LENGTH:
            score += 2
        if len(normalized) >= _MEDIUM_QUERY_TOKEN_LENGTH:
            score += 1
        if normalized in _GENERIC_SCIENCE_TERMS:
            score -= 3

        if score <= 0:
            continue

        ranked_terms.append(
            _ObjectiveQueryTerm(
                token=raw_token,
                normalized=normalized,
                score=score,
                index=index,
            ),
        )

    ranked_terms.sort(key=lambda term: (-term.score, term.index))
    return ranked_terms


def _build_query_from_ranked_terms(
    ranked_terms: list[_ObjectiveQueryTerm],
    *,
    max_terms: int,
) -> str | None:
    selected: list[_ObjectiveQueryTerm] = []
    seen: set[str] = set()
    for term in ranked_terms:
        if term.normalized in seen:
            continue
        selected.append(term)
        seen.add(term.normalized)
        if len(selected) >= max_terms:
            break
    if not selected:
        return None
    selected.sort(key=lambda term: term.index)
    return " ".join(term.token for term in selected)


def _build_pubmed_queries(
    objective: str,
    seed_terms: list[str],
) -> list[dict[str, str]]:
    """Build PubMed queries from research objective anchors and seed terms."""
    queries: list[dict[str, str]] = []
    cleaned_seed_terms = _dedupe_preserving_order(
        [
            term.strip()
            for term in seed_terms
            if term.strip() != "" and _is_actionable_seed_term(term)
        ],
    )
    ranked_terms = _rank_objective_query_terms(objective, cleaned_seed_terms)

    primary_query = _build_query_from_ranked_terms(
        ranked_terms,
        max_terms=_MAX_QUERY_TERMS,
    )
    if primary_query is not None:
        queries.append({"search_term": primary_query})

    focused_query = _build_query_from_ranked_terms(
        ranked_terms[: max(_MAX_QUERY_TERMS - 1, 1)],
        max_terms=4,
    )
    if focused_query is not None and focused_query != primary_query:
        queries.append({"search_term": focused_query})

    if len(cleaned_seed_terms) > 1:
        combined_seed_query = " ".join(cleaned_seed_terms[:3])
        queries.append({"search_term": combined_seed_query})

    for term in cleaned_seed_terms[:5]:
        query: dict[str, str] = {"search_term": term}
        if _looks_like_gene_symbol(term):
            query["gene_symbol"] = term
        queries.append(query)

    if not queries:
        fallback = objective.strip()[:80]
        if fallback != "":
            queries.append({"search_term": fallback})

    deduped_queries: list[dict[str, str]] = []
    seen_query_keys: set[tuple[str, str]] = set()
    for query in queries:
        key = (
            query.get("search_term", "").casefold(),
            query.get("gene_symbol", "").casefold(),
        )
        if key in seen_query_keys:
            continue
        seen_query_keys.add(key)
        deduped_queries.append(query)
    return deduped_queries


def _candidate_key(*, pmid: str | None, title: str) -> str:
    if pmid is not None and pmid.strip() != "":
        return f"pmid:{pmid.strip()}"
    return f"title:{_normalize_free_text(title)}"


def _merge_candidate(
    existing: _PubMedCandidate,
    incoming: _PubMedCandidate,
) -> _PubMedCandidate:
    merged_queries = _dedupe_preserving_order([*existing.queries, *incoming.queries])
    merged_text = (
        incoming.text if len(incoming.text) > len(existing.text) else existing.text
    )
    return _PubMedCandidate(
        title=existing.title,
        text=merged_text,
        queries=merged_queries,
        pmid=existing.pmid or incoming.pmid,
        doi=existing.doi or incoming.doi,
        pmc_id=existing.pmc_id or incoming.pmc_id,
        journal=existing.journal or incoming.journal,
    )


def _build_candidate_anchor_profile(
    objective: str,
    seed_terms: list[str],
) -> _CandidateAnchorProfile:
    cleaned_seed_terms = _dedupe_preserving_order(
        [
            _normalize_free_text(term)
            for term in seed_terms
            if term.strip() != "" and _is_actionable_seed_term(term)
        ],
    )
    ranked_terms = _rank_objective_query_terms(objective, cleaned_seed_terms)
    anchor_tokens = _dedupe_preserving_order(
        [term.normalized for term in ranked_terms[:8]],
    )
    anchor_phrases = tuple(phrase for phrase in cleaned_seed_terms if phrase != "")
    standalone_anchor_tokens = _dedupe_preserving_order(
        [
            normalized_tokens[0]
            for phrase in anchor_phrases
            if len(normalized_tokens := _normalized_tokens(phrase)) == 1
        ],
    )
    phrase_token_set = {
        token for phrase in anchor_phrases for token in _normalized_tokens(phrase)
    }
    focus_phrases = tuple(anchor_phrases[1:])
    focus_phrase_token_set = {
        token for phrase in focus_phrases for token in _normalized_tokens(phrase)
    }
    focus_tokens = tuple(
        token
        for token in anchor_tokens
        if token not in phrase_token_set or token in focus_phrase_token_set
    )
    core_anchor_tokens = tuple(
        token for token in anchor_tokens if token in standalone_anchor_tokens
    )
    core_anchor_phrases = tuple(
        phrase
        for phrase in anchor_phrases
        if any(token in core_anchor_tokens for token in _normalized_tokens(phrase))
    )
    return _CandidateAnchorProfile(
        anchor_phrases=anchor_phrases,
        anchor_tokens=tuple(anchor_tokens),
        focus_phrases=focus_phrases,
        focus_tokens=focus_tokens,
        core_anchor_phrases=core_anchor_phrases,
        core_anchor_tokens=core_anchor_tokens,
    )


def _query_specificity_score(query: str) -> int:
    tokens = {
        token for token in _normalized_tokens(query) if token not in _QUERY_STOPWORDS
    }
    if not tokens:
        return 0
    specific_tokens = {token for token in tokens if token not in _GENERIC_SCIENCE_TERMS}
    return (len(specific_tokens) * 3) + len(tokens)


def _candidate_primary_query_family(candidate: _PubMedCandidate) -> str:
    if not candidate.queries:
        return "__no_query__"
    return max(
        (
            _normalize_free_text(query)
            for query in candidate.queries
            if query.strip() != ""
        ),
        key=_query_specificity_score,
        default="__no_query__",
    )


def _candidate_priority_key(
    candidate: _PubMedCandidate,
    review: _PubMedCandidateReview,
) -> tuple[int, int, int, float, int, int]:
    return (
        review.focus_signal_count,
        review.query_specificity,
        review.signal_count,
        review.confidence,
        len(candidate.queries),
        len(candidate.text),
    )


def _shortlist_candidates_for_llm_review(  # noqa: PLR0912
    heuristic_shortlist: list[tuple[_PubMedCandidate, _PubMedCandidateReview]],
) -> list[tuple[_PubMedCandidate, _PubMedCandidateReview]]:
    if len(heuristic_shortlist) <= _MAX_CANDIDATES_FOR_LLM_REVIEW:
        return sorted(
            heuristic_shortlist,
            key=lambda item: _candidate_priority_key(item[0], item[1]),
            reverse=True,
        )

    ordered_shortlist = sorted(
        heuristic_shortlist,
        key=lambda item: _candidate_priority_key(item[0], item[1]),
        reverse=True,
    )
    grouped_candidates: dict[
        str,
        list[tuple[_PubMedCandidate, _PubMedCandidateReview]],
    ] = {}
    family_order: list[str] = []
    for candidate, review in ordered_shortlist:
        family_key = _candidate_primary_query_family(candidate)
        if family_key not in grouped_candidates:
            grouped_candidates[family_key] = []
            family_order.append(family_key)
        grouped_candidates[family_key].append((candidate, review))

    selected: list[tuple[_PubMedCandidate, _PubMedCandidateReview]] = []
    per_family_counts: dict[str, int] = {}
    while len(selected) < _MAX_CANDIDATES_FOR_LLM_REVIEW:
        added_in_round = False
        for family_key in family_order:
            family_candidates = grouped_candidates.get(family_key, [])
            if not family_candidates:
                continue
            if (
                per_family_counts.get(family_key, 0)
                >= _MAX_LLM_CANDIDATES_PER_QUERY_FAMILY
            ):
                continue
            candidate, review = family_candidates.pop(0)
            selected.append((candidate, review))
            per_family_counts[family_key] = per_family_counts.get(family_key, 0) + 1
            added_in_round = True
            if len(selected) >= _MAX_CANDIDATES_FOR_LLM_REVIEW:
                break
        if added_in_round:
            continue
        fallback_added = False
        for family_key in family_order:
            family_candidates = grouped_candidates.get(family_key, [])
            if not family_candidates:
                continue
            candidate, review = family_candidates.pop(0)
            selected.append((candidate, review))
            fallback_added = True
            if len(selected) >= _MAX_CANDIDATES_FOR_LLM_REVIEW:
                break
        if not fallback_added:
            break

    return selected


def _describe_scope_refinement_anchor(
    objective: str,
    seed_terms: list[str],
) -> str:
    cleaned_seed_terms = _dedupe_preserving_order(
        [
            term.strip()
            for term in seed_terms
            if term.strip() != "" and _is_actionable_seed_term(term)
        ],
    )
    if cleaned_seed_terms:
        return cleaned_seed_terms[0]
    queries = _build_pubmed_queries(objective, seed_terms)
    if queries:
        primary_query = queries[0].get("search_term", "").strip()
        if primary_query != "":
            return primary_query
    return objective.strip()


def _run_marrvel_enrichment(
    *,
    space_id: UUID,
    objective: str,
    graph_api_gateway: GraphTransportBundle,
    proposal_store: HarnessProposalStore | None = None,
    run_id: str | None = None,
) -> int:
    """Retired: MARRVEL proposals now come from the shared extraction pipeline.

    Direct MARRVEL proposal creation has been removed.  MARRVEL records are
    ingested as source documents with Tier 1 grounding attached, then flow
    through entity recognition → extraction → governed claims like all other
    connector families.
    """
    del objective, graph_api_gateway, proposal_store, run_id
    logging.getLogger(__name__).info(
        "MARRVEL direct enrichment retired for space %s — "
        "proposals now come from the shared extraction pipeline",
        space_id,
    )
    return 0


def _normalize_source_preferences(
    raw_sources: object,
) -> ResearchSpaceSourcePreferences:
    normalized: dict[str, bool] = {}
    if not isinstance(raw_sources, dict):
        return cast("ResearchSpaceSourcePreferences", normalized)
    allowed_keys = frozenset(research_plan_source_keys())
    for raw_key, value in raw_sources.items():
        if not isinstance(raw_key, str):
            continue
        key = normalize_source_key(raw_key)
        if key not in allowed_keys:
            continue
        if isinstance(value, bool):
            normalized[key] = value
    return cast("ResearchSpaceSourcePreferences", normalized)


def _unknown_source_preference_keys(raw_sources: object) -> tuple[str, ...]:
    return unknown_source_preference_keys(raw_sources)


def _resolve_research_init_sources(
    *,
    request_sources: object,
    space_settings: ResearchSpaceSettings | None,
) -> ResearchSpaceSourcePreferences:
    request_preferences = _normalize_source_preferences(request_sources)
    if request_preferences:
        request_resolved = cast(
            "ResearchSpaceSourcePreferences",
            dict.fromkeys(_DEFAULT_RESEARCH_INIT_SOURCES, False),
        )
        request_resolved.update(request_preferences)
        return request_resolved

    resolved = cast(
        "ResearchSpaceSourcePreferences",
        dict(_DEFAULT_RESEARCH_INIT_SOURCES),
    )
    if isinstance(space_settings, dict):
        resolved.update(_normalize_source_preferences(space_settings.get("sources")))
    return resolved


def _resolve_research_orchestration_mode(
    *,
    request_mode: ResearchInitOrchestrationMode | None,
    space_settings: ResearchSpaceSettings | None,
) -> ResearchInitOrchestrationMode:
    """Resolve the execution shell for research-init without changing defaults."""
    if request_mode is not None:
        return request_mode
    if not isinstance(space_settings, dict):
        return _DEFAULT_RESEARCH_ORCHESTRATION_MODE
    raw_mode = space_settings.get("research_orchestration_mode")
    if raw_mode is None:
        return _DEFAULT_RESEARCH_ORCHESTRATION_MODE
    if raw_mode in _RESEARCH_INIT_ORCHESTRATOR_PLANNER_MODES:
        return raw_mode
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Invalid research_orchestration_mode setting. Expected one of: "
            "deterministic, full_ai_shadow, full_ai_guarded."
        ),
    )


def _planner_mode_for_research_orchestration(
    mode: ResearchInitOrchestrationMode,
) -> FullAIOrchestratorPlannerMode | None:
    """Return the full-orchestrator planner mode for opt-in research-init runs."""
    return _RESEARCH_INIT_ORCHESTRATOR_PLANNER_MODES[mode]


def _prioritize_marrvel_gene_labels(
    labels: list[str],
    *,
    objective: str,
    limit: int,
) -> list[str]:
    return _shared_prioritize_marrvel_gene_labels(
        labels,
        objective=objective,
        limit=limit,
    )


def _build_scope_refinement_questions(
    *,
    objective: str,
    seed_terms: list[str],
) -> list[str]:
    anchor = _describe_scope_refinement_anchor(objective, seed_terms)
    if anchor == "":
        anchor = "this research space"
    return [
        (
            f"I did not find enough evidence in the initial research pass for {anchor}. "
            "Which direction should I deepen next: "
            "direct functional evidence, mechanisms and pathways, "
            "perturbation or model-system evidence, or "
            "related genes, proteins, biomarkers, or pathways?"
        ),
    ]


def _requires_core_anchor_signal(anchor_profile: _CandidateAnchorProfile) -> bool:
    return bool(anchor_profile.core_anchor_phrases) or bool(
        anchor_profile.core_anchor_tokens,
    )


def _heuristic_relevance_label(
    *,
    score: int,
    anchor_profile: _CandidateAnchorProfile,
    unique_core_signals: set[str],
) -> Literal["relevant", "non_relevant"]:
    if score < _HEURISTIC_RELEVANCE_THRESHOLD:
        return "non_relevant"
    if _requires_core_anchor_signal(anchor_profile) and not unique_core_signals:
        return "non_relevant"
    return "relevant"


def _build_heuristic_evidence_parts(
    *,
    matched_title_phrases: list[str],
    matched_text_phrases: list[str],
    matched_title_tokens: list[str],
    matched_text_tokens: list[str],
    unique_focus_signals: set[str],
    unique_core_signals: set[str],
    query_specificity: int,
    anchor_profile: _CandidateAnchorProfile,
    score: int,
) -> list[str]:
    return [
        f"title_phrases={','.join(matched_title_phrases) or 'none'}",
        f"text_phrases={','.join(matched_text_phrases) or 'none'}",
        f"title_tokens={','.join(matched_title_tokens) or 'none'}",
        f"text_tokens={','.join(matched_text_tokens) or 'none'}",
        f"focus_signals={','.join(sorted(unique_focus_signals)) or 'none'}",
        f"core_signals={','.join(sorted(unique_core_signals)) or 'none'}",
        f"query_specificity={query_specificity}",
        (
            "requires_core_signal="
            f"{'yes' if _requires_core_anchor_signal(anchor_profile) else 'no'}"
        ),
        f"score={score}",
    ]


def _match_anchor_phrases(
    *,
    normalized_title: str,
    normalized_text: str,
    anchor_profile: _CandidateAnchorProfile,
) -> _AnchorMatchResult:
    score = 0
    title_matches: list[str] = []
    text_matches: list[str] = []
    focus_matches: list[str] = []
    core_matches: list[str] = []
    for phrase in anchor_profile.anchor_phrases:
        if phrase in normalized_title:
            score += 4
            title_matches.append(phrase)
            if phrase in anchor_profile.focus_phrases:
                focus_matches.append(phrase)
            if phrase in anchor_profile.core_anchor_phrases:
                core_matches.append(phrase)
        elif phrase in normalized_text:
            score += 3
            text_matches.append(phrase)
            if phrase in anchor_profile.focus_phrases:
                focus_matches.append(phrase)
            if phrase in anchor_profile.core_anchor_phrases:
                core_matches.append(phrase)
    return _AnchorMatchResult(
        score=score,
        title_matches=title_matches,
        text_matches=text_matches,
        focus_matches=focus_matches,
        core_matches=core_matches,
    )


def _candidate_token_sets(candidate: _PubMedCandidate) -> tuple[set[str], set[str]]:
    return (
        {_normalize_text_token(token) for token in _tokenize_text(candidate.title)},
        {_normalize_text_token(token) for token in _tokenize_text(candidate.text)},
    )


def _match_anchor_tokens(
    *,
    title_tokens: set[str],
    body_tokens: set[str],
    anchor_profile: _CandidateAnchorProfile,
) -> _AnchorMatchResult:
    score = 0
    title_matches: list[str] = []
    text_matches: list[str] = []
    focus_matches: list[str] = []
    core_matches: list[str] = []
    for token in anchor_profile.anchor_tokens:
        if token in title_tokens:
            score += 2
            title_matches.append(token)
            if token in anchor_profile.focus_tokens:
                focus_matches.append(token)
            if token in anchor_profile.core_anchor_tokens:
                core_matches.append(token)
        elif token in body_tokens:
            score += 1
            text_matches.append(token)
            if token in anchor_profile.focus_tokens:
                focus_matches.append(token)
            if token in anchor_profile.core_anchor_tokens:
                core_matches.append(token)
    return _AnchorMatchResult(
        score=score,
        title_matches=title_matches,
        text_matches=text_matches,
        focus_matches=focus_matches,
        core_matches=core_matches,
    )


def _require_worker_ready() -> None:
    worker = read_heartbeat(
        _WORKER_HEARTBEAT_PATH,
        max_age_seconds=_WORKER_MAX_AGE_SECONDS,
    )
    if worker.status == "healthy":
        return
    detail = "Research init worker unavailable."
    if worker.last_tick is not None:
        detail += f" Last heartbeat: {worker.last_tick}."
    failure_reason = None
    if isinstance(worker.detail, dict):
        raw_reason = worker.detail.get("failure_reason")
        if isinstance(raw_reason, str) and raw_reason != "":
            failure_reason = raw_reason
    if failure_reason == "process_not_running":
        detail += " Worker process is not running."
    elif failure_reason == "stale":
        detail += " Worker heartbeat is stale."
    elif failure_reason == "loop_error":
        detail += " Worker loop is erroring."
    elif worker.status == "unknown":
        detail += " No worker heartbeat is available."
    LOGGER.warning(
        "research-init worker readiness check failed",
        extra={
            "heartbeat_status": worker.status,
            "heartbeat_last_tick": worker.last_tick,
            "heartbeat_pid": worker.pid,
            "heartbeat_failure_reason": failure_reason,
            "heartbeat_path": _WORKER_HEARTBEAT_PATH,
            "heartbeat_detail": worker.detail,
        },
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )


def _review_candidate_with_heuristics(
    candidate: _PubMedCandidate,
    *,
    objective: str,
    seed_terms: list[str],
) -> _PubMedCandidateReview:
    normalized_title = _normalize_free_text(candidate.title)
    normalized_text = _normalize_free_text(candidate.text)
    anchor_profile = _build_candidate_anchor_profile(
        objective,
        seed_terms,
    )

    phrase_matches = _match_anchor_phrases(
        normalized_title=normalized_title,
        normalized_text=normalized_text,
        anchor_profile=anchor_profile,
    )
    title_tokens, body_tokens = _candidate_token_sets(candidate)
    token_matches = _match_anchor_tokens(
        title_tokens=title_tokens,
        body_tokens=body_tokens,
        anchor_profile=anchor_profile,
    )
    score = phrase_matches.score + token_matches.score

    unique_signals = {
        *phrase_matches.title_matches,
        *phrase_matches.text_matches,
        *token_matches.title_matches,
        *token_matches.text_matches,
    }
    unique_focus_signals = {
        *phrase_matches.focus_matches,
        *token_matches.focus_matches,
    }
    unique_core_signals = {
        *phrase_matches.core_matches,
        *token_matches.core_matches,
    }
    query_specificity = max(
        (_query_specificity_score(query) for query in candidate.queries),
        default=0,
    )
    if unique_focus_signals:
        score += min(len(unique_focus_signals), 2)
    if query_specificity >= _HIGH_SPECIFICITY_QUERY_THRESHOLD:
        score += 1

    label = _heuristic_relevance_label(
        score=score,
        anchor_profile=anchor_profile,
        unique_core_signals=unique_core_signals,
    )

    evidence_parts = _build_heuristic_evidence_parts(
        matched_title_phrases=phrase_matches.title_matches,
        matched_text_phrases=phrase_matches.text_matches,
        matched_title_tokens=token_matches.title_matches,
        matched_text_tokens=token_matches.text_matches,
        unique_focus_signals=unique_focus_signals,
        unique_core_signals=unique_core_signals,
        query_specificity=query_specificity,
        anchor_profile=anchor_profile,
        score=score,
    )
    confidence = min(max(score / 8.0, 0.0), 1.0)
    return _PubMedCandidateReview(
        method="heuristic",
        label=label,
        confidence=confidence,
        rationale="; ".join(evidence_parts),
        signal_count=len(unique_signals),
        focus_signal_count=len(unique_focus_signals),
        query_specificity=query_specificity,
    )


async def _review_candidate_with_llm(
    candidate: _PubMedCandidate,
    *,
    objective: str,
) -> _PubMedCandidateReview:
    from artana_evidence_api.pubmed_relevance import (
        ArtanaPubMedRelevanceAdapter,
        PubMedRelevanceContext,
    )

    adapter = ArtanaPubMedRelevanceAdapter()
    try:
        result = await adapter.classify(
            PubMedRelevanceContext(
                source_type="pubmed",
                query=objective,
                title=candidate.title,
                abstract=candidate.text[:32000],
                domain_context="research-init",
                pubmed_id=candidate.pmid,
            ),
        )
    finally:
        await adapter.close()

    return _PubMedCandidateReview(
        method="llm",
        label=result.relevance,
        confidence=max(0.0, min(1.0, float(result.confidence_score))),
        rationale=result.rationale,
        agent_run_id=result.agent_run_id,
    )


async def _select_candidates_for_ingestion(
    candidates: list[_PubMedCandidate],
    *,
    objective: str,
    seed_terms: list[str],
    errors: list[str],
) -> list[tuple[_PubMedCandidate, _PubMedCandidateReview]]:
    heuristic_shortlist: list[tuple[_PubMedCandidate, _PubMedCandidateReview]] = []
    for candidate in candidates:
        review = _review_candidate_with_heuristics(
            candidate,
            objective=objective,
            seed_terms=seed_terms,
        )
        if review.label == "relevant":
            heuristic_shortlist.append((candidate, review))

    if not heuristic_shortlist:
        return []

    llm_shortlist = _shortlist_candidates_for_llm_review(heuristic_shortlist)
    semaphore = asyncio.Semaphore(_MAX_LLM_RELEVANCE_CONCURRENCY)

    async def _review_candidate(
        candidate: _PubMedCandidate,
        heuristic_review: _PubMedCandidateReview,
    ) -> tuple[
        _PubMedCandidate,
        _PubMedCandidateReview,
        _PubMedCandidateReview | None,
        bool,
    ]:
        try:
            async with semaphore:
                llm_review = await asyncio.wait_for(
                    _review_candidate_with_llm(
                        candidate,
                        objective=objective,
                    ),
                    timeout=_LLM_RELEVANCE_TIMEOUT_SECONDS,
                )
        except TimeoutError:
            errors.append(
                "PubMed relevance review fell back to heuristics: "
                f"timed out after {_LLM_RELEVANCE_TIMEOUT_SECONDS:.1f}s",
            )
            return candidate, heuristic_review, None, False
        except Exception as exc:  # noqa: BLE001
            errors.append(f"PubMed relevance review fell back to heuristics: {exc}")
            return candidate, heuristic_review, None, False
        return candidate, heuristic_review, llm_review, True

    reviewed_candidates = await asyncio.gather(
        *[
            _review_candidate(candidate, heuristic_review)
            for candidate, heuristic_review in llm_shortlist
        ],
    )

    llm_success_count = 0
    shortlisted: list[tuple[_PubMedCandidate, _PubMedCandidateReview]] = []
    for candidate, heuristic_review, llm_review, llm_succeeded in reviewed_candidates:
        if not llm_succeeded or llm_review is None:
            shortlisted.append((candidate, heuristic_review))
            continue
        llm_success_count += 1
        if llm_review.label == "relevant":
            shortlisted.append((candidate, llm_review))

    if llm_success_count == 0:
        shortlisted = llm_shortlist

    shortlisted.sort(
        key=lambda item: (
            item[1].confidence,
            *_candidate_priority_key(item[0], item[1]),
        ),
        reverse=True,
    )
    return shortlisted[:_MAX_CANDIDATES_TO_INGEST]


__all__ = [
    "ResearchInitOrchestrationMode",
    "_PubMedCandidate",
    "_PubMedCandidateReview",
    "_build_pubmed_queries",
    "_build_scope_refinement_questions",
    "_candidate_key",
    "_merge_candidate",
    "_planner_mode_for_research_orchestration",
    "_prioritize_marrvel_gene_labels",
    "_require_worker_ready",
    "_resolve_research_init_sources",
    "_resolve_research_orchestration_mode",
    "_review_candidate_with_heuristics",
    "_review_candidate_with_llm",
    "_run_marrvel_enrichment",
    "_select_candidates_for_ingestion",
    "_shortlist_candidates_for_llm_review",
    "_unknown_source_preference_keys",
]
