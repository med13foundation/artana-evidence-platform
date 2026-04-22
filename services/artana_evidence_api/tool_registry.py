"""Typed Artana tool registry for graph-harness kernel workflows."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import suppress
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from artana.ports.tool import LocalToolRegistry, ToolExecutionContext
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,
)
from artana_evidence_api.graph_integration.context import (
    GraphCallContext,
    GraphCallRole,
)
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.graph_integration.submission import (
    GraphWorkflowSubmissionService,
)
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    PubMedDiscoveryService,
    PubMedSortOption,
    RunPubmedSearchRequest,
    create_pubmed_discovery_service,
)
from artana_evidence_api.tool_catalog import (
    ConceptExternalRefToolArgs,
    GraphChangeClaimToolArgs,
    GraphChangeConceptToolArgs,
    get_graph_harness_tool_spec,
    list_graph_harness_tool_specs,
)
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    AIDecisionSubmitRequest,
    ClaimAIProvenanceEnvelope,
    ConceptExternalRefRequest,
    ConceptProposalCreateRequest,
    ConnectorProposalCreateRequest,
    CreateManualHypothesisRequest,
    DecisionConfidenceAssessment,
    GraphChangeClaimRequest,
    GraphChangeConceptRequest,
    GraphChangeProposalCreateRequest,
    KernelGraphDocumentCounts,
    KernelGraphDocumentMeta,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationSuggestionRequest,
)
from artana_evidence_api.types.graph_fact_assessment import FactAssessment

if TYPE_CHECKING:
    from collections.abc import Generator

    from artana.ports.tool import ToolPort
    from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryService
    from pydantic import BaseModel


_HTTP_NOT_FOUND = 404
_NULLISH_TOOL_TOKENS = frozenset({"", "null", "none", "nil", "undefined"})
logger = logging.getLogger(__name__)


def _json_result(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _stable_tool_input_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _tool_source_ref(
    *,
    explicit_source_ref: str | None,
    prefix: str,
    artana_context: ToolExecutionContext,
    input_payload: dict[str, object],
) -> str:
    if explicit_source_ref is not None and explicit_source_ref.strip():
        return explicit_source_ref.strip()
    idempotency_key = (
        artana_context.idempotency_key.strip()
        if artana_context.idempotency_key
        else _stable_tool_input_hash(input_payload)[:16]
    )
    return f"artana-tool:{artana_context.run_id}:{prefix}:{idempotency_key}"


def _normalize_optional_tool_text(
    value: str | None,
    *,
    tool_name: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized.lower() in _NULLISH_TOOL_TOKENS:
        logger.warning(
            "Normalized nullish graph tool argument",
            extra={
                "tool_name": tool_name,
                "field_name": field_name,
                "raw_value": value,
            },
        )
        return None
    return normalized


def _normalize_optional_tool_text_list(
    values: list[str] | None,
    *,
    tool_name: str,
    field_name: str,
) -> list[str] | None:
    if values is None:
        return None
    normalized: list[str] = []
    removed_count = 0
    for value in values:
        candidate = _normalize_optional_tool_text(
            value,
            tool_name=tool_name,
            field_name=field_name,
        )
        if candidate is None:
            removed_count += 1
            continue
        normalized.append(candidate)
    if removed_count:
        logger.warning(
            "Filtered nullish graph tool list arguments",
            extra={
                "tool_name": tool_name,
                "field_name": field_name,
                "removed_count": removed_count,
            },
        )
    return normalized or None


def _normalize_required_tool_uuid_list(
    values: list[str],
    *,
    tool_name: str,
    field_name: str,
) -> list[str]:
    normalized = _normalize_optional_tool_text_list(
        values,
        tool_name=tool_name,
        field_name=field_name,
    )
    if not normalized:
        raise ValueError(f"{field_name} must include at least one valid UUID")
    return normalized


def _normalize_graph_document_seed_entity_ids(
    seed_entity_ids: list[str],
) -> list[UUID]:
    normalized_seed_entity_ids = _normalize_optional_tool_text_list(
        seed_entity_ids,
        tool_name="get_graph_document",
        field_name="seed_entity_ids",
    )
    if normalized_seed_entity_ids is None:
        return []
    resolved_seed_entity_ids: list[UUID] = []
    invalid_seed_entity_ids: list[str] = []
    for seed_entity_id in normalized_seed_entity_ids:
        try:
            resolved_seed_entity_ids.append(UUID(seed_entity_id))
        except ValueError:
            invalid_seed_entity_ids.append(seed_entity_id)
    if invalid_seed_entity_ids:
        logger.warning(
            "Filtered non-UUID graph document seed ids",
            extra={
                "tool_name": "get_graph_document",
                "field_name": "seed_entity_ids",
                "removed_count": len(invalid_seed_entity_ids),
                "sample_removed_values": invalid_seed_entity_ids[:3],
            },
        )
    return resolved_seed_entity_ids


def _graph_tool_call_context(
    *,
    role: GraphCallRole = "researcher",
    graph_ai_principal: str | None = None,
) -> GraphCallContext:
    """Return the explicit service-owned graph authority for internal tools."""
    return GraphCallContext.service(
        role=role,
        graph_admin=True,
        graph_ai_principal=graph_ai_principal,
    )


def _scoped_graph_gateway(
    *,
    role: GraphCallRole = "researcher",
    graph_ai_principal: str | None = None,
) -> GraphTransportBundle:
    return GraphTransportBundle(
        call_context=_graph_tool_call_context(
            role=role,
            graph_ai_principal=graph_ai_principal,
        ),
    )


@lru_cache(maxsize=1)
def _graph_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()


@lru_cache(maxsize=1)
def _graph_submission_service() -> GraphWorkflowSubmissionService:
    return GraphWorkflowSubmissionService()


def _scoped_pubmed_service() -> Generator[PubMedDiscoveryService]:
    service = create_pubmed_discovery_service()
    try:
        yield service
    finally:
        service.close()


def _scoped_marrvel_service() -> Generator[MarrvelDiscoveryService]:
    from artana_evidence_api.marrvel_enrichment import create_marrvel_discovery_service

    service = create_marrvel_discovery_service()
    try:
        yield service
    finally:
        service.close()


def _owner_id_from_context(context: ToolExecutionContext) -> UUID:
    return uuid5(NAMESPACE_URL, f"harness-owner:{context.tenant_id}")


def _graph_document_request(
    *,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
) -> KernelGraphDocumentRequest:
    normalized_seed_entity_ids = _normalize_graph_document_seed_entity_ids(
        seed_entity_ids,
    )
    return KernelGraphDocumentRequest(
        mode="seeded" if normalized_seed_entity_ids else "starter",
        seed_entity_ids=normalized_seed_entity_ids,
        depth=depth,
        top_k=top_k,
        include_claims=True,
        include_evidence=True,
        max_claims=max(25, top_k * 2),
        evidence_limit_per_claim=3,
    )


def _is_missing_graph_document_error(exc: GraphServiceClientError) -> bool:
    return exc.status_code == _HTTP_NOT_FOUND and "/graph/document" in str(exc)


def _fallback_graph_document(
    *,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
) -> KernelGraphDocumentResponse:
    normalized_seed_entity_ids = _normalize_graph_document_seed_entity_ids(
        seed_entity_ids,
    )
    return KernelGraphDocumentResponse(
        nodes=[],
        edges=[],
        meta=KernelGraphDocumentMeta(
            mode="seeded" if normalized_seed_entity_ids else "starter",
            seed_entity_ids=normalized_seed_entity_ids,
            requested_depth=depth,
            requested_top_k=top_k,
            pre_cap_entity_node_count=0,
            pre_cap_canonical_edge_count=0,
            truncated_entity_nodes=False,
            truncated_canonical_edges=False,
            included_claims=True,
            included_evidence=True,
            max_claims=max(25, top_k * 2),
            evidence_limit_per_claim=3,
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


def _load_graph_document(
    *,
    gateway: GraphTransportBundle,
    space_id: str,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
) -> KernelGraphDocumentResponse:
    try:
        return gateway.get_graph_document(
            space_id=space_id,
            request=_graph_document_request(
                seed_entity_ids=seed_entity_ids,
                depth=depth,
                top_k=top_k,
            ),
        )
    except GraphServiceClientError as exc:
        if _is_missing_graph_document_error(exc):
            return _fallback_graph_document(
                seed_entity_ids=seed_entity_ids,
                depth=depth,
                top_k=top_k,
            )
        raise


async def get_graph_document(
    space_id: str,
    seed_entity_ids: list[str],
    depth: int = 2,
    top_k: int = 25,
) -> str:
    """Fetch one graph document for deterministic read-side grounding."""
    gateway = _scoped_graph_gateway()
    try:
        document = _load_graph_document(
            gateway=gateway,
            space_id=space_id,
            seed_entity_ids=seed_entity_ids,
            depth=depth,
            top_k=top_k,
        )
        return _json_result(document.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_graph_claims(
    space_id: str,
    claim_status: str | None = None,
    limit: int = 50,
) -> str:
    """List graph claims for one research space."""
    normalized_claim_status = _normalize_optional_tool_text(
        claim_status,
        tool_name="list_graph_claims",
        field_name="claim_status",
    )
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claims(
            space_id=space_id,
            claim_status=normalized_claim_status,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_graph_hypotheses(
    space_id: str,
    limit: int = 50,
) -> str:
    """List graph hypotheses for one research space."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_hypotheses(
            space_id=space_id,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def suggest_relations(  # noqa: PLR0913
    space_id: str,
    source_entity_ids: list[str],
    allowed_relation_types: list[str] | None = None,
    target_entity_types: list[str] | None = None,
    limit_per_source: int = 5,
    min_score: float = 0.0,
) -> str:
    """Suggest dictionary-constrained relations for one or more source entities."""
    normalized_source_entity_ids = _normalize_required_tool_uuid_list(
        source_entity_ids,
        tool_name="suggest_relations",
        field_name="source_entity_ids",
    )
    normalized_allowed_relation_types = _normalize_optional_tool_text_list(
        allowed_relation_types,
        tool_name="suggest_relations",
        field_name="allowed_relation_types",
    )
    normalized_target_entity_types = _normalize_optional_tool_text_list(
        target_entity_types,
        tool_name="suggest_relations",
        field_name="target_entity_types",
    )
    gateway = _scoped_graph_gateway()
    try:
        request = KernelRelationSuggestionRequest(
            source_entity_ids=[
                UUID(entity_id) for entity_id in normalized_source_entity_ids
            ],
            limit_per_source=limit_per_source,
            min_score=min_score,
            allowed_relation_types=normalized_allowed_relation_types,
            target_entity_types=normalized_target_entity_types,
            exclude_existing_relations=True,
        )
        response = gateway.suggest_relations(
            space_id=space_id,
            request=request,
        )
    except GraphServiceClientError as exc:
        logger.warning(
            "Graph suggest_relations tool failed",
            extra={
                "tool_name": "suggest_relations",
                "space_id": space_id,
                "source_entity_ids": normalized_source_entity_ids,
                "allowed_relation_types": normalized_allowed_relation_types,
                "target_entity_types": normalized_target_entity_types,
                "status_code": exc.status_code,
                "detail": exc.detail,
            },
        )
        raise
    else:
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def capture_graph_snapshot(
    space_id: str,
    seed_entity_ids: list[str],
    depth: int = 2,
    top_k: int = 25,
) -> str:
    """Capture one graph-context snapshot payload for later harness artifacts."""
    gateway = _scoped_graph_gateway()
    try:
        document = _load_graph_document(
            gateway=gateway,
            space_id=space_id,
            seed_entity_ids=seed_entity_ids,
            depth=depth,
            top_k=top_k,
        )
        payload = document.model_dump(mode="json")
        payload["snapshot_hash"] = str(
            uuid5(
                NAMESPACE_URL,
                json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
            ),
        )
        return _json_result(payload)
    finally:
        gateway.close()


async def run_pubmed_search(  # noqa: PLR0913
    search_term: str,
    artana_context: ToolExecutionContext,
    gene_symbol: str | None = None,
    additional_terms: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    max_results: int = 25,
) -> str:
    """Run one scoped PubMed discovery search and return the persisted job payload."""
    owner_id = _owner_id_from_context(artana_context)
    request = RunPubmedSearchRequest(
        parameters=AdvancedQueryParameters(
            search_term=search_term,
            gene_symbol=gene_symbol,
            additional_terms=additional_terms,
            date_from=date_from,
            date_to=date_to,
            max_results=max_results,
            sort_by=PubMedSortOption.RELEVANCE,
        ),
    )
    service_generator = _scoped_pubmed_service()
    service = next(service_generator)
    try:
        job = await service.run_pubmed_search(owner_id=owner_id, request=request)
        return _json_result(job.model_dump(mode="json"))
    finally:
        with suppress(StopIteration):
            next(service_generator)


async def run_marrvel_search(
    gene_symbol: str,
    artana_context: ToolExecutionContext,
    panels: list[str] | None = None,
    taxon_id: int = 9606,
) -> str:
    """Run one MARRVEL gene discovery search and return the result."""
    owner_id = _owner_id_from_context(artana_context)
    service_generator = _scoped_marrvel_service()
    service = next(service_generator)
    try:
        result = await service.search(
            owner_id=owner_id,
            space_id=uuid5(NAMESPACE_URL, "marrvel-tool"),
            gene_symbol=gene_symbol,
            taxon_id=taxon_id,
            panels=panels,
        )
        return _json_result(
            {
                "id": str(result.id),
                "gene_symbol": result.gene_symbol,
                "resolved_gene_symbol": result.resolved_gene_symbol,
                "status": result.status,
                "gene_found": result.gene_found,
                "omim_count": result.omim_count,
                "variant_count": result.variant_count,
                "panel_counts": result.panel_counts,
                "panels": result.panels,
                "available_panels": result.available_panels,
            },
        )
    finally:
        with suppress(StopIteration):
            next(service_generator)


async def list_reasoning_paths(  # noqa: PLR0913
    space_id: str,
    start_entity_id: str | None = None,
    end_entity_id: str | None = None,
    status: str | None = None,
    path_kind: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List reasoning paths for one graph space."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_reasoning_paths(
            space_id=space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
            offset=offset,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def get_reasoning_path(
    space_id: str,
    path_id: str,
) -> str:
    """Fetch one explained reasoning path."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.get_reasoning_path(
            space_id=space_id,
            path_id=path_id,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_claims_by_entity(
    space_id: str,
    entity_id: str,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List graph claims connected to one entity."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claims_by_entity(
            space_id=space_id,
            entity_id=entity_id,
            offset=offset,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_claim_participants(
    space_id: str,
    claim_id: str,
) -> str:
    """List participants for one graph claim."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claim_participants(
            space_id=space_id,
            claim_id=claim_id,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_claim_evidence(
    space_id: str,
    claim_id: str,
) -> str:
    """List evidence rows for one graph claim."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_claim_evidence(
            space_id=space_id,
            claim_id=claim_id,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def list_relation_conflicts(
    space_id: str,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List mixed-polarity canonical relation conflicts."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.list_relation_conflicts(
            space_id=space_id,
            offset=offset,
            limit=limit,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def create_graph_claim(  # noqa: PLR0913
    space_id: str,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    claim_text: str,
    source_document_ref: str,
    assessment: FactAssessment,
    evidence_summary: str,
    artana_context: ToolExecutionContext,
) -> str:
    """Create one unresolved graph claim through the governed graph-service path."""
    gateway = _scoped_graph_gateway()
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    try:
        input_payload: dict[str, object] = {
            "space_id": space_id,
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "relation_type": relation_type,
            "claim_text": claim_text,
            "source_document_ref": source_document_ref,
            "assessment": assessment.model_dump(mode="json"),
            "evidence_summary": evidence_summary,
        }
        input_hash = _stable_tool_input_hash(input_payload)
        idempotency_key = (
            artana_context.idempotency_key.strip()
            if artana_context.idempotency_key
            else input_hash[:16]
        )
        request = KernelRelationClaimCreateRequest(
            source_entity_id=UUID(source_entity_id),
            target_entity_id=UUID(target_entity_id),
            relation_type=relation_type,
            assessment=assessment,
            claim_text=claim_text,
            evidence_summary=evidence_summary,
            source_document_ref=source_document_ref,
            source_ref=f"artana-tool:{artana_context.run_id}:{idempotency_key}",
            agent_run_id=artana_context.run_id,
            ai_provenance=ClaimAIProvenanceEnvelope(
                model_id="artana-kernel",
                model_version="runtime",
                prompt_id="graph_harness.create_graph_claim",
                prompt_version="v1",
                input_hash=input_hash,
                rationale=evidence_summary or claim_text,
                evidence_references=[source_document_ref],
                tool_trace_ref=f"artana-run:{artana_context.run_id}",
            ),
            metadata={
                "artana_idempotency_key": artana_context.idempotency_key,
                "origin": "graph_harness",
            },
        )
        resolved_intent = await preflight_service.prepare_claim_create(
            space_id=UUID(space_id),
            request=request,
            graph_transport=gateway,
        )
        response = submission_service.submit_resolved_intent(
            resolved_intent=resolved_intent,
            graph_transport=gateway,
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def create_manual_hypothesis(  # noqa: PLR0913
    space_id: str,
    statement: str,
    rationale: str,
    seed_entity_ids: list[str],
    source_type: str,
    artana_context: ToolExecutionContext,
) -> str:
    """Create one manual graph hypothesis through the graph-service path."""
    gateway = _scoped_graph_gateway()
    try:
        response = gateway.create_manual_hypothesis(
            space_id=space_id,
            request=CreateManualHypothesisRequest(
                statement=statement,
                rationale=rationale,
                seed_entity_ids=seed_entity_ids,
                source_type=source_type,
                metadata={
                    "artana_idempotency_key": artana_context.idempotency_key,
                    "artana_run_id": artana_context.run_id,
                },
            ),
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


async def propose_graph_concept(  # noqa: PLR0913
    space_id: str,
    entity_type: str,
    canonical_label: str,
    artana_context: ToolExecutionContext,
    domain_context: str = "general",
    synonyms: list[str] | None = None,
    external_refs: list[ConceptExternalRefToolArgs] | None = None,
    evidence_payload: JSONObject | None = None,
    rationale: str | None = None,
    source_ref: str | None = None,
) -> str:
    """Submit one AI Full Mode concept proposal through the graph DB."""
    input_payload: dict[str, object] = {
        "space_id": space_id,
        "domain_context": domain_context,
        "entity_type": entity_type,
        "canonical_label": canonical_label,
        "synonyms": synonyms or [],
        "external_refs": [
            item.model_dump(mode="json") for item in (external_refs or [])
        ],
        "evidence_payload": evidence_payload or {},
        "rationale": rationale,
    }
    submission_service = _graph_submission_service()
    response = submission_service.propose_concept(
        space_id=space_id,
        request=ConceptProposalCreateRequest(
            domain_context=domain_context,
            entity_type=entity_type,
            canonical_label=canonical_label,
            synonyms=synonyms or [],
            external_refs=[
                ConceptExternalRefRequest.model_validate(
                    item.model_dump(mode="json"),
                )
                for item in (external_refs or [])
            ],
            evidence_payload={
                **(evidence_payload or {}),
                "artana_run_id": artana_context.run_id,
            },
            rationale=rationale,
            source_ref=_tool_source_ref(
                explicit_source_ref=source_ref,
                prefix="concept",
                artana_context=artana_context,
                input_payload=input_payload,
            ),
        ),
        call_context=_graph_tool_call_context(role="curator"),
    )
    return _json_result(response.model_dump(mode="json"))


async def propose_graph_change(
    space_id: str,
    concepts: list[GraphChangeConceptToolArgs],
    artana_context: ToolExecutionContext,
    claims: list[GraphChangeClaimToolArgs] | None = None,
    source_ref: str | None = None,
) -> str:
    """Submit one AI Full Mode mini-graph proposal through the graph DB."""
    raw_concepts = [item.model_dump(mode="json") for item in concepts]
    raw_claims = [item.model_dump(mode="json") for item in (claims or [])]
    input_payload: dict[str, object] = {
        "space_id": space_id,
        "concepts": raw_concepts,
        "claims": raw_claims,
    }
    submission_service = _graph_submission_service()
    response = submission_service.propose_graph_change(
        space_id=space_id,
        request=GraphChangeProposalCreateRequest(
            concepts=[
                GraphChangeConceptRequest.model_validate(item) for item in raw_concepts
            ],
            claims=[
                GraphChangeClaimRequest.model_validate(item) for item in raw_claims
            ],
            source_ref=_tool_source_ref(
                explicit_source_ref=source_ref,
                prefix="graph-change",
                artana_context=artana_context,
                input_payload=input_payload,
            ),
        ),
        call_context=_graph_tool_call_context(role="curator"),
    )
    return _json_result(response.model_dump(mode="json"))


async def submit_ai_full_mode_decision(  # noqa: PLR0913
    space_id: str,
    target_type: str,
    target_id: str,
    action: str,
    ai_principal: str,
    confidence_assessment: DecisionConfidenceAssessment,
    risk_tier: str,
    input_hash: str,
    artana_context: ToolExecutionContext,
    evidence_payload: JSONObject | None = None,
    decision_payload: JSONObject | None = None,
) -> str:
    """Submit one AI Full Mode decision envelope through the graph DB."""
    submission_service = _graph_submission_service()
    response = submission_service.submit_ai_decision(
        space_id=space_id,
        request=AIDecisionSubmitRequest(
            target_type=cast(
                "Literal['concept_proposal', 'graph_change_proposal']",
                target_type,
            ),
            target_id=UUID(target_id),
            action=cast(
                "Literal['APPROVE', 'MERGE', 'REJECT', "
                "'REQUEST_CHANGES', 'APPLY_RESOLUTION_PLAN']",
                action,
            ),
            ai_principal=ai_principal,
            confidence_assessment=confidence_assessment,
            risk_tier=cast("Literal['low', 'medium', 'high']", risk_tier),
            input_hash=input_hash,
            evidence_payload={
                **(evidence_payload or {}),
                "artana_run_id": artana_context.run_id,
            },
            decision_payload=decision_payload or {},
        ),
    )
    return _json_result(response.model_dump(mode="json"))


async def propose_connector_metadata(  # noqa: PLR0913
    space_id: str,
    connector_slug: str,
    display_name: str,
    connector_kind: str,
    domain_context: str,
    artana_context: ToolExecutionContext,
    metadata_payload: JSONObject | None = None,
    mapping_payload: JSONObject | None = None,
    evidence_payload: JSONObject | None = None,
    rationale: str | None = None,
    source_ref: str | None = None,
) -> str:
    """Submit one connector metadata proposal without running connector code."""
    input_payload: dict[str, object] = {
        "space_id": space_id,
        "connector_slug": connector_slug,
        "display_name": display_name,
        "connector_kind": connector_kind,
        "domain_context": domain_context,
        "metadata_payload": metadata_payload or {},
        "mapping_payload": mapping_payload or {},
        "evidence_payload": evidence_payload or {},
        "rationale": rationale,
    }
    gateway = _scoped_graph_gateway(role="curator")
    try:
        response = gateway.propose_connector_metadata(
            space_id=space_id,
            request=ConnectorProposalCreateRequest(
                connector_slug=connector_slug,
                display_name=display_name,
                connector_kind=connector_kind,
                domain_context=domain_context,
                metadata_payload=metadata_payload or {},
                mapping_payload=mapping_payload or {},
                evidence_payload={
                    **(evidence_payload or {}),
                    "artana_run_id": artana_context.run_id,
                },
                rationale=rationale,
                source_ref=_tool_source_ref(
                    explicit_source_ref=source_ref,
                    prefix="connector",
                    artana_context=artana_context,
                    input_payload=input_payload,
                ),
            ),
        )
        return _json_result(response.model_dump(mode="json"))
    finally:
        gateway.close()


_REGISTERED_FUNCTIONS = {
    "get_graph_document": get_graph_document,
    "list_graph_claims": list_graph_claims,
    "list_graph_hypotheses": list_graph_hypotheses,
    "suggest_relations": suggest_relations,
    "capture_graph_snapshot": capture_graph_snapshot,
    "run_pubmed_search": run_pubmed_search,
    "run_marrvel_search": run_marrvel_search,
    "list_reasoning_paths": list_reasoning_paths,
    "get_reasoning_path": get_reasoning_path,
    "list_claims_by_entity": list_claims_by_entity,
    "list_claim_participants": list_claim_participants,
    "list_claim_evidence": list_claim_evidence,
    "list_relation_conflicts": list_relation_conflicts,
    "create_graph_claim": create_graph_claim,
    "create_manual_hypothesis": create_manual_hypothesis,
    "propose_graph_concept": propose_graph_concept,
    "propose_graph_change": propose_graph_change,
    "submit_ai_full_mode_decision": submit_ai_full_mode_decision,
    "propose_connector_metadata": propose_connector_metadata,
}


def build_graph_harness_tool_registry() -> ToolPort:
    """Register the typed graph and discovery tools exposed to harness runs."""
    registry = LocalToolRegistry()
    for spec in list_graph_harness_tool_specs():
        function = _REGISTERED_FUNCTIONS[spec.name]
        registry.register(
            function,
            requires_capability=spec.required_capability,
            side_effect=spec.side_effect,
            tool_version=spec.tool_version,
            schema_version=spec.schema_version,
            risk_level=spec.risk_level,
        )
    return registry


def tool_argument_model(tool_name: str) -> type[BaseModel]:
    """Return the declared Pydantic argument model for one tool name."""
    spec = get_graph_harness_tool_spec(tool_name)
    if spec is None:
        msg = f"Unknown graph-harness tool {tool_name!r}."
        raise KeyError(msg)
    return spec.input_model


__all__ = [
    "build_graph_harness_tool_registry",
    "tool_argument_model",
]
