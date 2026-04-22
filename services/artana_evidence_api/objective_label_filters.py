"""Shared objective-aware label filtering helpers."""

from __future__ import annotations

import re
from typing import Literal

TaxonomicFilterReason = Literal["taxonomic_spillover"]
UnderanchoredFragmentFilterReason = Literal["underanchored_fragment_label"]

_ORGANISM_FOCUS_TERMS = frozenset(
    {
        "bacterial",
        "fungal",
        "host",
        "microbe",
        "microbial",
        "model",
        "mouse",
        "murine",
        "organism",
        "species",
        "strain",
        "yeast",
        "zebrafish",
    },
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9-]+")
_TAXONOMIC_NAME_PATTERN = re.compile(
    r"^[A-Z][a-z]+ [a-z][a-z-]+(?: [A-Z0-9][A-Za-z0-9.-]+)?$"
)
_FRAGMENT_TOKENS = frozenset(
    {
        "binding",
        "core",
        "domain",
        "domains",
        "head",
        "helix",
        "interface",
        "loop",
        "loops",
        "motif",
        "motifs",
        "region",
        "regions",
        "repeat",
        "repeats",
        "segment",
        "segments",
        "site",
        "sites",
        "tail",
        "terminal",
        "terminus",
    },
)
_GENERIC_FRAGMENT_TOKENS = _FRAGMENT_TOKENS | frozenset(
    {
        "c",
        "dna",
        "gene",
        "n",
        "protein",
        "rna",
    },
)
_MIN_FRAGMENT_ANCHOR_TOKEN_LENGTH = 4


def text_tokens(value: str | None) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(token for token in _TOKEN_PATTERN.findall(value.casefold()) if token)


def looks_like_taxonomic_name(label: str) -> bool:
    """Return whether one display label looks like a species or strain name."""

    return _TAXONOMIC_NAME_PATTERN.fullmatch(label.strip()) is not None


def is_organism_focused_objective(objective: str | None) -> bool:
    """Return whether one objective is explicitly about organisms or strains."""

    if not isinstance(objective, str) or objective.strip() == "":
        return False
    normalized = objective.strip()
    if looks_like_taxonomic_name(normalized):
        return True
    objective_tokens = set(text_tokens(normalized))
    return any(token in _ORGANISM_FOCUS_TERMS for token in objective_tokens)


def filtered_taxonomic_spillover_reason(
    *,
    label: str,
    objective: str | None,
) -> TaxonomicFilterReason | None:
    """Return the objective-aware taxonomic spillover reason for one label."""

    if looks_like_taxonomic_name(label) and not is_organism_focused_objective(
        objective
    ):
        return "taxonomic_spillover"
    return None


def filtered_underanchored_fragment_reason(
    *,
    label: str,
    objective: str | None,
) -> UnderanchoredFragmentFilterReason | None:
    """Return whether one fragment-like label lacks enough context to chase."""

    label_tokens = text_tokens(label)
    if not label_tokens:
        return None
    if not any(token in _FRAGMENT_TOKENS for token in label_tokens):
        return None
    objective_tokens = set(text_tokens(objective))
    if objective_tokens and set(label_tokens).issubset(objective_tokens):
        return None
    anchor_tokens = [
        token
        for token in label_tokens
        if token not in _GENERIC_FRAGMENT_TOKENS
        and (
            len(token) >= _MIN_FRAGMENT_ANCHOR_TOKEN_LENGTH
            or any(character.isdigit() for character in token)
        )
    ]
    if anchor_tokens:
        return None
    return "underanchored_fragment_label"


__all__ = [
    "TaxonomicFilterReason",
    "filtered_taxonomic_spillover_reason",
    "filtered_underanchored_fragment_reason",
    "is_organism_focused_objective",
    "looks_like_taxonomic_name",
    "text_tokens",
    "UnderanchoredFragmentFilterReason",
]
