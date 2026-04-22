"""Regression tests for DB-computed AI decision confidence."""

from __future__ import annotations

import pytest
from artana_evidence_db.common_types import JSONValue
from artana_evidence_db.decision_confidence import (
    DecisionConfidenceAssessment,
    score_decision_confidence,
)
from artana_evidence_db.graph_api_schemas.ai_full_mode_schemas import (
    AIDecisionSubmitRequest,
    GraphChangeClaimRequest,
)
from artana_evidence_db.graph_api_schemas.workflow_schemas import (
    GraphWorkflowActionRequest,
)
from pydantic import ValidationError

_STRONG_FACT_ASSESSMENT = {
    "support_band": "STRONG",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The cited span directly supports the decision.",
}
_SUPPORTED_FACT_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The cited span supports the claim.",
}


def _assessment(**overrides: JSONValue) -> DecisionConfidenceAssessment:
    payload: dict[str, JSONValue] = {
        "fact_assessment": _STRONG_FACT_ASSESSMENT,
        "validation_state": "VALID",
        "evidence_state": "ACCEPTED_DIRECT_EVIDENCE",
        "duplicate_conflict_state": "CLEAR",
        "source_reliability": "CURATED",
        "risk_tier": "low",
    }
    payload.update(overrides)
    return DecisionConfidenceAssessment.model_validate(payload)


def test_decision_confidence_scores_strong_direct_resolved_evidence() -> None:
    result = score_decision_confidence(_assessment())

    assert result.computed_confidence == pytest.approx(0.9)
    assert result.blocking_reasons == []
    assert result.human_review_reasons == []


def test_decision_confidence_caps_ambiguous_mapping() -> None:
    result = score_decision_confidence(
        _assessment(
            fact_assessment={
                **_STRONG_FACT_ASSESSMENT,
                "mapping_status": "AMBIGUOUS",
            },
        ),
    )

    assert result.computed_confidence == pytest.approx(0.65)


def test_decision_confidence_caps_generated_only_evidence() -> None:
    result = score_decision_confidence(
        _assessment(evidence_state="GENERATED_SUMMARY_ONLY"),
    )

    assert result.computed_confidence == pytest.approx(0.55)


def test_decision_confidence_blocks_missing_required_evidence() -> None:
    result = score_decision_confidence(
        _assessment(evidence_state="REQUIRED_EVIDENCE_MISSING"),
    )

    assert result.computed_confidence == 0.0
    assert result.blocking_reasons == ["required_evidence_missing"]


def test_decision_confidence_blocks_conflicting_claim() -> None:
    result = score_decision_confidence(
        _assessment(duplicate_conflict_state="CONFLICTING_CLAIM"),
    )

    assert result.computed_confidence == 0.0
    assert result.blocking_reasons == ["conflicting_claim"]


def test_workflow_action_rejects_raw_numeric_confidence() -> None:
    with pytest.raises(ValidationError):
        GraphWorkflowActionRequest(
            action="approve",
            confidence=0.99,
        )


def test_ai_full_mode_decision_rejects_raw_numeric_confidence() -> None:
    with pytest.raises(ValidationError):
        AIDecisionSubmitRequest(
            target_type="concept_proposal",
            target_id="11111111-1111-1111-1111-111111111111",
            action="APPROVE",
            ai_principal="agent:test",
            confidence=0.99,
            risk_tier="low",
            input_hash="a" * 64,
            evidence_payload={"source": "unit-test"},
            decision_payload={},
        )


def test_graph_change_claim_derives_confidence_from_assessment() -> None:
    request = GraphChangeClaimRequest(
        source_local_id="source",
        target_local_id="target",
        relation_type="ASSOCIATED_WITH",
        assessment=_SUPPORTED_FACT_ASSESSMENT,
    )

    assert request.derived_confidence == pytest.approx(0.7)
