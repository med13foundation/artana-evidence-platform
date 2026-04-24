"""Observation bridge helpers for research-init documents."""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from artana_evidence_api.db_schema import resolve_harness_db_schema
from artana_evidence_api.document_extraction import (
    resolve_graph_entity_label,
)
from artana_evidence_api.graph_db_schema import resolve_graph_db_schema
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.graph_integration.submission import (
    GraphWorkflowSubmissionService,
)
from artana_evidence_api.proposal_actions import infer_graph_entity_type_from_label
from artana_evidence_api.source_document_bridges import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocumentRepositoryProtocol,
    SourceType,
    build_source_document,
    build_source_document_repository,
    create_observation_bridge_entity_recognition_service,
    source_document_extraction_status_value,
    source_document_id,
    source_document_metadata,
    source_document_model_copy,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
    )


from artana_evidence_api.research_init_models import (
    _NoOpPipelineRunEventRepository,
    _ObservationBridgeBatchResult,
    _PubMedObservationSyncResult,
)


class _ObservationBridgeSummaryLike(Protocol):
    derived_graph_seed_entity_ids: tuple[str, ...]
    errors: tuple[str, ...]


_TOTAL_PROGRESS_STEPS = 5
_DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT = 4
_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS = 30.0
_PUBMED_QUERY_CONCURRENCY_LIMIT = 2
_MIN_CHASE_ENTITIES = 3
_MAX_CHASE_CANDIDATES = 10
_OBSERVATION_BRIDGE_AGENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_EXTRACTION_STAGE_TIMEOUT_SECONDS = 120.0
_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS = 45.0
_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_BATCH_SIZE = 3
_PUBMED_REPLAY_ARTIFACT_KEY = "research_init_pubmed_replay_bundle"
_STRUCTURED_REPLAY_SOURCE_KEYS = frozenset(
    {
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
        "mgi",
        "zfin",
        "marrvel",
    },
)
_STRUCTURED_REPLAY_SOURCE_KIND_TO_KEY = {
    "clinvar_enrichment": "clinvar",
    "drugbank_enrichment": "drugbank",
    "alphafold_enrichment": "alphafold",
    "clinicaltrials_enrichment": "clinical_trials",
    "mgi_enrichment": "mgi",
    "zfin_enrichment": "zfin",
    "marrvel_enrichment": "marrvel",
}
_MIN_GENE_FAMILY_TOKEN_LENGTH = 4



def _research_init_pubmed_source_id(space_id: UUID) -> UUID:
    """Return a stable hidden shared-source id for research-init PubMed docs."""
    return uuid5(NAMESPACE_URL, f"research-init-pubmed-source:{space_id}")

def _research_init_upload_source_id(space_id: UUID) -> UUID:
    """Return a stable hidden shared-source id for research-init uploaded docs."""
    return uuid5(NAMESPACE_URL, f"research-init-upload-source:{space_id}")

def _build_pubmed_raw_record_from_document(
    document: HarnessDocumentRecord,
) -> JSONObject:
    """Build the shared PubMed raw-record shape from one harness document."""
    metadata = document.metadata
    pubmed_metadata = json_object_or_empty(metadata.get("pubmed"))
    source_queries = metadata.get("source_queries")
    queries = (
        [item for item in source_queries if isinstance(item, str) and item.strip()]
        if isinstance(source_queries, list)
        else []
    )
    raw_record: JSONObject = {
        "title": document.title,
        "abstract": document.text_content,
        "text": document.text_content,
        "source": "research-init-pubmed",
        "source_queries": queries,
    }
    for source_key, target_key in (
        ("pmid", "pubmed_id"),
        ("doi", "doi"),
        ("pmc_id", "pmc_id"),
        ("journal", "journal"),
    ):
        value = pubmed_metadata.get(source_key)
        if isinstance(value, str) and value.strip():
            normalized_value = value.strip()
            raw_record[target_key] = normalized_value
            if source_key == "pmid":
                raw_record["pmid"] = normalized_value
    return raw_record

def _compute_pubmed_payload_hash(record: JSONObject) -> str:
    """Return a stable hash for one bridged PubMed raw record."""
    serialized = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

def _build_pubmed_external_record_id(record: JSONObject) -> str:
    """Return the canonical PubMed external record id for one bridged record."""
    for key in ("pmid", "pubmed_id", "doi"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            if key == "doi":
                normalized = normalized.lower()
            return f"pubmed:{key}:{normalized}"
        if isinstance(value, int):
            return f"pubmed:{key}:{value}"
    return f"pubmed:hash:{_compute_pubmed_payload_hash(record)}"

def _build_file_upload_raw_record_from_document(
    document: HarnessDocumentRecord,
) -> JSONObject:
    """Build the shared raw-record shape for uploaded text/PDF documents."""
    raw_record: JSONObject = {
        "title": document.title,
        "source": f"research-init-{document.source_type}",
        "text": document.text_content,
        "full_text": document.text_content,
        "full_text_source": (
            "research_init_pdf_enrichment"
            if document.source_type == "pdf"
            else "research_init_text"
        ),
        "media_type": document.media_type,
    }
    if document.filename is not None and document.filename.strip():
        raw_record["filename"] = document.filename.strip()
    if document.page_count is not None:
        raw_record["page_count"] = document.page_count
    return raw_record

def _extract_graph_entity_id(entity_payload: object) -> str | None:
    """Extract one graph entity id from a service response payload."""
    if not isinstance(entity_payload, dict):
        return None
    nested_entity = entity_payload.get("entity")
    resolved_payload = (
        nested_entity if isinstance(nested_entity, dict) else entity_payload
    )
    entity_id = resolved_payload.get("id")
    if not isinstance(entity_id, str) or entity_id.strip() == "":
        return None
    return entity_id.strip()

def _append_unique_entity_ids(
    *,
    target: list[str],
    entity_ids: Sequence[str],
) -> None:
    """Append UUID-backed entity ids while preserving order and uniqueness."""
    seen = set(target)
    for entity_id in entity_ids:
        if entity_id in seen:
            continue
        target.append(entity_id)
        seen.add(entity_id)

def _normalized_uuid_string(value: object) -> str | None:
    """Return one normalized UUID string when the input is UUID-like."""
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None

def _proposal_payload_entity_ids(
    proposals: Sequence[object],
) -> tuple[str, ...]:
    """Collect UUID-backed proposal endpoints that can feed chase preparation."""
    entity_ids: list[str] = []
    for proposal in proposals:
        payload = getattr(proposal, "payload", None)
        if not isinstance(payload, dict):
            continue
        for key in ("proposed_subject", "proposed_object"):
            entity_id = _normalized_uuid_string(payload.get(key))
            if entity_id is None or entity_id in entity_ids:
                continue
            entity_ids.append(entity_id)
    return tuple(entity_ids)

def _proposal_endpoint_label(
    *,
    payload: JSONObject,
    key: str,
) -> tuple[str | None, str | None]:
    """Return a proposal endpoint ref together with the best local grounding label."""
    raw_entity_ref = payload.get(key)
    entity_ref = (
        raw_entity_ref.strip()
        if isinstance(raw_entity_ref, str) and raw_entity_ref.strip() != ""
        else None
    )
    raw_label = payload.get(f"{key}_label")
    if isinstance(raw_label, str) and raw_label.strip() != "":
        return entity_ref, raw_label.strip()
    if entity_ref is None or not entity_ref.startswith("unresolved:"):
        return entity_ref, None
    label = entity_ref.removeprefix("unresolved:").replace("_", " ").strip()
    return entity_ref, label or None

def _ground_replay_candidate_claim_drafts(
    *,
    space_id: UUID,
    drafts: tuple[HarnessProposalDraft, ...],
    graph_api_gateway: GraphTransportBundle,
) -> tuple[
    tuple[HarnessProposalDraft, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Rewrite replayed candidate-claim drafts to current-space graph entity ids."""
    grounded_drafts: list[HarnessProposalDraft] = []
    surfaced_entity_ids: list[str] = []
    created_entity_ids: list[str] = []
    errors: list[str] = []
    resolved_entity_ids: dict[str, str] = {}
    for draft in drafts:
        if draft.proposal_type != "candidate_claim":
            grounded_drafts.append(draft)
            continue
        payload = dict(draft.payload)
        for key in ("proposed_subject", "proposed_object"):
            _, label = _proposal_endpoint_label(payload=payload, key=key)
            if label is None:
                continue
            entity_id, created_entity_id, error = _ground_candidate_claim_endpoint(
                space_id=space_id,
                entity_ref=f"label::{label.casefold()}",
                label=label,
                graph_api_gateway=graph_api_gateway,
                resolved_entity_ids=resolved_entity_ids,
            )
            if error is not None:
                errors.append(error)
                continue
            if entity_id is not None:
                payload[key] = entity_id
                if entity_id not in surfaced_entity_ids:
                    surfaced_entity_ids.append(entity_id)
            if (
                created_entity_id is not None
                and created_entity_id not in created_entity_ids
            ):
                created_entity_ids.append(created_entity_id)
        grounded_drafts.append(replace(draft, payload=payload))
    return (
        tuple(grounded_drafts),
        tuple(surfaced_entity_ids),
        tuple(created_entity_ids),
        tuple(errors),
    )

def _ground_candidate_claim_endpoint(
    *,
    space_id: UUID,
    entity_ref: str,
    label: str,
    graph_api_gateway: GraphTransportBundle,
    resolved_entity_ids: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Return one UUID-backed entity reference for a deferred proposal endpoint."""
    cached_entity_id = resolved_entity_ids.get(entity_ref)
    if cached_entity_id is not None:
        return cached_entity_id, None, None
    try:
        try:
            resolved_entity = resolve_graph_entity_label(
                space_id=space_id,
                label=label,
                graph_api_gateway=graph_api_gateway,
            )
        except Exception:  # noqa: BLE001
            resolved_entity = None
        entity_id = _extract_graph_entity_id(resolved_entity)
        if entity_id is not None:
            resolved_entity_ids[entity_ref] = entity_id
            created_entity_id: str | None = None
        else:
            preflight_service = GraphAIPreflightService()
            submission_service = GraphWorkflowSubmissionService()
            resolved_intent = preflight_service.prepare_entity_create(
                space_id=space_id,
                entity_type=infer_graph_entity_type_from_label(label),
                display_label=label,
                aliases=None,
                graph_transport=graph_api_gateway,
            )
            created_entity = submission_service.submit_resolved_intent(
                resolved_intent=resolved_intent,
                graph_transport=graph_api_gateway,
            )
            entity_id = _extract_graph_entity_id(created_entity)
            if entity_id is None:
                return (
                    None,
                    None,
                    f"Entity auto-creation skipped for '{label}': missing entity id",
                )
            resolved_entity_ids[entity_ref] = entity_id
            created_entity_id = entity_id
        return entity_id, created_entity_id, None  # noqa: TRY300
    except Exception as entity_exc:  # noqa: BLE001
        return (
            None,
            None,
            f"Entity auto-creation skipped for '{label}': {type(entity_exc).__name__}",
        )

def _ground_candidate_claim_drafts(
    *,
    space_id: UUID,
    drafts: tuple[HarnessProposalDraft, ...],
    graph_api_gateway: GraphTransportBundle,
) -> tuple[
    tuple[HarnessProposalDraft, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    """Resolve deferred candidate-claim endpoints to UUID-backed graph entities."""
    grounded_drafts: list[HarnessProposalDraft] = []
    surfaced_entity_ids: list[str] = []
    created_entity_ids: list[str] = []
    errors: list[str] = []
    resolved_entity_ids: dict[str, str] = {}
    for draft in drafts:
        if draft.proposal_type != "candidate_claim":
            grounded_drafts.append(draft)
            continue
        payload = dict(draft.payload)
        for key in ("proposed_subject", "proposed_object"):
            raw_entity_ref = payload.get(key)
            if not isinstance(raw_entity_ref, str):
                continue
            entity_ref = raw_entity_ref.strip()
            if not entity_ref.startswith("unresolved:"):
                continue
            label_key = f"{key}_label"
            raw_label = payload.get(label_key)
            if isinstance(raw_label, str) and raw_label.strip() != "":
                label = raw_label.strip()
            else:
                label = entity_ref.removeprefix("unresolved:").replace("_", " ").strip()
            if label == "":
                continue
            entity_id, created_entity_id, error = _ground_candidate_claim_endpoint(
                space_id=space_id,
                entity_ref=entity_ref,
                label=label,
                graph_api_gateway=graph_api_gateway,
                resolved_entity_ids=resolved_entity_ids,
            )
            if error is not None:
                errors.append(error)
                continue
            if entity_id is not None:
                payload[key] = entity_id
                surfaced_entity_ids.append(entity_id)
            if created_entity_id is not None:
                created_entity_ids.append(created_entity_id)
        grounded_drafts.append(replace(draft, payload=payload))
    return (
        tuple(grounded_drafts),
        tuple(surfaced_entity_ids),
        tuple(created_entity_ids),
        tuple(errors),
    )

async def _sync_pubmed_document_into_shared_observation_ingestion(
    *,
    space_id: UUID,
    owner_id: UUID,
    document: HarnessDocumentRecord,
) -> _PubMedObservationSyncResult:
    """Mirror one harness PubMed document into the shared observation pipeline."""
    batch_result = await _sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[document],
    )
    return batch_result.document_results.get(
        document.id,
        _PubMedObservationSyncResult(
            source_document_id=document.id,
            status="failed",
            observations_created=0,
            entities_created=0,
            seed_entity_ids=(),
            errors=("missing_observation_bridge_result",),
        ),
    )

def _build_observation_bridge_result(
    *,
    document: HarnessDocumentRecord,
    source_document: object | None,
) -> _PubMedObservationSyncResult:
    """Build one observation-bridge result from the persisted source document."""
    if source_document is None:
        return _PubMedObservationSyncResult(
            source_document_id=document.id,
            status="failed",
            observations_created=0,
            entities_created=0,
            seed_entity_ids=(),
            errors=("mirrored_source_document_missing",),
        )

    document_id = source_document_id(source_document)
    metadata = source_document_metadata(source_document)
    status = source_document_extraction_status_value(source_document)
    if document_id is None or metadata is None or status is None:
        return _PubMedObservationSyncResult(
            source_document_id=document.id,
            status="failed",
            observations_created=0,
            entities_created=0,
            seed_entity_ids=(),
            errors=("mirrored_source_document_missing",),
        )

    observations_created = metadata.get(
        "entity_recognition_ingestion_observations_created",
        0,
    )
    entities_created = metadata.get(
        "entity_recognition_ingestion_entities_created",
        0,
    )
    raw_errors = metadata.get("entity_recognition_ingestion_errors")
    errors: list[str] = []
    if isinstance(raw_errors, list):
        for error in raw_errors:
            if not isinstance(error, str):
                continue
            normalized_error = error.strip()
            if normalized_error == "" or normalized_error in errors:
                continue
            errors.append(normalized_error)
    failure_reason = metadata.get("entity_recognition_failure_reason")
    if isinstance(failure_reason, str):
        normalized_failure_reason = failure_reason.strip()
        if normalized_failure_reason != "" and normalized_failure_reason not in errors:
            errors.append(normalized_failure_reason)
    entity_recognition_error = metadata.get("entity_recognition_error")
    if isinstance(entity_recognition_error, str):
        normalized_entity_recognition_error = entity_recognition_error.strip()
        if (
            normalized_entity_recognition_error != ""
            and normalized_entity_recognition_error not in errors
        ):
            errors.append(normalized_entity_recognition_error)
    return _PubMedObservationSyncResult(
        source_document_id=str(document_id),
        status=status,
        observations_created=(
            observations_created if isinstance(observations_created, int) else 0
        ),
        entities_created=entities_created if isinstance(entities_created, int) else 0,
        seed_entity_ids=(),
        errors=tuple(errors),
    )

def _build_pubmed_bridge_source_document(
    *,
    document: HarnessDocumentRecord,
    space_id: UUID,
    source_id: UUID,
    ingestion_job_id: UUID,
) -> object:
    """Build one SourceDocument for a bridged PubMed harness record."""
    raw_record = _build_pubmed_raw_record_from_document(document)
    return build_source_document(
        id=UUID(document.id),
        research_space_id=space_id,
        source_id=source_id,
        ingestion_job_id=ingestion_job_id,
        external_record_id=_build_pubmed_external_record_id(raw_record),
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        raw_storage_key=document.raw_storage_key,
        enriched_storage_key=document.enriched_storage_key,
        content_hash=document.sha256,
        content_length_chars=len(document.text_content),
        enrichment_status=EnrichmentStatus.SKIPPED,
        enrichment_method="research_init_bridge",
        enrichment_agent_run_id=None,
        extraction_status=DocumentExtractionStatus.PENDING,
        extraction_agent_run_id=None,
        metadata={
            "raw_record": raw_record,
            "harness_document_id": document.id,
            "harness_ingestion_run_id": document.ingestion_run_id,
            "bridge_source": "research_init_pubmed",
        },
    )

def _build_file_upload_bridge_source_document(
    *,
    document: HarnessDocumentRecord,
    space_id: UUID,
    source_id: UUID,
    ingestion_job_id: UUID,
) -> object:
    """Build one SourceDocument for a bridged text/PDF harness record."""
    return build_source_document(
        id=UUID(document.id),
        research_space_id=space_id,
        source_id=source_id,
        ingestion_job_id=ingestion_job_id,
        external_record_id=f"research-init-upload:{document.id}",
        source_type=SourceType.FILE_UPLOAD,
        document_format=(
            DocumentFormat.PDF if document.source_type == "pdf" else DocumentFormat.TEXT
        ),
        raw_storage_key=document.raw_storage_key,
        enriched_storage_key=document.enriched_storage_key,
        content_hash=document.sha256,
        content_length_chars=len(document.text_content),
        enrichment_status=EnrichmentStatus.SKIPPED,
        enrichment_method="research_init_bridge",
        enrichment_agent_run_id=None,
        extraction_status=DocumentExtractionStatus.PENDING,
        extraction_agent_run_id=None,
        metadata={
            "raw_record": _build_file_upload_raw_record_from_document(document),
            "harness_document_id": document.id,
            "harness_ingestion_run_id": document.ingestion_run_id,
            "bridge_source": "research_init_upload",
        },
    )

def _observation_bridge_postgres_search_path(
    *,
    graph_schema: str | None = None,
    harness_schema: str | None = None,
) -> str:
    """Build a bridge search path that can see graph and harness tables.

    The observation bridge writes to graph-owned `source_documents`, but the
    shared entity-recognition runtime can still touch harness-owned tables while
    it processes the batch. Keep graph first so graph-owned tables remain the
    primary resolution target, then expose the harness schema, and always leave
    `public` available for shared platform tables.
    """

    resolved_graph_schema = resolve_graph_db_schema(
        (
            graph_schema
            if graph_schema is not None
            else os.getenv("GRAPH_DB_SCHEMA", "graph_runtime")
        ),
    )
    resolved_harness_schema = resolve_harness_db_schema(harness_schema)

    ordered_schemas: list[str] = []
    if resolved_graph_schema != "public":
        ordered_schemas.append(resolved_graph_schema)
    if (
        resolved_harness_schema != "public"
        and resolved_harness_schema not in ordered_schemas
    ):
        ordered_schemas.append(resolved_harness_schema)
    ordered_schemas.append("public")

    return ", ".join(
        "public" if schema_name == "public" else f'"{schema_name}"'
        for schema_name in ordered_schemas
    )

async def _run_observation_bridge_batch(
    *,
    space_id: UUID,
    documents: list[HarnessDocumentRecord],
    source_id: UUID,
    source_type: SourceType,
    pipeline_run_id: str | None,
    build_source_document: Callable[..., object],
) -> _ObservationBridgeBatchResult:
    """Run the shared observation-ingestion bridge with persisted SourceDocuments."""
    from artana_evidence_api.database import SessionLocal
    from sqlalchemy import text as sa_text

    if not documents:
        return _ObservationBridgeBatchResult(
            document_results={},
            seed_entity_ids=(),
            errors=(),
        )

    batch_ingestion_job_id = uuid4()
    source_documents = [
        build_source_document(
            document=document,
            space_id=space_id,
            source_id=source_id,
            ingestion_job_id=batch_ingestion_job_id,
        )
        for document in documents
    ]

    with SessionLocal() as session:
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(
                sa_text(
                    f"SET search_path TO {_observation_bridge_postgres_search_path()}"
                ),
            )
        source_document_repository = build_source_document_repository(session)
        source_document_repository.upsert_many(source_documents)

        entity_recognition_service = (
            create_observation_bridge_entity_recognition_service(
                session=session,
                source_document_repository=source_document_repository,
                pipeline_run_event_repository=_NoOpPipelineRunEventRepository(),
            )
        )
        _apply_observation_bridge_time_budget(
            entity_recognition_service=entity_recognition_service,
        )
        try:
            summary = cast(
                "_ObservationBridgeSummaryLike",
                await asyncio.wait_for(
                    entity_recognition_service.process_pending_documents(
                        limit=len(documents),
                        source_id=source_id,
                        research_space_id=space_id,
                        ingestion_job_id=batch_ingestion_job_id,
                        source_type=source_type.value,
                        pipeline_run_id=pipeline_run_id,
                    ),
                    timeout=_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS,
                ),
            )
        except TimeoutError:
            timeout_error_message = (
                "Observation bridge batch timed out after "
                f"{_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS:.1f}s"
            )
            _mark_observation_bridge_documents_failed(
                documents=documents,
                source_document_repository=source_document_repository,
                failure_reason="observation_bridge_batch_timeout",
                error_message=timeout_error_message,
            )
            document_results = {
                document.id: _build_observation_bridge_result(
                    document=document,
                    source_document=source_document_repository.get_by_id(
                        UUID(document.id),
                    ),
                )
                for document in documents
            }
            return _ObservationBridgeBatchResult(
                document_results=document_results,
                seed_entity_ids=(),
                errors=(timeout_error_message,),
            )
        finally:
            await entity_recognition_service.close()

        document_results = {
            document.id: _build_observation_bridge_result(
                document=document,
                source_document=source_document_repository.get_by_id(
                    UUID(document.id),
                ),
            )
            for document in documents
        }

    return _ObservationBridgeBatchResult(
        document_results=document_results,
        seed_entity_ids=summary.derived_graph_seed_entity_ids,
        errors=summary.errors,
    )

def _apply_observation_bridge_time_budget(
    *,
    entity_recognition_service: object,
) -> None:
    """Keep bridge-side extraction bounded so research-init does not stall."""

    _cap_service_timeout(
        entity_recognition_service=entity_recognition_service,
        attribute_name="_agent_timeout_seconds",
        max_seconds=_OBSERVATION_BRIDGE_AGENT_TIMEOUT_SECONDS,
    )
    _cap_service_timeout(
        entity_recognition_service=entity_recognition_service,
        attribute_name="_extraction_stage_timeout_seconds",
        max_seconds=_OBSERVATION_BRIDGE_EXTRACTION_STAGE_TIMEOUT_SECONDS,
    )

def _cap_service_timeout(
    *,
    entity_recognition_service: object,
    attribute_name: str,
    max_seconds: float,
) -> None:
    current_value = getattr(entity_recognition_service, attribute_name, None)
    if not isinstance(current_value, int | float):
        return
    setattr(
        entity_recognition_service,
        attribute_name,
        min(float(current_value), max_seconds),
    )

def _mark_observation_bridge_documents_failed(
    *,
    documents: list[HarnessDocumentRecord],
    source_document_repository: SourceDocumentRepositoryProtocol,
    failure_reason: str,
    error_message: str,
) -> None:
    for document in documents:
        source_document = source_document_repository.get_by_id(UUID(document.id))
        metadata = source_document_metadata(source_document) if source_document else None
        if metadata is None:
            continue
        existing_errors = metadata.get(
            "entity_recognition_ingestion_errors",
        )
        normalized_errors = (
            [
                error
                for error in existing_errors
                if isinstance(error, str) and error.strip() != ""
            ]
            if isinstance(existing_errors, list)
            else []
        )
        if error_message not in normalized_errors:
            normalized_errors.append(error_message)
        updated_source_document = source_document_model_copy(
            source_document,
            update={
                "extraction_status": DocumentExtractionStatus.FAILED,
                "metadata": {
                    **metadata,
                    "entity_recognition_failure_reason": failure_reason,
                    "entity_recognition_error": failure_reason,
                    "entity_recognition_ingestion_errors": normalized_errors,
                },
            },
        )
        if updated_source_document is not None:
            source_document_repository.upsert(updated_source_document)

async def _sync_pubmed_documents_into_shared_observation_ingestion(
    *,
    space_id: UUID,
    owner_id: UUID,
    documents: list[HarnessDocumentRecord],
    pipeline_run_id: str | None = None,
) -> _ObservationBridgeBatchResult:
    """Bridge PubMed harness docs into shared observation ingestion."""
    del owner_id
    return await _run_observation_bridge_batch(
        space_id=space_id,
        documents=documents,
        source_id=_research_init_pubmed_source_id(space_id),
        source_type=SourceType.PUBMED,
        pipeline_run_id=pipeline_run_id,
        build_source_document=_build_pubmed_bridge_source_document,
    )

async def _sync_file_upload_document_into_shared_observation_ingestion(
    *,
    space_id: UUID,
    owner_id: UUID,
    document: HarnessDocumentRecord,
) -> _PubMedObservationSyncResult:
    """Mirror one harness text/PDF document into the shared observation pipeline."""
    batch_result = await _sync_file_upload_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[document],
    )
    return batch_result.document_results.get(
        document.id,
        _PubMedObservationSyncResult(
            source_document_id=document.id,
            status="failed",
            observations_created=0,
            entities_created=0,
            seed_entity_ids=(),
            errors=("missing_observation_bridge_result",),
        ),
    )

async def _sync_file_upload_documents_into_shared_observation_ingestion(
    *,
    space_id: UUID,
    owner_id: UUID,
    documents: list[HarnessDocumentRecord],
    pipeline_run_id: str | None = None,
) -> _ObservationBridgeBatchResult:
    """Bridge text/PDF harness docs into shared observation ingestion."""
    del owner_id
    return await _run_observation_bridge_batch(
        space_id=space_id,
        documents=documents,
        source_id=_research_init_upload_source_id(space_id),
        source_type=SourceType.FILE_UPLOAD,
        pipeline_run_id=pipeline_run_id,
        build_source_document=_build_file_upload_bridge_source_document,
    )
