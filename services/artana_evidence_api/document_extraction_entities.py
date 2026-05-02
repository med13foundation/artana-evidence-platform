"""Entity-label cleanup and graph resolution helpers for document extraction."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle


def _graph_ai_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()


_LEADING_FILLER_RE = re.compile(
    r"^(?:the|a|an|this|that|these|those|our|their|its)\s+",
    re.IGNORECASE,
)
_TRAILING_CONTEXT_RE = re.compile(
    r"\s+(?:in|during|among|across|within|via|through|after|before|under|with)\s+"
    r"[A-Za-z0-9][A-Za-z0-9()\-/, ]*$",
    re.IGNORECASE,
)
_PARENTHETICAL_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
_ENTITY_LABEL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+./_-]*")
_GENE_SYMBOL_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:[/-][A-Z0-9]+)?)\b")
_GENE_SYMBOL_TOKEN_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9]{1,9})\b")
_GENE_SYMBOL_SLASH_SHORTHAND_RE = re.compile(
    r"\b([A-Z]{2,}[A-Z0-9]*?)(\d+[A-Z]?)/(\d+[A-Z]?)\b",
    re.IGNORECASE,
)
_GENE_SYMBOL_LIST_RE = re.compile(r"(?:\b(?:and|or|versus|vs)\b|[,/])", re.IGNORECASE)
_MIN_COMPOUND_SEGMENT_TOKEN_COUNT = 2
_MIN_EXACT_SPLIT_MATCH_COUNT = 2
_MIN_AMBIGUOUS_GENE_SYMBOL_COUNT = 2
_MIN_GENE_SYMBOL_FAMILY_CHARS = 3
_SUBJECT_CONTEXT_MARKERS = (
    " that ",
    " showed ",
    " shows ",
    " found ",
    " finds ",
    " suggests ",
    " suggested ",
    " demonstrated ",
    " demonstrates ",
    " indicates ",
    " indicated ",
    " observed ",
    " reports ",
    " reported ",
)
_ENTITY_LABEL_PREFIXES = (
    "loss of ",
    "deficiency of ",
    "depletion of ",
    "deletion of ",
    "overexpression of ",
    "underexpression of ",
    "mutation in ",
    "mutations in ",
    "variant in ",
    "variants in ",
)
_MAX_ENTITY_LABEL_WORDS = 4
_MAX_CANONICAL_ENTITY_LABEL_TOKENS = 6
_MAX_NUMERIC_FRAGMENT_CHARS = 3
_LEADING_FRAGMENT_TOKENS = frozenset(
    {
        "and",
        "although",
        "because",
        "but",
        "how",
        "other",
        "since",
        "some",
        "that",
        "though",
        "what",
        "when",
        "where",
        "whether",
        "which",
        "while",
        "who",
        "whose",
    },
)
_STANDALONE_FRAGMENT_TOKENS = frozenset(
    {
        "all",
        "are",
        "be",
        "been",
        "being",
        "both",
        "can",
        "could",
        "did",
        "do",
        "does",
        "had",
        "has",
        "have",
        "is",
        "may",
        "might",
        "must",
        "not",
        "now",
        "shall",
        "should",
        "sometimes",
        "there",
        "was",
        "were",
        "will",
        "would",
    },
)
_CLAUSE_VERB_TOKENS = frozenset(
    {
        "are",
        "be",
        "been",
        "being",
        "causes",
        "could",
        "demonstrated",
        "demonstrates",
        "did",
        "does",
        "found",
        "had",
        "has",
        "have",
        "indicated",
        "indicates",
        "is",
        "may",
        "might",
        "observed",
        "reported",
        "reports",
        "showed",
        "shows",
        "suggested",
        "suggests",
        "was",
        "were",
        "will",
    },
)
_FRAGMENT_ADVERB_TOKENS = frozenset(
    {
        "all",
        "both",
        "differentially",
        "negatively",
        "now",
        "positively",
        "sometimes",
    },
)
_GENERIC_CLASS_TOKENS = frozenset(
    {
        "features",
        "genes",
        "modules",
        "proteins",
    },
)
_GENE_SYMBOL_STOPWORDS = _LEADING_FRAGMENT_TOKENS | _STANDALONE_FRAGMENT_TOKENS


def clean_llm_entity_label(raw: str) -> str:
    """Clean an LLM-generated entity label to a short canonical name."""

    label = raw.strip().strip(".,;:\"'")
    if _is_ambiguous_gene_symbol_mention(label):
        return ""
    words = label.split()
    if (
        len(words) <= _MAX_ENTITY_LABEL_WORDS
        and canonical_entity_label_rejection_reason(label) is None
    ):
        return label

    gene_match = _GENE_SYMBOL_RE.search(label)
    if gene_match and gene_match.group(1).casefold() not in _GENE_SYMBOL_STOPWORDS:
        return gene_match.group(1)

    filler = {
        "the",
        "a",
        "an",
        "this",
        "that",
        "these",
        "those",
        "in",
        "of",
        "to",
        "for",
        "by",
        "with",
        "from",
        "on",
        "at",
        "is",
        "are",
        "was",
        "were",
        "and",
        "or",
        "whether",
        "order",
        "examine",
        "there",
        "both",
        "its",
    }
    meaningful = [word for word in words if word.lower() not in filler]
    cleaned = (
        " ".join(meaningful[:_MAX_ENTITY_LABEL_WORDS])
        if meaningful
        else " ".join(words[:_MAX_ENTITY_LABEL_WORDS])
    )
    if canonical_entity_label_rejection_reason(cleaned) is not None:
        return ""
    return cleaned


def is_canonical_entity_label(label: str) -> bool:
    """Return whether a label is shaped like one canonical entity name."""

    return canonical_entity_label_rejection_reason(label) is None


def canonical_entity_label_rejection_reason(label: str) -> str | None:
    """Return why one extracted entity label is too fragmentary to stage."""

    raw_label = label.strip()
    normalized_label = " ".join(raw_label.strip(".,;:\"'").split())
    tokens = tuple(
        token.casefold() for token in _ENTITY_LABEL_TOKEN_RE.findall(normalized_label)
    )
    reason: str | None = None
    if normalized_label == "":
        reason = "empty_entity_label"
    elif any(character in raw_label for character in "\n\r\t!?;"):
        reason = "sentence_fragment_punctuation"
    elif not tokens:
        reason = "empty_entity_label"
    elif _is_ambiguous_gene_symbol_mention(normalized_label):
        reason = "ambiguous_gene_symbol_mention"
    elif len(tokens) > _MAX_CANONICAL_ENTITY_LABEL_TOKENS:
        reason = "entity_label_too_long"
    elif len(tokens) == 1 and tokens[0] in _STANDALONE_FRAGMENT_TOKENS:
        reason = "standalone_fragment_label"
    elif (
        len(tokens) == 1
        and tokens[0][0].isdigit()
        and len(tokens[0]) <= _MAX_NUMERIC_FRAGMENT_CHARS
    ):
        reason = "numeric_fragment_label"
    elif tokens[0] in _LEADING_FRAGMENT_TOKENS:
        reason = "leading_fragment_token"
    elif any(token in _CLAUSE_VERB_TOKENS for token in tokens):
        reason = "sentence_fragment_verb"
    elif any(token in _FRAGMENT_ADVERB_TOKENS for token in tokens):
        reason = "sentence_fragment_modifier"
    elif tokens[-1] in _GENERIC_CLASS_TOKENS and _GENE_SYMBOL_RE.search(
        normalized_label,
    ) is None:
        reason = "generic_entity_class_label"
    return reason


def clean_candidate_label(
    raw_label: str,
    *,
    prefer_tail: bool = False,
) -> str:
    """Normalize one extracted entity label without resolving it."""

    label = " ".join(raw_label.split()).strip(" .,:;")
    if prefer_tail:
        label = label.split(",")[-1].strip()
        for marker in _SUBJECT_CONTEXT_MARKERS:
            normalized_label = label.casefold()
            marker_index = normalized_label.rfind(marker.strip())
            if marker_index == -1:
                continue
            candidate_label = label[marker_index + len(marker.strip()) :].strip()
            if candidate_label != "":
                label = candidate_label
                break
    label = _LEADING_FILLER_RE.sub("", label)
    for prefix in _ENTITY_LABEL_PREFIXES:
        if label.casefold().startswith(prefix):
            label = label[len(prefix) :].strip()
            break
    label = _TRAILING_CONTEXT_RE.sub("", label).strip()
    return _PARENTHETICAL_SUFFIX_RE.sub("", label).strip(" .,:;")


def split_compound_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> tuple[str, ...]:
    """Split compound object labels only when the split is likely intentional."""

    base_label = clean_candidate_label(label)
    segments, contains_comma, contains_and, contains_or = _segment_compound_label(
        label,
    )
    cleaned_segments: list[str] = []
    seen_labels: set[str] = set()
    for segment in segments:
        cleaned_segment = clean_candidate_label(segment)
        if cleaned_segment == "":
            continue
        normalized_segment = cleaned_segment.casefold()
        if normalized_segment in seen_labels:
            continue
        seen_labels.add(normalized_segment)
        cleaned_segments.append(cleaned_segment)
    if len(cleaned_segments) <= 1 or contains_or:
        return _base_or_cleaned_entity_labels(
            base_label=base_label,
            cleaned_segments=cleaned_segments,
        )
    if contains_comma or _should_split_conjunction_label(
        space_id=space_id,
        cleaned_segments=cleaned_segments,
        contains_and=contains_and,
        graph_api_gateway=graph_api_gateway,
    ):
        return tuple(cleaned_segments)
    return _base_or_cleaned_entity_labels(
        base_label=base_label,
        cleaned_segments=cleaned_segments,
    )


def _base_or_cleaned_entity_labels(
    *,
    base_label: str,
    cleaned_segments: list[str],
) -> tuple[str, ...]:
    if base_label != "":
        return (base_label,)
    return tuple(cleaned_segments)


def _should_split_conjunction_label(
    *,
    space_id: UUID,
    cleaned_segments: list[str],
    contains_and: bool,
    graph_api_gateway: GraphTransportBundle,
) -> bool:
    if not contains_and:
        return False
    if all(
        _token_count(segment) >= _MIN_COMPOUND_SEGMENT_TOKEN_COUNT
        for segment in cleaned_segments
    ):
        return True
    return (
        _count_exact_entity_matches(
            space_id=space_id,
            labels=cleaned_segments,
            graph_api_gateway=graph_api_gateway,
        )
        >= _MIN_EXACT_SPLIT_MATCH_COUNT
    )


def _segment_compound_label(label: str) -> tuple[list[str], bool, bool, bool]:
    segments: list[str] = []
    current: list[str] = []
    parentheses_depth = 0
    contains_comma = False
    contains_and = False
    contains_or = False
    index = 0
    while index < len(label):
        character = label[index]
        if character == "(":
            parentheses_depth += 1
            current.append(character)
            index += 1
            continue
        if character == ")":
            parentheses_depth = max(0, parentheses_depth - 1)
            current.append(character)
            index += 1
            continue
        if parentheses_depth == 0 and character == ",":
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_comma = True
            index += 1
            continue
        normalized_tail = label[index:].casefold()
        if parentheses_depth == 0 and normalized_tail.startswith(" and "):
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_and = True
            index += len(" and ")
            continue
        if parentheses_depth == 0 and normalized_tail.startswith(" or "):
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_or = True
            index += len(" or ")
            continue
        current.append(character)
        index += 1
    final_segment = "".join(current).strip()
    if final_segment != "":
        segments.append(final_segment)
    return segments, contains_comma, contains_and, contains_or


def _is_ambiguous_gene_symbol_mention(label: str) -> bool:
    if _GENE_SYMBOL_LIST_RE.search(label) is None:
        return False

    symbols = _collect_gene_symbol_mentions(label)
    if len(symbols) < _MIN_AMBIGUOUS_GENE_SYMBOL_COUNT:
        return False

    return _contains_similar_gene_symbol_pair(symbols)


def _collect_gene_symbol_mentions(label: str) -> tuple[str, ...]:
    symbols: list[str] = []
    seen_symbols: set[str] = set()

    for match in _GENE_SYMBOL_SLASH_SHORTHAND_RE.finditer(label):
        prefix = match.group(1)
        for suffix in (match.group(2), match.group(3)):
            _append_gene_symbol(
                symbols=symbols,
                seen_symbols=seen_symbols,
                symbol=f"{prefix}{suffix}",
            )

    for match in _GENE_SYMBOL_TOKEN_RE.finditer(label):
        _append_gene_symbol(
            symbols=symbols,
            seen_symbols=seen_symbols,
            symbol=match.group(1),
        )

    return tuple(symbols)


def _append_gene_symbol(
    *,
    symbols: list[str],
    seen_symbols: set[str],
    symbol: str,
) -> None:
    if not _is_gene_symbol_like_token(symbol):
        return
    normalized_symbol = symbol.casefold()
    if normalized_symbol in _GENE_SYMBOL_STOPWORDS:
        return
    if normalized_symbol in seen_symbols:
        return
    seen_symbols.add(normalized_symbol)
    symbols.append(symbol.upper())


def _is_gene_symbol_like_token(symbol: str) -> bool:
    return symbol.isupper() or (
        any(character.isupper() for character in symbol)
        and any(character.isdigit() for character in symbol)
    )


def _contains_similar_gene_symbol_pair(symbols: tuple[str, ...]) -> bool:
    for left_index, left_symbol in enumerate(symbols):
        for right_symbol in symbols[left_index + 1 :]:
            if _are_similar_gene_symbols(left_symbol, right_symbol):
                return True
    return False


def _are_similar_gene_symbols(left_symbol: str, right_symbol: str) -> bool:
    if left_symbol == right_symbol:
        return False

    shorter, longer = sorted((left_symbol, right_symbol), key=len)
    if len(shorter) >= _MIN_GENE_SYMBOL_FAMILY_CHARS and longer.startswith(shorter):
        return True

    left_stem = _gene_symbol_family_stem(left_symbol)
    right_stem = _gene_symbol_family_stem(right_symbol)
    return left_stem != "" and left_stem == right_stem


def _gene_symbol_family_stem(symbol: str) -> str:
    stem = re.sub(r"\d+[A-Z]*$", "", symbol)
    if len(stem) < _MIN_GENE_SYMBOL_FAMILY_CHARS:
        return ""
    return stem


def _token_count(label: str) -> int:
    return len([token for token in label.split() if token != ""])


def _count_exact_entity_matches(
    *,
    space_id: UUID,
    labels: list[str],
    graph_api_gateway: GraphTransportBundle,
) -> int:
    return sum(
        1
        for label in labels
        if resolve_exact_entity_label(
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_api_gateway,
        )
        is not None
    )


def build_unresolved_entity_id(label: str) -> str:
    """Build a stable placeholder entity id for unresolved labels."""

    normalized = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return f"unresolved:{normalized or 'entity'}"


def require_match_id(match: JSONObject) -> str:
    """Return a resolved match id or fail loudly on malformed graph data."""

    entity_id = match.get("id")
    if isinstance(entity_id, str) and entity_id.strip() != "":
        return entity_id
    message = "Resolved graph entity match is missing an id"
    raise ValueError(message)


def require_match_display_label(match: JSONObject) -> str:
    """Return a resolved display label, falling back to the match id."""

    display_label = match.get("display_label")
    if isinstance(display_label, str) and display_label.strip() != "":
        return display_label
    return require_match_id(match)


def resolve_graph_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    """Resolve an entity label through the graph preflight service."""

    return _graph_ai_preflight_service().resolve_entity_label(
        space_id=space_id,
        label=label,
        graph_transport=graph_api_gateway,
    )


def resolve_exact_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    """Resolve an entity label only when the graph has an exact label/alias hit."""

    try:
        response = graph_api_gateway.list_entities(
            space_id=space_id,
            q=label,
            limit=5,
        )
    except GraphServiceClientError:
        return None
    normalized_label = label.strip().casefold()
    for entity in response.entities:
        display_label = entity.display_label or ""
        aliases = entity.aliases
        exact_aliases = {alias.casefold() for alias in aliases}
        if (
            display_label.casefold() == normalized_label
            or normalized_label in exact_aliases
        ):
            return {
                "id": str(entity.id),
                "display_label": display_label or str(entity.id),
            }
    return None


def resolve_entity_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
    ai_resolved_entities: dict[str, JSONObject] | None = None,
) -> JSONObject | None:
    """Resolve entity label, checking AI pre-resolution cache first."""

    if ai_resolved_entities is not None:
        cache_key = label.strip().casefold()
        if cache_key in ai_resolved_entities:
            return ai_resolved_entities[cache_key]

    return resolve_graph_entity_label(
        space_id=space_id,
        label=label,
        graph_api_gateway=graph_api_gateway,
    )


__all__ = [
    "build_unresolved_entity_id",
    "canonical_entity_label_rejection_reason",
    "clean_candidate_label",
    "clean_llm_entity_label",
    "is_canonical_entity_label",
    "require_match_display_label",
    "require_match_id",
    "resolve_entity_label",
    "resolve_exact_entity_label",
    "resolve_graph_entity_label",
    "split_compound_entity_label",
]
