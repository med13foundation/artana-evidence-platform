"""Regression tests for the graph harness tool registry."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from artana.ports.tool import ToolExecutionContext
from artana_evidence_api import tool_registry
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.tool_catalog import visible_tool_names_for_harness
from artana_evidence_api.tool_registry import (
    build_graph_harness_tool_registry,
    get_graph_document,
    list_graph_claims,
    propose_connector_metadata,
    propose_graph_change,
    propose_graph_concept,
    submit_ai_full_mode_decision,
    suggest_relations,
)
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    AIDecisionResponse,
    AIDecisionSubmitRequest,
    ConceptProposalResponse,
    ConnectorProposalResponse,
    DecisionConfidenceAssessment,
    GraphChangeProposalResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentMeta,
    KernelGraphDocumentResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionSkippedSourceResponse,
)

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic tool evidence supports this graph write.",
}
_STRONG_ASSESSMENT = {
    "support_band": "STRONG",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic tool evidence strongly supports this decision.",
}
_DECISION_CONFIDENCE_ASSESSMENT = {
    "fact_assessment": _STRONG_ASSESSMENT,
    "validation_state": "VALID",
    "evidence_state": "ACCEPTED_DIRECT_EVIDENCE",
    "duplicate_conflict_state": "CLEAR",
    "source_reliability": "CURATED",
    "risk_tier": "low",
    "rationale": "Tool-registry deterministic decision assessment.",
}


def test_build_graph_harness_tool_registry_resolves_runtime_type_hints() -> None:
    """Registry construction should succeed when tool signatures use date hints."""
    registry = build_graph_harness_tool_registry()

    assert registry is not None


def test_scoped_graph_gateway_uses_explicit_service_admin_context() -> None:
    gateway = tool_registry._scoped_graph_gateway()
    try:
        assert gateway.call_context.graph_admin is True
        assert gateway.call_context.role == "researcher"
    finally:
        gateway.close()


def test_ai_full_mode_tools_visible_for_ai_harnesses() -> None:
    expected_tools = {
        "propose_graph_concept",
        "propose_graph_change",
        "submit_ai_full_mode_decision",
        "propose_connector_metadata",
    }

    for harness_id in ("full-ai-orchestrator", "continuous-learning", "supervisor"):
        assert expected_tools.issubset(visible_tool_names_for_harness(harness_id))


def test_ai_full_mode_tool_functions_call_governed_graph_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)

    class _FakeGateway:
        def __init__(self) -> None:
            self.closed = False
            self.concept_request = None
            self.graph_change_request = None
            self.decision_request = None
            self.connector_request = None

        def propose_concept(
            self,
            *,
            space_id: str,
            request: object,
        ) -> ConceptProposalResponse:
            del space_id
            self.concept_request = request
            return ConceptProposalResponse(
                id=str(uuid4()),
                research_space_id=str(uuid4()),
                status="SUBMITTED",
                candidate_decision="CREATE_NEW",
                domain_context="general",
                entity_type="PHENOTYPE",
                canonical_label="Astrocyte activation",
                normalized_label="astrocyte activation",
                concept_set_id=None,
                existing_concept_member_id=None,
                applied_concept_member_id=None,
                synonyms_payload=["Reactive astrocytes"],
                external_refs_payload=[],
                evidence_payload={"source": "test"},
                duplicate_checks_payload={},
                warnings_payload=[],
                decision_payload={},
                rationale="Useful missing concept.",
                proposed_by="manual:test",
                reviewed_by=None,
                reviewed_at=None,
                decision_reason=None,
                source_ref=request.source_ref,
                proposal_hash="a" * 64,
                created_at=now,
                updated_at=now,
            )

        def propose_graph_change(
            self,
            *,
            space_id: str,
            request: object,
        ) -> GraphChangeProposalResponse:
            del space_id
            self.graph_change_request = request
            return GraphChangeProposalResponse(
                id=str(uuid4()),
                research_space_id=str(uuid4()),
                status="READY_FOR_REVIEW",
                proposal_payload={"concepts": []},
                resolution_plan_payload={"steps": []},
                warnings_payload=[],
                error_payload=[],
                applied_concept_member_ids_payload=[],
                applied_claim_ids_payload=[],
                proposed_by="manual:test",
                reviewed_by=None,
                reviewed_at=None,
                decision_reason=None,
                source_ref=request.source_ref,
                proposal_hash="b" * 64,
                created_at=now,
                updated_at=now,
            )

        def submit_ai_decision(
            self,
            *,
            space_id: str,
            request: AIDecisionSubmitRequest,
        ) -> AIDecisionResponse:
            del space_id
            self.decision_request = request
            return AIDecisionResponse(
                id=str(uuid4()),
                research_space_id=str(uuid4()),
                target_type=request.target_type,
                target_id=str(request.target_id),
                action=request.action,
                status="APPLIED",
                ai_principal=request.ai_principal,
                confidence=0.9,
                computed_confidence=0.9,
                confidence_assessment_payload=cast(
                    "JSONObject",
                    request.confidence_assessment.model_dump(mode="json"),
                ),
                confidence_model_version="decision_confidence_v1",
                risk_tier=request.risk_tier,
                input_hash=request.input_hash,
                policy_outcome="ai_allowed_when_low_risk",
                evidence_payload=request.evidence_payload,
                decision_payload=request.decision_payload,
                rejection_reason=None,
                created_by="manual:test",
                applied_at=now,
                created_at=now,
                updated_at=now,
            )

        def propose_connector_metadata(
            self,
            *,
            space_id: str,
            request: object,
        ) -> ConnectorProposalResponse:
            del space_id
            self.connector_request = request
            return ConnectorProposalResponse(
                id=str(uuid4()),
                research_space_id=str(uuid4()),
                status="SUBMITTED",
                connector_slug=request.connector_slug,
                display_name=request.display_name,
                connector_kind=request.connector_kind,
                domain_context=request.domain_context,
                metadata_payload=request.metadata_payload,
                mapping_payload=request.mapping_payload,
                validation_payload={"valid": True},
                approval_payload={},
                rationale=request.rationale,
                evidence_payload=request.evidence_payload,
                proposed_by="manual:test",
                reviewed_by=None,
                reviewed_at=None,
                decision_reason=None,
                source_ref=request.source_ref,
                created_at=now,
                updated_at=now,
            )

        def close(self) -> None:
            self.closed = True

    gateway = _FakeGateway()

    class _FakeSubmissionService:
        def __init__(self) -> None:
            self.concept_call_context = None
            self.graph_change_call_context = None

        def propose_concept(
            self,
            *,
            space_id: str,
            request: object,
            call_context: object,
            idempotency_key: str | None = None,
        ) -> ConceptProposalResponse:
            del idempotency_key
            self.concept_call_context = call_context
            return gateway.propose_concept(space_id=space_id, request=request)

        def propose_graph_change(
            self,
            *,
            space_id: str,
            request: object,
            call_context: object,
            idempotency_key: str | None = None,
        ) -> GraphChangeProposalResponse:
            del idempotency_key
            self.graph_change_call_context = call_context
            return gateway.propose_graph_change(space_id=space_id, request=request)

        def submit_ai_decision(
            self,
            *,
            space_id: str,
            request: AIDecisionSubmitRequest,
            request_id: str | None = None,
        ) -> AIDecisionResponse:
            del request_id
            return gateway.submit_ai_decision(space_id=space_id, request=request)

    submission_service = _FakeSubmissionService()
    monkeypatch.setattr(
        tool_registry,
        "_graph_submission_service",
        lambda: submission_service,
    )
    monkeypatch.setattr(
        tool_registry, "_scoped_graph_gateway", lambda **kwargs: gateway
    )
    context = ToolExecutionContext(
        run_id="run-ai-full-mode-test",
        tenant_id="tenant-test",
        idempotency_key="idem-test",
        request_event_id=None,
        tool_version="1.0.0",
        schema_version="1",
    )
    space_id = str(uuid4())
    target_id = str(uuid4())

    concept_result = json.loads(
        asyncio.run(
            propose_graph_concept(
                space_id=space_id,
                entity_type="PHENOTYPE",
                canonical_label="Astrocyte activation",
                synonyms=["Reactive astrocytes"],
                evidence_payload={"source": "unit-test"},
                rationale="Useful missing concept.",
                artana_context=context,
            ),
        ),
    )
    graph_change_result = json.loads(
        asyncio.run(
            propose_graph_change(
                space_id=space_id,
                concepts=[
                    tool_registry.GraphChangeConceptToolArgs(
                        local_id="concept-1",
                        entity_type="PHENOTYPE",
                        canonical_label="Astrocyte activation",
                    ),
                ],
                claims=[
                    tool_registry.GraphChangeClaimToolArgs(
                        source_local_id="concept-1",
                        target_local_id="concept-1",
                        relation_type="ASSOCIATED_WITH",
                        assessment=_SUPPORTED_ASSESSMENT,
                    ),
                ],
                artana_context=context,
            ),
        ),
    )
    decision_result = json.loads(
        asyncio.run(
            submit_ai_full_mode_decision(
                space_id=space_id,
                target_type="concept_proposal",
                target_id=target_id,
                action="APPROVE",
                ai_principal="agent:test",
                confidence_assessment=DecisionConfidenceAssessment.model_validate(
                    _DECISION_CONFIDENCE_ASSESSMENT,
                ),
                risk_tier="low",
                input_hash="c" * 64,
                evidence_payload={"source": "unit-test"},
                artana_context=context,
            ),
        ),
    )
    connector_result = json.loads(
        asyncio.run(
            propose_connector_metadata(
                space_id=space_id,
                connector_slug="pubmed-test",
                display_name="PubMed Test",
                connector_kind="document_source",
                domain_context="genomics",
                mapping_payload={"field_mappings": []},
                evidence_payload={"source": "unit-test"},
                artana_context=context,
            ),
        ),
    )

    assert gateway.concept_request is not None
    assert gateway.concept_request.source_ref == (
        "artana-tool:run-ai-full-mode-test:concept:idem-test"
    )
    assert gateway.concept_request.evidence_payload["artana_run_id"] == (
        "run-ai-full-mode-test"
    )
    assert concept_result["proposal_hash"] == "a" * 64
    assert gateway.graph_change_request is not None
    assert gateway.graph_change_request.source_ref == (
        "artana-tool:run-ai-full-mode-test:graph-change:idem-test"
    )
    assert graph_change_result["proposal_hash"] == "b" * 64
    assert submission_service.concept_call_context is not None
    assert submission_service.concept_call_context.graph_admin is True
    assert submission_service.concept_call_context.role == "curator"
    assert submission_service.graph_change_call_context is not None
    assert submission_service.graph_change_call_context.graph_admin is True
    assert submission_service.graph_change_call_context.role == "curator"
    assert gateway.decision_request is not None
    assert gateway.decision_request.target_id == UUID(target_id)
    assert gateway.decision_request.evidence_payload["artana_run_id"] == (
        "run-ai-full-mode-test"
    )
    assert decision_result["status"] == "APPLIED"
    assert gateway.connector_request is not None
    assert gateway.connector_request.source_ref == (
        "artana-tool:run-ai-full-mode-test:connector:idem-test"
    )
    assert connector_result["connector_slug"] == "pubmed-test"
    assert gateway.closed is True


def test_list_graph_claims_normalizes_nullish_claim_status(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tool execution should treat string nulls like omitted optional status filters."""

    class _FakeGateway:
        def __init__(self) -> None:
            self.claim_status: str | None = "unset"
            self.closed = False

        def list_claims(
            self,
            *,
            space_id: str,
            claim_status: str | None = None,
            offset: int = 0,
            limit: int = 50,
        ) -> SimpleNamespace:
            del space_id, offset, limit
            self.claim_status = claim_status
            return SimpleNamespace(
                model_dump=lambda **kwargs: {
                    "claims": [],
                    "total": 0,
                    "offset": 0,
                    "limit": 50,
                },
            )

        def close(self) -> None:
            self.closed = True

    gateway = _FakeGateway()
    monkeypatch.setattr(
        tool_registry, "_scoped_graph_gateway", lambda **kwargs: gateway
    )

    with caplog.at_level("WARNING"):
        result = asyncio.run(
            list_graph_claims(
                space_id=str(uuid4()),
                claim_status=" null ",
                limit=25,
            ),
        )

    assert gateway.claim_status is None
    assert gateway.closed is True
    assert json.loads(result)["claims"] == []
    assert any(
        record.message == "Normalized nullish graph tool argument"
        and getattr(record, "tool_name", "") == "list_graph_claims"
        and getattr(record, "field_name", "") == "claim_status"
        for record in caplog.records
    )


def test_suggest_relations_filters_nullish_optional_lists(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Suggestion tool should sanitize nullish list values before graph requests."""

    class _FakeGateway:
        def __init__(self) -> None:
            self.request = None
            self.closed = False

        def suggest_relations(
            self,
            *,
            space_id: str,
            request: object,
        ) -> KernelRelationSuggestionListResponse:
            del space_id
            self.request = request
            return KernelRelationSuggestionListResponse(
                suggestions=[],
                total=0,
                limit_per_source=5,
                min_score=0.0,
                incomplete=True,
                skipped_sources=[
                    KernelRelationSuggestionSkippedSourceResponse(
                        entity_id=uuid4(),
                        state="pending",
                        reason="embedding_pending",
                    ),
                ],
            )

        def close(self) -> None:
            self.closed = True

    gateway = _FakeGateway()
    source_id = str(uuid4())
    monkeypatch.setattr(
        tool_registry, "_scoped_graph_gateway", lambda **kwargs: gateway
    )

    with caplog.at_level("WARNING"):
        result = asyncio.run(
            suggest_relations(
                space_id=str(uuid4()),
                source_entity_ids=[f" {source_id} "],
                allowed_relation_types=["null", " SUPPORTS ", ""],
                target_entity_types=["GENE", " none "],
                limit_per_source=3,
                min_score=0.2,
            ),
        )

    assert gateway.request is not None
    assert gateway.request.source_entity_ids == [UUID(source_id)]
    assert gateway.request.allowed_relation_types == ["SUPPORTS"]
    assert gateway.request.target_entity_types == ["GENE"]
    assert gateway.request.limit_per_source == 3
    assert gateway.request.min_score == 0.2
    assert gateway.closed is True
    assert json.loads(result)["incomplete"] is True
    assert any(
        record.message == "Filtered nullish graph tool list arguments"
        and getattr(record, "tool_name", "") == "suggest_relations"
        and getattr(record, "field_name", "") == "allowed_relation_types"
        for record in caplog.records
    )
    assert any(
        record.message == "Filtered nullish graph tool list arguments"
        and getattr(record, "tool_name", "") == "suggest_relations"
        and getattr(record, "field_name", "") == "target_entity_types"
        for record in caplog.records
    )


def test_suggest_relations_rejects_fully_nullish_source_entity_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Suggestion tool should fail fast when the LLM provides no usable source IDs."""

    class _FakeGateway:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        tool_registry,
        "_scoped_graph_gateway",
        lambda **kwargs: _FakeGateway(),
    )

    with pytest.raises(
        ValueError,
        match="source_entity_ids must include at least one valid UUID",
    ):
        asyncio.run(
            suggest_relations(
                space_id=str(uuid4()),
                source_entity_ids=["null", " "],
            ),
        )


def test_suggest_relations_logs_graph_service_failures(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Suggestion tool should log structured context before surfacing graph failures."""

    class _FakeGateway:
        def __init__(self) -> None:
            self.closed = False

        def suggest_relations(
            self,
            *,
            space_id: str,
            request: object,
        ) -> KernelRelationSuggestionListResponse:
            del space_id, request
            raise GraphServiceClientError(
                "Graph service request failed: POST /relations/suggestions",
                status_code=503,
                detail='{"detail":"upstream unavailable"}',
            )

        def close(self) -> None:
            self.closed = True

    gateway = _FakeGateway()
    space_id = str(uuid4())
    source_id = str(uuid4())
    monkeypatch.setattr(
        tool_registry, "_scoped_graph_gateway", lambda **kwargs: gateway
    )

    with (
        caplog.at_level("WARNING"),
        pytest.raises(GraphServiceClientError, match="Graph service request failed"),
    ):
        asyncio.run(
            suggest_relations(
                space_id=space_id,
                source_entity_ids=[source_id],
                allowed_relation_types=["SUPPORTS"],
                target_entity_types=["GENE"],
                limit_per_source=3,
                min_score=0.4,
            ),
        )

    assert gateway.closed is True
    records = [
        record
        for record in caplog.records
        if record.message == "Graph suggest_relations tool failed"
    ]
    assert records
    record = records[-1]
    assert getattr(record, "tool_name", None) == "suggest_relations"
    assert getattr(record, "space_id", None) == space_id


def test_get_graph_document_filters_non_uuid_seed_ids(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Graph document tool should drop placeholder seed ids instead of crashing."""

    class _FakeGateway:
        def __init__(self) -> None:
            self.request = None
            self.closed = False

        def get_graph_document(
            self,
            *,
            space_id: str,
            request: object,
        ) -> KernelGraphDocumentResponse:
            del space_id
            self.request = request
            return KernelGraphDocumentResponse(
                nodes=[],
                edges=[],
                meta=KernelGraphDocumentMeta(
                    mode=request.mode,
                    seed_entity_ids=list(request.seed_entity_ids),
                    requested_depth=request.depth,
                    requested_top_k=request.top_k,
                    pre_cap_entity_node_count=0,
                    pre_cap_canonical_edge_count=0,
                    truncated_entity_nodes=False,
                    truncated_canonical_edges=False,
                    included_claims=True,
                    included_evidence=True,
                    max_claims=request.max_claims,
                    evidence_limit_per_claim=request.evidence_limit_per_claim,
                    counts=KernelGraphDocumentCounts(
                        entity_nodes=0,
                        claim_nodes=0,
                        evidence_nodes=0,
                        canonical_edges=0,
                        claim_participant_edges=0,
                        claim_evidence_edges=0,
                    ),
                ),
            )

        def close(self) -> None:
            self.closed = True

    gateway = _FakeGateway()
    valid_seed_id = str(uuid4())
    monkeypatch.setattr(
        tool_registry,
        "_scoped_graph_gateway",
        lambda **kwargs: gateway,
    )

    with caplog.at_level("WARNING"):
        payload = json.loads(
            asyncio.run(
                get_graph_document(
                    space_id=str(uuid4()),
                    seed_entity_ids=["entity-1", f"  {valid_seed_id}  "],
                    depth=3,
                    top_k=12,
                ),
            ),
        )

    assert gateway.request is not None
    assert gateway.request.mode == "seeded"
    assert gateway.request.seed_entity_ids == [UUID(valid_seed_id)]
    assert gateway.closed is True
    assert payload["meta"]["mode"] == "seeded"
    assert payload["meta"]["seed_entity_ids"] == [valid_seed_id]
    assert any(
        record.message == "Filtered non-UUID graph document seed ids"
        and getattr(record, "tool_name", "") == "get_graph_document"
        and getattr(record, "field_name", "") == "seed_entity_ids"
        for record in caplog.records
    )


def test_get_graph_document_downgrades_to_starter_when_all_seed_ids_are_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph document tool should stay usable when all incoming seeds are placeholders."""

    class _FakeGateway:
        def __init__(self) -> None:
            self.request = None
            self.closed = False

        def get_graph_document(
            self,
            *,
            space_id: str,
            request: object,
        ) -> KernelGraphDocumentResponse:
            del space_id
            self.request = request
            return KernelGraphDocumentResponse(
                nodes=[],
                edges=[],
                meta=KernelGraphDocumentMeta(
                    mode=request.mode,
                    seed_entity_ids=list(request.seed_entity_ids),
                    requested_depth=request.depth,
                    requested_top_k=request.top_k,
                    pre_cap_entity_node_count=0,
                    pre_cap_canonical_edge_count=0,
                    truncated_entity_nodes=False,
                    truncated_canonical_edges=False,
                    included_claims=True,
                    included_evidence=True,
                    max_claims=request.max_claims,
                    evidence_limit_per_claim=request.evidence_limit_per_claim,
                    counts=KernelGraphDocumentCounts(
                        entity_nodes=0,
                        claim_nodes=0,
                        evidence_nodes=0,
                        canonical_edges=0,
                        claim_participant_edges=0,
                        claim_evidence_edges=0,
                    ),
                ),
            )

        def close(self) -> None:
            self.closed = True

    gateway = _FakeGateway()
    monkeypatch.setattr(
        tool_registry,
        "_scoped_graph_gateway",
        lambda **kwargs: gateway,
    )

    payload = json.loads(
        asyncio.run(
            get_graph_document(
                space_id=str(uuid4()),
                seed_entity_ids=["entity-1", "entity-2"],
            ),
        ),
    )

    assert gateway.request is not None
    assert gateway.request.mode == "starter"
    assert gateway.request.seed_entity_ids == []
    assert gateway.closed is True
    assert payload["meta"]["mode"] == "starter"
    assert payload["meta"]["seed_entity_ids"] == []
