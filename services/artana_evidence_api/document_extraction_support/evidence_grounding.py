"""Evidence sentence grounding helpers for document extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from artana_evidence_api.types.common import JSONObject

GroundingMatchKind = Literal["exact", "whitespace_normalized", "fuzzy", "none"]

_FUZZY_SENTENCE_THRESHOLD = 0.92
_THREE_TO_ONE_AMINO_ACID_CODES = {
    "ala": "A",
    "arg": "R",
    "asn": "N",
    "asp": "D",
    "cys": "C",
    "gln": "Q",
    "glu": "E",
    "gly": "G",
    "his": "H",
    "ile": "I",
    "leu": "L",
    "lys": "K",
    "met": "M",
    "phe": "F",
    "pro": "P",
    "ser": "S",
    "thr": "T",
    "trp": "W",
    "tyr": "Y",
    "val": "V",
    "ter": "*",
}


@dataclass(frozen=True, slots=True)
class SentenceAnchor:
    """Location and match quality for one sentence in source text."""

    start: int | None
    end: int | None
    match_kind: GroundingMatchKind
    score: float


@dataclass(frozen=True, slots=True)
class ArgumentPresence:
    """Whether a relation's endpoints appear in an evidence sentence."""

    subject_present: bool
    object_present: bool


@dataclass(frozen=True, slots=True)
class EvidenceGroundingResult:
    """Grounding state for one extracted relation sentence."""

    anchor: SentenceAnchor
    subject_present: bool
    object_present: bool

    @property
    def grounded(self) -> bool:
        """Return whether the sentence is anchored and contains both endpoints."""

        return (
            self.anchor.match_kind != "none"
            and self.subject_present
            and self.object_present
        )

    def to_metadata(self) -> JSONObject:
        """Return JSON-safe metadata for proposal and graph validation."""

        return {
            "anchor_start": self.anchor.start,
            "anchor_end": self.anchor.end,
            "match_kind": self.anchor.match_kind,
            "score": self.anchor.score,
            "subject_present": self.subject_present,
            "object_present": self.object_present,
            "grounded": self.grounded,
        }


def anchor_sentence(
    *,
    source_text: str,
    sentence: str,
    fuzzy_threshold: float = _FUZZY_SENTENCE_THRESHOLD,
) -> SentenceAnchor:
    """Find a sentence in source text using exact, normalized, then fuzzy match."""

    if not sentence.strip():
        return SentenceAnchor(start=None, end=None, match_kind="none", score=0.0)

    exact_start = source_text.find(sentence)
    if exact_start >= 0:
        return SentenceAnchor(
            start=exact_start,
            end=exact_start + len(sentence),
            match_kind="exact",
            score=1.0,
        )

    whitespace_span = _whitespace_normalized_span(
        source_text=source_text,
        sentence=sentence,
    )
    if whitespace_span is not None:
        return SentenceAnchor(
            start=whitespace_span[0],
            end=whitespace_span[1],
            match_kind="whitespace_normalized",
            score=1.0,
        )

    best_score = 0.0
    best_span: tuple[int, int] | None = None
    normalized_sentence = _normalize_sentence(sentence)
    for start, end, source_sentence in _source_sentence_spans(source_text):
        score = SequenceMatcher(
            None,
            normalized_sentence,
            _normalize_sentence(source_sentence),
        ).ratio()
        if score > best_score:
            best_score = score
            best_span = (start, end)
    if best_span is not None and best_score >= fuzzy_threshold:
        return SentenceAnchor(
            start=best_span[0],
            end=best_span[1],
            match_kind="fuzzy",
            score=round(best_score, 4),
        )
    return SentenceAnchor(
        start=None,
        end=None,
        match_kind="none",
        score=round(best_score, 4),
    )


def args_present(*, sentence: str, subject: str, object_: str) -> ArgumentPresence:
    """Return whether subject and object labels are present in a sentence."""

    normalized_sentence = _normalize_argument_text(sentence)
    return ArgumentPresence(
        subject_present=_contains_any_alias(
            normalized_sentence=normalized_sentence,
            aliases=_argument_aliases(subject),
        ),
        object_present=_contains_any_alias(
            normalized_sentence=normalized_sentence,
            aliases=_argument_aliases(object_),
        ),
    )


def ground_relation_sentence(
    *,
    source_text: str,
    sentence: str,
    subject: str,
    object_: str,
) -> EvidenceGroundingResult:
    """Anchor a relation sentence and require both relation endpoints in it."""

    anchor = anchor_sentence(source_text=source_text, sentence=sentence)
    presence = args_present(sentence=sentence, subject=subject, object_=object_)
    return EvidenceGroundingResult(
        anchor=anchor,
        subject_present=presence.subject_present,
        object_present=presence.object_present,
    )


def _whitespace_normalized_span(
    *,
    source_text: str,
    sentence: str,
) -> tuple[int, int] | None:
    tokens = sentence.split()
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, source_text, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.start(), match.end()


def _source_sentence_spans(source_text: str) -> tuple[tuple[int, int, str], ...]:
    spans: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^.!?]+[.!?]?", source_text):
        text = match.group(0)
        if text.strip():
            spans.append((match.start(), match.end(), text))
    return tuple(spans)


def _normalize_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_any_alias(
    *,
    normalized_sentence: str,
    aliases: tuple[str, ...],
) -> bool:
    padded_sentence = f" {normalized_sentence} "
    return any(f" {alias} " in padded_sentence for alias in aliases if alias)


def _argument_aliases(label: str) -> tuple[str, ...]:
    aliases = {_normalize_argument_text(label)}
    protein_alias = _protein_alias(label)
    if protein_alias is not None:
        aliases.add(_normalize_argument_text(protein_alias))
        aliases.add(_normalize_argument_text(protein_alias.removesuffix("*")))
    return tuple(sorted(alias for alias in aliases if alias))


def _normalize_argument_text(value: str) -> str:
    normalized = value.casefold()
    normalized = normalized.replace("p.", " ")
    normalized = re.sub(r"[^a-z0-9*]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _protein_alias(label: str) -> str | None:
    match = re.search(
        r"p\.?\s*([A-Za-z]{3})(\d+)(\*|[A-Za-z]{3})",
        label,
    )
    if match is None:
        return None
    start = _THREE_TO_ONE_AMINO_ACID_CODES.get(match.group(1).casefold())
    end = match.group(3)
    end_code = (
        "*"
        if end == "*"
        else _THREE_TO_ONE_AMINO_ACID_CODES.get(end.casefold())
    )
    if start is None or end_code is None:
        return None
    return f"{start}{match.group(2)}{end_code}"


__all__ = [
    "ArgumentPresence",
    "EvidenceGroundingResult",
    "GroundingMatchKind",
    "SentenceAnchor",
    "anchor_sentence",
    "args_present",
    "ground_relation_sentence",
]
