"""Fail-closed evidence support verification for extracted triples."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from artana_evidence_api.document_extraction_support.evidence_grounding import (
    args_present,
)
from artana_evidence_api.types.common import JSONObject

TripleSupport = Literal["ENTAILS", "NEUTRAL", "CONTRADICTS"]
_MODEL_ID = "artana-heuristic-support-v1"


@dataclass(frozen=True, slots=True)
class TripleSupportResult:
    """Support verification result for one candidate triple and sentence."""

    support: TripleSupport
    rationale: str
    model_id: str | None = None

    def to_metadata(self) -> JSONObject:
        """Return JSON-safe support verification metadata."""

        return {
            "support": self.support,
            "rationale": self.rationale,
            "model_id": self.model_id,
        }


class TripleSupportModel(Protocol):
    """Port for model-backed triple support verification."""

    model_id: str

    def verify(
        self,
        *,
        sentence: str,
        subject: str,
        relation_type: str,
        object_: str,
    ) -> TripleSupportResult:
        """Return support verification for one candidate triple."""


def verify_triple_support(
    *,
    sentence: str,
    subject: str,
    relation_type: str,
    object_: str,
    model: TripleSupportModel | None = None,
) -> TripleSupportResult:
    """Verify whether a sentence supports, contradicts, or misses a triple."""

    if model is not None:
        try:
            return model.verify(
                sentence=sentence,
                subject=subject,
                relation_type=relation_type,
                object_=object_,
            )
        except Exception as exc:  # noqa: BLE001
            return TripleSupportResult(
                support="NEUTRAL",
                rationale=f"Support verifier failed closed: {exc}",
                model_id=model.model_id,
            )
    return _heuristic_support(
        sentence=sentence,
        subject=subject,
        relation_type=relation_type,
        object_=object_,
    )


def _heuristic_support(
    *,
    sentence: str,
    subject: str,
    relation_type: str,
    object_: str,
) -> TripleSupportResult:
    presence = args_present(sentence=sentence, subject=subject, object_=object_)
    if not presence.subject_present or not presence.object_present:
        return TripleSupportResult(
            support="NEUTRAL",
            rationale="Sentence does not contain both relation endpoints.",
            model_id=_MODEL_ID,
        )
    normalized_sentence = _normalize_text(sentence)
    cues = _relation_cues(relation_type)
    normalized_relation_type = _normalized_relation_type(relation_type)
    if _has_negated_relation_support(
        sentence=normalized_sentence,
        subject=subject,
        object_=object_,
        normalized_relation_type=normalized_relation_type,
        cues=cues,
    ):
        return TripleSupportResult(
            support="CONTRADICTS",
            rationale=(
                "Sentence negates a correctly oriented relation cue for the "
                "candidate triple."
            ),
            model_id=_MODEL_ID,
        )
    if _has_entailing_relation_support(
        sentence=normalized_sentence,
        subject=subject,
        object_=object_,
        normalized_relation_type=normalized_relation_type,
        cues=cues,
    ):
        return TripleSupportResult(
            support="ENTAILS",
            rationale=(
                "Sentence contains both endpoints in a relation-supported "
                "orientation."
            ),
            model_id=_MODEL_ID,
        )
    return TripleSupportResult(
        support="NEUTRAL",
        rationale="Sentence contains both endpoints but no relation cue.",
        model_id=_MODEL_ID,
    )


def _relation_cues(relation_type: str) -> tuple[str, ...]:
    normalized = _normalized_relation_type(relation_type)
    cues = _RELATION_CUES.get(normalized)
    if cues is not None:
        return cues
    return tuple(
        token.casefold()
        for token in normalized.split("_")
        if len(token) >= _MIN_FALLBACK_CUE_LENGTH
    )


def _has_negated_relation_support(
    *,
    sentence: str,
    subject: str,
    object_: str,
    normalized_relation_type: str,
    cues: tuple[str, ...],
) -> bool:
    return any(
        _is_negated_cue(sentence=sentence, cue=cue)
        and _has_oriented_relation_support(
            sentence=sentence,
            subject=subject,
            object_=object_,
            normalized_relation_type=normalized_relation_type,
            cue=cue,
        )
        for cue in cues
    )


def _has_entailing_relation_support(
    *,
    sentence: str,
    subject: str,
    object_: str,
    normalized_relation_type: str,
    cues: tuple[str, ...],
) -> bool:
    return any(
        not _is_negated_cue(sentence=sentence, cue=cue)
        and _has_oriented_relation_support(
            sentence=sentence,
            subject=subject,
            object_=object_,
            normalized_relation_type=normalized_relation_type,
            cue=cue,
        )
        for cue in cues
    )


def _has_oriented_relation_support(
    *,
    sentence: str,
    subject: str,
    object_: str,
    normalized_relation_type: str,
    cue: str,
) -> bool:
    subject_spans = _phrase_spans(sentence, _normalize_text(subject))
    object_spans = _phrase_spans(sentence, _normalize_text(object_))
    cue_spans = _phrase_spans(sentence, cue)
    if normalized_relation_type in _SYMMETRIC_RELATION_TYPES:
        return any(
            _span_between(
                cue_span=cue_span,
                left_span=subject_span,
                right_span=object_span,
            )
            or _span_between(
                cue_span=cue_span,
                left_span=object_span,
                right_span=subject_span,
            )
            for subject_span in subject_spans
            for object_span in object_spans
            for cue_span in cue_spans
        )
    passive_cues = _PASSIVE_CUES_BY_RELATION.get(normalized_relation_type, ())
    return any(
        (
            cue not in passive_cues
            and not _cue_span_is_passive_context(sentence=sentence, cue_span=cue_span)
            and _span_before(
                left_span=subject_span,
                middle_span=cue_span,
                right_span=object_span,
            )
        )
        or (
            cue in passive_cues
            and _span_before(
                left_span=object_span,
                middle_span=cue_span,
                right_span=subject_span,
            )
        )
        for subject_span in subject_spans
        for object_span in object_spans
        for cue_span in cue_spans
    )


def _cue_span_is_passive_context(
    *,
    sentence: str,
    cue_span: tuple[int, int],
) -> bool:
    return sentence[cue_span[1] :].lstrip().startswith("by ")


def _is_negated_cue(*, sentence: str, cue: str) -> bool:
    return any(
        re.search(pattern.format(cue=re.escape(cue)), sentence) is not None
        for pattern in _NEGATED_CUE_PATTERNS
    )


def _phrase_spans(sentence: str, phrase: str) -> tuple[tuple[int, int], ...]:
    if not phrase:
        return ()
    prefix_boundary = r"(?<![a-z0-9])" if phrase[0].isalnum() else ""
    suffix_boundary = r"(?![a-z0-9])" if phrase[-1].isalnum() else ""
    pattern = f"{prefix_boundary}{re.escape(phrase)}{suffix_boundary}"
    return tuple(
        (match.start(), match.end())
        for match in re.finditer(pattern, sentence)
    )


def _span_before(
    *,
    left_span: tuple[int, int],
    middle_span: tuple[int, int],
    right_span: tuple[int, int],
) -> bool:
    return left_span[0] < middle_span[0] and middle_span[1] <= right_span[0]


def _span_between(
    *,
    cue_span: tuple[int, int],
    left_span: tuple[int, int],
    right_span: tuple[int, int],
) -> bool:
    return left_span[0] < cue_span[0] and cue_span[1] <= right_span[0]


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9*]+", " ", value.casefold())
    return re.sub(r"\s+", " ", normalized).strip()


def _normalized_relation_type(relation_type: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", relation_type.upper()).strip("_")


_MIN_FALLBACK_CUE_LENGTH = 4
_NEGATED_CUE_PATTERNS = (
    r"\b(?:does not|do not|did not|not|never)\s+{cue}\b",
    r"\b(?:fails to|failed to|failure to)\s+{cue}\b",
    r"\bwithout\s+{cue}\b",
)
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


__all__ = [
    "TripleSupport",
    "TripleSupportModel",
    "TripleSupportResult",
    "verify_triple_support",
]
