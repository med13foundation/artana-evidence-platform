"""Adversarial tests for the graph-owned TG-03 persistence quarantine."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_db.graph_api_schemas.claim_graph_schemas import (
    ClaimRelationCreateRequest,
)
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)
from artana_evidence_db.validation.ai_persistence_quarantine import (
    GraphAIPersistenceQuarantinePolicy,
)

_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "The exact source sentence supports the relation.",
}
_POLICY = GraphAIPersistenceQuarantinePolicy()


def test_typed_agent_authorship_is_quarantined() -> None:
    request = _claim_request(authorship="AGENT")

    violation = _POLICY.violation_for_request(request)

    assert violation is not None
    assert violation.code == "qualified_claim_persistence_not_ready"


@pytest.mark.parametrize(
    ("metadata_key", "metadata_value"),
    [
        ("agent_run_id", "agent-1"),
        ("ai_provenance", {"model": "luna"}),
        ("artana_idempotency_key", "attempt-1"),
        ("extraction_agent_run_id", "agent-1"),
        ("harness_run_id", "harness-1"),
    ],
)
def test_each_legacy_ai_metadata_key_is_quarantined(
    metadata_key: str,
    metadata_value: object,
) -> None:
    request = _claim_request(metadata={metadata_key: metadata_value})

    assert _POLICY.violation_for_request(request) is not None


@pytest.mark.parametrize(
    ("metadata_field", "marker"),
    [
        ("authorship", "agent"),
        ("origin", "document_extraction"),
        ("source", "llm"),
        ("author_type", "ai"),
        ("created_by", "graph_harness"),
        ("created_by", "agent:workflow-creator"),
        ("created_by", "ai:review-service"),
    ],
)
def test_each_legacy_ai_marker_is_quarantined(
    metadata_field: str,
    marker: str,
) -> None:
    request = _claim_request(metadata={metadata_field: marker})

    assert _POLICY.violation_for_request(request) is not None


def test_production_document_extraction_shape_is_quarantined() -> None:
    request = _claim_request(
        evidence_sentence_source="verbatim_span",
        metadata={
            "origin": "document_extraction",
            "harness_run_id": "live-run-1",
        },
    )

    assert _POLICY.violation_for_request(request) is not None


def test_unknown_metadata_does_not_turn_a_manual_write_into_agent_authorship() -> None:
    request = _claim_request(
        metadata={"origin": "curator_import", "workflow_note": "reviewed"},
    )

    assert _POLICY.violation_for_request(request) is None


def test_typed_agent_canonical_relation_is_quarantined() -> None:
    request = KernelRelationCreateRequest(
        source_id=uuid4(),
        target_id=uuid4(),
        relation_type="ASSOCIATED_WITH",
        assessment=_ASSESSMENT,
        authorship="AGENT",
    )

    assert _POLICY.violation_for_request(request) is not None


def test_agent_claim_relation_is_quarantined() -> None:
    request = ClaimRelationCreateRequest(
        source_claim_id=uuid4(),
        target_claim_id=uuid4(),
        relation_type="SUPPORTS",
        assessment=_ASSESSMENT,
        agent_run_id="agent-1",
    )

    assert _POLICY.violation_for_request(request) is not None


def _claim_request(**overrides: object) -> KernelRelationClaimCreateRequest:
    payload: dict[str, object] = {
        "source_entity_id": uuid4(),
        "target_entity_id": uuid4(),
        "relation_type": "ASSOCIATED_WITH",
        "assessment": _ASSESSMENT,
    }
    payload.update(overrides)
    return KernelRelationClaimCreateRequest.model_validate(payload)
