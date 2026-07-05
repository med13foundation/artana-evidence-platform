"""Specificity pruning for extracted relation candidates."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    canonicalize_extraction_relation_type,
)

_GENERIC_RELATION_TYPES = frozenset({"ASSOCIATED_WITH"})
_LOW_VALUE_GENERIC_RELATION_LEMMAS = frozenset(
    {
        "correlates with",
        "correlated with",
        "is correlated with",
        "was correlated with",
        "were correlated with",
    },
)
_MIN_BROADENED_ENTITY_TOKENS = 2
_WEAK_GENERIC_RELATION_CUE_RE = re.compile(
    r"\b("
    r"exploratory|may|might|nominally|possible|possibly|small cohort|"
    r"speculative|suggestive|trend|trended|weakly"
    r")\b",
    re.IGNORECASE,
)
_HYPHENATED_MODIFIER_TEMPLATE = (
    r"\b[A-Za-z0-9]+-[A-Za-z0-9]+(?:\s+[A-Za-z0-9]+){{0,2}}\s+{label}\b"
)


@dataclass(frozen=True, slots=True)
class PrunedGenericRelationCandidate:
    """A generic candidate removed because a specific sibling exists."""

    candidate_index: int
    candidate: ExtractedRelationCandidate
    suppressing_relation_type: str


@dataclass(frozen=True, slots=True)
class WeakGenericRelationCandidate:
    """A generic candidate removed because its evidence is too weak."""

    candidate_index: int
    candidate: ExtractedRelationCandidate


@dataclass(frozen=True, slots=True)
class RelationSpecificityPruningResult:
    """Candidate list plus audit details for removed generic candidates."""

    candidates: tuple[ExtractedRelationCandidate, ...]
    pruned_candidates: tuple[PrunedGenericRelationCandidate, ...]
    weak_generic_candidates: tuple[WeakGenericRelationCandidate, ...] = ()

    @property
    def pruned_count(self) -> int:
        """Return the number of generic candidates removed."""

        return len(self.pruned_candidates) + len(self.weak_generic_candidates)


class SpecificityFilteredCandidateList(list[ExtractedRelationCandidate]):
    """Backward-compatible list carrying specificity-filter telemetry."""

    def __init__(
        self,
        candidates: Iterable[ExtractedRelationCandidate],
        *,
        pruned_generic_relation_count: int,
        quality_filtered_candidate_count: int = 0,
        llm_extraction_chunk_count: int = 0,
        llm_extraction_text_char_count: int = 0,
    ) -> None:
        super().__init__(candidates)
        self.pruned_generic_relation_count = pruned_generic_relation_count
        self.quality_filtered_candidate_count = quality_filtered_candidate_count
        self.llm_extraction_chunk_count = llm_extraction_chunk_count
        self.llm_extraction_text_char_count = llm_extraction_text_char_count


def prune_redundant_generic_relation_candidates(
    candidates: Iterable[ExtractedRelationCandidate],
) -> RelationSpecificityPruningResult:
    """Remove generic relation candidates shadowed by specific siblings."""

    indexed_candidates = tuple(enumerate(candidates))
    specific_relation_by_pair_and_sentence: dict[tuple[str, str, str], str] = {}
    specific_relation_by_subject_and_sentence: dict[tuple[str, str], str] = {}
    for _, candidate in indexed_candidates:
        canonical_relation = _candidate_specific_relation_type(candidate)
        if canonical_relation is None:
            continue
        specific_relation_by_pair_and_sentence.setdefault(
            _candidate_entity_pair_and_sentence(candidate),
            canonical_relation,
        )
        specific_relation_by_subject_and_sentence.setdefault(
            _candidate_subject_and_sentence(candidate),
            canonical_relation,
        )

    kept_candidates: list[ExtractedRelationCandidate] = []
    pruned_candidates: list[PrunedGenericRelationCandidate] = []
    weak_generic_candidates: list[WeakGenericRelationCandidate] = []
    for candidate_index, candidate in indexed_candidates:
        canonical_relation = canonicalize_extraction_relation_type(
            candidate.relation_type,
        )
        if is_low_value_generic_relation_candidate(
            relation_type=candidate.relation_type,
            lemma="",
            sentence=candidate.sentence,
        ):
            weak_generic_candidates.append(
                WeakGenericRelationCandidate(
                    candidate_index=candidate_index,
                    candidate=candidate,
                ),
            )
            continue
        suppressing_relation_type = specific_relation_by_pair_and_sentence.get(
            _candidate_entity_pair_and_sentence(candidate),
        )
        if suppressing_relation_type is None and _is_generic_tail_clause(candidate):
            suppressing_relation_type = (
                specific_relation_by_subject_and_sentence.get(
                    _candidate_subject_and_sentence(candidate),
                )
            )
        if (
            canonical_relation in _GENERIC_RELATION_TYPES
            and suppressing_relation_type is not None
        ):
            pruned_candidates.append(
                PrunedGenericRelationCandidate(
                    candidate_index=candidate_index,
                    candidate=candidate,
                    suppressing_relation_type=suppressing_relation_type,
                ),
            )
            continue
        kept_candidates.append(candidate)

    return RelationSpecificityPruningResult(
        candidates=tuple(kept_candidates),
        pruned_candidates=tuple(pruned_candidates),
        weak_generic_candidates=tuple(weak_generic_candidates),
    )


def is_low_value_generic_relation_candidate(
    *,
    relation_type: str,
    lemma: str,
    sentence: str,
) -> bool:
    """Return whether a generic candidate is too weak to stage."""

    canonical_relation_type = canonicalize_extraction_relation_type(relation_type)
    if canonical_relation_type != "ASSOCIATED_WITH":
        return False
    return (
        lemma in _LOW_VALUE_GENERIC_RELATION_LEMMAS
        or _WEAK_GENERIC_RELATION_CUE_RE.search(sentence) is not None
    )


def _candidate_specific_relation_type(
    candidate: ExtractedRelationCandidate,
) -> str | None:
    if (
        candidate.relation_governance_status == "requires_relation_review"
        and candidate.proposed_relation_type is not None
        and candidate.proposed_relation_type.strip()
    ):
        return candidate.proposed_relation_type.strip().upper()
    canonical_relation = canonicalize_extraction_relation_type(
        candidate.relation_type,
    )
    if canonical_relation is None or canonical_relation in _GENERIC_RELATION_TYPES:
        return None
    return canonical_relation


def _is_generic_tail_clause(candidate: ExtractedRelationCandidate) -> bool:
    if canonicalize_extraction_relation_type(candidate.relation_type) not in (
        _GENERIC_RELATION_TYPES
    ):
        return False
    sentence = _normalize_sentence(candidate.sentence)
    return (
        " and is associated with " in sentence
        or " and was associated with " in sentence
        or " and were associated with " in sentence
    )


def has_broadened_entity_label(*, label: str, sentence: str) -> bool:
    """Return whether an entity label drops an explicit sentence modifier."""

    normalized_label = _normalize_entity_label(label)
    if (
        not normalized_label
        or len(normalized_label.split()) < _MIN_BROADENED_ENTITY_TOKENS
    ):
        return False
    label_pattern = r"\s+".join(
        re.escape(token) for token in normalized_label.split()
    )
    modifier_pattern = re.compile(
        _HYPHENATED_MODIFIER_TEMPLATE.format(label=label_pattern),
        re.IGNORECASE,
    )
    exact_label_pattern = re.compile(rf"\b{label_pattern}\b", re.IGNORECASE)
    return (
        exact_label_pattern.search(sentence) is not None
        and modifier_pattern.search(sentence) is not None
    )


def _candidate_entity_pair(candidate: ExtractedRelationCandidate) -> tuple[str, str]:
    return (
        _normalize_entity_label(candidate.subject_label),
        _normalize_entity_label(candidate.object_label),
    )


def _candidate_entity_pair_and_sentence(
    candidate: ExtractedRelationCandidate,
) -> tuple[str, str, str]:
    subject, object_ = _candidate_entity_pair(candidate)
    return subject, object_, _normalize_sentence(candidate.sentence)


def _candidate_subject_and_sentence(
    candidate: ExtractedRelationCandidate,
) -> tuple[str, str]:
    return (
        _normalize_entity_label(candidate.subject_label),
        _normalize_sentence(candidate.sentence),
    )


def _normalize_entity_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.casefold()).strip()


def _normalize_sentence(sentence: str) -> str:
    return re.sub(r"\s+", " ", sentence.casefold()).strip()


__all__ = [
    "PrunedGenericRelationCandidate",
    "RelationSpecificityPruningResult",
    "SpecificityFilteredCandidateList",
    "WeakGenericRelationCandidate",
    "has_broadened_entity_label",
    "is_low_value_generic_relation_candidate",
    "prune_redundant_generic_relation_candidates",
]
