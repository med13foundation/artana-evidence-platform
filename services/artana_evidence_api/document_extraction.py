"""Document extraction helpers for the standalone harness service."""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from contextlib import suppress
from typing import TYPE_CHECKING, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from artana_evidence_api.document_context_summary import summarize_document_context
from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
    DocumentExtractionReviewContext,
    DocumentProposalReview,
    DocumentProposalReviewDiagnostics,
    DocumentTextExtraction,
    ExtractedRelationCandidate,
    LLMExtractionResultLike,
    ProposalReviewResultLike,
)
from artana_evidence_api.document_extraction_diagnostics import (
    candidate_completed,
    candidate_fallback,
    candidate_llm_empty,
    candidate_not_needed,
    proposal_review_completed,
    proposal_review_fallback_error,
    proposal_review_not_needed,
    proposal_review_unavailable,
    runtime_error_candidate_status,
)
from artana_evidence_api.document_extraction_drafts import (
    build_document_extraction_drafts,
)
from artana_evidence_api.document_extraction_entities import (
    canonical_entity_label_rejection_reason,
    clean_candidate_label,
    clean_llm_entity_label,
    resolve_exact_entity_label,
    resolve_graph_entity_label,  # noqa: F401 - compatibility import path
)
from artana_evidence_api.document_extraction_prompting import (
    DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT,
    LLM_EXTRACTION_SYSTEM_PROMPT,
    build_llm_extraction_output_schema,
    build_proposal_review_output_schema,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_RELATION_SYNONYMS,
    LLM_VALID_RELATION_TYPES,
)
from artana_evidence_api.document_extraction_review import (
    apply_document_proposal_review,
    build_document_review_context,
    build_fallback_document_review,
    goal_context_summary,
    review_from_draft_metadata,
    shorten_text,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.graph_integration.preflight import GraphAIPreflightService
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.step_helpers import run_single_step_with_policy
from artana_evidence_api.types.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

logger = logging.getLogger(__name__)
_LLM_EXTRACTION_PSEUDO_SPACE_ID = uuid5(
    NAMESPACE_URL,
    "artana-evidence-api:llm-extraction",
)


def _graph_ai_preflight_service() -> GraphAIPreflightService:
    return GraphAIPreflightService()

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MIN_ENTITY_LABEL_LENGTH = 2
_MAX_AI_ENTITY_PRE_RESOLUTION_LABELS = 4
_AI_ENTITY_PRE_RESOLUTION_TIMEOUT_SECONDS = 2.0
_LLM_CANDIDATE_EXTRACTION_TIMEOUT_SECONDS = 5.0
_LLM_PROPOSAL_REVIEW_TIMEOUT_SECONDS = 5.0
_RELATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9\- ]{1,80}?)\s+"
            r"(?P<lemma>regulates|activated|activates|inhibits|interacts with|"
            r"interact with|associates with|associate with|associated with|"
            r"is associated with|was associated with|were associated with|"
            r"has been associated with|have been associated with|linked to|"
            r"is linked to|was linked to|were linked to|has been linked to|"
            r"have been linked to|causes|caused|drives|driven|promotes|"
            r"promoted|supports|supported|results in|resulted in|leads to|"
            r"led to|contributes to|contributed to|correlates with|"
            r"correlated with|is correlated with|was correlated with|"
            r"were correlated with)\s+"
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,80}?)\s+"
            r"(?:is|was|were)\s+regulated by\s+"
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "REGULATES",
    ),
    (
        re.compile(
            r"(?P<object>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,80}?)\s+"
            r"(?:is|was|were)\s+caused by\s+"
            r"(?P<subject>[A-Za-z0-9][A-Za-z0-9()\-/, ]{1,160})",
            re.IGNORECASE,
        ),
        "CAUSES",
    ),
)
_LEMMA_RELATION_TYPES = {
    "activate": "ACTIVATES",
    "activated": "ACTIVATES",
    "activates": "ACTIVATES",
    "associate with": "ASSOCIATED_WITH",
    "associated with": "ASSOCIATED_WITH",
    "associates with": "ASSOCIATED_WITH",
    "caused": "CAUSES",
    "causes": "CAUSES",
    "contribute to": "ASSOCIATED_WITH",
    "contributed to": "ASSOCIATED_WITH",
    "contributes to": "ASSOCIATED_WITH",
    "correlated with": "ASSOCIATED_WITH",
    "drive": "ASSOCIATED_WITH",
    "driven": "ASSOCIATED_WITH",
    "drives": "ASSOCIATED_WITH",
    "has been associated with": "ASSOCIATED_WITH",
    "has been linked to": "ASSOCIATED_WITH",
    "have been associated with": "ASSOCIATED_WITH",
    "have been linked to": "ASSOCIATED_WITH",
    "interact with": "INTERACTS_WITH",
    "inhibits": "INHIBITS",
    "interacts with": "INTERACTS_WITH",
    "is associated with": "ASSOCIATED_WITH",
    "is correlated with": "ASSOCIATED_WITH",
    "is linked to": "ASSOCIATED_WITH",
    "lead to": "CAUSES",
    "leads to": "CAUSES",
    "led to": "CAUSES",
    "linked to": "ASSOCIATED_WITH",
    "promote": "ACTIVATES",
    "promoted": "ACTIVATES",
    "promotes": "ACTIVATES",
    "regulate": "REGULATES",
    "regulates": "REGULATES",
    "reported": "ASSOCIATED_WITH",
    "resulted in": "CAUSES",
    "results in": "CAUSES",
    "support": "ASSOCIATED_WITH",
    "supported": "ASSOCIATED_WITH",
    "supports": "ASSOCIATED_WITH",
    "was associated with": "ASSOCIATED_WITH",
    "was correlated with": "ASSOCIATED_WITH",
    "was linked to": "ASSOCIATED_WITH",
    "were associated with": "ASSOCIATED_WITH",
    "were correlated with": "ASSOCIATED_WITH",
    "were linked to": "ASSOCIATED_WITH",
}


def sha256_hex(payload: bytes) -> str:
    """Return the SHA-256 digest for one document payload."""
    return hashlib.sha256(payload).hexdigest()


def _fingerprinted_step_key(prefix: str, *parts: str) -> str:
    """Return a stable per-input step key for replay-sensitive model calls."""
    payload = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{prefix}.{digest}"


def _llm_extraction_step_key(
    *,
    text: str,
    max_relations: int,
) -> str:
    """Return the stable extraction step key for one normalized document body."""
    normalized_text = normalize_text_document(text)
    return _fingerprinted_step_key(
        "research_init.llm_extraction.v1",
        str(max_relations),
        normalized_text[:4000],
    )


def _proposal_review_step_key(
    *,
    document: HarnessDocumentRecord,
    claims_text: str,
    goal_context_summary: str,
) -> str:
    """Return the stable proposal-review step key for one review payload."""
    return _fingerprinted_step_key(
        "document_extraction.proposal_review.v1",
        document.sha256,
        document.source_type,
        document.title,
        claims_text,
        goal_context_summary,
    )


def extract_pdf_text(payload: bytes) -> DocumentTextExtraction:
    """Extract text content from one PDF payload."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PDF upload support requires the optional 'pypdf' dependency.",
        ) from exc
    reader = PdfReader(io.BytesIO(payload))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    return DocumentTextExtraction(
        text_content="\n\n".join(text for text in page_texts if text.strip() != ""),
        page_count=len(reader.pages),
    )


def normalize_text_document(text: str) -> str:
    """Normalize one raw text submission for harness storage."""
    normalized_lines = [
        line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(normalized_lines).strip()


def extract_relation_candidates(text: str) -> list[ExtractedRelationCandidate]:
    """Extract lightweight relation candidates from document text."""
    normalized_text = normalize_text_document(text)
    if normalized_text == "":
        return []
    candidates: list[ExtractedRelationCandidate] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for sentence in _SENTENCE_SPLIT_RE.split(normalized_text):
        cleaned_sentence = " ".join(sentence.split()).strip()
        if cleaned_sentence == "":
            continue
        for pattern, fixed_relation_type in _RELATION_PATTERNS:
            match = pattern.search(cleaned_sentence)
            if match is None:
                continue
            subject_label = clean_candidate_label(
                match.group("subject"),
                prefer_tail=True,
            )
            object_label = clean_candidate_label(match.group("object"))
            relation_type = fixed_relation_type or _LEMMA_RELATION_TYPES.get(
                match.groupdict().get("lemma", "").strip().lower(),
                "ASSOCIATED_WITH",
            )
            if subject_label == "" or object_label == "":
                continue
            if canonical_entity_label_rejection_reason(subject_label) is not None:
                continue
            candidate_key = (
                subject_label.casefold(),
                relation_type,
                object_label.casefold(),
                cleaned_sentence.casefold(),
            )
            if candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            candidates.append(
                ExtractedRelationCandidate(
                    subject_label=subject_label,
                    relation_type=relation_type,
                    object_label=object_label,
                    sentence=cleaned_sentence,
                ),
            )
            break
    return candidates




async def extract_relation_candidates_with_llm(  # noqa: PLR0912, PLR0915
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> list[ExtractedRelationCandidate]:
    """Extract relation candidates using an LLM via ArtanaKernel.

    This function intentionally returns only the LLM-generated candidates.
    Use ``discover_relation_candidates()`` for LLM-first discovery with
    heuristic fallback and diagnostics.
    """
    from uuid import uuid4

    from artana_evidence_api.runtime_support import (
        ModelCapability,
        get_model_registry,
        has_configured_openai_api_key,
    )

    if not has_configured_openai_api_key():
        msg = "OPENAI_API_KEY not configured"
        raise RuntimeError(msg)

    output_schema = build_llm_extraction_output_schema(max_relations)

    # Create kernel components using Evidence API patterns
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
    from artana.ports.model import LiteLLMAdapter

    model_port = LiteLLMAdapter(timeout_seconds=60.0)
    kernel: ArtanaKernel | None = None
    store = None

    # Resolve model and normalize for LiteLLM (openai:gpt-5.4-mini → openai/gpt-5.4-mini)
    from artana_evidence_api.runtime_support import (
        create_artana_postgres_store,
        normalize_litellm_model_id,
    )

    registry = get_model_registry()
    model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
    model_id = normalize_litellm_model_id(model_spec.model_id)

    tenant = TenantContext(
        tenant_id="research-init-extraction",
        capabilities=frozenset(),
        budget_usd_limit=1.0,
    )

    prompt = (
        f"{LLM_EXTRACTION_SYSTEM_PROMPT}\n\n"
        f"---\nTEXT TO ANALYZE:\n---\n{text[:4000]}\n---\n\n"
        f"Return the relations as JSON. Remember: subject and object must each be "
        f"a short canonical entity name (1-4 words, like BRCA1, cisplatin, EGFR T790M, TNBC). "
        f"Never use sentence fragments as entity names."
    )
    step_key = _llm_extraction_step_key(
        text=text,
        max_relations=max_relations,
    )

    try:
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        result = await run_single_step_with_policy(
            client,
            run_id=f"research-init-extraction:{uuid4()}",
            tenant=tenant,
            model=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            replay_policy="fork_on_drift",
        )

        output = result.output
        parsed = cast(
            "LLMExtractionResultLike",
            (
                output
                if isinstance(output, output_schema)
                else output_schema.model_validate(output)
            ),
        )

        # Convert to ExtractedRelationCandidate with label cleanup
        candidates: list[ExtractedRelationCandidate] = []
        unknown_relation_types: set[str] = set()

        for rel in parsed.relations:
            relation_type = rel.relation_type.upper().strip().replace(" ", "_")
            # Fast path: deterministic synonym map for well-known aliases
            relation_type = LLM_RELATION_SYNONYMS.get(relation_type, relation_type)

            subject = clean_llm_entity_label(rel.subject)
            obj = clean_llm_entity_label(rel.object)

            # Skip if labels are empty or too generic after cleaning
            if (
                not subject
                or not obj
                or len(subject) < _MIN_ENTITY_LABEL_LENGTH
                or len(obj) < _MIN_ENTITY_LABEL_LENGTH
            ):
                continue

            # Track unknown types for AI resolution
            if relation_type not in LLM_VALID_RELATION_TYPES:
                unknown_relation_types.add(relation_type)

            candidates.append(
                ExtractedRelationCandidate(
                    subject_label=subject,
                    relation_type=relation_type,
                    object_label=obj,
                    sentence=rel.sentence.strip(),
                ),
            )

        # AI-powered resolution for unknown relation types
        if unknown_relation_types:
            from artana_evidence_api.relation_type_resolver import RelationTypeAction

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
                # Apply decisions: replace relation types in candidates
                for i, candidate in enumerate(candidates):
                    key = candidate.relation_type.strip().upper()
                    if key in decisions:
                        decision = decisions[key]
                        if decision.action in (
                            RelationTypeAction.MAP_TO_EXISTING,
                            RelationTypeAction.TYPO_CORRECTION,
                        ):
                            candidates[i] = ExtractedRelationCandidate(
                                subject_label=candidate.subject_label,
                                relation_type=decision.canonical_type,
                                object_label=candidate.object_label,
                                sentence=candidate.sentence,
                            )
                            logger.info(
                                "Relation type resolved: %s → %s (%s)",
                                key,
                                decision.canonical_type,
                                decision.action.value,
                            )
                        else:
                            # register_new: keep the canonical_type (cleaned)
                            candidates[i] = ExtractedRelationCandidate(
                                subject_label=candidate.subject_label,
                                relation_type=decision.canonical_type,
                                object_label=candidate.object_label,
                                sentence=candidate.sentence,
                            )
                            logger.info(
                                "New relation type will be registered: %s",
                                decision.canonical_type,
                            )
            except Exception:
                logger.exception(
                    "AI relation type resolution failed for %s; "
                    "keeping raw types (will resolve at promotion time)",
                    unknown_relation_types,
                )

        if not candidates:
            logger.debug(
                "LLM extraction returned zero usable candidates",
                extra={
                    "model_id": model_id,
                    "text_length": len(text),
                    "raw_relation_count": len(parsed.relations),
                    "usable_candidate_count": 0,
                },
            )
        return candidates
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
        fallback_candidates = extract_relation_candidates(normalized_text)
        return (
            fallback_candidates,
            candidate_fallback(
                status="fallback_error",
                error="LLM candidate extraction timed out",
                fallback_candidate_count=len(fallback_candidates),
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
        fallback_candidates = extract_relation_candidates(normalized_text)
        return (
            fallback_candidates,
            candidate_fallback(
                status="unavailable",
                error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
            ),
        )
    except RuntimeError as exc:
        fallback_candidates = extract_relation_candidates(normalized_text)
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
        fallback_candidates = extract_relation_candidates(normalized_text)
        return (
            fallback_candidates,
            candidate_fallback(
                status="fallback_error",
                error=str(exc),
                fallback_candidate_count=len(fallback_candidates),
            ),
        )

    if llm_candidates:
        return (
            llm_candidates,
            candidate_completed(candidate_count=len(llm_candidates)),
        )

    fallback_candidates = extract_relation_candidates(normalized_text)
    return (
        fallback_candidates,
        candidate_llm_empty(
            fallback_candidate_count=len(fallback_candidates),
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
                    "Goal relevance could not be reviewed precisely for this "
                    "proposal."
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
    claim_blocks: list[str] = []
    for index, draft in enumerate(drafts):
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
                    f"Claim {index}",
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
        "Return one review for each claim index."
    )
    step_key = _proposal_review_step_key(
        document=document,
        claims_text=claims_text,
        goal_context_summary=goal_context,
    )

    from uuid import uuid4

    kernel: ArtanaKernel | None = None
    store = None
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
            model_port=LiteLLMAdapter(timeout_seconds=60.0),
        )
        client = SingleStepModelClient(kernel=kernel)
        result = await asyncio.wait_for(
            run_single_step_with_policy(
                client,
                run_id=f"document-proposal-review:{uuid4()}",
                tenant=tenant,
                model=model_id,
                prompt=prompt,
                output_schema=output_schema,
                step_key=step_key,
                replay_policy="fork_on_drift",
            ),
            timeout=_LLM_PROPOSAL_REVIEW_TIMEOUT_SECONDS,
        )
        output = result.output
        parsed = cast(
            "ProposalReviewResultLike",
            (
                output
                if isinstance(output, output_schema)
                else output_schema.model_validate(output)
            ),
        )
        reviews_by_index = {
            item.index: DocumentProposalReview(
                factual_support=item.factual_support,
                goal_relevance=item.goal_relevance,
                priority=item.priority,
                rationale=item.rationale.strip(),
                factual_rationale=item.factual_rationale.strip(),
                relevance_rationale=item.relevance_rationale.strip(),
                method="llm_judge_v1",
                model_id=model_spec.model_id,
            )
            for item in parsed.reviews
            if 0 <= item.index < len(drafts)
        }
    except TimeoutError:
        reviews_by_index = {}
        diagnostics = proposal_review_fallback_error(
            "LLM proposal review timed out",
        )
    except Exception as exc:  # noqa: BLE001
        reviews_by_index = {}
        diagnostics = proposal_review_fallback_error(str(exc))
    else:
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
                review=reviews_by_index.get(index, fallback_reviews[index]),
                review_context=normalized_context,
            )
            for index, draft in enumerate(drafts)
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
]
