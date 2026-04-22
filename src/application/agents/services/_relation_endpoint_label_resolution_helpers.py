"""Shared label-resolution helpers for extraction relation endpoint matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import KernelEntity

_CONCEPTUAL_ENTITY_TYPES = frozenset(
    {
        "GENE",
        "PROTEIN",
        "VARIANT",
        "PHENOTYPE",
        "DISEASE",
        "PATHWAY",
        "DRUG",
        "MECHANISM",
        "COMPLEX",
    },
)
_TOKEN_BASE_CONCEPT_KEY_TYPES = frozenset({"GENE", "PROTEIN", "COMPLEX"})
_TOKEN_BASE_FAMILY_TYPES = frozenset({"GENE", "PROTEIN", "COMPLEX", "VARIANT"})
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    },
)
_HARD_SENTENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bthis study\b", re.IGNORECASE),
    re.compile(r"\bwe (show|found|demonstrate|demonstrated|report)\b", re.IGNORECASE),
    re.compile(r"\bresults? (show|suggest|indicate)\b", re.IGNORECASE),
    re.compile(r"\bconclusion\b", re.IGNORECASE),
)
_SOFT_SENTENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bassociated with\b", re.IGNORECASE),
    re.compile(r"\bcompared with\b", re.IGNORECASE),
    re.compile(r"\bin patients?\b", re.IGNORECASE),
    re.compile(r"\busing\b", re.IGNORECASE),
)
_URL_OR_IDENTIFIER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\bwww\.", re.IGNORECASE),
    re.compile(r"\bdoi:\s*\S+", re.IGNORECASE),
    re.compile(r"\S+@\S+"),
)
_REFERENCE_MARKER_PATTERN = re.compile(
    r"\b(et\s+al\.?|PMID\s*:?\s*\d+)\b|\[\d{1,3}\]|(?:19|20)\d{2}",
    re.IGNORECASE,
)
_ALLOWED_SYMBOL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[A-Z0-9][A-Z0-9\-]{1,24}$"),
    re.compile(r"^rs\d+$", re.IGNORECASE),
    re.compile(r"^c\.[0-9+_\-]+[ACGT]>[ACGT]$", re.IGNORECASE),
    re.compile(r"^p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}$"),
    re.compile(r"^chr(?:[0-9]+|X|Y|M):\d+(?:-\d+)?$", re.IGNORECASE),
)
_MAX_HARD_LABEL_LENGTH = 180
_MAX_SOFT_TOKEN_COUNT = 16
_MAX_SOFT_PUNCTUATION_RATIO = 0.18
_MAX_SOFT_STOPWORD_RATIO = 0.55
_MULTILINE_HARD_LABEL_LENGTH = 80
_TERMINAL_PUNCT_MIN_TOKEN_COUNT = 6
_STOPWORD_RATIO_MIN_TOKEN_COUNT = 8
_PUNCT_RATIO_MIN_TOKEN_COUNT = 6
_BORDERLINE_SIGNAL_THRESHOLD = 2


type EntityShapeGuardOutcome = Literal["ACCEPT", "REJECT", "BORDERLINE"]


@dataclass(frozen=True)
class EntityShapeGuardDecision:
    """Deterministic endpoint-entity label shape classification result."""

    outcome: EntityShapeGuardOutcome
    normalized_label: str
    reason_code: str
    signals: tuple[str, ...] = ()


def build_label_variants(label: str) -> tuple[str, ...]:
    """Build normalized query variants for endpoint lookup."""
    variants: list[str] = []
    seen: set[str] = set()

    def _append(raw_value: str) -> None:
        normalized = raw_value.strip()
        if not normalized:
            return
        dedupe_key = normalized.casefold()
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        variants.append(normalized)

    _append(label)
    without_parenthetical = re.sub(r"\([^)]*\)", " ", label)
    without_parenthetical = " ".join(without_parenthetical.split())
    _append(without_parenthetical)

    normalized_for_matching = normalize_label_for_matching(label)
    if normalized_for_matching:
        _append(normalized_for_matching)
        primary_token = extract_primary_token(normalized_for_matching)
        if primary_token is not None:
            _append(primary_token)
    return tuple(variants)


def evaluate_entity_shape(  # noqa: C901, PLR0912
    *,
    entity_type: str,
    label: str,
) -> EntityShapeGuardDecision:
    """Classify endpoint-label shape as ACCEPT/REJECT/BORDERLINE."""
    del entity_type
    raw_label = label.strip()
    normalized_label = " ".join(raw_label.split())
    if not normalized_label:
        return EntityShapeGuardDecision(
            outcome="REJECT",
            normalized_label="",
            reason_code="shape_empty_label",
            signals=("empty_label",),
        )
    if _is_allowlisted_symbol(normalized_label):
        return EntityShapeGuardDecision(
            outcome="ACCEPT",
            normalized_label=normalized_label,
            reason_code="shape_allowlisted_symbol",
        )

    hard_signals: list[str] = []
    soft_signals: list[str] = []

    if len(normalized_label) > _MAX_HARD_LABEL_LENGTH:
        hard_signals.append("label_too_long")
    if "\n" in raw_label and len(normalized_label) > _MULTILINE_HARD_LABEL_LENGTH:
        hard_signals.append("multi_line_label")
    if any(pattern.search(normalized_label) for pattern in _URL_OR_IDENTIFIER_PATTERNS):
        hard_signals.append("url_or_identifier_like")
    if any(pattern.search(normalized_label) for pattern in _HARD_SENTENCE_PATTERNS):
        hard_signals.append("sentence_discourse_marker")

    lowered = normalized_label.casefold()
    tokens = re.findall(r"[A-Za-z0-9]+", lowered)
    token_count = len(tokens)
    if token_count == 0:
        return EntityShapeGuardDecision(
            outcome="REJECT",
            normalized_label=normalized_label,
            reason_code="shape_no_alnum_tokens",
            signals=("no_alnum_tokens",),
        )

    if token_count > _MAX_SOFT_TOKEN_COUNT:
        soft_signals.append("high_token_count")
    if any(pattern.search(normalized_label) for pattern in _SOFT_SENTENCE_PATTERNS):
        soft_signals.append("soft_sentence_marker")
    if _REFERENCE_MARKER_PATTERN.search(normalized_label):
        soft_signals.append("citation_or_year_marker")
    if (
        normalized_label.endswith((".", ";", ":", "?", "!"))
        and token_count >= _TERMINAL_PUNCT_MIN_TOKEN_COUNT
    ):
        soft_signals.append("terminal_sentence_punctuation")

    stopword_count = sum(1 for token in tokens if token in _STOPWORDS)
    stopword_ratio = stopword_count / max(token_count, 1)
    if (
        token_count >= _STOPWORD_RATIO_MIN_TOKEN_COUNT
        and stopword_ratio >= _MAX_SOFT_STOPWORD_RATIO
    ):
        soft_signals.append("high_stopword_ratio")

    punctuation_count = sum(
        1 for char in normalized_label if not char.isalnum() and not char.isspace()
    )
    punctuation_ratio = punctuation_count / max(len(normalized_label), 1)
    if (
        token_count >= _PUNCT_RATIO_MIN_TOKEN_COUNT
        and punctuation_ratio >= _MAX_SOFT_PUNCTUATION_RATIO
    ):
        soft_signals.append("high_punctuation_ratio")

    if hard_signals:
        return EntityShapeGuardDecision(
            outcome="REJECT",
            normalized_label=normalized_label,
            reason_code="shape_hard_reject",
            signals=tuple(hard_signals),
        )

    if len(soft_signals) >= _BORDERLINE_SIGNAL_THRESHOLD:
        return EntityShapeGuardDecision(
            outcome="BORDERLINE",
            normalized_label=normalized_label,
            reason_code="shape_borderline",
            signals=tuple(soft_signals),
        )

    return EntityShapeGuardDecision(
        outcome="ACCEPT",
        normalized_label=normalized_label,
        reason_code="shape_ok",
        signals=tuple(soft_signals),
    )


def select_best_candidate(
    *,
    query_label: str,
    candidates: tuple[KernelEntity, ...],
) -> KernelEntity | None:
    """Pick the best entity candidate for a query label."""
    if not candidates:
        return None
    query_normalized = normalize_label_for_matching(query_label)
    if not query_normalized:
        return None

    for candidate in candidates:
        candidate_label = (
            candidate.display_label if isinstance(candidate.display_label, str) else ""
        )
        if normalize_label_for_matching(candidate_label) == query_normalized:
            return candidate

    query_primary = extract_primary_token(query_normalized)
    if query_primary is None:
        return None
    query_species = extract_species_hints(query_normalized)

    token_matches: list[KernelEntity] = []
    for candidate in candidates:
        candidate_label = (
            candidate.display_label if isinstance(candidate.display_label, str) else ""
        )
        candidate_normalized = normalize_label_for_matching(candidate_label)
        candidate_primary = extract_primary_token(candidate_normalized)
        if candidate_primary != query_primary:
            continue
        candidate_species = extract_species_hints(candidate_normalized)
        if query_species and candidate_species and query_species != candidate_species:
            continue
        token_matches.append(candidate)

    if not token_matches:
        return None
    return min(
        token_matches,
        key=lambda candidate: len(
            normalize_label_for_matching(
                candidate.display_label if candidate.display_label is not None else "",
            ),
        ),
    )


def normalize_label_for_matching(label: str) -> str:
    """Normalize labels to a lower-cased alphanumeric token form."""
    without_parenthetical = re.sub(r"\([^)]*\)", " ", label)
    flattened = re.sub(r"[^A-Za-z0-9]+", " ", without_parenthetical)
    return " ".join(flattened.lower().split())


def extract_primary_token(normalized_label: str) -> str | None:
    """Extract the strongest token for coarse concept matching."""
    tokens = normalized_label.split()
    if not tokens:
        return None
    for token in tokens:
        if any(char.isdigit() for char in token) and any(
            char.isalpha() for char in token
        ):
            return token
    for token in tokens:
        if any(char.isalpha() for char in token):
            return token
    return tokens[0]


def extract_species_hints(normalized_label: str) -> set[str]:
    """Extract coarse species hints used to avoid bad cross-species merges."""
    species_tokens = {
        "human",
        "mouse",
        "rat",
        "zebrafish",
        "drosophila",
        "plant",
        "arabidopsis",
    }
    tokens = set(normalized_label.split())
    return {token for token in tokens if token in species_tokens}


def normalize_entity_type(entity_type: str) -> str:
    """Normalize entity-type text for identity functions."""
    return entity_type.strip().upper()


def is_conceptual_entity_type(entity_type: str) -> bool:
    """Return whether an entity type should participate in concept identity."""
    return normalize_entity_type(entity_type) in _CONCEPTUAL_ENTITY_TYPES


def _normalized_label_component(label: str) -> str | None:
    normalized_label = normalize_label_for_matching(label)
    if not normalized_label:
        return None
    return normalized_label.replace(" ", "_").upper()


def build_entity_concept_key(entity_type: str, label: str) -> str | None:
    """Build a deterministic concept key for one entity node."""
    normalized_type = normalize_entity_type(entity_type)
    if normalized_type not in _CONCEPTUAL_ENTITY_TYPES:
        return None
    normalized_label = normalize_label_for_matching(label)
    if not normalized_label:
        return None
    species = extract_species_hints(normalized_label)
    species_key = "+".join(sorted(species)) if species else "unspecified"
    if normalized_type in _TOKEN_BASE_CONCEPT_KEY_TYPES:
        primary = extract_primary_token(normalized_label)
        if primary is None:
            return None
        identity_component = primary.upper()
    else:
        normalized_component = _normalized_label_component(label)
        if normalized_component is None:
            return None
        identity_component = normalized_component
    return f"{normalized_type}::{identity_component}::{species_key}"


def build_concept_family_key(entity_type: str, label: str) -> str | None:
    """Build a family key used to group related conceptual entities."""
    normalized_type = normalize_entity_type(entity_type)
    if normalized_type not in _CONCEPTUAL_ENTITY_TYPES:
        return None
    normalized_label = normalize_label_for_matching(label)
    if not normalized_label:
        return None
    if normalized_type in _TOKEN_BASE_FAMILY_TYPES:
        primary = extract_primary_token(normalized_label)
        if primary is None:
            return None
        family_component = primary.upper()
    else:
        normalized_component = _normalized_label_component(label)
        if normalized_component is None:
            return None
        family_component = normalized_component
    species = extract_species_hints(normalized_label)
    if species:
        return f"{family_component}::{'+'.join(sorted(species))}"
    return family_component


def build_concept_family_key_from_label(label: str) -> str | None:
    """Build a family key directly from a label."""
    normalized_label = normalize_label_for_matching(label)
    primary = extract_primary_token(normalized_label)
    if primary is None:
        return None
    species = extract_species_hints(normalized_label)
    if species:
        return f"{primary.upper()}::{'+'.join(sorted(species))}"
    return primary.upper()


def _is_allowlisted_symbol(label: str) -> bool:
    if " " in label:
        return False
    return any(pattern.fullmatch(label) for pattern in _ALLOWED_SYMBOL_PATTERNS)


__all__ = [
    "EntityShapeGuardDecision",
    "EntityShapeGuardOutcome",
    "build_label_variants",
    "build_concept_family_key",
    "build_concept_family_key_from_label",
    "build_entity_concept_key",
    "evaluate_entity_shape",
    "extract_primary_token",
    "extract_species_hints",
    "is_conceptual_entity_type",
    "normalize_entity_type",
    "normalize_label_for_matching",
    "select_best_candidate",
]
