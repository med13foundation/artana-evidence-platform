"""Regression tests for graph-service qualitative confidence contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_db.fact_assessment import FactAssessment, assessment_confidence
from artana_evidence_db.service_contracts import (
    ClaimRelationCreateRequest,
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)
from pydantic import ValidationError

_TENTATIVE_ASSESSMENT = {
    "support_band": "TENTATIVE",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The source text is indirect and should remain tentative.",
}


def test_relation_create_confidence_is_derived_from_assessment() -> None:
    request = KernelRelationCreateRequest(
        source_id=uuid4(),
        target_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        assessment=_TENTATIVE_ASSESSMENT,
    )

    assert request.derived_confidence == 0.45


def test_db_owned_fact_assessment_computes_expected_confidence() -> None:
    assessment = FactAssessment.model_validate(_TENTATIVE_ASSESSMENT)

    assert assessment_confidence(assessment) == 0.45


def test_relation_create_rejects_numeric_confidence_input() -> None:
    with pytest.raises(ValidationError):
        KernelRelationCreateRequest(
            source_id=uuid4(),
            target_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
            confidence=0.99,
            assessment=_TENTATIVE_ASSESSMENT,
        )


def test_claim_create_requires_assessment() -> None:
    with pytest.raises(ValidationError):
        KernelRelationClaimCreateRequest(
            source_entity_id=uuid4(),
            target_entity_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
        )


def test_claim_relation_create_requires_assessment() -> None:
    with pytest.raises(ValidationError):
        ClaimRelationCreateRequest(
            source_claim_id=uuid4(),
            target_claim_id=uuid4(),
            relation_type="SUPPORTS",
        )
