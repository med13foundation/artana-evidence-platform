"""Service-local helpers for shared fact-assessment contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Protocol, TypeGuard

from artana_evidence_api.types.common import JSONObject, JSONValue
from artana_evidence_api.types.graph_fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
    build_fact_assessment_from_confidence,
)
from pydantic import ValidationError

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


class DataclassInstance(Protocol):
    """Protocol describing dataclass instances for type narrowing."""

    __dataclass_fields__: dict[str, object]


def _is_dataclass_instance(value: object) -> TypeGuard[DataclassInstance]:
    """Type guard ensuring value is a dataclass instance."""
    return is_dataclass(value)


def to_json_value(value: object) -> JSONValue:
    """Convert arbitrary Python objects into a JSONValue structure."""
    result: JSONValue
    if value is None or isinstance(value, str | int | float | bool):
        result = value
    elif isinstance(value, datetime | date):
        result = value.isoformat()
    elif isinstance(value, Enum):
        enum_value = value.value
        if isinstance(enum_value, str | int | float | bool):
            result = enum_value
        else:
            result = str(enum_value)
    elif _is_dataclass_instance(value):
        dataclass_dict = asdict(value)  # type: ignore[call-overload]
        result = {key: to_json_value(item) for key, item in dataclass_dict.items()}
    elif isinstance(value, dict):
        result = {str(key): to_json_value(item) for key, item in value.items()}
    elif isinstance(value, list | tuple | set):
        result = [to_json_value(item) for item in value]
    else:
        result = str(value)
    return result


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
    """Serialize one structured fact assessment for metadata payloads."""
    assessment = _coerce_fact_assessment(fact)
    if assessment is None:
        return None
    payload: JSONObject = assessment.model_dump(mode="json")
    payload["derived_evidence_weight"] = fact_evidence_weight(fact)
    return payload


def fact_evidence_weight(fact: object) -> float:
    """Derive a deterministic evidence weight from one fact assessment."""
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


__all__ = [
    "fact_assessment_payload",
    "fact_evidence_weight",
    "to_json_value",
]
