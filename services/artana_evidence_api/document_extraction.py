"""Document extraction helpers for the standalone harness service."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from contextlib import suppress
from typing import TYPE_CHECKING, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from artana_evidence_api.document_context_summary import summarize_document_context
from artana_evidence_api.document_extraction_contracts import (
    ClaimExtractionRoutingStatus,
    DocumentCandidateExtractionDiagnostics,
    DocumentExtractionReviewContext,
    DocumentProposalReview,
    DocumentProposalReviewDiagnostics,
    DocumentTextExtraction,
    ExtractedRelationCandidate,
    PdfTextExtractionOutcome,
    ProposalReviewResultLike,
    normalize_claim_extraction_routing_status,
)
from artana_evidence_api.document_extraction_diagnostics import (
    candidate_completed,
    candidate_fallback,
    candidate_llm_empty,
    candidate_not_needed,
    candidate_semantic_incomplete,
    proposal_review_completed,
    proposal_review_fallback_error,
    proposal_review_not_needed,
    proposal_review_unavailable,
    runtime_error_candidate_status,
)
from artana_evidence_api.document_extraction_drafts import (
    build_document_extraction_drafts,
    with_candidate_extraction_trust_metadata,
)
from artana_evidence_api.document_extraction_entities import (
    canonical_entity_label_rejection_reason,
    resolve_exact_entity_label,
    resolve_graph_entity_label,  # noqa: F401 - compatibility import path
)
from artana_evidence_api.document_extraction_prompting import (
    DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT,
    build_llm_extraction_output_schema,
    build_llm_guarded_extraction_output_schema,
    build_llm_weak_review_extraction_output_schema,
    build_proposal_review_output_schema,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_VALID_RELATION_TYPES,
    normalize_relation_type_label,
)
from artana_evidence_api.document_extraction_review import (
    apply_document_proposal_review,
    build_document_review_context,
    build_fallback_document_review,
    goal_context_summary,
    review_from_draft_metadata,
    shorten_text,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.heuristics.relation_extraction import (
    extract_relation_candidates,
)
from artana_evidence_api.document_extraction_support.llm_extraction.runner import (
    LLMRelationExtractionAttempt,
    run_llm_relation_extraction_with_zero_retry,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditContext,
    fingerprinted_step_key,
    llm_extraction_document_fingerprint,
    merge_duplicate_relation_candidates,
    record_model_attempt,
)
from artana_evidence_api.document_extraction_support.relation_candidate_quality_filter import (
    RelationCandidateQualityFilterResult,
    filter_low_value_relation_candidates,
)
from artana_evidence_api.document_extraction_support.relation_resolution_decisions import (
    apply_relation_resolution_decisions,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    RelationSpecificityPruningResult,
    SpecificityFilteredCandidateList,
    prune_redundant_generic_relation_candidates,
)
from artana_evidence_api.document_extraction_support.review_policy.proposal_review_mapping import (
    build_proposal_review_draft_refs,
    map_proposal_reviews_by_ref,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.step_helpers import run_single_step_with_policy
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from pydantic import ValidationError

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

logger = logging.getLogger(__name__)
_LLM_EXTRACTION_PSEUDO_SPACE_ID = uuid5(
    NAMESPACE_URL,
    "artana-evidence-api:llm-extraction",
)


def _graph_ai_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()


_MAX_AI_ENTITY_PRE_RESOLUTION_LABELS = 4
_AI_ENTITY_PRE_RESOLUTION_TIMEOUT_SECONDS = 2.0
_LLM_CANDIDATE_EXTRACTION_TIMEOUT_SECONDS = 5.0


def sha256_hex(payload: bytes) -> str:
    """Return the SHA-256 digest for one document payload."""
    return hashlib.sha256(payload).hexdigest()


def _proposal_review_step_key(
    *,
    document: HarnessDocumentRecord,
    claims_text: str,
    goal_context_summary: str,
) -> str:
    """Return the stable proposal-review step key for one review payload."""
    return fingerprinted_step_key(
        "document_extraction.proposal_review.v1",
        document.sha256,
        document.source_type,
        document.title,
        claims_text,
        goal_context_summary,
    )


async def _resolve_unknown_llm_relation_types(
    *,
    candidates: list[ExtractedRelationCandidate],
    unknown_relation_types: set[str],
    space_context: str,
) -> list[ExtractedRelationCandidate]:
    if not unknown_relation_types:
        return candidates
    try:
        preflight_service = _graph_ai_preflight_service()
        decisions = {
            candidate: await preflight_service.resolve_relation_type(
                space_id=_LLM_EXTRACTION_PSEUDO_SPACE_ID,
                relation_type=candidate,
                known_types=sorted(LLM_VALID_RELATION_TYPES),
                space_context=space_context,
                domain_context="biomedical",
            )
            for candidate in sorted(unknown_relation_types)
        }
        return apply_relation_resolution_decisions(
            candidates=candidates,
            decisions=decisions,
        )
    except Exception:
        logger.exception(
            "AI relation type resolution failed for %s; "
            "dropping raw types until governed review succeeds",
            unknown_relation_types,
        )
        return [
            candidate
            for candidate in candidates
            if normalize_relation_type_label(candidate.relation_type)
            not in unknown_relation_types
        ]


def extract_pdf_text(payload: bytes) -> DocumentTextExtraction:
    """Extract text content from one PDF payload."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PDF upload support requires the optional 'pypdf' dependency.",
        ) from exc
    reader = PdfReader(io.BytesIO(payload))
    page_count = len(reader.pages)
    page_texts: list[str] = []
    pages_without_text: list[int] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip() == "":
            pages_without_text.append(page_number)
        else:
            page_texts.append(page_text)
    text_content = "\n\n".join(page_texts)
    return DocumentTextExtraction(
        text_content=text_content,
        page_count=page_count,
        extraction_outcome=_pdf_text_extraction_outcome(
            page_count=page_count,
            text_content=text_content,
            pages_without_text=tuple(pages_without_text),
        ),
        pages_without_text=tuple(pages_without_text),
    )


def _pdf_text_extraction_outcome(
    *,
    page_count: int,
    text_content: str,
    pages_without_text: tuple[int, ...],
) -> PdfTextExtractionOutcome:
    if page_count == 0:
        return "no_pages"
    if text_content.strip() == "":
        return "no_text_image_likely"
    if pages_without_text:
        return "partial_text_ocr_needed"
    return "text"


def normalize_text_document(text: str) -> str:
    """Normalize one raw text submission for harness storage."""
    normalized_lines = [
        line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(normalized_lines).strip()


def _prune_relation_candidate_specificity(
    candidates: list[ExtractedRelationCandidate],
) -> RelationSpecificityPruningResult:
    return prune_redundant_generic_relation_candidates(candidates)


def _fallback_candidates_with_specificity_pruning(
    text: str,
) -> RelationSpecificityPruningResult:
    return _prune_relation_candidate_specificity(extract_relation_candidates(text))


def _filter_relation_candidate_quality(
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> RelationCandidateQualityFilterResult:
    result = filter_low_value_relation_candidates(candidates)
    if result.filtered_count > 0:
        logger.info(
            "Suppressed %s low-evidence relation candidates after LLM extraction",
            result.filtered_count,
        )
    return result


def _route_agent_extraction_result(
    *,
    extraction_attempt: LLMRelationExtractionAttempt,
    quality_filter_result: RelationCandidateQualityFilterResult,
    pruning_result: RelationSpecificityPruningResult,
    max_relations: int,
    normalized_text_length: int,
) -> SpecificityFilteredCandidateList:
    """Route bounded compatibility output without losing any framed claim."""

    usable_candidates = tuple(quality_filter_result.candidates)
    routing_status: ClaimExtractionRoutingStatus
    if not extraction_attempt.semantic_inventory_complete:
        visible_candidates: tuple[ExtractedRelationCandidate, ...] = ()
        overflow_candidates = usable_candidates
        routing_status = "semantic_incomplete"
    else:
        visible_candidates = usable_candidates[:max_relations]
        overflow_candidates = usable_candidates[max_relations:]
        routing_status = "candidate_overflow" if overflow_candidates else "complete"
    return SpecificityFilteredCandidateList(
        visible_candidates,
        pruned_generic_relation_count=pruning_result.pruned_count,
        quality_filtered_candidate_count=quality_filter_result.filtered_count,
        llm_extraction_chunk_count=extraction_attempt.processed_chunk_count,
        llm_extraction_text_char_count=normalized_text_length,
        raw_agent_outputs=extraction_attempt.raw_agent_outputs,
        model_attempt_records=tuple(
            record.as_json() for record in extraction_attempt.model_attempt_records
        ),
        claim_extraction_routing_status=routing_status,
        overflow_candidates=overflow_candidates,
        all_framed_candidates=tuple(extraction_attempt.candidates),
        claim_lineage=extraction_attempt.claim_lineage,
        inventory_incompleteness=tuple(
            {
                "inventory_id": claim.inventory_id,
                "claim": claim.item.model_dump(mode="json"),
            }
            for claim in extraction_attempt.inventory_incompleteness
        ),
    )


async def extract_relation_candidates_with_llm(
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
    execution_namespace: str = "",
) -> list[ExtractedRelationCandidate]:
    """Extract relation candidates using an LLM via ArtanaKernel.

    This function intentionally returns only the LLM-generated candidates.
    Use ``discover_relation_candidates()`` for LLM-first discovery with
    heuristic fallback and diagnostics.
    """
    from artana_evidence_api.runtime_support import (
        ModelCapability,
        get_model_registry,
        has_configured_openai_api_key,
    )

    if not has_configured_openai_api_key():
        msg = "OPENAI_API_KEY not configured"
        raise RuntimeError(msg)

    normalized_text = normalize_text_document(text)
    chunks = build_relation_extraction_text_chunks(normalized_text)
    if not chunks:
        return SpecificityFilteredCandidateList(
            (),
            pruned_generic_relation_count=0,
        )
    document_fingerprint = llm_extraction_document_fingerprint(normalized_text)
    output_schema = build_llm_guarded_extraction_output_schema(max_relations)
    weak_review_output_schema = build_llm_weak_review_extraction_output_schema(
        max_relations,
    )

    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter

    kernel: ArtanaKernel | None = None
    store = None

    # Resolve model and normalize for LiteLLM (openai:gpt-5.4-mini → openai/gpt-5.4-mini)
    from artana_evidence_api.runtime_support import (
        create_artana_postgres_store,
        normalize_litellm_model_id,
    )

    model_id = normalize_litellm_model_id(
        get_model_registry()
        .get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        )
        .model_id,
    )

    tenant = TenantContext(
        tenant_id="research-init-extraction",
        capabilities=frozenset(),
        budget_usd_limit=1.0,
    )

    try:
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=60.0),
        )
        client = SingleStepModelClient(kernel=kernel)
        extraction_attempt = await run_llm_relation_extraction_with_zero_retry(
            normalized_text=normalized_text,
            chunks=chunks,
            max_relations=max_relations,
            document_fingerprint=document_fingerprint,
            output_schema=output_schema,
            weak_review_output_schema=weak_review_output_schema,
            client=client,
            tenant=tenant,
            model_id=model_id,
            step_runner=run_single_step_with_policy,
            execution_namespace=execution_namespace,
        )
        raw_relation_count = extraction_attempt.raw_relation_count
        candidates = extraction_attempt.candidates
        unknown_relation_types = extraction_attempt.unknown_relation_types

        candidates = await _resolve_unknown_llm_relation_types(
            candidates=candidates,
            unknown_relation_types=unknown_relation_types,
            space_context=space_context,
        )
        candidates = merge_duplicate_relation_candidates(candidates)

        pruning_result = _prune_relation_candidate_specificity(candidates)
        if pruning_result.pruned_count > 0:
            logger.info(
                "Suppressed %s generic relation candidates after LLM extraction",
                pruning_result.pruned_count,
            )
        quality_filter_result = _filter_relation_candidate_quality(
            pruning_result.candidates,
        )
        filtered_candidates = _route_agent_extraction_result(
            extraction_attempt=extraction_attempt,
            quality_filter_result=quality_filter_result,
            pruning_result=pruning_result,
            max_relations=max_relations,
            normalized_text_length=len(normalized_text),
        )
        candidates = filtered_candidates

        if not candidates:
            logger.debug(
                "LLM extraction returned zero usable candidates",
                extra={
                    "model_id": model_id,
                    "text_length": len(normalized_text),
                    "chunk_count": extraction_attempt.processed_chunk_count,
                    "raw_relation_count": raw_relation_count,
                    "usable_candidate_count": 0,
                },
            )
        return filtered_candidates
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()


async def discover_relation_candidates(  # noqa: PLR0911
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> tuple[list[ExtractedRelationCandidate], DocumentCandidateExtractionDiagnostics]:
    """Discover relation candidates with LLM-first fallback and diagnostics."""
    normalized_text = normalize_text_document(text)
    if normalized_text == "":
        return (
            [],
            candidate_not_needed(),
        )

    try:
        llm_candidates = await asyncio.wait_for(
            extract_relation_candidates_with_llm(
                normalized_text,
                max_relations=max_relations,
                space_context=space_context,
            ),
            timeout=_LLM_CANDIDATE_EXTRACTION_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.debug(
            "LLM relation extraction timed out, falling back to regex heuristics",
            extra={
                "space_context_length": len(space_context),
                "text_length": len(normalized_text),
            },
        )
        fallback_pruning = _fallback_candidates_with_specificity_pruning(
            normalized_text,
        )
        fallback_candidates = list(fallback_pruning.candidates)
        return (
            fallback_candidates,
            candidate_fallback(
                status="fallback_error",
                error="LLM candidate extraction timed out",
                fallback_candidate_count=len(fallback_candidates),
                pruned_generic_relation_count=fallback_pruning.pruned_count,
            ),
        )
    except (ModuleNotFoundError, ImportError) as exc:
        logger.debug(
            "LLM relation extraction unavailable, falling back to regex heuristics: %s",
            str(exc),
            extra={
                "space_context_length": len(space_context),
                "text_length": len(normalized_text),
                "exception_type": type(exc).__name__,
            },
        )
        fallback_pruning = _fallback_candidates_with_specificity_pruning(
            normalized_text,
        )
        fallback_candidates = list(fallback_pruning.candidates)
        return (
            fallback_candidates,
            candidate_fallback(
                status="unavailable",
                error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
                pruned_generic_relation_count=fallback_pruning.pruned_count,
            ),
        )
    except RuntimeError as exc:
        fallback_pruning = _fallback_candidates_with_specificity_pruning(
            normalized_text,
        )
        fallback_candidates = list(fallback_pruning.candidates)
        status = runtime_error_candidate_status(str(exc))
        if status == "unavailable":
            logger.debug(
                "LLM relation extraction unavailable, falling back to regex heuristics: %s",
                str(exc),
                extra={
                    "space_context_length": len(space_context),
                    "text_length": len(normalized_text),
                    "exception_type": type(exc).__name__,
                },
            )
        else:
            logger.warning(
                "LLM relation extraction failed, falling back to regex: %s",
                str(exc),
                extra={
                    "space_context_length": len(space_context),
                    "text_length": len(normalized_text),
                    "exception_type": type(exc).__name__,
                },
            )
        return (
            fallback_candidates,
            candidate_fallback(
                status=status,
                error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
                pruned_generic_relation_count=fallback_pruning.pruned_count,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM relation extraction failed, falling back to regex: %s",
            str(exc),
            extra={
                "space_context_length": len(space_context),
                "text_length": len(normalized_text),
                "exception_type": type(exc).__name__,
            },
        )
        fallback_pruning = _fallback_candidates_with_specificity_pruning(
            normalized_text,
        )
        fallback_candidates = list(fallback_pruning.candidates)
        return (
            fallback_candidates,
            candidate_fallback(
                status="fallback_error",
                error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
                pruned_generic_relation_count=fallback_pruning.pruned_count,
            ),
        )

    llm_pruned_generic_relation_count = int(
        getattr(llm_candidates, "pruned_generic_relation_count", 0),
    )
    llm_quality_filtered_candidate_count = int(
        getattr(llm_candidates, "quality_filtered_candidate_count", 0),
    )
    llm_extraction_chunk_count = int(
        getattr(llm_candidates, "llm_extraction_chunk_count", 0),
    )
    llm_extraction_text_char_count = int(
        getattr(llm_candidates, "llm_extraction_text_char_count", 0),
    )
    if not hasattr(llm_candidates, "claim_extraction_routing_status"):
        llm_pruning = _prune_relation_candidate_specificity(llm_candidates)
        llm_pruned_generic_relation_count += llm_pruning.pruned_count
        llm_candidates = list(llm_pruning.candidates)
    routing_status = normalize_claim_extraction_routing_status(
        getattr(llm_candidates, "claim_extraction_routing_status", "not_run"),
    )
    candidate_overflow_count = int(
        getattr(llm_candidates, "candidate_overflow_count", 0),
    )
    claim_lineage = tuple(getattr(llm_candidates, "claim_lineage", ()))
    raw_agent_outputs = tuple(getattr(llm_candidates, "raw_agent_outputs", ()))
    model_attempt_records = tuple(
        getattr(llm_candidates, "model_attempt_records", ()),
    )

    if routing_status == "semantic_incomplete":
        return (
            llm_candidates,
            candidate_semantic_incomplete(
                claim_lineage=claim_lineage,
                raw_agent_outputs=raw_agent_outputs,
                model_attempt_records=model_attempt_records,
                llm_extraction_chunk_count=llm_extraction_chunk_count,
                llm_extraction_text_char_count=llm_extraction_text_char_count,
            ),
        )

    if llm_candidates:
        return (
            llm_candidates,
            candidate_completed(
                candidate_count=len(llm_candidates),
                pruned_generic_relation_count=llm_pruned_generic_relation_count,
                quality_filtered_candidate_count=(llm_quality_filtered_candidate_count),
                llm_extraction_chunk_count=llm_extraction_chunk_count,
                llm_extraction_text_char_count=llm_extraction_text_char_count,
                claim_extraction_routing_status=routing_status,
                candidate_overflow_count=candidate_overflow_count,
                claim_lineage=claim_lineage,
                raw_agent_outputs=raw_agent_outputs,
                model_attempt_records=model_attempt_records,
            ),
        )

    fallback_pruning = _fallback_candidates_with_specificity_pruning(
        normalized_text,
    )
    fallback_candidates = list(fallback_pruning.candidates)
    return (
        fallback_candidates,
        candidate_llm_empty(
            fallback_candidate_count=len(fallback_candidates),
            pruned_generic_relation_count=(
                llm_pruned_generic_relation_count + fallback_pruning.pruned_count
            ),
            quality_filtered_candidate_count=llm_quality_filtered_candidate_count,
            llm_extraction_chunk_count=llm_extraction_chunk_count,
            llm_extraction_text_char_count=llm_extraction_text_char_count,
            claim_extraction_routing_status=routing_status,
            claim_lineage=claim_lineage,
            raw_agent_outputs=raw_agent_outputs,
            model_attempt_records=model_attempt_records,
        ),
    )


async def extract_relation_candidates_with_diagnostics(
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> tuple[list[ExtractedRelationCandidate], DocumentCandidateExtractionDiagnostics]:
    """Extract relation candidates with LLM-first fallback diagnostics."""
    return await discover_relation_candidates(
        text,
        max_relations=max_relations,
        space_context=space_context,
    )


async def review_document_extraction_drafts_with_diagnostics(  # noqa: PLR0912, PLR0915
    *,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    drafts: tuple[HarnessProposalDraft, ...],
    review_context: DocumentExtractionReviewContext | None = None,
) -> tuple[tuple[HarnessProposalDraft, ...], DocumentProposalReviewDiagnostics]:
    """Apply an LLM review pass to extracted document proposals when available."""
    if not drafts:
        return (
            drafts,
            proposal_review_not_needed(),
        )

    normalized_context = review_context or build_document_review_context()
    fallback_reviews: list[DocumentProposalReview] = []
    for index, draft in enumerate(drafts):
        existing_review = review_from_draft_metadata(draft)
        if existing_review is not None:
            fallback_reviews.append(existing_review)
            continue
        if candidates:
            candidate = candidates[min(index, len(candidates) - 1)]
            fallback_reviews.append(
                build_fallback_document_review(
                    candidate=candidate,
                    review_context=normalized_context,
                ),
            )
            continue
        fallback_reviews.append(
            DocumentProposalReview(
                factual_support="moderate",
                goal_relevance="unscoped",
                priority="review",
                rationale=(
                    "A fallback review was applied because no extracted candidate "
                    "context was available."
                ),
                factual_rationale=(
                    "The proposal was preserved for manual review without a richer "
                    "candidate-level confidence analysis."
                ),
                relevance_rationale=(
                    "Goal relevance could not be reviewed precisely for this proposal."
                ),
                method="heuristic_fallback_v1",
            ),
        )

    def _apply_fallback_reviews() -> tuple[HarnessProposalDraft, ...]:
        return tuple(
            apply_document_proposal_review(
                draft=draft,
                review=fallback_reviews[index],
                review_context=normalized_context,
            )
            for index, draft in enumerate(drafts)
        )

    try:
        from artana.agent import SingleStepModelClient
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter
        from artana_evidence_api.runtime_support import (
            ModelCapability,
            get_model_registry,
            has_configured_openai_api_key,
            normalize_litellm_model_id,
        )

    except Exception as exc:  # noqa: BLE001
        return (
            _apply_fallback_reviews(),
            proposal_review_unavailable(str(exc)),
        )

    if not has_configured_openai_api_key():
        return (
            _apply_fallback_reviews(),
            proposal_review_unavailable("OPENAI_API_KEY not configured"),
        )

    output_schema = build_proposal_review_output_schema()

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.JUDGE)
    model_id = normalize_litellm_model_id(model_spec.model_id)
    draft_refs = build_proposal_review_draft_refs(
        document_sha256=document.sha256,
        drafts=drafts,
    )
    claim_blocks: list[str] = []
    for draft_ref, draft in zip(draft_refs, drafts, strict=True):
        subject_label = draft.metadata.get(
            "resolved_subject_label",
        ) or draft.metadata.get(
            "subject_label",
        )
        object_label = draft.metadata.get(
            "resolved_object_label",
        ) or draft.metadata.get(
            "object_label",
        )
        relation_type = draft.payload.get("proposed_claim_type")
        claim_blocks.append(
            "\n".join(
                [
                    f"Claim reference: {draft_ref}",
                    f"- subject: {subject_label}",
                    f"- relation_type: {relation_type}",
                    f"- object: {object_label}",
                    f"- excerpt: {shorten_text(draft.summary, max_length=500)}",
                ],
            ),
        )
    claims_text = "\n\n".join(claim_blocks)
    goal_context = goal_context_summary(normalized_context)
    prompt = (
        f"{DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT}\n\n"
        f"RESEARCH SPACE CONTEXT\n{goal_context}\n\n"
        f"DOCUMENT\n"
        f"- title: {shorten_text(document.title, max_length=200)}\n"
        f"- source_type: {document.source_type}\n\n"
        f"CLAIMS TO REVIEW\n{claims_text}\n\n"
        "Return one review for each claim reference, copying every draft_ref exactly."
    )
    step_key = _proposal_review_step_key(
        document=document,
        claims_text=claims_text,
        goal_context_summary=goal_context,
    )

    kernel: ArtanaKernel | None = None
    store = None
    invocation_id = str(uuid4())
    model_result: object | None = None
    raw_model_output: object | None = None
    audit_context = ModelAttemptAuditContext(
        attempt_role="proposal_review",
        pass_role="proposal_review",
        retry_context=None,
        source_sha256=hashlib.sha256(
            document.text_content.encode("utf-8"),
        ).hexdigest(),
        input_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )
    tenant = TenantContext(
        tenant_id=f"document-proposal-review:{document.space_id}",
        capabilities=frozenset(),
        budget_usd_limit=1.0,
    )
    try:
        from artana_evidence_api.runtime_support import create_artana_postgres_store

        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=model_spec.timeout_seconds),
        )
        client = SingleStepModelClient(kernel=kernel)
        result = await asyncio.wait_for(
            run_single_step_with_policy(
                client,
                run_id=f"document-proposal-review:{invocation_id}",
                tenant=tenant,
                model=model_id,
                prompt=prompt,
                output_schema=output_schema,
                schema_id="document_extraction.proposal_review.v1",
                step_key=step_key,
                replay_policy="fork_on_drift",
            ),
            timeout=model_spec.timeout_seconds,
        )
        model_result = result
        output = result.output
        raw_model_output = output
        parsed = cast(
            "ProposalReviewResultLike",
            (
                output
                if isinstance(output, output_schema)
                else output_schema.model_validate(output)
            ),
        )
        reviews_by_ref = map_proposal_reviews_by_ref(
            result=parsed,
            expected_refs=draft_refs,
            model_id=model_spec.model_id,
        )
    except TimeoutError as exc:
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_model_output,
            validation_outcome="invocation_failed",
            error_type=type(exc).__name__,
        )
        reviews_by_ref = {}
        diagnostics = proposal_review_fallback_error(
            "LLM proposal review timed out",
        )
    except ValidationError as exc:
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_model_output,
            validation_outcome="schema_invalid",
            error_type=type(exc).__name__,
        )
        reviews_by_ref = {}
        diagnostics = proposal_review_fallback_error(str(exc))
    except Exception as exc:  # noqa: BLE001
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_model_output,
            validation_outcome=(
                "semantic_invalid" if model_result is not None else "invocation_failed"
            ),
            error_type=type(exc).__name__,
        )
        reviews_by_ref = {}
        diagnostics = proposal_review_fallback_error(str(exc))
    else:
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=audit_context,
            model_result=model_result,
            raw_output=raw_model_output,
            validation_outcome="accepted",
            error_type=None,
        )
        diagnostics = proposal_review_completed()
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()

    return (
        tuple(
            apply_document_proposal_review(
                draft=draft,
                review=reviews_by_ref.get(draft_ref, fallback_reviews[index]),
                review_context=normalized_context,
            )
            for index, (draft_ref, draft) in enumerate(
                zip(draft_refs, drafts, strict=True),
            )
        ),
        diagnostics,
    )


async def review_document_extraction_drafts(  # noqa: PLR0915
    *,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    drafts: tuple[HarnessProposalDraft, ...],
    review_context: DocumentExtractionReviewContext | None = None,
) -> tuple[HarnessProposalDraft, ...]:
    """Apply an LLM review pass to extracted document proposals when available."""
    reviewed_drafts, _ = await review_document_extraction_drafts_with_diagnostics(
        document=document,
        candidates=candidates,
        drafts=drafts,
        review_context=review_context,
    )
    return reviewed_drafts


async def _resolve_entity_label_with_ai(
    *,
    space_id: UUID,
    label: str,
    graph_api_gateway: GraphTransportBundle,
    space_context: str = "",
) -> JSONObject | None:
    return await _graph_ai_preflight_service().resolve_entity_label_with_ai(
        space_id=space_id,
        label=label,
        graph_transport=graph_api_gateway,
        space_context=space_context,
    )


async def pre_resolve_entities_with_ai(
    *,
    space_id: UUID,
    candidates: list[ExtractedRelationCandidate],
    graph_api_gateway: GraphTransportBundle,
    space_context: str = "",
) -> dict[str, JSONObject]:
    """Pre-resolve entity labels using AI before building proposals.

    Collects all unique entity labels from extraction candidates, runs them
    through the AI entity resolver, and returns a mapping from
    ``label.casefold()`` → ``{"id": ..., "display_label": ...}`` for labels
    that matched existing entities.

    Labels that should be created as new entities are NOT included in the
    result (so the caller falls through to the standard
    ``_build_unresolved_entity_id`` path).

    Call this BEFORE ``build_document_extraction_drafts`` and pass the result
    as ``ai_resolved_entities``.
    """
    import logging

    _logger = logging.getLogger(__name__)
    resolved: dict[str, JSONObject] = {}
    # Preserve first-seen order so the bounded AI budget is spent on the
    # earliest extraction labels instead of an arbitrary set iteration order.
    ordered_labels: list[str] = []
    seen_labels: set[str] = set()
    for candidate in candidates:
        for label in (candidate.subject_label, candidate.object_label):
            normalized_label = label.strip()
            if normalized_label == "":
                continue
            if canonical_entity_label_rejection_reason(normalized_label) is not None:
                continue
            cache_key = normalized_label.casefold()
            if cache_key in seen_labels:
                continue
            seen_labels.add(cache_key)
            ordered_labels.append(normalized_label)

    ai_attempted_labels = 0
    ai_budget_exhausted = False

    for label in ordered_labels:
        # Skip labels that already resolve deterministically (exact match)
        deterministic = await asyncio.to_thread(
            resolve_exact_entity_label,
            space_id=space_id,
            label=label,
            graph_api_gateway=graph_api_gateway,
        )
        if deterministic is not None:
            resolved[label.strip().casefold()] = deterministic
            continue

        if ai_attempted_labels >= _MAX_AI_ENTITY_PRE_RESOLUTION_LABELS:
            ai_budget_exhausted = True
            continue

        # Use AI resolution
        try:
            ai_attempted_labels += 1
            ai_result = await asyncio.wait_for(
                _resolve_entity_label_with_ai(
                    space_id=space_id,
                    label=label,
                    graph_api_gateway=graph_api_gateway,
                    space_context=space_context,
                ),
                timeout=_AI_ENTITY_PRE_RESOLUTION_TIMEOUT_SECONDS,
            )
            if ai_result is not None:
                resolved[label.strip().casefold()] = ai_result
                _logger.info(
                    "AI entity resolution: '%s' → '%s' (id=%s)",
                    label,
                    ai_result.get("display_label"),
                    ai_result.get("id"),
                )
        except TimeoutError:
            _logger.debug(
                "AI entity resolution timed out for '%s'; falling back to "
                "deterministic/unresolved handling",
                label,
            )
        except Exception:
            _logger.exception(
                "AI entity resolution failed for '%s', falling back to "
                "deterministic resolution",
                label,
            )

    if ai_budget_exhausted:
        _logger.info(
            "AI entity pre-resolution budget exhausted after %d labels; "
            "remaining labels will use deterministic/unresolved handling",
            _MAX_AI_ENTITY_PRE_RESOLUTION_LABELS,
        )

    return resolved


__all__ = [
    "DocumentCandidateExtractionDiagnostics",
    "DocumentTextExtraction",
    "DocumentExtractionReviewContext",
    "DocumentProposalReviewDiagnostics",
    "ExtractedRelationCandidate",
    "build_document_review_context",
    "build_document_extraction_drafts",
    "build_llm_extraction_output_schema",
    "build_proposal_review_output_schema",
    "discover_relation_candidates",
    "extract_pdf_text",
    "extract_relation_candidates",
    "extract_relation_candidates_with_diagnostics",
    "normalize_text_document",
    "pre_resolve_entities_with_ai",
    "review_document_extraction_drafts",
    "review_document_extraction_drafts_with_diagnostics",
    "sha256_hex",
    "summarize_document_context",
    "with_candidate_extraction_trust_metadata",
]
