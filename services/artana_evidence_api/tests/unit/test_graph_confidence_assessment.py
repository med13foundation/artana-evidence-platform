"""Regression tests for qualitative-first graph confidence contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.types.graph_contracts import (
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)
from pydantic import ValidationError

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The cited span directly supports the claim.",
}


def test_relation_create_confidence_is_derived_from_assessment() -> None:
    request = KernelRelationCreateRequest(
        source_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        target_id=uuid4(),
        assessment=_SUPPORTED_ASSESSMENT,
    )

    assert request.derived_confidence == 0.7


def test_relation_create_rejects_numeric_confidence_input() -> None:
    with pytest.raises(ValidationError):
        KernelRelationCreateRequest(
            source_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
            target_id=uuid4(),
            confidence=0.99,
            assessment=_SUPPORTED_ASSESSMENT,
        )


def test_claim_create_requires_qualitative_assessment() -> None:
    with pytest.raises(ValidationError):
        KernelRelationClaimCreateRequest(
            source_entity_id=uuid4(),
            target_entity_id=uuid4(),
            relation_type="ASSOCIATED_WITH",
        )
