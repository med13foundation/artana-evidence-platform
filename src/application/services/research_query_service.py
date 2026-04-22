"""Interface-layer service for research intent parsing and query planning."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from artana_evidence_db.query_ports import ResearchQueryPort
from artana_evidence_db.research_query_models import (
    ResearchQueryIntent,
    ResearchQueryPlan,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import DictionarySearchResult
    from artana_evidence_db.semantic_ports import DictionaryPort

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "what",
        "which",
        "with",
    },
)

_ENTITY_TYPE_HINTS: Final[dict[str, str]] = {
    "gene": "GENE",
    "genes": "GENE",
    "variant": "VARIANT",
    "variants": "VARIANT",
    "phenotype": "PHENOTYPE",
    "phenotypes": "PHENOTYPE",
    "patient": "PATIENT",
    "patients": "PATIENT",
    "team": "TEAM",
    "teams": "TEAM",
    "player": "PLAYER",
    "players": "PLAYER",
}

_RELATION_TYPE_HINTS: Final[dict[str, str]] = {
    "associated": "ASSOCIATED_WITH",
    "association": "ASSOCIATED_WITH",
    "causes": "CAUSES",
    "plays": "PLAYS_FOR",
    "traded": "TRADED_TO",
}


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


def _extract_quoted_phrases(question: str) -> list[str]:
    return [match for match in re.findall(r'"([^"]+)"', question) if match.strip()]


def _tokenize(question: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_:-]+", question.casefold())
    filtered = [token for token in tokens if token not in _STOPWORDS and len(token) > 1]
    return _dedupe(filtered)


def _clamp(value: int, *, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


class ResearchQueryService(ResearchQueryPort):
    """Deterministic interface-layer parser that maps questions to query plans."""

    def __init__(self, *, dictionary_service: DictionaryPort) -> None:
        self._dictionary = dictionary_service

    def parse_intent(
        self,
        *,
        question: str,
        research_space_id: str,
    ) -> ResearchQueryIntent:
        _ = research_space_id
        normalized_question = question.strip()
        if not normalized_question:
            msg = "question is required"
            raise ValueError(msg)

        quoted_phrases = _extract_quoted_phrases(normalized_question)
        tokens = _tokenize(normalized_question)
        terms = _dedupe([*quoted_phrases, *tokens])
        if not terms:
            terms = [normalized_question]

        resolved = self.resolve_terms(
            terms=terms,
            domain_context=None,
            limit=50,
        )
        entity_types = [
            result.entry_id for result in resolved if result.dimension == "entity_types"
        ]
        relation_types = [
            result.entry_id
            for result in resolved
            if result.dimension == "relation_types"
        ]
        variable_ids = [
            result.entry_id for result in resolved if result.dimension == "variables"
        ]

        for token in tokens:
            hinted_entity = _ENTITY_TYPE_HINTS.get(token)
            if hinted_entity is not None:
                entity_types.append(hinted_entity)
            hinted_relation = _RELATION_TYPE_HINTS.get(token)
            if hinted_relation is not None:
                relation_types.append(hinted_relation)

        domain_context: str | None = None
        for result in resolved:
            if result.domain_context:
                domain_context = result.domain_context
                break

        entity_types = _dedupe(entity_types)
        relation_types = _dedupe(relation_types)
        variable_ids = _dedupe(variable_ids)

        notes: list[str] = []
        if not resolved:
            notes.append("No direct dictionary matches found; using keyword fallback.")
        if not entity_types:
            notes.append("No explicit entity type resolved from dictionary results.")

        return ResearchQueryIntent(
            original_query=normalized_question,
            normalized_terms=terms,
            requested_entity_types=entity_types,
            requested_relation_types=relation_types,
            requested_variable_ids=variable_ids,
            domain_context=domain_context,
            ambiguous=not bool(entity_types or relation_types or variable_ids),
            notes=notes,
        )

    def resolve_terms(
        self,
        *,
        terms: list[str],
        domain_context: str | None = None,
        limit: int = 50,
    ) -> list[DictionarySearchResult]:
        deduped_terms = _dedupe(terms)
        if not deduped_terms:
            return []
        return self._dictionary.dictionary_search(
            terms=deduped_terms,
            dimensions=["variables", "entity_types", "relation_types"],
            domain_context=domain_context,
            limit=_clamp(limit, lower=1, upper=100),
        )

    def build_query_plan(
        self,
        *,
        intent: ResearchQueryIntent,
        max_depth: int = 2,
        top_k: int = 25,
    ) -> ResearchQueryPlan:
        normalized_depth = _clamp(max_depth, lower=1, upper=4)
        normalized_top_k = _clamp(top_k, lower=1, upper=100)
        query_terms = intent.normalized_terms or _tokenize(intent.original_query)
        if not query_terms:
            query_terms = [intent.original_query]

        summary = (
            "Deterministic plan: "
            f"{len(intent.requested_entity_types)} entity type hints, "
            f"{len(intent.requested_relation_types)} relation type hints, "
            f"{len(intent.requested_variable_ids)} variable constraints, "
            f"depth={normalized_depth}, top_k={normalized_top_k}."
        )

        return ResearchQueryPlan(
            query_terms=query_terms,
            entity_types=_dedupe(intent.requested_entity_types),
            relation_types=_dedupe(intent.requested_relation_types),
            variable_ids=_dedupe(intent.requested_variable_ids),
            max_depth=normalized_depth,
            top_k=normalized_top_k,
            plan_summary=summary,
        )


__all__ = ["ResearchQueryService"]
