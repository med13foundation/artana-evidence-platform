"""Deterministic relation triage used only by observable fallback paths."""

from __future__ import annotations

import re

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_entities import (
    canonical_entity_label_rejection_reason,
    clean_candidate_label,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    is_low_value_generic_relation_candidate,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_RELATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9\- ]{1,80}?)\s+"
            r"(?P<lemma>regulates|activated|activates|inhibits|interacts with|"
            r"interact with|associates with|associate with|associated with|"
            r"is associated with|was associated with|were associated with|"
            r"has been associated with|have been associated with|linked to|"
            r"is linked to|was linked to|were linked to|has been linked to|"
            r"have been linked to|causes|caused|drives|driven|promotes|"
            r"promoted|supports|supported|results in|resulted in|leads to|"
            r"led to|contributes to|contributed to|correlates with|"
            r"correlated with|is correlated with|was correlated with|"
            r"were correlated with)\s+"
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,80}?)\s+"
            r"(?:is|was|were)\s+regulated by\s+"
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "REGULATES",
    ),
    (
        re.compile(
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,80}?)\s+"
            r"(?:is|was|were)\s+caused by\s+"
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "CAUSES",
    ),
)
_LEMMA_RELATION_TYPES = {
    "activate": "ACTIVATES",
    "activated": "ACTIVATES",
    "activates": "ACTIVATES",
    "associate with": "ASSOCIATED_WITH",
    "associated with": "ASSOCIATED_WITH",
    "associates with": "ASSOCIATED_WITH",
    "caused": "CAUSES",
    "causes": "CAUSES",
    "contribute to": "ASSOCIATED_WITH",
    "contributed to": "ASSOCIATED_WITH",
    "contributes to": "ASSOCIATED_WITH",
    "correlated with": "ASSOCIATED_WITH",
    "drive": "ASSOCIATED_WITH",
    "driven": "ASSOCIATED_WITH",
    "drives": "ASSOCIATED_WITH",
    "has been associated with": "ASSOCIATED_WITH",
    "has been linked to": "ASSOCIATED_WITH",
    "have been associated with": "ASSOCIATED_WITH",
    "have been linked to": "ASSOCIATED_WITH",
    "interact with": "INTERACTS_WITH",
    "inhibits": "INHIBITS",
    "interacts with": "INTERACTS_WITH",
    "is associated with": "ASSOCIATED_WITH",
    "is correlated with": "ASSOCIATED_WITH",
    "is linked to": "ASSOCIATED_WITH",
    "lead to": "CAUSES",
    "leads to": "CAUSES",
    "led to": "CAUSES",
    "linked to": "ASSOCIATED_WITH",
    "promote": "ACTIVATES",
    "promoted": "ACTIVATES",
    "promotes": "ACTIVATES",
    "regulate": "REGULATES",
    "regulates": "REGULATES",
    "reported": "ASSOCIATED_WITH",
    "resulted in": "CAUSES",
    "results in": "CAUSES",
    "support": "ASSOCIATED_WITH",
    "supported": "ASSOCIATED_WITH",
    "supports": "ASSOCIATED_WITH",
    "was associated with": "ASSOCIATED_WITH",
    "was correlated with": "ASSOCIATED_WITH",
    "was linked to": "ASSOCIATED_WITH",
    "were associated with": "ASSOCIATED_WITH",
    "were correlated with": "ASSOCIATED_WITH",
    "were linked to": "ASSOCIATED_WITH",
}
_MIN_HEURISTIC_SUBJECT_CHARS = 3
_SHORT_BIOMEDICAL_SUBJECT_LABELS = frozenset({"Hh"})
_BAD_STANDALONE_SUBJECT_LABELS = frozenset(
    {
        "a",
        "all",
        "an",
        "both",
        "closely",
        "drug",
        "each",
        "forms",
        "it",
        "many",
        "most",
        "one",
        "plays",
        "rna",
        "several",
        "some",
        "such",
        "the",
        "these",
        "they",
        "this",
        "we",
    },
)
_BAD_STANDALONE_SUBJECT_LEMMAS = frozenset({"acts", "binds"})


def extract_relation_candidates(text: str) -> list[ExtractedRelationCandidate]:
    """Extract untrusted relation candidates for fallback triage."""

    normalized_text = _normalize_text_document(text)
    if normalized_text == "":
        return []
    candidates: list[ExtractedRelationCandidate] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for sentence in _SENTENCE_SPLIT_RE.split(normalized_text):
        cleaned_sentence = " ".join(sentence.split()).strip()
        if cleaned_sentence == "":
            continue
        for pattern, fixed_relation_type in _RELATION_PATTERNS:
            match = pattern.search(cleaned_sentence)
            if match is None:
                continue
            subject_label = clean_candidate_label(
                match.group("subject"),
                prefer_tail=True,
            )
            object_label = clean_candidate_label(match.group("object"))
            lemma = match.groupdict().get("lemma", "").strip().lower()
            relation_type = fixed_relation_type or _LEMMA_RELATION_TYPES.get(
                lemma,
                "ASSOCIATED_WITH",
            )
            if subject_label == "" or object_label == "":
                continue
            if _is_bad_heuristic_subject_label(subject_label):
                continue
            if canonical_entity_label_rejection_reason(subject_label) is not None:
                continue
            if is_low_value_generic_relation_candidate(
                relation_type=relation_type,
                lemma=lemma,
                sentence=cleaned_sentence,
            ):
                continue
            candidate_key = (
                subject_label.casefold(),
                relation_type,
                object_label.casefold(),
                cleaned_sentence.casefold(),
            )
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            candidates.append(
                ExtractedRelationCandidate(
                    subject_label=subject_label,
                    relation_type=relation_type,
                    object_label=object_label,
                    sentence=cleaned_sentence,
                ),
            )
            break
    return candidates


def _normalize_text_document(text: str) -> str:
    normalized_lines = [
        line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(normalized_lines).strip()


def _is_bad_heuristic_subject_label(label: str) -> bool:
    normalized_label = " ".join(label.strip(".,;:\"'").split())
    if normalized_label == "":
        return True
    normalized_token = normalized_label.casefold()
    if (
        " " not in normalized_label
        and normalized_token in _BAD_STANDALONE_SUBJECT_LABELS
    ):
        return True
    if normalized_token in _BAD_STANDALONE_SUBJECT_LEMMAS:
        return True
    return (
        len(normalized_label) < _MIN_HEURISTIC_SUBJECT_CHARS
        and normalized_label not in _SHORT_BIOMEDICAL_SUBJECT_LABELS
    )


__all__ = ["extract_relation_candidates"]
