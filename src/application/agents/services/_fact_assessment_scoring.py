"""Deterministic scoring helpers for qualitative fact assessments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import prod

from pydantic import ValidationError

from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
    assessment_priority,
    build_fact_assessment_from_confidence,
)
from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.json_utils import to_json_value

_SUPPORT_BAND_SCORES: dict[SupportBand, float] = {
    SupportBand.INSUFFICIENT: 0.2,
    SupportBand.TENTATIVE: 0.45,
    SupportBand.SUPPORTED: 0.7,
    SupportBand.STRONG: 0.9,
}

_GROUNDING_CAPS: dict[GroundingLevel, float] = {
    GroundingLevel.SPAN: 1.0,
    GroundingLevel.SECTION: 0.85,
    GroundingLevel.DOCUMENT: 0.7,
    GroundingLevel.GENERATED: 0.55,
    GroundingLevel.GRAPH_INFERENCE: 0.85,
}

_MAPPING_CAPS: dict[MappingStatus, float] = {
    MappingStatus.RESOLVED: 1.0,
    MappingStatus.AMBIGUOUS: 0.65,
    MappingStatus.NOT_APPLICABLE: 1.0,
}

_SPECULATION_CAPS: dict[SpeculationLevel, float] = {
    SpeculationLevel.DIRECT: 1.0,
    SpeculationLevel.HEDGED: 0.75,
    SpeculationLevel.HYPOTHETICAL: 0.55,
    SpeculationLevel.NOT_APPLICABLE: 1.0,
}


def _normalize_confidence_value(raw_value: object) -> float | None:
    if isinstance(raw_value, bool):
        return None
    if isinstance(raw_value, float | int):
        return max(0.0, min(float(raw_value), 1.0))
    return None


def _lookup_assessment_value(assessment: object, field_name: str) -> object | None:
    if isinstance(assessment, Mapping):
        value = assessment.get(field_name)
        return value if value is not None else None
    return getattr(assessment, field_name, None)


def _coerce_fact_assessment(fact: object) -> FactAssessment | None:
    raw_assessment = _lookup_assessment_value(fact, "assessment")
    if raw_assessment is not None:
        try:
            return FactAssessment.model_validate(raw_assessment)
        except ValidationError:
            if isinstance(raw_assessment, Mapping):
                mapping_assessment = {
                    str(key): to_json_value(value)
                    for key, value in raw_assessment.items()
                }
                return FactAssessment.model_validate(mapping_assessment)
            normalized_assessment: JSONObject = {
                "support_band": to_json_value(
                    _lookup_assessment_value(raw_assessment, "support_band"),
                ),
                "grounding_level": to_json_value(
                    _lookup_assessment_value(raw_assessment, "grounding_level"),
                ),
                "mapping_status": to_json_value(
                    _lookup_assessment_value(raw_assessment, "mapping_status"),
                ),
                "speculation_level": to_json_value(
                    _lookup_assessment_value(raw_assessment, "speculation_level"),
                ),
                "confidence_rationale": to_json_value(
                    _lookup_assessment_value(
                        raw_assessment,
                        "confidence_rationale",
                    ),
                ),
            }
            return FactAssessment.model_validate(normalized_assessment)

    confidence_value = _lookup_assessment_value(fact, "confidence")
    if confidence_value is None:
        confidence_value = _lookup_assessment_value(fact, "confidence_score")
    normalized_confidence = _normalize_confidence_value(confidence_value)
    if normalized_confidence is None:
        return None

    rationale = _lookup_assessment_value(fact, "confidence_rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        rationale = _lookup_assessment_value(fact, "rationale")
    normalized_rationale = (
        rationale.strip()
        if isinstance(rationale, str) and rationale.strip()
        else "Legacy numeric confidence fallback."
    )
    return build_fact_assessment_from_confidence(
        normalized_confidence,
        confidence_rationale=normalized_rationale,
        grounding_level=GroundingLevel.SPAN,
        mapping_status=MappingStatus.NOT_APPLICABLE,
        speculation_level=SpeculationLevel.NOT_APPLICABLE,
    )


def fact_assessment_payload(fact: object) -> JSONObject | None:
    assessment = _coerce_fact_assessment(fact)
    if assessment is None:
        return None
    payload: JSONObject = assessment.model_dump(mode="json")
    payload["derived_evidence_weight"] = fact_evidence_weight(fact)
    return payload


def fact_evidence_weight(fact: object) -> float:
    assessment = _coerce_fact_assessment(fact)
    if assessment is None:
        return 0.0
    support_score = _SUPPORT_BAND_SCORES[SupportBand(assessment.support_band)]
    grounding_score = _GROUNDING_CAPS[GroundingLevel(assessment.grounding_level)]
    mapping_score = _MAPPING_CAPS[MappingStatus(assessment.mapping_status)]
    speculation_score = _SPECULATION_CAPS[
        SpeculationLevel(assessment.speculation_level)
    ]
    return max(
        0.0,
        min(support_score, grounding_score, mapping_score, speculation_score),
    )


def aggregate_fact_evidence_weight(weights: Iterable[float]) -> float:
    normalized_weights = tuple(
        max(0.0, min(float(weight), 1.0))
        for weight in weights
        if not isinstance(weight, bool)
    )
    if not normalized_weights:
        return 0.0
    return 1.0 - prod(1.0 - weight for weight in normalized_weights)


def run_confidence_from_assessments(
    assessment_scores: Iterable[float],
) -> float:
    """Use the strongest structured fact and ignore raw numeric model scores."""
    normalized_assessment_scores = tuple(
        max(0.0, min(float(score), 1.0))
        for score in assessment_scores
        if not isinstance(score, bool)
    )
    positive_scores = tuple(
        score for score in normalized_assessment_scores if score > 0.0
    )
    if positive_scores:
        return max(positive_scores)
    return 0.0


def fact_assessment_priority(fact: object) -> tuple[int, int, int, int, float]:
    assessment = _coerce_fact_assessment(fact)
    if assessment is None:
        confidence_value = _lookup_assessment_value(fact, "confidence")
        if confidence_value is None:
            confidence_value = _lookup_assessment_value(fact, "confidence_score")
        normalized_confidence = _normalize_confidence_value(confidence_value) or 0.0
        return (0, 0, 0, 0, normalized_confidence)
    return (
        *assessment_priority(assessment),
        fact_evidence_weight(fact),
    )


__all__ = [
    "aggregate_fact_evidence_weight",
    "fact_assessment_payload",
    "fact_assessment_priority",
    "fact_evidence_weight",
    "run_confidence_from_assessments",
]
