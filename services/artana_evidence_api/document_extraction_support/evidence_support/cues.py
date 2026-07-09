"""Relation cue lexicon for heuristic evidence support verification."""

from __future__ import annotations

_MIN_FALLBACK_CUE_LENGTH = 4
_SYMMETRIC_RELATION_TYPES = frozenset(
    {
        "ASSOCIATED_WITH",
        "PHYSICALLY_INTERACTS_WITH",
    }
)
_PASSIVE_CUES_BY_RELATION: dict[str, tuple[str, ...]] = {
    "ACTIVATES": ("activated by", "activation by"),
    "CAUSES": ("caused by",),
    "INHIBITS": ("inhibited by", "suppressed by", "reduced by"),
    "REGULATES": ("regulated by",),
    "TARGETS": ("targeted by",),
    "TREATS": ("responsive to",),
}
_RELATION_CUES: dict[str, tuple[str, ...]] = {
    "ACTIVATES": (
        "activate",
        "activates",
        "activated",
        "activated by",
        "activation",
        "activation by",
        "upregulates",
        "increases",
    ),
    "ASSOCIATED_WITH": (
        "associated with",
        "linked to",
        "correlated with",
        "correlates with",
    ),
    "BIOMARKER_FOR": (
        "biomarker for",
        "marker for",
        "predicts",
        "predictor of",
        "indicator of",
    ),
    "CAUSES": ("causes", "caused", "caused by", "leads to", "results in"),
    "CONFERS_RESISTANCE_TO": (
        "confers resistance to",
        "causes resistance to",
        "drives resistance to",
        "mediates resistance to",
        "renders resistant to",
        "resistant to",
    ),
    "DOWNSTREAM_OF": ("downstream of", "downstream", "triggered by"),
    "INHIBITS": (
        "inhibits",
        "inhibit",
        "inhibited",
        "inhibited by",
        "suppresses",
        "suppressed",
        "suppressed by",
        "reduces",
        "reduced by",
    ),
    "PHYSICALLY_INTERACTS_WITH": (
        "interacts with",
        "binds",
        "binds to",
        "bound to",
    ),
    "PREDISPOSES_TO": (
        "predispose to",
        "predispose",
        "predisposes to",
        "predisposes",
        "increases risk of",
        "confers susceptibility to",
        "susceptibility to",
    ),
    "PROTECTS_AGAINST": ("protects against", "protective against"),
    "REGULATES": ("regulates", "regulated", "regulated by", "regulation", "controls"),
    "SENSITIZES_TO": (
        "sensitizes to",
        "sensitizes",
        "increases sensitivity to",
        "confers sensitivity to",
        "renders sensitive to",
        "sensitive to",
    ),
    "TARGETS": ("targets", "targeted", "targeted by", "binds"),
    "TREATS": ("treats", "treated", "treatment with", "responsive to"),
}


def relation_cues(normalized_relation_type: str) -> tuple[str, ...]:
    """Return lexical cues for one normalized relation type."""

    cues = _RELATION_CUES.get(normalized_relation_type)
    if cues is not None:
        return cues
    return tuple(
        token.casefold()
        for token in normalized_relation_type.split("_")
        if len(token) >= _MIN_FALLBACK_CUE_LENGTH
    )


def passive_cues_for_relation(normalized_relation_type: str) -> tuple[str, ...]:
    """Return cues where relation orientation is object-cue-subject."""

    return _PASSIVE_CUES_BY_RELATION.get(normalized_relation_type, ())


def is_symmetric_relation(normalized_relation_type: str) -> bool:
    """Return whether either endpoint order can entail this relation."""

    return normalized_relation_type in _SYMMETRIC_RELATION_TYPES


__all__ = [
    "is_symmetric_relation",
    "passive_cues_for_relation",
    "relation_cues",
]
