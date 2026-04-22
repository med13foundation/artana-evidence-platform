"""Shared proposal promotion and rejection helpers for harness workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.confidence_assessment import (
    assessment_confidence_metadata,
    proposal_fact_assessment,
)
from artana_evidence_api.document_extraction import resolve_graph_entity_label
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.graph_integration.submission import (
    GraphWorkflowSubmissionService,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.types.graph_contracts import (
    ClaimAIProvenanceEnvelope,
    CreateManualHypothesisRequest,
    KernelObservationCreateRequest,
    KernelObservationResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimResponse,
    KernelRelationCreateRequest,
)
from artana_evidence_api.types.graph_fact_assessment import assessment_confidence
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )

_NON_GENE_DISEASE_LABELS = frozenset({"ADHD", "ASD"})
_DISEASE_HINTS = (
    "disease",
    "disorder",
    "encephalopathy",
    "cardiomyopathy",
    "cancer",
    "tumor",
    "tumour",
    "autism",
)
_PHENOTYPE_HINTS = (
    "phenotype",
    "delay",
    "impairment",
    "defect",
    "disability",
    "dd/id",
    "developmental",
)
_DRUG_SUFFIXES = (
    "nib",
    "mab",
    "zumab",
    "ximab",
    "tinib",
    "rafenib",
    "ciclib",
    "lisib",
    "parin",
    "parib",
    "platin",
    "statin",
    "olol",
    "pril",
    "sartan",
    "floxacin",
    "mycin",
    "cillin",
    "azole",
    "vir",
    "navir",
    "previr",
)


def _stable_json_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _metadata_text(
    metadata: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default
_DISEASE_SUFFIXES = (
    "oma",
    "emia",
    "itis",
    "osis",
    "pathy",
    "trophy",
    "plasia",
    "ectomy",
)
_PATHWAY_HINTS = ("pathway", "signaling", "signalling", "cascade", "network")
_RELATION_CONSTRAINT_ERROR_RE = re.compile(
    r"relation \((?P<triple>[^)]+)\) is not allowed by ACTIVE relation constraints",
    re.IGNORECASE,
)
_EXACT_RELATION_CONSTRAINT_PROMOTION_RE = re.compile(
    r"Triple \((?P<triple>[^)]+)\) requires an active exact relation constraint before promotion\.",
    re.IGNORECASE,
)
_SQLALCHEMY_SQL_MARKER = "[SQL:"
_SQLALCHEMY_BACKGROUND_MARKER = "Background on this error at:"
_KNOWN_GENE_SYMBOLS = frozenset(
    {
        "TP53",
        "BRCA1",
        "BRCA2",
        "EGFR",
        "KRAS",
        "BRAF",
        "MYC",
        "RB1",
        "PTEN",
        "PIK3CA",
        "AKT1",
        "CDKN2A",
        "NF1",
        "NF2",
        "KDR",
        "VEGFR2",
        "PTPRB",
        "PLCG1",
        "FLT1",
        "FLT4",
        "PDGFRA",
        "KIT",
        "ALK",
        "ROS1",
        "MET",
        "RET",
        "FGFR1",
        "FGFR2",
        "FGFR3",
        "JAK2",
        "IDH1",
        "IDH2",
        "ARID1A",
        "ATM",
        "ERBB2",
        "HER2",
        "APC",
        "VHL",
        "WT1",
        "MDM2",
        "SNCA",
        "LRRK2",
        "PARK2",
        "GBA",
        "SOD1",
        "FUS",
        "TARDBP",
        "HTT",
        "CFTR",
        "SMN1",
        "DMD",
        "FMR1",
    },
)
_MAX_GENE_SYMBOL_LENGTH = 10


@lru_cache(maxsize=1)
def _graph_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()


@lru_cache(maxsize=1)
def _graph_submission_service() -> GraphWorkflowSubmissionService:
    return GraphWorkflowSubmissionService()


def _run_async_preflight(awaitable):  # type: ignore[no-untyped-def]
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
    return result["value"]


def _message_from_graph_detail_mapping(
    parsed: object,
    *,
    fallback: str,
) -> str:
    if not isinstance(parsed, dict):
        return fallback

    nested_detail = parsed.get("detail")
    if isinstance(nested_detail, str) and nested_detail.strip() != "":
        return nested_detail.strip()

    nested_message = parsed.get("message")
    if isinstance(nested_message, str) and nested_message.strip() != "":
        return nested_message.strip()

    return fallback


def _normalize_raw_graph_detail(raw_detail: str | None) -> str:
    if not isinstance(raw_detail, str):
        return ""

    stripped = raw_detail.strip()
    if stripped == "":
        return ""

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped
    return _message_from_graph_detail_mapping(parsed, fallback=stripped)


def _strip_sqlalchemy_detail_noise(detail: str) -> str:
    if _SQLALCHEMY_SQL_MARKER in detail:
        detail = detail.split(_SQLALCHEMY_SQL_MARKER, 1)[0].rstrip()
    if _SQLALCHEMY_BACKGROUND_MARKER in detail:
        detail = detail.split(_SQLALCHEMY_BACKGROUND_MARKER, 1)[0].rstrip()
    return detail.strip()


def _looks_like_gene_symbol(label: str) -> bool:
    normalized = label.strip()
    upper = normalized.upper()
    if upper in _KNOWN_GENE_SYMBOLS:
        return True
    return (
        len(normalized) <= _MAX_GENE_SYMBOL_LENGTH
        and normalized.isascii()
        and normalized == upper
        and any(character.isalpha() for character in normalized)
        and any(character.isdigit() for character in normalized)
    )


def _looks_like_gene_family(label: str) -> bool:
    parts = [part.strip() for part in re.split(r"[\\/]", label) if part.strip() != ""]
    return len(parts) > 1 and all(_looks_like_gene_symbol(part) for part in parts)


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


def infer_graph_entity_type_from_label(label: str) -> str:
    """Infer one graph entity type for unresolved promotion labels."""
    normalized_label = label.strip()
    lowered = normalized_label.casefold()
    entity_type = "PHENOTYPE"
    if (
        normalized_label.upper() in _NON_GENE_DISEASE_LABELS
        or any(token in lowered for token in _DISEASE_HINTS)
        or any(
            lowered.endswith(suffix) and len(normalized_label) > len(suffix) + 2
            for suffix in _DISEASE_SUFFIXES
        )
    ):
        entity_type = "DISEASE"
    elif any(token in lowered for token in _PHENOTYPE_HINTS):
        entity_type = "PHENOTYPE"
    elif "complex" in lowered:
        entity_type = "PROTEIN_COMPLEX"
    elif any(token in lowered for token in _PATHWAY_HINTS):
        entity_type = "SIGNALING_PATHWAY"
    elif any(lowered.endswith(suffix) for suffix in _DRUG_SUFFIXES):
        entity_type = "DRUG"
    elif "syndrome" in lowered:
        entity_type = "SYNDROME"
    elif _looks_like_gene_family(normalized_label) or _looks_like_gene_symbol(
        normalized_label,
    ):
        entity_type = "GENE"
    return entity_type


def _extract_graph_service_error_detail(
    exc: GraphServiceClientError,
) -> str:
    detail = _normalize_raw_graph_detail(exc.detail)
    if detail == "":
        detail = str(exc)
    return _strip_sqlalchemy_detail_noise(detail)


def _graph_promotion_error_response(
    exc: GraphServiceClientError,
) -> tuple[int, str]:
    detail = _extract_graph_service_error_detail(exc)
    triple_match = _RELATION_CONSTRAINT_ERROR_RE.search(detail)
    if triple_match is None:
        triple_match = _EXACT_RELATION_CONSTRAINT_PROMOTION_RE.search(detail)
    if triple_match is not None:
        triple = " ".join(triple_match.group("triple").split())
        return (
            status.HTTP_409_CONFLICT,
            (
                "This proposal cannot be promoted as a canonical relation because "
                f"the active graph constraints do not allow {triple}. Review the "
                "claim structure or relation type before promoting."
            ),
        )

    return (
        exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
        detail or str(exc),
    )


def _is_relation_constraint_error(exc: GraphServiceClientError) -> bool:
    detail = _extract_graph_service_error_detail(exc)
    return (
        _RELATION_CONSTRAINT_ERROR_RE.search(detail) is not None
        or _EXACT_RELATION_CONSTRAINT_PROMOTION_RE.search(detail) is not None
    )


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


def _optional_json_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _resolve_entity_reference_value(
    *,
    payload: JSONObject,
    field_name: str,
    label_field_name: str,
    metadata: JSONObject,
    metadata_label_field_name: str,
) -> str:
    raw_value = _optional_json_string(payload.get(field_name))
    if raw_value is not None:
        return raw_value

    payload_label = _optional_json_string(payload.get(label_field_name))
    if payload_label is not None:
        return f"unresolved:{payload_label}"

    metadata_label = _optional_json_string(metadata.get(metadata_label_field_name))
    if metadata_label is not None:
        return f"unresolved:{metadata_label}"

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Proposal payload is missing required '{field_name}' or "
            f"'{label_field_name}' for graph promotion"
        ),
    )


def _entity_candidate_field_name(field_name: str) -> str:
    if field_name == "proposed_subject":
        return "proposed_subject_entity_candidate"
    if field_name == "proposed_object":
        return "proposed_object_entity_candidate"
    return "subject_entity_candidate"


def _optional_payload_object(
    payload: JSONObject,
    *,
    field_name: str,
) -> JSONObject | None:
    raw_value = payload.get(field_name)
    if not isinstance(raw_value, dict):
        return None
    return {
        str(key): value
        for key, value in raw_value.items()
    }


def _payload_entity_aliases(candidate_payload: JSONObject) -> list[str]:
    raw_aliases = candidate_payload.get("aliases")
    if not isinstance(raw_aliases, list):
        return []
    aliases: list[str] = []
    seen: set[str] = set()
    for item in raw_aliases:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if not trimmed:
            continue
        key = trimmed.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(trimmed)
    return aliases


def _payload_entity_metadata(candidate_payload: JSONObject) -> JSONObject:
    raw_metadata = candidate_payload.get("metadata")
    if not isinstance(raw_metadata, dict):
        return {}
    return {
        str(key): value
        for key, value in raw_metadata.items()
    }


def _payload_entity_identifiers(
    candidate_payload: JSONObject,
) -> dict[str, str]:
    raw_identifiers = candidate_payload.get("identifiers")
    identifiers: dict[str, str] = {}
    if isinstance(raw_identifiers, dict):
        for key, value in raw_identifiers.items():
            if not isinstance(value, str) or not value.strip():
                continue
            identifiers[str(key)] = value.strip()
    raw_anchors = candidate_payload.get("anchors")
    if isinstance(raw_anchors, dict):
        for key in ("gene_symbol", "hgvs_notation", "hpo_term"):
            value = raw_anchors.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            identifiers.setdefault(key, value.strip())
    return identifiers


def _payload_entity_display_label(candidate_payload: JSONObject) -> str:
    for key in ("display_label", "label"):
        value = candidate_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Entity candidate payload is missing 'label' or 'display_label'",
    )


def _candidate_resolution_labels(candidate_payload: JSONObject) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    def _add(value: object) -> None:
        if not isinstance(value, str):
            return
        trimmed = value.strip()
        if trimmed == "":
            return
        key = trimmed.casefold()
        if key in seen:
            return
        seen.add(key)
        labels.append(trimmed)

    for key in ("display_label", "label"):
        _add(candidate_payload.get(key))
    for alias in _payload_entity_aliases(candidate_payload):
        _add(alias)
    for identifier_value in _payload_entity_identifiers(candidate_payload).values():
        _add(identifier_value)
    anchors = candidate_payload.get("anchors")
    if isinstance(anchors, dict):
        for value in anchors.values():
            _add(value)
    return labels


def _resolve_existing_entity_from_candidate_payload(
    *,
    space_id: UUID,
    candidate_payload: JSONObject,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject | None:
    for label in _candidate_resolution_labels(candidate_payload):
        resolved = resolve_graph_entity_label(
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_api_gateway,
        )
        if resolved is not None:
            return resolved
    return None


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


def build_graph_claim_request(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
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
    source_document_ref = f"harness_proposal:{proposal.id}"
    input_hash = _stable_json_hash(
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
        source_document_ref=source_document_ref,
        source_ref=f"harness-proposal-claim:{proposal.id}",
        agent_run_id=agent_run_id_value,
        ai_provenance=ClaimAIProvenanceEnvelope(
            model_id=_metadata_text(
                proposal.metadata,
                "model_id",
                default="artana-kernel",
            ),
            model_version=_metadata_text(
                proposal.metadata,
                "model_version",
                default="unknown",
            ),
            prompt_id=_metadata_text(
                proposal.metadata,
                "prompt_id",
                default=f"harness_proposal:{proposal.proposal_type}",
            ),
            prompt_version=_metadata_text(
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
            **proposal.metadata,
            **request_metadata,
            **assessment_confidence_metadata(assessment),
            "proposal_id": proposal.id,
            "document_id": proposal.document_id,
            "harness_run_id": proposal.run_id,
            "proposal_type": proposal.proposal_type,
            "source_kind": proposal.source_kind,
            "source_key": proposal.source_key,
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
    reasoning = proposal.reasoning_path.get("reasoning")
    evidence_sentence = (
        reasoning
        if isinstance(reasoning, str) and reasoning.strip() != ""
        else proposal.summary
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
        evidence_sentence=evidence_sentence,
        evidence_sentence_source="artana_generated",
        evidence_sentence_confidence="medium",
        source_document_ref=f"harness_proposal:{proposal.id}",
        metadata={
            **proposal.metadata,
            **request_metadata,
            **assessment_confidence_metadata(assessment),
            "proposal_id": proposal.id,
            "document_id": proposal.document_id,
            "harness_run_id": proposal.run_id,
            "proposal_type": proposal.proposal_type,
            "source_kind": proposal.source_kind,
            "source_key": proposal.source_key,
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
    subject_candidate = _optional_payload_object(
        proposal.payload,
        field_name="subject_entity_candidate",
    )
    if subject_candidate is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Observation proposal payload is missing 'subject_entity_candidate'",
        )
    subject_label = _payload_entity_display_label(subject_candidate)
    subject_resolution = _resolve_existing_entity_from_candidate_payload(
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
    unit = _optional_json_string(proposal.payload.get("unit"))
    return KernelObservationCreateRequest(
        subject_id=UUID(subject_id),
        variable_id=_require_payload_string(proposal.payload, field_name="variable_id"),
        value=proposal.payload["value"],
        unit=unit,
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
    raw_value = _resolve_entity_reference_value(
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

    candidate_payload = _optional_payload_object(
        payload,
        field_name=_entity_candidate_field_name(field_name),
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
    display_label = _payload_entity_display_label(candidate_payload)
    entity_type = _optional_json_string(candidate_payload.get("entity_type")) or (
        infer_graph_entity_type_from_label(display_label)
    )
    metadata = _payload_entity_metadata(candidate_payload)
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
            aliases=_payload_entity_aliases(candidate_payload),
            metadata=metadata,
            identifiers=_payload_entity_identifiers(candidate_payload),
            graph_transport=graph_api_gateway,
        )
        created = submission_service.submit_resolved_intent(
            resolved_intent=resolved_intent,
            graph_transport=graph_api_gateway,
        )
    except GraphServiceClientError as exc:
        status_code, detail = _graph_promotion_error_response(exc)
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
        status_code, detail = _graph_promotion_error_response(exc)
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


def field_name_from_label_field(label_field_name: str) -> str:
    if label_field_name == "proposed_subject_label":
        return "proposed_subject_label"
    if label_field_name == "proposed_object_label":
        return "proposed_object_label"
    return label_field_name


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


def promote_to_graph_claim(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    """Promote a harness proposal to the graph.

    Prefer a RESOLVED+SUPPORT claim materialized into a canonical relation.
    When the active graph constraints reject that canonical triple, keep the
    review action useful by storing an open graph claim instead.
    """
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    try:
        relation_request = build_graph_relation_request(
            space_id=space_id,
            proposal=proposal,
            request_metadata=request_metadata,
            graph_api_gateway=graph_api_gateway,
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
        if _is_relation_constraint_error(exc):
            return _promote_to_open_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata={
                    **request_metadata,
                    "canonical_promotion_blocked": True,
                    "canonical_promotion_error": _extract_graph_service_error_detail(
                        exc,
                    ),
                },
                graph_api_gateway=graph_api_gateway,
            )
        status_code, detail = _graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    source_claim_id = relation.source_claim_id
    return {
        "graph_claim_id": str(source_claim_id) if source_claim_id is not None else None,
        "graph_claim_status": "RESOLVED",
        "graph_claim_validation_state": "ALLOWED",
        "graph_claim_persistability": "PERSISTABLE",
        "graph_claim_polarity": "SUPPORT",
        "graph_relation_id": str(relation.id),
        "graph_relation_curation_status": relation.curation_status,
        "graph_promotion_mode": "canonical_relation",
    }


def _promote_to_open_graph_claim(
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    request_metadata: JSONObject,
    graph_api_gateway: GraphTransportBundle,
) -> JSONObject:
    preflight_service = _graph_preflight_service()
    submission_service = _graph_submission_service()
    try:
        claim_request = build_graph_claim_request(
            space_id=space_id,
            proposal=proposal,
            request_metadata=request_metadata,
            graph_api_gateway=graph_api_gateway,
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
        status_code, detail = _graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    return _graph_claim_promotion_result(claim=claim)


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
        fallback_label=_payload_entity_display_label(proposal.payload),
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
        status_code, detail = _graph_promotion_error_response(exc)
        raise HTTPException(
            status_code=status_code,
            detail=detail,
        ) from exc
    return _graph_observation_promotion_result(observation=observation)


def _graph_observation_promotion_result(
    *,
    observation: KernelObservationResponse,
) -> JSONObject:
    return {
        "graph_observation_id": str(observation.id),
        "graph_observation_subject_id": str(observation.subject_id),
        "graph_observation_variable_id": observation.variable_id,
    }


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
        status_code, detail = _graph_promotion_error_response(exc)
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
