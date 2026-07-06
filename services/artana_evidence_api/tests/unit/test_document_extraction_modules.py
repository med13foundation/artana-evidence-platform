"""Unit coverage for extracted document-extraction helper modules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from artana_evidence_api.document_context_summary import summarize_document_context
from artana_evidence_api.document_extraction import extract_relation_candidates
from artana_evidence_api.document_extraction_contracts import (
    DocumentCandidateExtractionDiagnostics,
    DocumentProposalReview,
    DocumentProposalReviewDiagnostics,
    ExtractedRelationCandidate,
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
    with_candidate_extraction_trust_metadata,
)
from artana_evidence_api.document_extraction_entities import (
    build_unresolved_entity_id,
    canonical_entity_label_rejection_reason,
    clean_candidate_label,
    clean_llm_entity_label,
    is_canonical_entity_label,
    require_match_display_label,
    require_match_id,
    resolve_exact_entity_label,
    split_compound_entity_label,
)
from artana_evidence_api.document_extraction_prompting import (
    LLM_EXTRACTION_SYSTEM_PROMPT,
    build_llm_extraction_output_schema,
    build_llm_weak_review_extraction_output_schema,
    build_proposal_review_output_schema,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_PROPOSE_NEW_RELATION_TYPE,
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
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    LLM_EXTRACTION_PROMPT_VERSION,
    llm_relations_to_candidates,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft


class _GraphGateway:
    def __init__(self, labels: dict[str, dict[str, object]] | None = None) -> None:
        self._labels = {} if labels is None else labels

    def list_entities(self, *, space_id, q: str, limit: int):  # noqa: ANN001
        del space_id, limit
        entities = []
        for key, payload in self._labels.items():
            aliases = payload.get("aliases", [])
            if key.casefold() != q.casefold() and q.casefold() not in {
                str(alias).casefold() for alias in aliases
            }:
                continue
            entities.append(
                SimpleNamespace(
                    id=payload["id"],
                    display_label=payload["display_label"],
                    aliases=aliases,
                ),
            )
        return SimpleNamespace(entities=entities)


def _document() -> HarnessDocumentRecord:
    now = datetime.now(UTC)
    return HarnessDocumentRecord(
        id="document-1",
        space_id=str(uuid4()),
        created_by=str(uuid4()),
        title="MED13 document",
        source_type="text",
        filename=None,
        media_type="text/plain",
        sha256="sha",
        byte_size=1,
        page_count=None,
        text_content="MED13 activates EGFR.",
        text_excerpt="MED13 activates EGFR.",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=str(uuid4()),
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="completed",
        metadata={},
        created_at=now,
        updated_at=now,
    )


def test_diagnostics_builders_normalize_candidate_and_review_status() -> None:
    assert candidate_not_needed() == DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="not_needed",
    )
    assert candidate_completed(candidate_count=2) == (
        DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=2,
        )
    )
    assert candidate_llm_empty(fallback_candidate_count=1).as_metadata() == {
        "llm_candidate_status": "llm_empty",
        "llm_candidate_attempted": True,
        "llm_candidate_failed": False,
        "agent_extraction_completed": False,
        "fallback_output_used": True,
        "trusted_evidence_eligible": False,
        "fallback_candidate_count": 1,
        "llm_candidate_error": "LLM succeeded but returned zero usable candidates",
    }
    assert candidate_fallback(
        status="unavailable",
        error="missing key",
        fallback_candidate_count=3,
    ).llm_candidate_status == "unavailable"
    assert runtime_error_candidate_status("OPENAI_API_KEY not configured") == (
        "unavailable"
    )
    assert runtime_error_candidate_status("boom") == "fallback_error"

    assert proposal_review_not_needed() == DocumentProposalReviewDiagnostics(
        llm_review_status="not_needed",
    )
    assert proposal_review_unavailable("missing").llm_review_status == "unavailable"
    assert proposal_review_fallback_error("timeout").llm_review_status == (
        "fallback_error"
    )
    assert proposal_review_completed() == DocumentProposalReviewDiagnostics(
        llm_review_status="completed",
    )


def test_prompt_schema_builders_validate_structured_outputs() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)
    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "MED13",
                    "subject_curie": "HGNC:22474",
                    "relation_type": "ACTIVATES",
                    "object": "EGFR",
                    "object_curie": "HGNC:3236",
                    "sentence": "MED13 activates EGFR.",
                },
            ],
        },
    )
    assert parsed.relations[0].subject == "MED13"
    assert parsed.relations[0].subject_curie == "HGNC:22474"
    assert parsed.relations[0].object_curie == "HGNC:3236"

    review_schema = build_proposal_review_output_schema()
    review = review_schema.model_validate(
        {
            "reviews": [
                {
                    "index": 0,
                    "factual_support": "strong",
                    "goal_relevance": "direct",
                    "priority": "prioritize",
                    "rationale": "Directly supported.",
                    "factual_rationale": "The sentence is direct.",
                    "relevance_rationale": "Matches the objective.",
                },
            ],
        },
    )
    assert review.reviews[0].priority == "prioritize"


def test_llm_extraction_schema_rejects_raw_unknown_relation_type() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)

    with pytest.raises(Exception):
        extraction_schema.model_validate(
            {
                "relations": [
                    {
                        "subject": "MET amplification",
                        "relation_type": "PROTECTS_AGAINST",
                        "object": "erlotinib",
                        "sentence": "MET amplification protects against erlotinib.",
                    },
                ],
            },
        )


def test_llm_extraction_prompt_preserves_useful_weak_claims_as_review_only() -> None:
    normalized_prompt = " ".join(LLM_EXTRACTION_SYSTEM_PROMPT.split())

    assert "WEAK REVIEW-ONLY RELATIONS" in normalized_prompt
    assert "only as review_only" in normalized_prompt
    assert "do not treat them as trusted evidence" in normalized_prompt
    assert "do not invent relations absent from the support sentence" in (
        normalized_prompt
    )
    assert "Reject vague non-relational role statements" in normalized_prompt
    assert "MED13 may be linked to congenital heart disease" in normalized_prompt
    assert "MET amplification was correlated with resistance" in normalized_prompt
    assert "AKT activation showed a trend toward association" in normalized_prompt


def test_llm_extraction_prompt_prioritizes_specific_sensitizes_relation() -> None:
    normalized_prompt = " ".join(LLM_EXTRACTION_SYSTEM_PROMPT.split())

    assert "BRCA1 loss sensitizes triple-negative breast cancer to cisplatin" in (
        normalized_prompt
    )
    assert "subject BRCA1 loss" in normalized_prompt
    assert "object cisplatin" in normalized_prompt
    assert "Do not replace this with ASSOCIATED_WITH DNA repair defects" in (
        normalized_prompt
    )


def test_llm_extraction_prompt_version_changes_for_review_only_schema() -> None:
    assert LLM_EXTRACTION_PROMPT_VERSION == "document_extraction.llm_extraction.v4"


def test_llm_extraction_schema_accepts_review_only_lane_fields() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)

    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "MED13",
                    "relation_type": "ASSOCIATED_WITH",
                    "object": "congenital heart disease",
                    "sentence": "MED13 may be linked to congenital heart disease.",
                    "review_status": "review_only",
                    "review_reason_codes": ["hedged_language", "may_link"],
                },
            ],
        },
    )

    assert parsed.relations[0].review_status == "review_only"
    assert parsed.relations[0].review_reason_codes == [
        "hedged_language",
        "may_link",
    ]


def test_weak_review_extraction_schema_allows_raw_relation_type_for_guard() -> None:
    extraction_schema = build_llm_weak_review_extraction_output_schema(max_relations=1)

    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "MED13",
                    "relation_type": "CASES",
                    "object": "congenital heart disease",
                    "sentence": "MED13 may be linked to congenital heart disease.",
                    "review_status": "review_only",
                },
            ],
        },
    )

    assert parsed.relations[0].relation_type == "CASES"


def test_llm_extraction_schema_accepts_confers_resistance_as_canonical() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)

    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "MET amplification",
                    "relation_type": "CONFERS_RESISTANCE_TO",
                    "object": "erlotinib",
                    "sentence": "MET amplification confers resistance to erlotinib.",
                },
            ],
        },
    )

    assert parsed.relations[0].relation_type == "CONFERS_RESISTANCE_TO"
    assert parsed.relations[0].proposed_relation_type is None

    proposed_canonical = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "MET amplification",
                    "relation_type": "PROPOSE_NEW_RELATION_TYPE",
                    "proposed_relation_type": "CONFERS_RESISTANCE_TO",
                    "new_relation_type_rationale": (
                        "Resistance is now governed as a canonical relation."
                    ),
                    "object": "erlotinib",
                    "sentence": "MET amplification confers resistance to erlotinib.",
                },
            ],
        },
    )

    assert proposed_canonical.relations[0].relation_type == "CONFERS_RESISTANCE_TO"
    assert proposed_canonical.relations[0].proposed_relation_type is None
    assert proposed_canonical.relations[0].new_relation_type_rationale is None


def test_llm_extraction_schema_canonicalizes_relation_type_synonyms() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)

    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "BRCA1 loss",
                    "relation_type": "SENSITIZES",
                    "object": "olaparib",
                    "sentence": "BRCA1 loss sensitizes tumors to olaparib.",
                },
            ],
        },
    )

    assert parsed.relations[0].relation_type == "SENSITIZES_TO"

    proposed_canonical = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "BRCA1 loss",
                    "relation_type": "PROPOSE_NEW_RELATION_TYPE",
                    "proposed_relation_type": "SENSITIZES",
                    "new_relation_type_rationale": (
                        "This is already covered by SENSITIZES_TO."
                    ),
                    "object": "olaparib",
                    "sentence": "BRCA1 loss sensitizes tumors to olaparib.",
                },
            ],
        },
    )

    assert proposed_canonical.relations[0].relation_type == "SENSITIZES_TO"
    assert proposed_canonical.relations[0].proposed_relation_type is None
    assert proposed_canonical.relations[0].new_relation_type_rationale is None


def test_llm_extraction_schema_accepts_structured_new_relation_proposal() -> None:
    extraction_schema = build_llm_extraction_output_schema(max_relations=1)

    parsed = extraction_schema.model_validate(
        {
            "relations": [
                {
                    "subject": "BRCA1 loss",
                    "relation_type": "PROPOSE_NEW_RELATION_TYPE",
                    "proposed_relation_type": "REDUCES_TOXICITY_OF",
                    "new_relation_type_rationale": (
                        "Toxicity-specific treatment effect needs governance."
                    ),
                    "object": "cisplatin",
                    "sentence": "BRCA1 loss reduces cisplatin toxicity.",
                },
            ],
        },
    )

    assert parsed.relations[0].relation_type == "PROPOSE_NEW_RELATION_TYPE"
    assert parsed.relations[0].proposed_relation_type == "REDUCES_TOXICITY_OF"

    with pytest.raises(ValueError):
        extraction_schema.model_validate({"relations": [{"subject": ""}]})


def test_relation_taxonomy_keeps_canonical_types_and_synonyms_together() -> None:
    assert "ASSOCIATED_WITH" in LLM_VALID_RELATION_TYPES
    assert "ACTIVATES" in LLM_VALID_RELATION_TYPES
    assert "CONFERS_RESISTANCE_TO" in LLM_VALID_RELATION_TYPES
    assert LLM_RELATION_SYNONYMS["CORRELATED_WITH"] == "ASSOCIATED_WITH"
    assert LLM_RELATION_SYNONYMS["STIMULATES"] == "ACTIVATES"
    assert all(
        canonical_type in LLM_VALID_RELATION_TYPES
        for canonical_type in LLM_RELATION_SYNONYMS.values()
    )


def test_llm_prompt_lists_every_extraction_relation_type() -> None:
    for relation_type in LLM_VALID_RELATION_TYPES:
        assert relation_type in LLM_EXTRACTION_SYSTEM_PROMPT


def test_llm_prompt_requires_preserving_specific_relation_arguments() -> None:
    assert "Preserve modifiers that define the biomedical entity" in (
        LLM_EXTRACTION_SYSTEM_PROMPT
    )
    assert "BRCA-mutated ovarian cancer" in LLM_EXTRACTION_SYSTEM_PROMPT
    assert "response to pembrolizumab" in LLM_EXTRACTION_SYSTEM_PROMPT


def test_llm_conversion_rejects_broadened_specific_object_label() -> None:
    parsed = SimpleNamespace(
        relations=[
            SimpleNamespace(
                subject="Olaparib",
                subject_curie=None,
                relation_type="TREATS",
                proposed_relation_type=None,
                new_relation_type_rationale=None,
                object="ovarian cancer",
                object_curie=None,
                sentence=(
                    "Olaparib treats BRCA-mutated ovarian cancer by exploiting "
                    "homologous recombination deficiency."
                ),
            ),
        ],
    )

    candidates, unknown_relation_types = llm_relations_to_candidates(parsed)

    assert candidates == []
    assert unknown_relation_types == set()


def test_llm_conversion_preserves_specific_relation_arguments() -> None:
    parsed = SimpleNamespace(
        relations=[
            SimpleNamespace(
                subject="Olaparib",
                subject_curie=None,
                relation_type="TREATS",
                proposed_relation_type=None,
                new_relation_type_rationale=None,
                object="BRCA-mutated ovarian cancer",
                object_curie=None,
                sentence=(
                    "Olaparib treats BRCA-mutated ovarian cancer by exploiting "
                    "homologous recombination deficiency."
                ),
            ),
        ],
    )

    candidates, unknown_relation_types = llm_relations_to_candidates(parsed)

    assert unknown_relation_types == set()
    assert len(candidates) == 1
    assert candidates[0].object_label == "BRCA-mutated ovarian cancer"


def test_llm_conversion_preserves_model_review_only_reason_hints() -> None:
    parsed = SimpleNamespace(
        relations=[
            SimpleNamespace(
                subject="MED13",
                subject_curie=None,
                relation_type="ASSOCIATED_WITH",
                proposed_relation_type=None,
                new_relation_type_rationale=None,
                object="congenital heart disease",
                object_curie=None,
                sentence="MED13 was associated with congenital heart disease.",
                review_status="review_only",
                review_reason_codes=["agent_review_hint"],
            ),
        ],
    )

    candidates, unknown_relation_types = llm_relations_to_candidates(parsed)

    assert unknown_relation_types == set()
    assert len(candidates) == 1
    assert candidates[0].review_status == "review_only"
    assert candidates[0].review_reason_codes == ("agent_review_hint",)
    assert candidates[0].trusted_evidence_eligible is False


def test_llm_conversion_keeps_confers_resistance_as_canonical_candidate() -> None:
    parsed = SimpleNamespace(
        relations=[
            SimpleNamespace(
                subject="MET amplification",
                subject_curie=None,
                relation_type="CONFERS_RESISTANCE_TO",
                proposed_relation_type=None,
                new_relation_type_rationale=None,
                object="erlotinib",
                object_curie=None,
                sentence="MET amplification confers resistance to erlotinib.",
            ),
        ],
    )

    candidates, unknown_relation_types = llm_relations_to_candidates(parsed)

    assert unknown_relation_types == set()
    assert len(candidates) == 1
    assert candidates[0].relation_type == "CONFERS_RESISTANCE_TO"
    assert candidates[0].proposed_relation_type is None
    assert candidates[0].relation_governance_status == "canonical"


def test_llm_conversion_repairs_resistance_proposal_typo_without_trusting_it() -> None:
    parsed = SimpleNamespace(
        relations=[
            SimpleNamespace(
                subject="MET amplification",
                subject_curie=None,
                relation_type="PROPOSE_NEW_RELATION_TYPE",
                proposed_relation_type="CONFOERS_RESISTANCE_TO",
                new_relation_type_rationale="Typo in resistance proposal.",
                object="erlotinib",
                object_curie=None,
                sentence="MET amplification confers resistance to erlotinib.",
            ),
        ],
    )

    candidates, unknown_relation_types = llm_relations_to_candidates(parsed)

    assert unknown_relation_types == set()
    assert len(candidates) == 1
    assert candidates[0].relation_type == "PROPOSE_NEW_RELATION_TYPE"
    assert candidates[0].proposed_relation_type == "CONFERS_RESISTANCE_TO"
    assert candidates[0].relation_governance_status == "requires_relation_review"
    assert candidates[0].trusted_evidence_eligible is False
    assert "proposal_relation_type_repaired_to:CONFERS_RESISTANCE_TO" in (
        candidates[0].new_relation_type_rationale or ""
    )


def test_llm_conversion_verifies_model_curie_hints_against_dictionary() -> None:
    parsed = SimpleNamespace(
        relations=[
            SimpleNamespace(
                subject="MED13",
                subject_curie="HGNC:22474",
                relation_type="CAUSES",
                proposed_relation_type=None,
                new_relation_type_rationale=None,
                object="developmental delay",
                object_curie="HP:0001263",
                sentence="MED13 causes developmental delay.",
            ),
        ],
    )

    candidates, unknown_relation_types = llm_relations_to_candidates(parsed)

    assert unknown_relation_types == set()
    assert len(candidates) == 1
    assert candidates[0].subject_curie == "HGNC:22474"
    assert candidates[0].subject_curie_source == "verified_linker"
    assert candidates[0].object_curie == "HP:0001263"
    assert candidates[0].object_curie_source == "verified_linker"


def test_entity_helpers_clean_split_and_resolve_labels() -> None:
    gateway = _GraphGateway(
        {
            "EGFR": {
                "id": uuid4(),
                "display_label": "EGFR",
                "aliases": ["ERBB1"],
            },
            "AKT1": {
                "id": uuid4(),
                "display_label": "AKT1",
                "aliases": [],
            },
        },
    )
    space_id = uuid4()

    assert clean_candidate_label("mutation in MED13 in patients") == "MED13"
    assert clean_llm_entity_label("Inherited pathogenic variants in BRCA1") == "BRCA1"
    assert clean_llm_entity_label("Inherited variants in MED13 or MED13L") == ""
    assert clean_llm_entity_label("Inherited variants in Med13 or MED13L") == ""
    assert clean_llm_entity_label("BRCA1/2") == ""
    assert clean_llm_entity_label("were") == ""
    assert clean_llm_entity_label("Some features are common between conditions") == ""
    assert clean_llm_entity_label("and MED13L are now all") == "MED13L"
    assert build_unresolved_entity_id("MED13 gene") == "unresolved:med13_gene"
    assert split_compound_entity_label(
        space_id=space_id,
        label="EGFR and AKT1",
        graph_api_gateway=gateway,
    ) == ("EGFR", "AKT1")
    resolved = resolve_exact_entity_label(
        space_id=space_id,
        label="ERBB1",
        graph_api_gateway=gateway,
    )
    assert resolved is not None
    assert require_match_display_label(resolved) == "EGFR"
    assert require_match_id(resolved) != ""

    gene_gateway = _GraphGateway(
        {
            "MED13": {
                "id": uuid4(),
                "display_label": "MED13",
                "aliases": [],
            },
            "MED13L": {
                "id": uuid4(),
                "display_label": "MED13L",
                "aliases": [],
            },
        },
    )
    assert split_compound_entity_label(
        space_id=space_id,
        label="MED13 or MED13L",
        graph_api_gateway=gene_gateway,
    ) == ("MED13 or MED13L",)


@pytest.mark.parametrize(
    "label",
    [
        "BRCA1",
        "cisplatin",
        "EGFR T790M",
        "triple-negative breast cancer",
        "DNA damage repair",
        "PD-L1",
        "5-FU",
        "1q21",
        "MED13L",
        "BRCA2",
        "Cancer associated fibroblasts",
        "BRCA1 regulated genes",
        "T cell effector activity",
        "dilated cardiomyopathy",
    ],
)
def test_canonical_entity_label_filter_accepts_entity_like_labels(label: str) -> None:
    assert is_canonical_entity_label(label)


@pytest.mark.parametrize(
    ("label", "reason"),
    [
        ("were", "standalone_fragment_label"),
        ("sometimes", "standalone_fragment_label"),
        ("13L", "numeric_fragment_label"),
        ("and MED13L are now all", "leading_fragment_token"),
        ("Some features are common between the four conditions", "entity_label_too_long"),
        ("how the Module", "leading_fragment_token"),
        ("gene expression both positively", "sentence_fragment_modifier"),
        ("Differentially expressed genes", "sentence_fragment_modifier"),
        ("MED13 or MED13L", "ambiguous_gene_symbol_mention"),
        ("MED13 and MED13L", "ambiguous_gene_symbol_mention"),
        ("Med13 or MED13L", "ambiguous_gene_symbol_mention"),
        ("BRCA1, BRCA2", "ambiguous_gene_symbol_mention"),
        ("BRCA1/BRCA2", "ambiguous_gene_symbol_mention"),
        ("BRCA1/2", "ambiguous_gene_symbol_mention"),
        ("CDK8 and CDK19", "ambiguous_gene_symbol_mention"),
        ("MED13 vs. MED13L", "ambiguous_gene_symbol_mention"),
    ],
)
def test_canonical_entity_label_filter_rejects_fragments(
    label: str,
    reason: str,
) -> None:
    assert canonical_entity_label_rejection_reason(label) == reason
    assert not is_canonical_entity_label(label)


def test_ambiguous_gene_filter_allows_different_families_joined_with_and() -> None:
    assert canonical_entity_label_rejection_reason("BRCA1 and TP53") is None
    assert is_canonical_entity_label("BRCA1 and TP53")


def test_regex_extraction_drops_fragmentary_review_sentence_subjects() -> None:
    candidates = extract_relation_candidates(
        "MED12, MED13, CDK8, and MED13L are now all associated with "
        "developmental disorders.",
    )

    assert candidates == []


def test_review_helpers_apply_ranked_metadata_to_drafts() -> None:
    context = build_document_review_context(
        objective="Study MED13 EGFR activation.",
        current_hypotheses=("MED13 activates EGFR", "MED13 activates EGFR"),
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )
    review = build_fallback_document_review(
        candidate=candidate,
        review_context=context,
    )
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="document-1:0",
        title="MED13 activates EGFR",
        summary="MED13 activates EGFR.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[{"relevance": 0.1}],
        payload={},
        metadata={},
        document_id="document-1",
    )

    updated = apply_document_proposal_review(
        draft=draft,
        review=review,
        review_context=context,
    )

    assert "Objective: Study MED13 EGFR activation." in goal_context_summary(context)
    assert shorten_text("a " * 20, max_length=10).endswith("...")
    assert updated.confidence > draft.confidence
    assert updated.metadata["proposal_review"]["method"] == "heuristic_fallback_v1"
    assert review_from_draft_metadata(updated) == review


def test_review_helpers_rank_specific_grounded_entailed_claim_above_generic_ungrounded_claim() -> None:
    context = build_document_review_context(objective="Study MED13 EGFR activation.")
    review = DocumentProposalReview(
        factual_support="strong",
        goal_relevance="direct",
        priority="prioritize",
        rationale="Same review labels for ranking isolation.",
        factual_rationale="Same factual label.",
        relevance_rationale="Same relevance label.",
        method="unit_test",
    )
    strong = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="document-1:0",
        title="MED13 activates EGFR",
        summary="MED13 activates EGFR.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[{"relevance": 0.1}],
        payload={"proposed_claim_type": "ACTIVATES"},
        metadata={
            "evidence_grounding": {
                "grounded": True,
                "subject_present": True,
                "object_present": True,
            },
            "support_verification": {"support": "ENTAILS"},
        },
        document_id="document-1",
    )
    weak = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="document-1:1",
        title="MED13 associated with phenotype",
        summary="The paper discusses cardiac development.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[{"relevance": 0.1}],
        payload={"proposed_claim_type": "ASSOCIATED_WITH"},
        metadata={
            "evidence_grounding": {
                "grounded": False,
                "subject_present": False,
                "object_present": False,
            },
        },
        document_id="document-1",
    )

    ranked_strong = apply_document_proposal_review(
        draft=strong,
        review=review,
        review_context=context,
    )
    ranked_weak = apply_document_proposal_review(
        draft=weak,
        review=review,
        review_context=context,
    )

    assert ranked_strong.ranking_score > ranked_weak.ranking_score
    assert ranked_strong.metadata["evidence_quality_component"] == 1.0
    assert ranked_weak.metadata["evidence_quality_component"] == 0.0


def test_draft_builder_assembles_reviewed_proposals_from_candidates() -> None:
    gateway = _GraphGateway()
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=gateway,
        review_context=build_document_review_context(
            objective="Study MED13 activates EGFR.",
        ),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].payload["proposed_subject"] == "unresolved:med13"
    assert drafts[0].payload["proposed_object"] == "unresolved:egfr"
    assert drafts[0].metadata["proposal_review"]["goal_relevance"] == "direct"


def test_draft_builder_propagates_document_evidence_grade() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR in a randomized trial.",
    )
    document = replace(
        _document(),
        source_type="pubmed",
        text_content="MED13 activates EGFR in a randomized trial.",
        text_excerpt="MED13 activates EGFR in a randomized trial.",
        metadata={
            "pubmed": {
                "pmid": "12345",
                "publication_types": ["Randomized Controlled Trial"],
            },
        },
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].evidence_grade == "High"
    assert drafts[0].metadata["evidence_grade"] == "High"
    assert drafts[0].metadata["evidence_grounding"] == {
        "anchor_start": 0,
        "anchor_end": 43,
        "match_kind": "exact",
        "score": 1.0,
        "subject_present": True,
        "object_present": True,
        "grounded": True,
    }
    assert drafts[0].metadata["support_verification"]["support"] == "ENTAILS"


def test_draft_builder_marks_contradicted_support_low_priority() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 does not activate EGFR.",
    )
    document = replace(
        _document(),
        text_content="MED13 does not activate EGFR.",
        text_excerpt="MED13 does not activate EGFR.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].ranking_score == 0.1
    assert drafts[0].metadata["support_verification"]["support"] == "CONTRADICTS"


def test_draft_builder_preserves_review_only_candidate_trust_floor() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        subject_curie="HGNC:22474",
        subject_curie_source="verified_linker",
        relation_type="CAUSES",
        object_label="developmental delay",
        object_curie="HP:0001263",
        object_curie_source="verified_linker",
        sentence="MED13 causes developmental delay.",
        review_status="review_only",
        review_reason_codes=("hedged_language", "weak_claim"),
    )
    document = replace(
        _document(),
        text_content="MED13 causes developmental delay.",
        text_excerpt="MED13 causes developmental delay.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].metadata["review_status"] == "review_only"
    assert drafts[0].metadata["review_reason_codes"] == [
        "hedged_language",
        "weak_claim",
    ]

    (trusted_draft,) = with_candidate_extraction_trust_metadata(
        drafts=drafts,
        diagnostics=DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=1,
        ),
    )

    assert trusted_draft.metadata["trusted_evidence_eligible"] is False
    assert trusted_draft.metadata["trust_tier"] == "agent_candidate"
    assert trusted_draft.metadata["trust_floor_failures"] == [
        "review_only_candidate",
    ]


def test_draft_builder_omits_support_verification_when_grounding_fails() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 activates EGFR.",
    )
    document = replace(
        _document(),
        text_content="The paper discusses cardiac development.",
        text_excerpt="The paper discusses cardiac development.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].metadata["evidence_grounding"]["grounded"] is False
    assert "support_verification" not in drafts[0].metadata


def test_candidate_extraction_trust_requires_entailing_support() -> None:
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        title="MED13 activates EGFR",
        summary="MED13 and EGFR were both measured.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[],
        payload={},
        metadata={
            "support_verification": {
                "support": "NEUTRAL",
                "rationale": "No relation cue.",
                "model_id": "artana-heuristic-support-v1",
            },
        },
    )

    (trusted_draft,) = with_candidate_extraction_trust_metadata(
        drafts=(draft,),
        diagnostics=DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=1,
        ),
    )

    assert trusted_draft.metadata["agent_extraction_completed"] is True
    assert trusted_draft.metadata["fallback_output_used"] is False
    assert trusted_draft.metadata["trusted_evidence_eligible"] is False


def test_candidate_extraction_trust_requires_all_hard_floors() -> None:
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        title="MED13 causes developmental delay",
        summary="MED13 causes developmental delay.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[],
        payload={"proposed_claim_type": "CAUSES"},
        metadata={
            "evidence_grounding": {
                "grounded": True,
                "subject_present": True,
                "object_present": True,
            },
            "support_verification": {"support": "ENTAILS"},
            "entity_linking": {
                "subject": {"status": "abstained", "reason": "missing_curie"},
                "object": {
                    "status": "linked",
                    "curie": "HP:0001263",
                    "source": "verified_linker",
                },
            },
        },
    )

    (trusted_draft,) = with_candidate_extraction_trust_metadata(
        drafts=(draft,),
        diagnostics=DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=1,
        ),
    )

    assert trusted_draft.metadata["agent_extraction_completed"] is True
    assert trusted_draft.metadata["fallback_output_used"] is False
    assert trusted_draft.metadata["trusted_evidence_eligible"] is False
    assert trusted_draft.metadata["trust_tier"] == "verified_evidence"
    assert trusted_draft.metadata["trust_floor_failures"] == [
        "curie_linked_subject",
    ]


def test_candidate_extraction_trust_marks_verified_linked_agent_relation_trusted() -> (
    None
):
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        title="MED13 causes developmental delay",
        summary="MED13 causes developmental delay.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[],
        payload={"proposed_claim_type": "CAUSES"},
        metadata={
            "evidence_grounding": {
                "grounded": True,
                "subject_present": True,
                "object_present": True,
            },
            "support_verification": {"support": "ENTAILS"},
            "entity_linking": {
                "subject": {
                    "status": "linked",
                    "curie": "HGNC:22474",
                    "source": "verified_linker",
                },
                "object": {
                    "status": "linked",
                    "curie": "HP:0001263",
                    "source": "verified_linker",
                },
            },
        },
    )

    (trusted_draft,) = with_candidate_extraction_trust_metadata(
        drafts=(draft,),
        diagnostics=DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=1,
        ),
    )

    assert trusted_draft.metadata["trusted_evidence_eligible"] is True
    assert trusted_draft.metadata["trust_tier"] == "trusted"
    assert trusted_draft.metadata["trust_floor_failures"] == []


def test_candidate_extraction_trust_blocks_review_only_candidates() -> None:
    draft = HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        title="MED13 causes developmental delay",
        summary="MED13 may cause developmental delay.",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[],
        payload={"proposed_claim_type": "CAUSES"},
        metadata={
            "review_status": "review_only",
            "review_reason_codes": ["hedged_language"],
            "evidence_grounding": {
                "grounded": True,
                "subject_present": True,
                "object_present": True,
            },
            "support_verification": {"support": "ENTAILS"},
            "entity_linking": {
                "subject": {
                    "status": "linked",
                    "curie": "HGNC:22474",
                    "source": "verified_linker",
                },
                "object": {
                    "status": "linked",
                    "curie": "HP:0001263",
                    "source": "verified_linker",
                },
            },
        },
    )

    (trusted_draft,) = with_candidate_extraction_trust_metadata(
        drafts=(draft,),
        diagnostics=DocumentCandidateExtractionDiagnostics(
            llm_candidate_status="completed",
            llm_candidate_count=1,
        ),
    )

    assert trusted_draft.metadata["trusted_evidence_eligible"] is False
    assert trusted_draft.metadata["trust_tier"] == "agent_candidate"
    assert trusted_draft.metadata["trust_floor_failures"] == [
        "review_only_candidate",
    ]


def test_draft_builder_skips_non_canonical_subject_labels() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="were",
        relation_type="ASSOCIATED_WITH",
        object_label="other congenital anomalies",
        sentence="They were associated with other congenital anomalies.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert drafts == ()
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "non_canonical_subject_label"
    assert skipped[0]["label"] == "were"
    assert skipped[0]["label_rejection_reason"] == "standalone_fragment_label"


def test_draft_builder_skips_raw_unknown_relation_types(
) -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="PROTECTS_AGAINST",
        object_label="developmental disorder",
        sentence="MED13 protects against developmental disorder.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert drafts == ()
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "unknown_relation_type"
    assert skipped[0]["relation_type"] == "PROTECTS_AGAINST"


def test_draft_builder_stages_governed_relation_type_proposals() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="BRCA1 loss",
        relation_type=LLM_PROPOSE_NEW_RELATION_TYPE,
        proposed_relation_type="REDUCES_TOXICITY_OF",
        new_relation_type_rationale=(
            "Toxicity-specific treatment effect needs governance."
        ),
        relation_governance_status="requires_relation_review",
        object_label="cisplatin",
        sentence="BRCA1 loss reduces cisplatin toxicity.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 1
    assert drafts[0].proposal_type == "relation_type_candidate"
    assert drafts[0].payload["proposed_relation_type"] == "REDUCES_TOXICITY_OF"
    assert drafts[0].payload["trusted_evidence_eligible"] is False
    assert drafts[0].metadata["relation_governance_status"] == (
        "requires_relation_review"
    )
    assert drafts[0].metadata["trusted_evidence_eligible"] is False


def test_draft_builder_prunes_redundant_generic_relation_siblings() -> None:
    document = replace(
        _document(),
        text_content="MED13 activates EGFR and is associated with EGFR.",
        text_excerpt="MED13 activates EGFR and is associated with EGFR.",
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ASSOCIATED_WITH",
            object_label="EGFR",
            sentence="MED13 activates EGFR and is associated with EGFR.",
        ),
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ACTIVATES",
            object_label="EGFR",
            sentence="MED13 activates EGFR and is associated with EGFR.",
        ),
    ]

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert len(drafts) == 1
    assert drafts[0].payload["proposed_claim_type"] == "ACTIVATES"
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "redundant_generic_relation_sibling"
    assert skipped[0]["relation_type"] == "ASSOCIATED_WITH"
    assert skipped[0]["suppressing_relation_type"] == "ACTIVATES"


def test_draft_builder_prunes_generic_tail_when_specific_subject_sibling_exists() -> None:
    document = replace(
        _document(),
        text_content=(
            "EGFR T790M causes resistance to gefitinib and is associated "
            "with disease progression."
        ),
        text_excerpt=(
            "EGFR T790M causes resistance to gefitinib and is associated "
            "with disease progression."
        ),
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="EGFR T790M",
            relation_type="CONFERS_RESISTANCE_TO",
            object_label="gefitinib",
            sentence=(
                "EGFR T790M causes resistance to gefitinib and is associated "
                "with disease progression."
            ),
        ),
        ExtractedRelationCandidate(
            subject_label="EGFR T790M",
            relation_type="ASSOCIATED_WITH",
            object_label="disease progression",
            sentence=(
                "EGFR T790M causes resistance to gefitinib and is associated "
                "with disease progression."
            ),
        ),
    ]

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert len(drafts) == 1
    assert drafts[0].payload["proposed_claim_type"] == "CONFERS_RESISTANCE_TO"
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "redundant_generic_relation_sibling"
    assert skipped[0]["relation_type"] == "ASSOCIATED_WITH"
    assert skipped[0]["suppressing_relation_type"] == "CONFERS_RESISTANCE_TO"


def test_draft_builder_prunes_generic_tail_when_governed_proposal_sibling_exists() -> None:
    document = replace(
        _document(),
        text_content=(
            "MET amplification confers resistance to erlotinib and is "
            "associated with EGFR-mutant lung adenocarcinoma."
        ),
        text_excerpt=(
            "MET amplification confers resistance to erlotinib and is "
            "associated with EGFR-mutant lung adenocarcinoma."
        ),
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MET amplification",
            relation_type="CONFERS_RESISTANCE_TO",
            object_label="erlotinib",
            sentence=(
                "MET amplification confers resistance to erlotinib and is "
                "associated with EGFR-mutant lung adenocarcinoma."
            ),
        ),
        ExtractedRelationCandidate(
            subject_label="MET amplification",
            relation_type="ASSOCIATED_WITH",
            object_label="EGFR-mutant lung adenocarcinoma",
            sentence=(
                "MET amplification confers resistance to erlotinib and is "
                "associated with EGFR-mutant lung adenocarcinoma."
            ),
        ),
    ]

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert len(drafts) == 1
    assert drafts[0].payload["proposed_claim_type"] == "CONFERS_RESISTANCE_TO"
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "redundant_generic_relation_sibling"
    assert skipped[0]["relation_type"] == "ASSOCIATED_WITH"
    assert skipped[0]["suppressing_relation_type"] == "CONFERS_RESISTANCE_TO"


def test_draft_builder_keeps_generic_relation_from_different_sentence() -> None:
    document = replace(
        _document(),
        text_content=(
            "MED13 activates EGFR in cardiomyocytes. "
            "MED13 was also associated with EGFR expression in fibroblasts."
        ),
        text_excerpt=(
            "MED13 activates EGFR in cardiomyocytes. "
            "MED13 was also associated with EGFR expression in fibroblasts."
        ),
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ACTIVATES",
            object_label="EGFR",
            sentence="MED13 activates EGFR in cardiomyocytes.",
        ),
        ExtractedRelationCandidate(
            subject_label="MED13",
            relation_type="ASSOCIATED_WITH",
            object_label="EGFR",
            sentence="MED13 was also associated with EGFR expression in fibroblasts.",
        ),
    ]

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert len(drafts) == 2
    assert skipped == []
    assert {draft.payload["proposed_claim_type"] for draft in drafts} == {
        "ACTIVATES",
        "ASSOCIATED_WITH",
    }


def test_draft_builder_skips_weak_generic_relation_candidates() -> None:
    document = replace(
        _document(),
        text_content=(
            "MET amplification was correlated with resistance in a small "
            "exploratory cohort."
        ),
        text_excerpt=(
            "MET amplification was correlated with resistance in a small "
            "exploratory cohort."
        ),
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="resistance",
        sentence=(
            "MET amplification was correlated with resistance in a small "
            "exploratory cohort."
        ),
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert drafts == ()
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "weak_generic_relation"
    assert skipped[0]["relation_type"] == "ASSOCIATED_WITH"


def test_draft_builder_propagates_curie_identifiers_for_graph_entity_creation() -> None:
    document = replace(
        _document(),
        text_content="MED13 causes developmental delay.",
        text_excerpt="MED13 causes developmental delay.",
    )
    candidates = [
        ExtractedRelationCandidate(
                subject_label="MED13",
                subject_curie="HGNC:22474",
                subject_curie_source="verified_linker",
                relation_type="CAUSES",
                object_label="developmental delay",
                object_curie="HP:0001263",
                object_curie_source="verified_linker",
                sentence="MED13 causes developmental delay.",
            ),
        ]

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_GraphGateway(),
    )

    assert skipped == []
    assert len(drafts) == 1
    subject_candidate = drafts[0].payload["proposed_subject_entity_candidate"]
    object_candidate = drafts[0].payload["proposed_object_entity_candidate"]
    assert subject_candidate["entity_type"] == "GENE"
    assert subject_candidate["identifiers"] == {"hgnc_id": "HGNC:22474"}
    assert object_candidate["entity_type"] == "PHENOTYPE"
    assert object_candidate["identifiers"] == {"hpo_id": "HP:0001263"}
    assert drafts[0].metadata["subject_curie"] == "HGNC:22474"
    assert drafts[0].metadata["object_curie"] == "HP:0001263"
    assert drafts[0].metadata["entity_linking"]["subject"]["status"] == "linked"
    assert drafts[0].metadata["entity_linking"]["object"]["status"] == "linked"
    assert drafts[0].metadata["entity_linking"]["subject"]["trusted_identifier"] is True
    assert drafts[0].metadata["entity_linking"]["object"]["trusted_identifier"] is True


def test_draft_builder_replaces_wrong_model_curie_hints_with_dictionary_ids() -> None:
    document = replace(
        _document(),
        text_content="MED13 causes developmental delay.",
        text_excerpt="MED13 causes developmental delay.",
    )
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            subject_curie="MONDO:0007254",
            subject_curie_source="model",
            relation_type="CAUSES",
            object_label="developmental delay",
            object_curie="HGNC:22474",
            object_curie_source="model",
            sentence="MED13 causes developmental delay.",
        ),
    ]

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=document,
        candidates=candidates,
        graph_api_gateway=_GraphGateway(),
    )

    assert skipped == []
    assert len(drafts) == 1
    subject_candidate = drafts[0].payload["proposed_subject_entity_candidate"]
    object_candidate = drafts[0].payload["proposed_object_entity_candidate"]
    assert subject_candidate["identifiers"] == {"hgnc_id": "HGNC:22474"}
    assert object_candidate["identifiers"] == {"hpo_id": "HP:0001263"}
    assert drafts[0].metadata["entity_linking"]["subject"]["source"] == (
        "verified_linker"
    )
    assert drafts[0].metadata["entity_linking"]["object"]["source"] == (
        "verified_linker"
    )
    assert drafts[0].metadata["entity_linking"]["subject"]["trusted_identifier"] is True
    assert drafts[0].metadata["entity_linking"]["object"]["trusted_identifier"] is True
    assert drafts[0].metadata["entity_linking"]["subject"]["model_hint_status"] == (
        "replaced"
    )
    assert drafts[0].metadata["entity_linking"]["object"]["model_hint_status"] == (
        "replaced"
    )


def test_draft_builder_skips_ambiguous_gene_family_subject_labels() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13 or MED13L",
        relation_type="ASSOCIATED_WITH",
        object_label="developmental disorder",
        sentence="MED13 or MED13L was associated with developmental disorder.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert drafts == ()
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "non_canonical_subject_label"
    assert skipped[0]["label"] == "MED13 or MED13L"
    assert skipped[0]["label_rejection_reason"] == "ambiguous_gene_symbol_mention"


def test_draft_builder_skips_non_canonical_object_labels() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="REGULATES",
        object_label="gene expression both positively",
        sentence="MED13 regulates gene expression both positively.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=_GraphGateway(),
        review_context=build_document_review_context(),
    )

    assert drafts == ()
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "non_canonical_object_label"
    assert skipped[0]["label"] == "gene expression both positively"


def test_draft_builder_uses_resolved_entities_and_splits_compound_objects() -> None:
    med13_id = uuid4()
    egfr_id = uuid4()
    akt1_id = uuid4()
    gateway = _GraphGateway(
        {
            "MED13": {
                "id": med13_id,
                "display_label": "MED13",
                "aliases": [],
            },
            "EGFR": {
                "id": egfr_id,
                "display_label": "EGFR",
                "aliases": [],
            },
            "AKT1": {
                "id": akt1_id,
                "display_label": "AKT1",
                "aliases": [],
            },
        },
    )
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR and AKT1",
        sentence="MED13 was associated with EGFR and AKT1.",
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=uuid4(),
        document=_document(),
        candidates=[candidate],
        graph_api_gateway=gateway,
        review_context=build_document_review_context(),
    )

    assert skipped == []
    assert len(drafts) == 2
    assert [draft.payload["proposed_subject"] for draft in drafts] == [
        str(med13_id),
        str(med13_id),
    ]
    assert {draft.payload["proposed_object"] for draft in drafts} == {
        str(egfr_id),
        str(akt1_id),
    }
    assert all(draft.metadata["object_split_applied"] is True for draft in drafts)


def test_document_context_summary_lists_documents_and_top_proposals() -> None:
    summary = summarize_document_context(
        documents=(_document(),),
        proposals_by_document_id={
            "document-1": [
                {"summary": "First claim."},
                {"summary": "Second claim."},
                {"summary": "Third claim."},
                {"summary": "Ignored fourth claim."},
            ],
        },
    )

    assert summary is not None
    assert "MED13 document [text] (4 staged proposal(s))" in summary
    assert "First claim." in summary
    assert "Ignored fourth claim." not in summary
