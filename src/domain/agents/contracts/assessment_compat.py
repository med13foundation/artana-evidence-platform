"""Compatibility helpers for qualitative agent assessments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, runtime_checkable

from pydantic import ValidationError

from src.domain.agents.contracts.fact_assessment import (
    FactAssessment,
    assessment_confidence_weight,
)
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TC001
from src.type_definitions.json_utils import to_json_value

_NUMERIC_CONFIDENCE_FIELDS = (
    "confidence_score",
    "confidence",
    "derived_confidence",
    "evidence_weight",
)

_BAND_SCORE_BY_TOKEN: dict[str, float] = {
    "STRONG": 0.9,
    "HIGH": 0.9,
    "SUPPORTED": 0.7,
    "MEDIUM": 0.65,
    "TENTATIVE": 0.45,
    "LOW": 0.35,
    "INSUFFICIENT": 0.1,
    "RESOLVED": 0.9,
    "MATCHED": 0.9,
    "AMBIGUOUS": 0.35,
    "NO_MATCH": 0.05,
    "REJECTED": 0.05,
}

_BOUNDARY_QUALITY_CAPS: dict[str, float] = {
    "CLEAN": 1.0,
    "EXACT": 1.0,
    "PRECISE": 1.0,
    "CLEAR": 1.0,
    "BORDERLINE": 0.8,
    "PARTIAL": 0.8,
    "FUZZY": 0.7,
    "UNCLEAR": 0.7,
    "NOISY": 0.6,
    "POOR": 0.6,
}

_NORMALIZATION_STATUS_CAPS: dict[str, float] = {
    "RESOLVED": 1.0,
    "NORMALIZED": 1.0,
    "PARTIAL": 0.85,
    "AMENDED": 0.85,
    "AMBIGUOUS": 0.75,
    "UNRESOLVED": 0.65,
    "FAILED": 0.55,
}

_AMBIGUITY_STATUS_CAPS: dict[str, float] = {
    "NONE": 1.0,
    "CLEAR": 1.0,
    "UNAMBIGUOUS": 1.0,
    "RESOLVED": 1.0,
    "LOW": 0.85,
    "MILD": 0.85,
    "SOME": 0.85,
    "MEDIUM": 0.7,
    "HIGH": 0.65,
    "AMBIGUOUS": 0.65,
    "CONFLICTING": 0.6,
}


@runtime_checkable
class _SupportsModelDump(Protocol):
    def model_dump(self, *, mode: str = "python") -> object: ...


def _model_dump_json(value: object) -> object | None:
    if not isinstance(value, _SupportsModelDump):
        return None
    return value.model_dump(mode="json")


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    dumped = _model_dump_json(value)
    if dumped is not None and isinstance(dumped, Mapping):
        return dumped
    if hasattr(value, "__dict__"):
        return {str(key): getattr(value, key) for key in vars(value)}
    return None


def _lookup_value(value: object, field_name: str) -> object | None:
    mapping = _as_mapping(value)
    if mapping is not None and field_name in mapping:
        return mapping[field_name]
    return None


def _normalize_numeric(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, float | int):
        return max(0.0, min(float(value), 1.0))
    return None


def _normalize_token(value: object) -> str | None:
    raw_value = getattr(value, "value", value)
    if isinstance(raw_value, str):
        normalized = raw_value.strip().upper()
        return normalized or None
    if isinstance(value, bool):
        return None
    if isinstance(raw_value, float | int):
        return str(raw_value).strip().upper()
    return None


def assessment_payload(value: object) -> JSONObject | None:
    """Return a JSON-safe assessment payload when the object carries one."""
    assessment = _lookup_value(value, "assessment")
    if assessment is None:
        return None
    return _json_safe_object(assessment)


def confidence_from_assessment(assessment: object) -> float:
    """Derive a deterministic confidence score from a qualitative assessment."""
    fact_assessment = _coerce_fact_assessment(assessment)
    if fact_assessment is not None:
        return assessment_confidence_weight(fact_assessment)

    base_score = _band_score_for_assessment(assessment)
    if base_score is not None:
        caps = [base_score]
        boundary_cap = _cap_from_lookup(
            assessment,
            "boundary_quality",
            _BOUNDARY_QUALITY_CAPS,
        )
        if boundary_cap is not None:
            caps.append(boundary_cap)

        normalization_cap = _cap_from_lookup(
            assessment,
            "normalization_status",
            _NORMALIZATION_STATUS_CAPS,
        )
        if normalization_cap is not None:
            caps.append(normalization_cap)

        ambiguity_cap = _cap_from_lookup(
            assessment,
            "ambiguity_status",
            _AMBIGUITY_STATUS_CAPS,
        )
        if ambiguity_cap is not None:
            caps.append(ambiguity_cap)

        return max(0.0, min(caps))

    direct_confidence = _first_numeric_value(
        assessment,
        _NUMERIC_CONFIDENCE_FIELDS,
    )
    if direct_confidence is not None:
        return direct_confidence
    return 0.0


def _coerce_fact_assessment(value: object) -> FactAssessment | None:
    mapping = _as_mapping(value)
    if mapping is None:
        return None

    required_fields = (
        "support_band",
        "grounding_level",
        "mapping_status",
        "speculation_level",
        "confidence_rationale",
    )
    if not all(field_name in mapping for field_name in required_fields):
        return None

    try:
        return FactAssessment.model_validate(mapping)
    except ValidationError:
        return None


def confidence_from_item(item: object) -> float:
    """Derive confidence for one candidate item."""
    assessment = _lookup_value(item, "assessment")
    if assessment is not None:
        derived = confidence_from_assessment(assessment)
        if derived > 0.0:
            return derived

    direct_confidence = _first_numeric_value(
        item,
        _NUMERIC_CONFIDENCE_FIELDS,
    )
    if direct_confidence is not None:
        return direct_confidence

    similarity_score = _normalize_numeric(_lookup_value(item, "similarity_score"))
    if similarity_score is not None:
        return similarity_score

    return 0.0


def aggregate_confidence_scores(scores: Iterable[float]) -> float:
    """Use the strongest structured confidence instead of saturating many items."""
    positive_scores = tuple(
        max(0.0, min(float(score), 1.0))
        for score in scores
        if not isinstance(score, bool) and float(score) > 0.0
    )
    if not positive_scores:
        return 0.0
    return max(positive_scores)


def confidence_from_entity_recognition_contract(contract: object) -> float:
    """Derive run-level confidence for entity-recognition outcomes."""
    assessment = _lookup_value(contract, "assessment")
    if assessment is not None:
        derived = confidence_from_assessment(assessment)
        if derived > 0.0:
            return derived

    aggregate_score = aggregate_confidence_scores(
        confidence_from_item(item)
        for field_name in ("recognized_entities", "recognized_observations")
        for item in _iter_items(_lookup_value(contract, field_name))
    )
    if aggregate_score > 0.0:
        return aggregate_score
    return 0.0


def confidence_from_mapping_judge_contract(contract: object) -> float:
    """Derive run-level confidence for mapping-judge outcomes."""
    assessment = _lookup_value(contract, "assessment")
    if assessment is not None:
        derived = confidence_from_assessment(assessment)
        if derived > 0.0:
            return derived

    selected_candidate = _lookup_value(contract, "selected_candidate")
    if selected_candidate is not None:
        selected_confidence = confidence_from_item(selected_candidate)
        if selected_confidence > 0.0:
            return selected_confidence

    candidate_scores = [
        confidence_from_item(candidate)
        for candidate in _iter_items(_lookup_value(contract, "candidates"))
    ]
    positive_scores = [score for score in candidate_scores if score > 0.0]
    if positive_scores:
        return max(positive_scores)
    direct_confidence = _first_numeric_value(
        contract,
        _NUMERIC_CONFIDENCE_FIELDS,
    )
    if direct_confidence is not None and direct_confidence > 0.0:
        return direct_confidence
    return direct_confidence or 0.0


def confidence_from_extraction_contract(contract: object) -> float:
    """Derive run-level confidence for extraction outcomes."""
    aggregate_score = aggregate_confidence_scores(
        confidence_from_item(item)
        for field_name in ("entities", "observations", "relations")
        for item in _iter_items(_lookup_value(contract, field_name))
    )
    if aggregate_score > 0.0:
        return aggregate_score
    return 0.0


def confidence_from_graph_connection_contract(contract: object) -> float:
    """Derive run-level confidence for graph-connection outcomes."""
    aggregate_score = aggregate_confidence_scores(
        confidence_from_item(item)
        for field_name in ("proposed_relations", "rejected_candidates")
        for item in _iter_items(_lookup_value(contract, field_name))
    )
    if aggregate_score > 0.0:
        return aggregate_score
    return 0.0


def _first_numeric_value(value: object, field_names: tuple[str, ...]) -> float | None:
    for field_name in field_names:
        field_value = _lookup_value(value, field_name)
        normalized = _normalize_numeric(field_value)
        if normalized is not None:
            return normalized
    return None


def _band_score_for_assessment(assessment: object) -> float | None:
    for field_name in (
        "support_band",
        "recognition_band",
        "resolution_status",
        "decision_band",
    ):
        token = _normalize_token(_lookup_value(assessment, field_name))
        if token is None:
            continue
        if token in _BAND_SCORE_BY_TOKEN:
            return _BAND_SCORE_BY_TOKEN[token]
    return None


def _cap_from_lookup(
    value: object,
    field_name: str,
    caps: dict[str, float],
) -> float | None:
    token = _normalize_token(_lookup_value(value, field_name))
    if token is None:
        return None
    if token in caps:
        return caps[token]
    return None


def _iter_items(value: object | None) -> Iterable[object]:
    if value is None:
        return ()
    if isinstance(value, list | tuple | set | frozenset):
        return tuple(value)
    return ()


def _json_safe_object(value: object) -> JSONObject | None:
    mapping = _as_mapping(value)
    if mapping is None:
        return None
    return {str(key): _json_safe_value(item) for key, item in mapping.items()}


def _json_safe_value(value: object) -> JSONValue:
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    dumped = _model_dump_json(value)
    if dumped is not None:
        if isinstance(dumped, Mapping):
            return {str(key): _json_safe_value(item) for key, item in dumped.items()}
        return to_json_value(dumped)
    if hasattr(value, "__dict__"):
        return {str(key): _json_safe_value(getattr(value, key)) for key in vars(value)}
    if isinstance(value, list | tuple | set | frozenset):
        return [_json_safe_value(item) for item in value]
    return to_json_value(value)


__all__ = [
    "aggregate_confidence_scores",
    "assessment_payload",
    "confidence_from_assessment",
    "confidence_from_entity_recognition_contract",
    "confidence_from_extraction_contract",
    "confidence_from_graph_connection_contract",
    "confidence_from_item",
    "confidence_from_mapping_judge_contract",
]
