"""Strict document relation discovery without heuristic fallback."""

from __future__ import annotations

from artana_evidence_api.document_extraction import (
    extract_relation_candidates_with_llm,
    normalize_text_document,
)
from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_diagnostics import (
    candidate_completed,
    candidate_llm_empty,
    candidate_not_needed,
)


async def discover_relation_candidates_strict(
    text: str,
    *,
    max_relations: int = 10,
    space_context: str = "",
) -> tuple[list[ExtractedRelationCandidate], DocumentCandidateExtractionDiagnostics]:
    """Discover relation candidates through the LLM path only.

    This is for quality gates and trusted-evidence evaluation where heuristic
    fallback must be visible as failure, not silently substituted.
    """

    normalized_text = normalize_text_document(text)
    if normalized_text == "":
        return [], candidate_not_needed()

    llm_candidates = await extract_relation_candidates_with_llm(
        normalized_text,
        max_relations=max_relations,
        space_context=space_context,
    )
    candidates = list(llm_candidates)
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

    if candidates:
        return candidates, candidate_completed(
            candidate_count=len(candidates),
            pruned_generic_relation_count=pruned_generic_relation_count,
            quality_filtered_candidate_count=quality_filtered_candidate_count,
            llm_extraction_chunk_count=llm_extraction_chunk_count,
            llm_extraction_text_char_count=llm_extraction_text_char_count,
        )

    return [], candidate_llm_empty(
        fallback_candidate_count=0,
        pruned_generic_relation_count=pruned_generic_relation_count,
        quality_filtered_candidate_count=quality_filtered_candidate_count,
        llm_extraction_chunk_count=llm_extraction_chunk_count,
        llm_extraction_text_char_count=llm_extraction_text_char_count,
    )


__all__ = ["discover_relation_candidates_strict", "extract_relation_candidates_with_llm"]
