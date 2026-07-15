"""Shared proposal promotion and rejection helpers for harness workflows."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from functools import lru_cache
from typing import TYPE_CHECKING, TypeVar, cast
from uuid import UUID

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.confidence_assessment import (
    assessment_confidence_metadata,
    proposal_fact_assessment,
)
from artana_evidence_api.document_extraction import resolve_graph_entity_label
from artana_evidence_api.document_extraction_support.variant import (
    observation_promotion_support,
)
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.graph_integration.proposal_support import (
    extract_graph_service_error_detail,
    graph_promotion_error_response,
    is_relation_constraint_error,
    merge_promotion_metadata,
    metadata_text,
    stable_json_hash,
)
from artana_evidence_api.graph_integration.source_provenance import (
    ResolvedSourceProvenance,
    SourceProvenanceError,
    source_evidence_handoff,
    verify_persisted_source_provenance,
)
from artana_evidence_api.graph_integration.submission import (
    GraphWorkflowSubmissionService,
)
from artana_evidence_api.proposal_entity_payloads import (
    entity_candidate_field_name,
    field_name_from_label_field,
    infer_graph_entity_type_from_label,
    optional_json_string,
    optional_payload_object,
    payload_entity_aliases,
    payload_entity_display_label,
    payload_entity_identifiers,
    payload_entity_metadata,
    resolve_entity_reference_value,
    resolve_existing_entity_from_candidate_payload,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.types.graph_contracts import (
    ClaimAIProvenanceEnvelope,
    CreateManualHypothesisRequest,
    KernelObservationCreateRequest,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimResponse,
    KernelRelationCreateRequest,
    KernelRelationResponse,
)
from artana_evidence_api.types.graph_fact_assessment import assessment_confidence
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )

_T = TypeVar("_T")


@lru_cache(maxsize=1)
def _graph_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()


@lru_cache(maxsize=1)
def _graph_submission_service() -> GraphWorkflowSubmissionService:
    return GraphWorkflowSubmissionService()


def _run_async_preflight(awaitable: Coroutine[object, object, _T]) -> _T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except Exception as exc:  # noqa: BLE001 pragma: no cover - surfaced to caller
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return cast("_T", result["value"])


def require_proposal(
    *,
    space_id: UUID,
    proposal_id: UUID | str,
    proposal_store: HarnessProposalStore,
) -> HarnessProposalRecord:
    """Return one proposal from the store or raise a typed 404."""
    proposal = proposal_store.get_proposal(space_id=space_id, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found in space '{space_id}'",
        )
    return proposal


def status_counts(
    proposals: list[HarnessProposalRecord],
) -> dict[str, int]:
    """Count proposal decisions for one run snapshot."""
    counts = {
        "pending_review": 0,
        "promoted": 0,
        "rejected": 0,
    }
    for proposal in proposals:
        counts[proposal.status] = counts.get(proposal.status, 0) + 1
    return counts


def _require_payload_string(
    payload: JSONObject,
    *,
    field_name: str,
) -> str:
    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Proposal payload is missing required '{field_name}' for graph promotion"
        ),
    )


def _require_payload_string_list(
    payload: JSONObject,
    *,
    field_name: str,
) -> list[str]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proposal payload is missing required '{field_name}' list",
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if trimmed == "":
            continue
        normalized.append(trimmed)
    if normalized:
        return normalized
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Proposal payload is missing required '{field_name}' list",
    )


def _require_payload_uuid(
    payload: JSONObject,
    *,
    field_name: str,
) -> UUID:
    value = _require_payload_string(payload, field_name=field_name)
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proposal payload field '{field_name}' must be a UUID",
        ) from exc


def _proposal_source_document_uuid(proposal: HarnessProposalRecord) -> UUID:
    if proposal.document_id is None:
        raise SourceProvenanceError(
            "missing_source_document",
            "Verified source provenance requires a source document identifier.",
        )
    try:
        return UUID(proposal.document_id)
    except ValueError as exc:
        raise SourceProvenanceError(
            "invalid_source_document_id",
            "Verified source provenance requires a UUID source document identifier.",
        ) from exc


def build_graph_claim_request(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
    source_provenance: ResolvedSourceProvenance | None = None,
    source_provenance_reason_code: str | None = None,
) -> KernelRelationClaimCreateRequest:
    """Build one graph-claim creation request from a harness proposal."""
    if proposal.proposal_type != "candidate_claim":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "graph claim promotion"
            ),
        )
    reasoning = proposal.reasoning_path.get("reasoning")
    agent_run_id = proposal.metadata.get("agent_run_id")
    agent_run_id_value = (
        agent_run_id
        if isinstance(agent_run_id, str) and agent_run_id.strip()
        else proposal.run_id
    )
    assessment = proposal_fact_assessment(proposal)
    claim_text = (
        reasoning
        if isinstance(reasoning, str) and reasoning.strip() != ""
        else proposal.summary
    )
    source_document_ref = (
        source_provenance.source_identity.authoritative_identifier
        if source_provenance is not None
        else f"harness_proposal:{proposal.id}"
    )
    evidence_sentence = (
        source_provenance.evidence_locator.exact_quote
        if source_provenance is not None
        else None
    )
    input_hash = stable_json_hash(
        {
            "proposal_id": proposal.id,
            "document_id": proposal.document_id,
            "run_id": proposal.run_id,
            "payload": proposal.payload,
            "summary": proposal.summary,
            "reasoning_path": proposal.reasoning_path,
            "assessment": assessment.model_dump(mode="json"),
        },
    )
    return KernelRelationClaimCreateRequest(
        source_entity_id=_resolve_payload_entity_id(
            payload=proposal.payload,
            field_name="proposed_subject",
            label_field_name="proposed_subject_label",
            metadata=proposal.metadata,
            metadata_label_field_name="subject_label",
            space_id=space_id,
            graph_api_gateway=graph_api_gateway,
        ),
        target_entity_id=_resolve_payload_entity_id(
            payload=proposal.payload,
            field_name="proposed_object",
            label_field_name="proposed_object_label",
            metadata=proposal.metadata,
            metadata_label_field_name="object_label",
            space_id=space_id,
            graph_api_gateway=graph_api_gateway,
        ),
        relation_type=_require_payload_string(
            proposal.payload,
            field_name="proposed_claim_type",
        ),
        assessment=assessment,
        claim_text=claim_text,
        evidence_summary=proposal.summary,
        evidence_sentence=evidence_sentence,
        evidence_sentence_source=(
            "verbatim_span" if source_provenance is not None else None
        ),
        evidence_sentence_confidence=(
            "high" if source_provenance is not None else None
        ),
        source_document_id=(
            _proposal_source_document_uuid(proposal)
            if source_provenance is not None
            else None
        ),
        source_document_ref=source_document_ref,
        source_evidence=(
            source_evidence_handoff(
                research_space_id=space_id,
                document_id=_proposal_source_document_uuid(proposal),
                provenance=source_provenance,
            )
            if source_provenance is not None
            else None
        ),
        source_ref=f"harness-proposal-claim:{proposal.id}",
        agent_run_id=agent_run_id_value,
        ai_provenance=ClaimAIProvenanceEnvelope(
            model_id=metadata_text(
                proposal.metadata,
                "model_id",
                default="artana-kernel",
            ),
            model_version=metadata_text(
                proposal.metadata,
                "model_version",
                default="unknown",
            ),
            prompt_id=metadata_text(
                proposal.metadata,
                "prompt_id",
                default=f"harness_proposal:{proposal.proposal_type}",
            ),
            prompt_version=metadata_text(
                proposal.metadata,
                "prompt_version",
                default="unknown",
            ),
            input_hash=input_hash,
            rationale=claim_text or proposal.summary,
            evidence_references=[source_document_ref],
            tool_trace_ref=f"harness-run:{proposal.run_id}",
        ),
        metadata={
            **merge_promotion_metadata(
                proposal_metadata=proposal.metadata,
                request_metadata=request_metadata,
            ),
            **assessment_confidence_metadata(assessment),
            "proposal_id": proposal.id,
            "document_id": proposal.document_id,
            "harness_run_id": proposal.run_id,
            "proposal_type": proposal.proposal_type,
            "source_kind": proposal.source_kind,
            "source_key": proposal.source_key,
            "source_provenance_status": (
                "verified"
                if source_provenance is not None
                else "invalid"
                if source_provenance_reason_code is not None
                else "unverified"
            ),
            "source_provenance_reason_code": source_provenance_reason_code,
            "reasoning_path": proposal.reasoning_path,
            "evidence_bundle": proposal.evidence_bundle,
        },
    )


def build_graph_relation_request(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
    source_provenance: ResolvedSourceProvenance,
) -> KernelRelationCreateRequest:
    """Build a relation-creation request from a harness proposal.

    Unlike ``build_graph_claim_request`` which creates an unresolved claim,
    this builds a request for ``POST /relations`` which creates a RESOLVED
    claim and materializes it into a canonical relation in one transaction.
    """
    if proposal.proposal_type != "candidate_claim":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "graph relation promotion"
            ),
        )
    assessment = proposal_fact_assessment(proposal)
    return KernelRelationCreateRequest(
        source_id=_resolve_payload_entity_id(
            payload=proposal.payload,
            field_name="proposed_subject",
            label_field_name="proposed_subject_label",
            metadata=proposal.metadata,
            metadata_label_field_name="subject_label",
            space_id=space_id,
            graph_api_gateway=graph_api_gateway,
        ),
        target_id=_resolve_payload_entity_id(
            payload=proposal.payload,
            field_name="proposed_object",
            label_field_name="proposed_object_label",
            metadata=proposal.metadata,
            metadata_label_field_name="object_label",
            space_id=space_id,
            graph_api_gateway=graph_api_gateway,
        ),
        relation_type=_require_payload_string(
            proposal.payload,
            field_name="proposed_claim_type",
        ),
        assessment=assessment,
        evidence_summary=proposal.summary,
        evidence_sentence=source_provenance.evidence_locator.exact_quote,
        evidence_sentence_source="verbatim_span",
        evidence_sentence_confidence="high",
        source_document_id=_proposal_source_document_uuid(proposal),
        source_document_ref=(
            source_provenance.source_identity.authoritative_identifier
        ),
        source_evidence=source_evidence_handoff(
            research_space_id=space_id,
            document_id=_proposal_source_document_uuid(proposal),
            provenance=source_provenance,
        ),
        metadata={
            **merge_promotion_metadata(
                proposal_metadata=proposal.metadata,
                request_metadata=request_metadata,
            ),
            **assessment_confidence_metadata(assessment),
            "proposal_id": proposal.id,
            "document_id": proposal.document_id,
            "harness_run_id": proposal.run_id,
            "proposal_type": proposal.proposal_type,
            "source_kind": proposal.source_kind,
            "source_key": proposal.source_key,
            "source_provenance_status": "verified",
            "reasoning_path": proposal.reasoning_path,
            "evidence_bundle": list(proposal.evidence_bundle),
        },
    )


def build_graph_observation_request(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    graph_api_gateway: GraphTransportBundle,
) -> KernelObservationCreateRequest:
    """Build one graph observation request from a staged observation proposal."""
    if proposal.proposal_type != "observation_candidate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "graph observation promotion"
            ),
        )
    subject_candidate = optional_payload_object(
        proposal.payload,
        field_name="subject_entity_candidate",
    )
    if subject_candidate is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Observation proposal payload is missing 'subject_entity_candidate'",
        )
    subject_label = payload_entity_display_label(subject_candidate)
    subject_resolution = resolve_existing_entity_from_candidate_payload(
        space_id=space_id,
        candidate_payload=subject_candidate,
        graph_api_gateway=graph_api_gateway,
    )
    if subject_resolution is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Observation promotion requires an existing subject entity. "
                f"Promote or resolve '{subject_label}' first, then retry the "
                "observation."
            ),
        )
    subject_id = subject_resolution.get("id")
    if not isinstance(subject_id, str) or not subject_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to resolve an entity id for the observation subject",
        )
    assessment = proposal_fact_assessment(proposal)
    if "value" not in proposal.payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Observation proposal payload is missing required 'value'",
        )
    unit = optional_json_string(proposal.payload.get("unit"))
    provenance = observation_promotion_support.build_source_measurement_provenance_request(
        proposal=proposal, mapping_confidence=assessment_confidence(assessment)
    )
    return KernelObservationCreateRequest(
        subject_id=UUID(subject_id),
        variable_id=_require_payload_string(proposal.payload, field_name="variable_id"),
        value=proposal.payload["value"],
        unit=unit,
        provenance=provenance,
        observation_origin="AI_AUTHORED" if provenance is not None else "MANUAL",
        confidence=assessment_confidence(assessment),
    )


def _resolve_payload_entity_id(  # noqa: PLR0913
    *,
    payload: JSONObject,
    field_name: str,
    label_field_name: str,
    metadata: JSONObject,
    metadata_label_field_name: str,
    space_id: UUID,
    graph_api_gateway: GraphTransportBundle,
) -> UUID:
    raw_value = resolve_entity_reference_value(
        payload=payload,
        field_name=field_name,
        label_field_name=label_field_name,
        metadata=metadata,
        metadata_label_field_name=metadata_label_field_name,
    )
    try:
        return UUID(raw_value)
    except ValueError:
        pass

    candidate_payload = optional_payload_object(
        payload,
        field_name=entity_candidate_field_name(field_name),
    )
    label = _resolve_payload_entity_label(
        payload=payload,
        value=raw_value,
        label_field_name=label_field_name,
        metadata=metadata,
        metadata_label_field_name=metadata_label_field_name,
    )
    resolved = resolve_graph_entity_label(
        space_id=space_id,
        label=label,
        graph_api_gateway=graph_api_gateway,
    )
    if resolved is None:
        if candidate_payload is not None:
            resolved = _create_graph_entity_from_candidate_payload(
                space_id=space_id,
                candidate_payload=candidate_payload,
                fallback_label=label,
                graph_api_gateway=graph_api_gateway,
            )
        else:
            resolved = _create_graph_entity_for_label(
                space_id=space_id,
                label=label,
                graph_api_gateway=graph_api_gateway,
            )
    resolved_id = resolved.get("id")
    if not isinstance(resolved_id, str) or resolved_id.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Graph entity resolution returned an invalid id",
        )
    return UUID(resolved_id)


def _create_graph_entity_from_candidate_payload(
    *,
    space_id: UUID,
    candidate_payload: JSONObject,
    fallback_label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    display_label = payload_entity_display_label(candidate_payload)
    entity_type = optional_json_string(candidate_payload.get("entity_type")) or (
        infer_graph_entity_type_from_label(display_label)
    )
    metadata = payload_entity_metadata(candidate_payload)
    anchors = candidate_payload.get("anchors")
    if isinstance(anchors, dict) and anchors:
        metadata = {
            **metadata,
            "source_anchors": {
                str(key): value
                for key, value in anchors.items()
            },
        }
    try:
        resolved_intent = preflight_service.prepare_entity_create(
            space_id=space_id,
            entity_type=entity_type,
            display_label=display_label,
            aliases=payload_entity_aliases(candidate_payload),
            metadata=metadata,
            identifiers=payload_entity_identifiers(candidate_payload),
            graph_transport=graph_api_gateway,
        )
        created = submission_service.submit_resolved_intent(
            resolved_intent=resolved_intent,
            graph_transport=graph_api_gateway,
        )
    except GraphServiceClientError as exc:
        status_code, detail = graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    if not isinstance(created, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to create graph entity for '{fallback_label}': invalid "
                "response payload"
            ),
        )

    nested_entity = created.get("entity")
    entity_payload = nested_entity if isinstance(nested_entity, dict) else created
    resolved_id = entity_payload.get("id")
    if not isinstance(resolved_id, str) or not resolved_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(f"Failed to create graph entity for '{fallback_label}': missing entity id"),
        )

    resolved_display_label = entity_payload.get("display_label")
    return {
        "id": resolved_id,
        "display_label": (
            resolved_display_label
            if isinstance(resolved_display_label, str) and resolved_display_label.strip()
            else display_label
        ),
        "created": bool(created.get("created")) if "created" in created else None,
    }


def _create_graph_entity_for_label(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    try:
        resolved_intent = preflight_service.prepare_entity_create(
            space_id=space_id,
            entity_type=infer_graph_entity_type_from_label(label),
            display_label=label,
            aliases=None,
            metadata=None,
            identifiers=None,
            graph_transport=graph_api_gateway,
        )
        created = submission_service.submit_resolved_intent(
            resolved_intent=resolved_intent,
            graph_transport=graph_api_gateway,
        )
    except GraphServiceClientError as exc:
        status_code, detail = graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc

    if not isinstance(created, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to create graph entity for '{label}': invalid response payload"
            ),
        )

    nested_entity = created.get("entity")
    entity_payload = nested_entity if isinstance(nested_entity, dict) else created
    resolved_id = entity_payload.get("id")
    if not isinstance(resolved_id, str) or resolved_id.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(f"Failed to create graph entity for '{label}': missing entity id"),
        )

    display_label = entity_payload.get("display_label")
    return {
        "id": resolved_id,
        "display_label": (
            display_label
            if isinstance(display_label, str) and display_label.strip() != ""
            else label
        ),
        "created": (
            bool(created.get("created"))
            if isinstance(created, dict) and "created" in created
            else None
        ),
    }


def _resolve_payload_entity_label(
    *,
    payload: JSONObject,
    value: str,
    label_field_name: str,
    metadata: JSONObject,
    metadata_label_field_name: str,
) -> str:
    payload_label = payload.get(label_field_name)
    if isinstance(payload_label, str) and payload_label.strip() != "":
        return payload_label.strip()

    metadata_label = metadata.get(metadata_label_field_name)
    if isinstance(metadata_label, str) and metadata_label.strip() != "":
        return metadata_label.strip()

    if value.startswith("unresolved:"):
        unresolved_label = value.removeprefix("unresolved:").replace("_", " ").strip()
        if unresolved_label != "":
            return unresolved_label

    if value.strip() != "":
        return value.strip()

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Proposal payload field '{field_name_from_label_field(label_field_name)}' "
            "is required to resolve deferred graph entities"
        ),
    )


def build_manual_hypothesis_request(
    *,
    proposal: HarnessProposalRecord,
) -> CreateManualHypothesisRequest:
    """Build one manual-hypothesis creation request from a mechanism proposal."""
    if proposal.proposal_type != "mechanism_candidate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "manual hypothesis promotion"
            ),
        )
    return CreateManualHypothesisRequest(
        statement=_require_payload_string(
            proposal.payload,
            field_name="hypothesis_statement",
        ),
        rationale=_require_payload_string(
            proposal.payload,
            field_name="hypothesis_rationale",
        ),
        seed_entity_ids=_require_payload_string_list(
            proposal.payload,
            field_name="seed_entity_ids",
        ),
        source_type=_require_payload_string(
            proposal.payload,
            field_name="source_type",
        ),
    )


def _require_source_document_for_promotion(
    source_document: HarnessDocumentRecord | None,
) -> HarnessDocumentRecord:
    if source_document is None:
        raise SourceProvenanceError(
            "missing_source_document",
            "Canonical promotion requires the proposal's stored source document.",
        )
    return source_document


def promote_to_graph_claim(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
    source_document: HarnessDocumentRecord | None = None,
) -> JSONObject:
    """Promote a harness proposal to the graph.

    Prefer a RESOLVED+SUPPORT claim materialized into a canonical relation.
    When the active graph constraints reject that canonical triple, keep the
    review action useful by storing an open graph claim instead.
    """
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    try:
        source_document = _require_source_document_for_promotion(source_document)
        source_provenance = verify_persisted_source_provenance(
            document=source_document,
            proposal=proposal,
        )
        _proposal_source_document_uuid(proposal)
    except SourceProvenanceError as exc:
        return _promote_to_open_graph_claim(
            space_id=space_id,
            proposal=proposal,
            request_metadata={
                **request_metadata,
                "canonical_promotion_blocked": True,
                "canonical_promotion_error": str(exc),
                "source_provenance_status": "invalid",
                "source_provenance_reason_code": exc.reason_code,
            },
            graph_api_gateway=graph_api_gateway,
            source_provenance=None,
            source_provenance_reason_code=exc.reason_code,
        )
    try:
        relation_request = build_graph_relation_request(
            space_id=space_id,
            proposal=proposal,
            request_metadata=request_metadata,
            graph_api_gateway=graph_api_gateway,
            source_provenance=source_provenance,
        )
        resolved_intent = _run_async_preflight(
            preflight_service.prepare_relation_create(
                space_id=space_id,
                request=relation_request,
                graph_transport=graph_api_gateway,
            ),
        )
        relation = submission_service.submit_resolved_intent(
            resolved_intent=resolved_intent,
            graph_transport=graph_api_gateway,
        )
    except GraphServiceClientError as exc:
        if is_relation_constraint_error(exc):
            return _promote_to_open_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata={
                    **request_metadata,
                    "canonical_promotion_blocked": True,
                    "canonical_promotion_error": extract_graph_service_error_detail(
                        exc,
                    ),
                },
                graph_api_gateway=graph_api_gateway,
                source_provenance=source_provenance,
            )
        status_code, detail = graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    relation_response = cast("KernelRelationResponse", relation)
    source_claim_id = relation_response.source_claim_id
    return {
        "graph_claim_id": str(source_claim_id) if source_claim_id is not None else None,
        "graph_claim_status": "RESOLVED",
        "graph_claim_validation_state": "ALLOWED",
        "graph_claim_persistability": "PERSISTABLE",
        "graph_claim_polarity": "SUPPORT",
        "graph_relation_id": str(relation_response.id),
        "graph_relation_curation_status": relation_response.curation_status,
        "graph_promotion_mode": "canonical_relation",
        "source_provenance_status": "verified",
        "source_provenance_reason_code": None,
    }


def _promote_to_open_graph_claim(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
    source_provenance: ResolvedSourceProvenance | None = None,
    source_provenance_reason_code: str | None = None,
) -> JSONObject:
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    try:
        claim_request = build_graph_claim_request(
            space_id=space_id,
            proposal=proposal,
            request_metadata=request_metadata,
            graph_api_gateway=graph_api_gateway,
            source_provenance=source_provenance,
            source_provenance_reason_code=source_provenance_reason_code,
        )
        resolved_intent = _run_async_preflight(
            preflight_service.prepare_claim_create(
                space_id=space_id,
                request=claim_request,
                graph_transport=graph_api_gateway,
            ),
        )
        claim = submission_service.submit_resolved_intent(
            resolved_intent=resolved_intent,
            graph_transport=graph_api_gateway,
        )
    except GraphServiceClientError as exc:
        status_code, detail = graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    return {
        **_graph_claim_promotion_result(
            claim=cast("KernelRelationClaimResponse", claim)
        ),
        "source_provenance_status": (
            "verified"
            if source_provenance is not None
            else "invalid"
            if source_provenance_reason_code is not None
            else "unverified"
        ),
        "source_provenance_reason_code": source_provenance_reason_code,
    }


def _graph_claim_promotion_result(
    *,
    claim: KernelRelationClaimResponse,
) -> JSONObject:
    linked_relation_id = claim.linked_relation_id
    return {
        "graph_claim_id": str(claim.id),
        "graph_claim_status": claim.claim_status,
        "graph_claim_validation_state": claim.validation_state,
        "graph_claim_persistability": claim.persistability,
        "graph_claim_polarity": claim.polarity,
        "graph_relation_id": (
            str(linked_relation_id) if linked_relation_id is not None else None
        ),
        "graph_relation_curation_status": None,
        "graph_promotion_mode": "claim",
    }


def promote_to_graph_entity(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    """Create or resolve one graph entity from a staged entity proposal."""
    if proposal.proposal_type != "entity_candidate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "graph entity promotion"
            ),
        )
    created = _create_graph_entity_from_candidate_payload(
        space_id=space_id,
        candidate_payload=proposal.payload,
        fallback_label=payload_entity_display_label(proposal.payload),
        graph_api_gateway=graph_api_gateway,
    )
    entity_id = created.get("id")
    if not isinstance(entity_id, str) or not entity_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Graph entity promotion returned an invalid id",
        )
    display_label = created.get("display_label")
    return {
        "graph_entity_id": entity_id,
        "graph_entity_display_label": (
            display_label if isinstance(display_label, str) and display_label.strip() else None
        ),
        "graph_entity_created": created.get("created"),
    }


def promote_to_graph_observation(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    """Create one observation from a staged observation proposal."""
    if proposal.proposal_type != "observation_candidate":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Proposal type '{proposal.proposal_type}' is not supported for "
                "graph observation promotion"
            ),
        )
    request = build_graph_observation_request(
        space_id=space_id,
        proposal=proposal,
        graph_api_gateway=graph_api_gateway,
    )
    validation_transport = getattr(graph_api_gateway, "validation", None)
    if validation_transport is not None and hasattr(
        validation_transport,
        "validate_observation_create",
    ):
        validation = validation_transport.validate_observation_create(
            space_id=space_id,
            request=request,
        )
        if not validation.valid or validation.persistability != "PERSISTABLE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation.message,
            )
    submission_service = _graph_submission_service()
    try:
        observation = submission_service.record_observation(
            space_id=space_id,
            request=request,
            graph_transport=graph_api_gateway,
        )
    except GraphServiceClientError as exc:
        status_code, detail = graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    return observation_promotion_support.graph_observation_promotion_result(
        observation=observation,
    )


def promote_to_graph_hypothesis(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    """Create one manual graph hypothesis from a staged mechanism proposal."""
    try:
        hypothesis = graph_api_gateway.create_manual_hypothesis(
            space_id=space_id,
            request=build_manual_hypothesis_request(proposal=proposal),
        )
    except GraphServiceClientError as exc:
        status_code, detail = graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    return {
        "graph_hypothesis_claim_id": str(hypothesis.claim_id),
        "graph_hypothesis_origin": hypothesis.origin,
        "graph_hypothesis_claim_status": hypothesis.claim_status,
        "graph_hypothesis_validation_state": hypothesis.validation_state,
        "graph_hypothesis_persistability": hypothesis.persistability,
    }


def decide_proposal(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposal_id: UUID | str,
    decision_status: str,
    decision_reason: str | None,
    request_metadata: JSONObject,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    decision_metadata: JSONObject | None = None,
    event_payload: JSONObject | None = None,
    workspace_patch: JSONObject | None = None,
) -> HarnessProposalRecord:
    """Persist one proposal decision and update its originating run state."""
    proposal = require_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        proposal_store=proposal_store,
    )
    merged_metadata = {
        **request_metadata,
        **(decision_metadata or {}),
    }
    try:
        updated = proposal_store.decide_proposal(
            space_id=space_id,
            proposal_id=proposal_id,
            status=decision_status,
            decision_reason=decision_reason,
            metadata=merged_metadata,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if "already decided" in str(exc)
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found in space '{space_id}'",
        )

    run = run_registry.get_run(space_id=space_id, run_id=proposal.run_id)
    if run is not None:
        proposals_for_run = proposal_store.list_proposals(
            space_id=space_id,
            run_id=proposal.run_id,
        )
        proposal_counts = status_counts(proposals_for_run)
        run_registry.record_event(
            space_id=space_id,
            run_id=proposal.run_id,
            event_type=f"proposal.{decision_status}",
            message=f"Proposal '{proposal.id}' marked {decision_status}.",
            payload={
                "proposal_id": proposal.id,
                "proposal_type": proposal.proposal_type,
                "status_counts": proposal_counts,
                "reason": decision_reason,
                "metadata": merged_metadata,
                **(event_payload or {}),
            },
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=proposal.run_id,
            patch={
                "proposal_counts": proposal_counts,
                "last_proposal_id": proposal.id,
                "last_proposal_status": decision_status,
                (
                    "last_promoted_proposal_id"
                    if decision_status == "promoted"
                    else "last_rejected_proposal_id"
                ): proposal.id,
                **(workspace_patch or {}),
            },
        )
    return updated


__all__ = [
    "build_graph_observation_request",
    "build_manual_hypothesis_request",
    "build_graph_claim_request",
    "decide_proposal",
    "promote_to_graph_claim",
    "promote_to_graph_entity",
    "promote_to_graph_hypothesis",
    "promote_to_graph_observation",
    "require_proposal",
    "status_counts",
]
