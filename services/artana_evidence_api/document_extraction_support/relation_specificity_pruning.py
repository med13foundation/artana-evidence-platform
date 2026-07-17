"""Specificity pruning for extracted relation candidates."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from artana_evidence_api.document_extraction_contracts import (
    ClaimExtractionLineage,
    ClaimExtractionRoutingStatus,
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
_ENTITY_MODIFIER_TERMS = (
    "amplification",
    "activation",
    "deficiency",
    "deletion",
    "depletion",
    "downregulation",
    "knockdown",
    "knockout",
    "loss",
    "loss of",
    "loss-of-function",
    "phosphorylation",
    "overexpression",
    "pathogenic",
    "silencing",
    "suppression",
    "truncating",
    "mutated",
    "upregulation",
    "mutation",
    "variant",
    "variants",
)
_ENTITY_MODIFIER_PREFIXES = (
    "amplified",
    "activated",
    "deficient",
    "deleted",
    "depleted",
    "downregulated",
    "knocked down",
    "knocked out",
    "loss of",
    "mutated",
    "overexpressed",
    "phosphorylated",
    "silenced",
    "suppressed",
    "upregulated",
    "variant",
)
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
_SUBTYPE_TAIL_CUE_TOKENS = frozenset(
    {
        "amplification",
        "deletion",
        "deletions",
        "exon",
        "expressing",
        "fusion",
        "fusions",
        "harboring",
        "loss",
        "mutant",
        "mutated",
        "mutation",
        "mutations",
        "pathogenic",
        "positive",
        "truncating",
        "variant",
        "variants",
    },
)
_SUBTYPE_TAIL_DISEASE_TOKENS = frozenset(
    {
        "adenocarcinoma",
        "cancer",
        "cancers",
        "carcinoma",
        "disease",
        "hypercholesterolemia",
        "leukemia",
        "lymphoma",
        "melanoma",
        "neoplasm",
        "neoplasms",
        "polyposis",
        "syndrome",
        "tumor",
        "tumors",
    },
)
_SUBTYPE_TAIL_STOP_TOKENS = frozenset(
    {
        "activates",
        "across",
        "after",
        "among",
        "associated",
        "before",
        "biomarker",
        "by",
        "confers",
        "correlates",
        "causes",
        "during",
        "for",
        "from",
        "in",
        "inhibits",
        "of",
        "predisposes",
        "predictor",
        "predicts",
        "regardless",
        "regulates",
        "sensitizes",
        "targeted",
        "targets",
        "through",
        "to",
        "treat",
        "treated",
        "treating",
        "treats",
        "under",
        "via",
        "when",
        "where",
        "whereas",
        "while",
        "with",
    },
)
_CONTEXT_TAIL_PREPOSITIONS = ("with", "including", "involving")
_TREATMENT_RELATION_CUES = (
    "treat",
    "treats",
    "treated",
    "treating",
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
        raw_agent_outputs: tuple[dict[str, object], ...] = (),
        model_attempt_records: tuple[dict[str, object], ...] = (),
        claim_extraction_routing_status: ClaimExtractionRoutingStatus = "not_run",
        overflow_candidates: tuple[ExtractedRelationCandidate, ...] = (),
        all_framed_candidates: tuple[ExtractedRelationCandidate, ...] = (),
        claim_lineage: tuple[ClaimExtractionLineage, ...] = (),
        inventory_incompleteness: tuple[dict[str, object], ...] = (),
        inventory_non_relation_items: tuple[dict[str, object], ...] = (),
        inventory_binding_rejections: tuple[dict[str, object], ...] = (),
    ) -> None:
        super().__init__(candidates)
        self.pruned_generic_relation_count = pruned_generic_relation_count
        self.quality_filtered_candidate_count = quality_filtered_candidate_count
        self.llm_extraction_chunk_count = llm_extraction_chunk_count
        self.llm_extraction_text_char_count = llm_extraction_text_char_count
        self.raw_agent_outputs = raw_agent_outputs
        self.model_attempt_records = model_attempt_records
        self.claim_extraction_routing_status = claim_extraction_routing_status
        self.overflow_candidates = overflow_candidates
        self.all_framed_candidates = all_framed_candidates
        self.claim_lineage = claim_lineage
        self.inventory_incompleteness = inventory_incompleteness
        self.inventory_non_relation_items = inventory_non_relation_items
        self.inventory_binding_rejections = inventory_binding_rejections

    @property
    def candidate_overflow_count(self) -> int:
        """Return claims routed outside the bounded compatibility list."""

        return len(self.overflow_candidates)


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
        if (
            candidate.review_status != "review_only"
            and is_low_value_generic_relation_candidate(
                relation_type=candidate.relation_type,
                lemma="",
                sentence=candidate.sentence,
            )
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
            suppressing_relation_type = specific_relation_by_subject_and_sentence.get(
                _candidate_subject_and_sentence(candidate),
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


def has_broadened_entity_label(
    *,
    label: str,
    sentence: str,
    counterpart_label: str | None = None,
) -> bool:
    """Return whether an entity label drops an explicit sentence modifier."""

    normalized_label = _normalize_entity_label(label)
    if not normalized_label:
        return False
    label_pattern = r"\s+".join(re.escape(token) for token in normalized_label.split())
    normalized_sentence = _normalize_sentence(sentence)
    if re.search(rf"\b{label_pattern}\b", normalized_sentence) is None:
        return False
    search_scopes = _claim_scopes_for_entity(
        label_pattern=label_pattern,
        counterpart_label=counterpart_label,
        sentence=normalized_sentence,
    )
    return any(
        _scope_has_broadened_entity_label(
            label_pattern=label_pattern,
            sentence=scope,
        )
        for scope in search_scopes
    )


def _claim_scopes_for_entity(
    *,
    label_pattern: str,
    counterpart_label: str | None,
    sentence: str,
) -> tuple[str, ...]:
    if counterpart_label is None:
        return (sentence,)
    normalized_counterpart = _normalize_entity_label(counterpart_label)
    if not normalized_counterpart:
        return (sentence,)
    counterpart_pattern = r"\s+".join(
        re.escape(token) for token in normalized_counterpart.split()
    )
    scoped_clauses = tuple(
        clause
        for clause in _split_sentence_claim_clauses(sentence)
        if re.search(rf"\b{label_pattern}\b", clause) is not None
        and re.search(rf"\b{counterpart_pattern}\b", clause) is not None
    )
    return scoped_clauses or (sentence,)


def _split_sentence_claim_clauses(sentence: str) -> tuple[str, ...]:
    return tuple(
        clause.strip(" ,")
        for clause in re.split(
            r"(?:[.;:]|,\s*(?:and|while|whereas|but)\b|\b(?:while|whereas|but)\b)",
            sentence,
        )
        if clause.strip(" ,")
    )


def _scope_has_broadened_entity_label(*, label_pattern: str, sentence: str) -> bool:
    if _has_post_modifier(label_pattern=label_pattern, sentence=sentence):
        return True
    if _has_prefix_modifier(label_pattern=label_pattern, sentence=sentence):
        return True
    if _has_subtype_tail_modifier(label_pattern=label_pattern, sentence=sentence):
        return True
    return _has_hyphenated_prefix_modifier(
        label_pattern=label_pattern,
        sentence=sentence,
    )


def _has_post_modifier(*, label_pattern: str, sentence: str) -> bool:
    modifier_pattern = "|".join(
        r"\s+".join(re.escape(token) for token in modifier.split())
        for modifier in _ENTITY_MODIFIER_TERMS
    )
    return (
        re.search(
            rf"\b{label_pattern}(?:\s+|-)(?:{modifier_pattern})\b",
            sentence,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _has_prefix_modifier(*, label_pattern: str, sentence: str) -> bool:
    modifier_pattern = "|".join(
        r"\s+".join(re.escape(token) for token in modifier.split())
        for modifier in _ENTITY_MODIFIER_PREFIXES
    )
    return (
        re.search(
            rf"\b(?:{modifier_pattern})\s+{label_pattern}\b",
            sentence,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _has_subtype_tail_modifier(*, label_pattern: str, sentence: str) -> bool:
    label_tokens = tuple(label_pattern.split(r"\s+"))
    label_has_disease_class = bool(
        _SUBTYPE_TAIL_DISEASE_TOKENS.intersection(label_tokens),
    )
    pattern = re.compile(
        rf"\b{label_pattern}\b(?P<tail>(?:\s+[a-z0-9+*/_-]+){{1,8}})",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sentence):
        tail_tokens = _bounded_tail_tokens(match.group("tail"))
        if not tail_tokens:
            continue
        if _SUBTYPE_TAIL_CUE_TOKENS.intersection(tail_tokens) and (
            label_has_disease_class
            or _SUBTYPE_TAIL_DISEASE_TOKENS.intersection(tail_tokens)
        ):
            return True
    return False


def _has_hyphenated_prefix_modifier(*, label_pattern: str, sentence: str) -> bool:
    modifier_pattern = re.compile(
        _HYPHENATED_MODIFIER_TEMPLATE.format(label=label_pattern),
        re.IGNORECASE,
    )
    for match in modifier_pattern.finditer(sentence):
        matched_tokens = re.findall(r"[a-z0-9+*/_-]+", match.group(0).casefold())
        label_token_count = len(label_pattern.split(r"\s+"))
        bridge_tokens = matched_tokens[1:-label_token_count]
        if _SUBTYPE_TAIL_STOP_TOKENS.intersection(bridge_tokens):
            continue
        return True
    return False


def has_context_tail_entity_label(
    *,
    label: str,
    sentence: str,
    counterpart_label: str | None,
    relation_type: str,
) -> bool:
    """Return whether a treatment object is only a context tail."""

    if relation_type != "TREATS" or counterpart_label is None:
        return False
    normalized_label = _normalize_entity_label(label)
    normalized_counterpart = _normalize_entity_label(counterpart_label)
    if not normalized_label or not normalized_counterpart:
        return False
    normalized_sentence = _normalize_sentence(sentence)
    label_pattern = r"\s+".join(re.escape(token) for token in normalized_label.split())
    counterpart_pattern = r"\s+".join(
        re.escape(token) for token in normalized_counterpart.split()
    )
    treatment_pattern = _phrase_alternation(_TREATMENT_RELATION_CUES)
    preposition_pattern = _phrase_alternation(_CONTEXT_TAIL_PREPOSITIONS)
    disease_pattern = "|".join(
        re.escape(token)
        for token in sorted(_SUBTYPE_TAIL_DISEASE_TOKENS, key=len, reverse=True)
    )
    pattern = re.compile(
        rf"\b{counterpart_pattern}\b"
        rf".{{0,80}}\b(?:{treatment_pattern})\b"
        rf".{{0,120}}\b(?:{disease_pattern})\b"
        rf".{{0,40}}\b(?:{preposition_pattern})\s+{label_pattern}\b",
        re.IGNORECASE,
    )
    return pattern.search(normalized_sentence) is not None


def _phrase_alternation(phrases: tuple[str, ...]) -> str:
    return "|".join(
        r"\s+".join(re.escape(token) for token in phrase.split())
        for phrase in sorted(phrases, key=len, reverse=True)
    )


def _bounded_tail_tokens(raw_tail: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9+*/_-]+", raw_tail.casefold()):
        if token in _SUBTYPE_TAIL_STOP_TOKENS:
            break
        tokens.append(token)
    return tuple(tokens)


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
    "has_context_tail_entity_label",
    "is_low_value_generic_relation_candidate",
    "prune_redundant_generic_relation_candidates",
]
