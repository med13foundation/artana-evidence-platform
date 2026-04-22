"""Graph-service helpers for qualitative confidence assessment."""

from __future__ import annotations

from artana_evidence_db.common_types import JSONObject

from artana_evidence_db.fact_assessment import (
    FactAssessment,
    assessment_confidence,
)


def fact_assessment_payload(assessment: FactAssessment) -> JSONObject:
    """Serialize one qualitative fact assessment for graph metadata."""
    return {
        "support_band": str(assessment.support_band),
        "grounding_level": str(assessment.grounding_level),
        "mapping_status": str(assessment.mapping_status),
        "speculation_level": str(assessment.speculation_level),
        "confidence_rationale": assessment.confidence_rationale,
    }


def fact_assessment_metadata(assessment: FactAssessment) -> JSONObject:
    """Return the metadata block proving confidence was backend-derived."""
    return {
        "assessment": fact_assessment_payload(assessment),
        "confidence_derivation": {
            "method": "qualitative_assessment_v1",
            "derived_confidence": assessment_confidence(assessment),
        },
    }


__all__ = ["fact_assessment_metadata", "fact_assessment_payload"]
