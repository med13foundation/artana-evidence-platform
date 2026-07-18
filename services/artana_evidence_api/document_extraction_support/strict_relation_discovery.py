"""Strict document relation discovery without heuristic fallback."""

from __future__ import annotations

from artana_evidence_api.document_extraction import (
    extract_relation_candidates_with_llm,
    normalize_text_document,
)
from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
    ExtractedRelationCandidate,
    normalize_claim_extraction_routing_status,
)
from artana_evidence_api.document_extraction_diagnostics import (
    candidate_completed,
    candidate_llm_empty,
    candidate_not_needed,
    candidate_semantic_incomplete,
)


async def discover_relation_candidates_strict(
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
    execution_namespace: str = "",
) -> tuple[list[ExtractedRelationCandidate], DocumentCandidateExtractionDiagnostics]:
    """Discover relation candidates through the LLM path only.

    This is for quality gates and trusted-evidence evaluation where heuristic
    fallback must be visible as failure, not silently substituted.
    """

    normalized_text = normalize_text_document(text)
    if normalized_text == "":
        return [], candidate_not_needed()

    if execution_namespace:
        llm_candidates = await extract_relation_candidates_with_llm(
            normalized_text,
            max_relations=max_relations,
            space_context=space_context,
            execution_namespace=execution_namespace,
        )
    else:
        llm_candidates = await extract_relation_candidates_with_llm(
            normalized_text,
            max_relations=max_relations,
            space_context=space_context,
        )
    candidates = llm_candidates
    pruned_generic_relation_count = int(
        getattr(llm_candidates, "pruned_generic_relation_count", 0),
    )
    quality_filtered_candidate_count = int(
        getattr(llm_candidates, "quality_filtered_candidate_count", 0),
    )
    llm_extraction_chunk_count = int(
        getattr(llm_candidates, "llm_extraction_chunk_count", 0),
    )
    llm_extraction_text_char_count = int(
        getattr(llm_candidates, "llm_extraction_text_char_count", 0),
    )
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
    inventory_binding_rejections = tuple(
        getattr(llm_candidates, "inventory_binding_rejections", ()),
    )
    inventory_incompleteness = tuple(
        getattr(llm_candidates, "inventory_incompleteness", ()),
    )
    controlled_event_links = tuple(
        getattr(llm_candidates, "controlled_event_links", ()),
    )
    controlled_event_link_ambiguities = tuple(
        getattr(llm_candidates, "controlled_event_link_ambiguities", ()),
    )

    if routing_status == "semantic_incomplete":
        return candidates, candidate_semantic_incomplete(
            candidate_count=len(candidates),
            claim_lineage=claim_lineage,
            raw_agent_outputs=raw_agent_outputs,
            model_attempt_records=model_attempt_records,
            inventory_binding_rejections=inventory_binding_rejections,
            inventory_incompleteness=inventory_incompleteness,
            controlled_event_links=controlled_event_links,
            controlled_event_link_ambiguities=controlled_event_link_ambiguities,
            llm_extraction_chunk_count=llm_extraction_chunk_count,
            llm_extraction_text_char_count=llm_extraction_text_char_count,
        )

    if candidates:
        return candidates, candidate_completed(
            candidate_count=len(candidates),
            pruned_generic_relation_count=pruned_generic_relation_count,
            quality_filtered_candidate_count=quality_filtered_candidate_count,
            llm_extraction_chunk_count=llm_extraction_chunk_count,
            llm_extraction_text_char_count=llm_extraction_text_char_count,
            claim_extraction_routing_status=routing_status,
            candidate_overflow_count=candidate_overflow_count,
            claim_lineage=claim_lineage,
            raw_agent_outputs=raw_agent_outputs,
            model_attempt_records=model_attempt_records,
            inventory_binding_rejections=inventory_binding_rejections,
            controlled_event_links=controlled_event_links,
            controlled_event_link_ambiguities=controlled_event_link_ambiguities,
        )

    return [], candidate_llm_empty(
        fallback_candidate_count=0,
        pruned_generic_relation_count=pruned_generic_relation_count,
        quality_filtered_candidate_count=quality_filtered_candidate_count,
        llm_extraction_chunk_count=llm_extraction_chunk_count,
        llm_extraction_text_char_count=llm_extraction_text_char_count,
        claim_extraction_routing_status=routing_status,
        claim_lineage=claim_lineage,
        raw_agent_outputs=raw_agent_outputs,
        model_attempt_records=model_attempt_records,
        inventory_binding_rejections=inventory_binding_rejections,
        controlled_event_links=controlled_event_links,
        controlled_event_link_ambiguities=controlled_event_link_ambiguities,
    )


__all__ = [
    "discover_relation_candidates_strict",
    "extract_relation_candidates_with_llm",
]
