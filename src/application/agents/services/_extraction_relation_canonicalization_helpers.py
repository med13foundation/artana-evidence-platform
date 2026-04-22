"""Canonicalization helpers for extraction relation candidates before persistence."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from src.domain.services.domain_context_resolver import DomainContextResolver
from src.domain.value_objects.relation_types import normalize_relation_type

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.application.agents.services._extraction_relation_policy_helpers import (
        _ResolvedRelationCandidate,
    )
    from src.domain.agents.contracts.extraction_policy import (
        RelationTypeMappingProposal,
    )
    from src.domain.entities.source_document import SourceDocument
    from src.type_definitions.common import JSONObject

_RELATION_SEARCH_LIMIT = 8
_RELATION_SEARCH_HIGH_CONFIDENCE = 0.85
_RELATION_SEARCH_AMBIGUITY_DELTA = 0.08
_MAPPING_PROPOSAL_MIN_CONFIDENCE = 0.70
_MATCH_METHOD_PRIORITY: dict[str, int] = {
    "exact": 0,
    "synonym": 1,
    "fuzzy": 2,
    "vector": 3,
}


class _ExtractionRelationCanonicalizationHelpers:
    """Canonicalize relation candidates via deterministic-first dictionary policy."""

    _dictionary: DictionaryPort | None

    def _canonicalize_relation_candidate(  # noqa: C901
        self,
        *,
        candidate: _ResolvedRelationCandidate,
        mapping_proposal: RelationTypeMappingProposal | None,
        document: SourceDocument,
    ) -> tuple[_ResolvedRelationCandidate, JSONObject]:
        normalized_relation_type = normalize_relation_type(candidate.relation_type)
        if not normalized_relation_type:
            return candidate, {"strategy": "invalid_relation_type"}
        if candidate.persistability != "PERSISTABLE":
            return (
                replace(candidate, relation_type=normalized_relation_type),
                {
                    "strategy": "non_persistable_passthrough",
                    "observed_relation_type": candidate.relation_type,
                    "canonical_relation_type": normalized_relation_type,
                },
            )

        metadata: JSONObject = {
            "strategy": "normalize_only",
            "observed_relation_type": candidate.relation_type,
            "canonical_relation_type": normalized_relation_type,
        }
        selected_relation_type = normalized_relation_type

        if self._dictionary is not None:
            direct = self._dictionary.get_relation_type(selected_relation_type)
            if direct is not None:
                metadata["strategy"] = "dictionary_exact_id"
            else:
                resolved, strategy, score = self._resolve_relation_type_by_search(
                    relation_type=selected_relation_type,
                    document=document,
                )
                if resolved is not None:
                    selected_relation_type = resolved
                    metadata["strategy"] = strategy
                    metadata["canonical_relation_type"] = selected_relation_type
                    if score is not None:
                        metadata["score"] = float(score)

        proposal_used = False
        if mapping_proposal is not None:
            mapped_relation_type = normalize_relation_type(
                mapping_proposal.mapped_relation_type,
            )
            if (
                mapped_relation_type
                and float(mapping_proposal.confidence)
                >= _MAPPING_PROPOSAL_MIN_CONFIDENCE
                and (
                    self._dictionary is None
                    or self._dictionary.get_relation_type(mapped_relation_type)
                    is not None
                )
            ):
                selected_relation_type = mapped_relation_type
                proposal_used = True
                metadata["strategy"] = "policy_mapping_proposal"
                metadata["canonical_relation_type"] = selected_relation_type
                metadata["proposal_confidence"] = float(mapping_proposal.confidence)

        if selected_relation_type != candidate.relation_type or proposal_used:
            return (
                replace(candidate, relation_type=selected_relation_type),
                metadata,
            )
        return candidate, metadata

    def _resolve_relation_type_by_search(  # noqa: PLR0911
        self,
        *,
        relation_type: str,
        document: SourceDocument,
    ) -> tuple[str | None, str, float | None]:
        dictionary = self._dictionary
        if dictionary is None:
            return None, "dictionary_unavailable", None

        domain_context = DomainContextResolver.resolve(
            explicit_domain_context=None,
            metadata=document.metadata,
            source_type=document.source_type.value,
            fallback=DomainContextResolver.GENERAL_DEFAULT_DOMAIN,
        )
        terms = [relation_type, relation_type.replace("_", " ")]
        search_results = dictionary.dictionary_search(
            terms=terms,
            dimensions=["relation_types"],
            domain_context=domain_context,
            limit=_RELATION_SEARCH_LIMIT,
            include_inactive=False,
        )
        relation_results = [
            result for result in search_results if result.dimension == "relation_types"
        ]
        if not relation_results:
            return None, "dictionary_search_no_match", None

        ranked = sorted(
            relation_results,
            key=lambda result: (
                _MATCH_METHOD_PRIORITY.get(result.match_method, 99),
                -result.similarity_score,
                result.entry_id,
            ),
        )
        top = ranked[0]
        if top.match_method in {"exact", "synonym"}:
            return top.entry_id, f"dictionary_search_{top.match_method}", 1.0

        if top.match_method not in {"fuzzy", "vector"}:
            return None, "dictionary_search_unsupported_method", top.similarity_score

        if len(ranked) > 1:
            second = ranked[1]
            if (
                second.match_method == top.match_method
                and abs(top.similarity_score - second.similarity_score)
                <= _RELATION_SEARCH_AMBIGUITY_DELTA
            ):
                return None, "dictionary_search_ambiguous", top.similarity_score

        if top.similarity_score >= _RELATION_SEARCH_HIGH_CONFIDENCE:
            return (
                top.entry_id,
                f"dictionary_search_{top.match_method}",
                top.similarity_score,
            )
        return None, "dictionary_search_low_confidence", top.similarity_score


__all__ = ["_ExtractionRelationCanonicalizationHelpers"]
