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
_MIN_COMPOUND_SEGMENT_TOKEN_COUNT = 2
_MIN_EXACT_SPLIT_MATCH_COUNT = 2
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


def clean_llm_entity_label(raw: str) -> str:
    """Clean an LLM-generated entity label to a short canonical name."""

    label = raw.strip().strip(".,;:\"'")
    words = label.split()
    if len(words) <= _MAX_ENTITY_LABEL_WORDS:
        return label

    gene_match = re.search(r"\b([A-Z][A-Z0-9]{1,9}(?:[/-][A-Z0-9]+)?)\b", label)
    if gene_match:
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
    if meaningful:
        return " ".join(meaningful[:_MAX_ENTITY_LABEL_WORDS])
    return " ".join(words[:_MAX_ENTITY_LABEL_WORDS])


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
    segments, contains_comma, contains_conjunction = _segment_compound_label(label)
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
    if len(cleaned_segments) <= 1:
        if base_label != "":
            return (base_label,)
        return tuple(cleaned_segments)
    if contains_comma:
        return tuple(cleaned_segments)
    if contains_conjunction and (
        all(
            _token_count(segment) >= _MIN_COMPOUND_SEGMENT_TOKEN_COUNT
            for segment in cleaned_segments
        )
        or _count_exact_entity_matches(
            space_id=space_id,
            labels=cleaned_segments,
            graph_api_gateway=graph_api_gateway,
        )
        >= _MIN_EXACT_SPLIT_MATCH_COUNT
    ):
        return tuple(cleaned_segments)
    if base_label != "":
        return (base_label,)
    return tuple(cleaned_segments)


def _segment_compound_label(label: str) -> tuple[list[str], bool, bool]:
    segments: list[str] = []
    current: list[str] = []
    parentheses_depth = 0
    contains_comma = False
    contains_conjunction = False
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
            contains_conjunction = True
            index += len(" and ")
            continue
        if parentheses_depth == 0 and normalized_tail.startswith(" or "):
            segment = "".join(current).strip()
            if segment != "":
                segments.append(segment)
            current = []
            contains_conjunction = True
            index += len(" or ")
            continue
        current.append(character)
        index += 1
    final_segment = "".join(current).strip()
    if final_segment != "":
        segments.append(final_segment)
    return segments, contains_comma, contains_conjunction


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
    "clean_candidate_label",
    "clean_llm_entity_label",
    "require_match_display_label",
    "require_match_id",
    "resolve_entity_label",
    "resolve_exact_entity_label",
    "resolve_graph_entity_label",
    "split_compound_entity_label",
]
