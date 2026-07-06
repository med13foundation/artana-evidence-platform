"""Unit coverage for evidence/value filtering of extracted candidates."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_support.relation_candidate_quality_filter import (
    filter_low_value_relation_candidates,
)


def test_quality_filter_keeps_entailed_specific_candidate() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="RET p.Arg1174*",
        relation_type="ACTIVATES",
        object_label="MAPK signaling",
        sentence="RET p.Arg1174* activates MAPK signaling in engineered cells.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == (candidate,)
    assert result.filtered_candidates == ()


@pytest.mark.parametrize(
    "candidate",
    [
        ExtractedRelationCandidate(
            subject_label="LDLR loss-of-function variants",
            relation_type="PREDISPOSES_TO",
            object_label="familial hypercholesterolemia",
            sentence=(
                "LDLR loss-of-function variants predispose carriers to "
                "familial hypercholesterolemia."
            ),
        ),
        ExtractedRelationCandidate(
            subject_label="BRCA1 truncating variants",
            relation_type="PREDISPOSES_TO",
            object_label="hereditary breast and ovarian cancer syndrome",
            sentence=(
                "BRCA1 truncating variants predispose carriers to hereditary "
                "breast and ovarian cancer syndrome."
            ),
        ),
        ExtractedRelationCandidate(
            subject_label="APC pathogenic variants",
            relation_type="PREDISPOSES_TO",
            object_label="familial adenomatous polyposis",
            sentence=(
                "APC pathogenic variants predispose carriers to familial "
                "adenomatous polyposis."
            ),
        ),
        ExtractedRelationCandidate(
            subject_label="Larotrectinib",
            relation_type="TREATS",
            object_label="NTRK fusion solid tumors",
            sentence=(
                "Larotrectinib treats solid tumors harboring NTRK gene "
                "fusions regardless of tissue origin."
            ),
        ),
    ],
)
def test_quality_filter_keeps_specific_v3_relation_surfaces(
    candidate: ExtractedRelationCandidate,
) -> None:
    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == (candidate,)
    assert result.filtered_candidates == ()


def test_quality_filter_removes_companion_phenotype_when_disease_sibling_exists() -> None:
    disease_candidate = ExtractedRelationCandidate(
        subject_label="MECP2 pathogenic variants",
        relation_type="ASSOCIATED_WITH",
        object_label="Rett syndrome",
        sentence=(
            "MECP2 pathogenic variants are associated with Rett syndrome and "
            "developmental regression."
        ),
    )
    phenotype_candidate = ExtractedRelationCandidate(
        subject_label="MECP2 pathogenic variants",
        relation_type="ASSOCIATED_WITH",
        object_label="developmental regression",
        sentence=(
            "MECP2 pathogenic variants are associated with Rett syndrome and "
            "developmental regression."
        ),
    )

    result = filter_low_value_relation_candidates(
        (disease_candidate, phenotype_candidate),
    )

    assert result.candidates == (disease_candidate,)
    assert result.filtered_candidates[0].candidate == phenotype_candidate
    assert result.filtered_candidates[0].reason == (
        "companion_phenotype_shadowed_by_disease"
    )


def test_quality_filter_marks_single_companion_phenotype_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MECP2 pathogenic variants",
        relation_type="ASSOCIATED_WITH",
        object_label="developmental regression",
        sentence=(
            "MECP2 pathogenic variants are associated with Rett syndrome and "
            "developmental regression."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].review_status == "review_only"
    assert "companion_phenotype_shadowed_by_disease" in (
        result.candidates[0].review_reason_codes
    )
    assert result.filtered_candidates == ()


def test_quality_filter_marks_single_biochemical_companion_phenotype_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="PAH pathogenic variants",
        relation_type="ASSOCIATED_WITH",
        object_label="elevated phenylalanine",
        sentence=(
            "PAH pathogenic variants are associated with phenylketonuria and "
            "elevated phenylalanine."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].review_status == "review_only"
    assert "companion_phenotype_shadowed_by_disease" in (
        result.candidates[0].review_reason_codes
    )
    assert result.filtered_candidates == ()


def test_quality_filter_keeps_correlated_only_specific_relation_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="CONFERS_RESISTANCE_TO",
        object_label="EGFR inhibition",
        sentence=(
            "MET amplification was correlated with resistance to EGFR "
            "inhibition."
        ),
        review_status="review_only",
        review_reason_codes=("hedged_language", "correlated_only"),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].review_status == "review_only"
    assert "correlated_only" in result.candidates[0].review_reason_codes
    assert result.filtered_candidates == ()


def test_quality_filter_repairs_correlated_resistance_review_object() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR inhibition",
        sentence=(
            "MET amplification was correlated with resistance to EGFR "
            "inhibition in a small exploratory cohort."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].object_label == "resistance to EGFR inhibition"
    assert result.candidates[0].review_status == "review_only"
    assert "correlated_only" in result.candidates[0].review_reason_codes
    assert result.candidates[0].trusted_evidence_eligible is False
    assert result.filtered_candidates == ()


def test_quality_filter_clears_stale_object_curie_after_resistance_object_repair() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR inhibition",
        object_curie="GO:0000000",
        object_curie_source="model",
        sentence=(
            "MET amplification was correlated with resistance to EGFR "
            "inhibition in a small exploratory cohort."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].object_label == "resistance to EGFR inhibition"
    assert result.candidates[0].object_curie is None
    assert result.candidates[0].object_curie_source == "none"
    assert result.candidates[0].review_status == "review_only"
    assert result.candidates[0].trusted_evidence_eligible is False


def test_quality_filter_does_not_repair_resistance_object_from_prefix_match() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR",
        sentence=(
            "MET amplification was correlated with resistance to EGFR "
            "inhibition in a small exploratory cohort."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].object_label == "EGFR"
    assert result.candidates[0].review_status == "review_only"


def test_quality_filter_does_not_repair_trend_relation_from_unrelated_clause() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="EGFR expression",
        relation_type="BIOMARKER_FOR",
        object_label="erlotinib response",
        sentence=(
            "EGFR expression is a biomarker for erlotinib response. MET "
            "amplification trended with resistance to EGFR inhibition."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].relation_type == "BIOMARKER_FOR"
    assert result.candidates[0].review_status == "candidate"


def test_quality_filter_does_not_repair_trend_relation_from_bare_and_clause() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="EGFR expression",
        relation_type="BIOMARKER_FOR",
        object_label="erlotinib response",
        sentence=(
            "EGFR expression is a biomarker for erlotinib response and MET "
            "amplification trended with resistance to EGFR inhibition."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].relation_type == "BIOMARKER_FOR"
    assert result.candidates[0].review_status == "candidate"


def test_quality_filter_does_not_repair_resistance_object_from_unrelated_clause() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR inhibition",
        sentence=(
            "MET amplification was observed in resistant tumors. EGFR "
            "expression was correlated with resistance to EGFR inhibition."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].object_label == "EGFR inhibition"


def test_quality_filter_does_not_repair_resistance_object_from_bare_and_clause() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR inhibition",
        sentence=(
            "MET amplification was observed in resistant tumors and EGFR "
            "expression was correlated with resistance to EGFR inhibition."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].object_label == "EGFR inhibition"


def test_quality_filter_deduplicates_repaired_review_candidates() -> None:
    primary_candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="EGFR inhibition",
        sentence=(
            "MET amplification was correlated with resistance to EGFR "
            "inhibition in a small exploratory cohort."
        ),
    )
    weak_pass_candidate = ExtractedRelationCandidate(
        subject_label="MET amplification",
        relation_type="ASSOCIATED_WITH",
        object_label="resistance to EGFR inhibition",
        sentence=(
            "MET amplification was correlated with resistance to EGFR "
            "inhibition in a small exploratory cohort."
        ),
        review_status="review_only",
        review_reason_codes=("weak_review_agent_pass",),
    )

    result = filter_low_value_relation_candidates(
        (primary_candidate, weak_pass_candidate),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].object_label == "resistance to EGFR inhibition"
    assert result.candidates[0].review_status == "review_only"
    assert result.candidates[0].review_reason_codes == (
        "hedged_language",
        "correlated_only",
        "weak_review_agent_pass",
    )
    assert result.filtered_candidates == ()


def test_quality_filter_repairs_trend_response_relation_type_to_review_association() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="EGFR expression",
        relation_type="BIOMARKER_FOR",
        object_label="erlotinib response",
        sentence=(
            "EGFR expression trended with erlotinib response but did not meet "
            "the prespecified threshold."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].relation_type == "ASSOCIATED_WITH"
    assert result.candidates[0].review_status == "review_only"
    assert result.candidates[0].review_reason_codes == (
        "hedged_language",
        "trend_only",
    )
    assert result.candidates[0].trusted_evidence_eligible is False


def test_quality_filter_removes_nested_biomarker_context_object() -> None:
    response_candidate = ExtractedRelationCandidate(
        subject_label="PD-L1 expression",
        relation_type="BIOMARKER_FOR",
        object_label="response to pembrolizumab",
        sentence=(
            "PD-L1 expression predicts response to pembrolizumab in "
            "non-small cell lung cancer."
        ),
    )
    context_candidate = ExtractedRelationCandidate(
        subject_label="PD-L1 expression",
        relation_type="BIOMARKER_FOR",
        object_label="non-small cell lung cancer",
        sentence=(
            "PD-L1 expression predicts response to pembrolizumab in "
            "non-small cell lung cancer."
        ),
        review_status="review_only",
        review_reason_codes=("nested_biomarker_context",),
    )

    result = filter_low_value_relation_candidates(
        (response_candidate, context_candidate),
    )

    assert result.candidates == (response_candidate,)
    assert result.filtered_candidates[0].candidate == context_candidate
    assert result.filtered_candidates[0].reason == "nested_context_object"


def test_quality_filter_marks_single_nested_biomarker_context_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="PD-L1 expression",
        relation_type="BIOMARKER_FOR",
        object_label="non-small cell lung cancer",
        sentence=(
            "PD-L1 expression predicts response to pembrolizumab in "
            "non-small cell lung cancer."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].review_status == "review_only"
    assert "nested_context_object" in result.candidates[0].review_reason_codes
    assert result.filtered_candidates == ()


def test_quality_filter_marks_explicit_pathway_effect_with_direct_target_review_only() -> None:
    target_candidate = ExtractedRelationCandidate(
        subject_label="Vemurafenib",
        relation_type="TARGETS",
        object_label="BRAF V600E",
        sentence="Vemurafenib targets BRAF V600E and inhibits MAPK signaling.",
    )
    pathway_candidate = ExtractedRelationCandidate(
        subject_label="Vemurafenib",
        relation_type="INHIBITS",
        object_label="MAPK signaling",
        sentence="Vemurafenib targets BRAF V600E and inhibits MAPK signaling.",
    )

    result = filter_low_value_relation_candidates(
        (target_candidate, pathway_candidate),
    )

    assert result.candidates[0] == target_candidate
    assert result.candidates[1].review_status == "review_only"
    assert "pathway_effect_shadowed_by_direct_target" in (
        result.candidates[1].review_reason_codes
    )
    assert result.filtered_candidates == ()


def test_quality_filter_marks_proliferation_effect_with_pathway_sibling_review_only() -> None:
    pathway_candidate = ExtractedRelationCandidate(
        subject_label="KRAS G12D",
        relation_type="ACTIVATES",
        object_label="MAPK signaling",
        sentence=(
            "KRAS G12D activates MAPK signaling and increases pancreatic "
            "cancer cell proliferation."
        ),
    )
    proliferation_candidate = ExtractedRelationCandidate(
        subject_label="KRAS G12D",
        relation_type="ACTIVATES",
        object_label="pancreatic cancer cell proliferation",
        sentence=(
            "KRAS G12D activates MAPK signaling and increases pancreatic "
            "cancer cell proliferation."
        ),
    )

    result = filter_low_value_relation_candidates(
        (pathway_candidate, proliferation_candidate),
    )

    assert result.candidates[0] == pathway_candidate
    assert result.candidates[1].review_status == "review_only"
    assert "process_effect_shadowed_by_pathway_mechanism" in (
        result.candidates[1].review_reason_codes
    )
    assert result.filtered_candidates == ()


def test_quality_filter_marks_cell_context_activation_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="JAK-STAT",
        relation_type="ACTIVATES",
        object_label="macrophages",
        sentence=(
            "IL6 regulates inflammatory signaling through JAK-STAT activation "
            "in macrophages."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert len(result.candidates) == 1
    assert result.candidates[0].review_status == "review_only"
    assert "cell_context_object" in result.candidates[0].review_reason_codes
    assert result.filtered_candidates == ()


def test_quality_filter_removes_candidate_that_drops_subject_modifier() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="BRCA1",
        relation_type="SENSITIZES_TO",
        object_label="cisplatin",
        sentence="BRCA1 loss sensitizes tumors to cisplatin.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == ()
    assert result.filtered_candidates[0].reason == "dropped_subject_modifier"


def test_quality_filter_removes_candidate_that_drops_common_biomedical_modifier() -> None:
    candidates = (
        ExtractedRelationCandidate(
            subject_label="BRCA1",
            relation_type="SENSITIZES_TO",
            object_label="cisplatin",
            sentence="BRCA1 deletion sensitizes tumors to cisplatin.",
        ),
        ExtractedRelationCandidate(
            subject_label="BRCA1",
            relation_type="SENSITIZES_TO",
            object_label="cisplatin",
            sentence="BRCA1 knockdown sensitizes tumors to cisplatin.",
        ),
        ExtractedRelationCandidate(
            subject_label="BRCA1",
            relation_type="SENSITIZES_TO",
            object_label="cisplatin",
            sentence="BRCA1 deficiency sensitizes tumors to cisplatin.",
        ),
    )

    result = filter_low_value_relation_candidates(candidates)

    assert result.candidates == ()
    assert {
        filtered.reason for filtered in result.filtered_candidates
    } == {"dropped_subject_modifier"}


def test_quality_filter_keeps_candidate_that_preserves_subject_modifier() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="BRCA1 loss",
        relation_type="SENSITIZES_TO",
        object_label="cisplatin",
        sentence="BRCA1 loss sensitizes tumors to cisplatin.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == (candidate,)
    assert result.filtered_candidates == ()


def test_quality_filter_keeps_unmodified_claim_in_separate_clause() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="BRCA1",
        relation_type="ACTIVATES",
        object_label="DNA repair",
        sentence=(
            "BRCA1 loss sensitizes tumors to cisplatin, while BRCA1 activates "
            "DNA repair."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == (candidate,)
    assert result.filtered_candidates == ()


def test_quality_filter_keeps_unmodified_claim_in_coordinated_clause() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="BRCA1",
        relation_type="ACTIVATES",
        object_label="DNA repair",
        sentence=(
            "BRCA1 loss sensitizes tumors to cisplatin, and BRCA1 activates "
            "DNA repair."
        ),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == (candidate,)
    assert result.filtered_candidates == ()


def test_quality_filter_removes_context_relation_shadowed_by_direct_mechanism() -> None:
    direct_candidate = ExtractedRelationCandidate(
        subject_label="Trametinib",
        relation_type="INHIBITS",
        object_label="ERK phosphorylation",
        sentence="Trametinib inhibits ERK phosphorylation downstream of MEK.",
    )
    context_candidate = ExtractedRelationCandidate(
        subject_label="ERK phosphorylation",
        relation_type="DOWNSTREAM_OF",
        object_label="MEK",
        sentence="Trametinib inhibits ERK phosphorylation downstream of MEK.",
    )

    result = filter_low_value_relation_candidates(
        (direct_candidate, context_candidate),
    )

    assert result.candidates == (direct_candidate,)
    assert result.filtered_candidates[0].candidate == context_candidate
    assert result.filtered_candidates[0].reason == (
        "context_relation_shadowed_by_direct_mechanism"
    )


def test_quality_filter_keeps_context_relation_when_it_is_separate_claim() -> None:
    direct_candidate = ExtractedRelationCandidate(
        subject_label="Trametinib",
        relation_type="INHIBITS",
        object_label="ERK phosphorylation",
        sentence=(
            "Trametinib inhibits ERK phosphorylation, and ERK phosphorylation "
            "is downstream of MEK."
        ),
    )
    context_candidate = ExtractedRelationCandidate(
        subject_label="ERK phosphorylation",
        relation_type="DOWNSTREAM_OF",
        object_label="MEK",
        sentence=(
            "Trametinib inhibits ERK phosphorylation, and ERK phosphorylation "
            "is downstream of MEK."
        ),
    )

    result = filter_low_value_relation_candidates(
        (direct_candidate, context_candidate),
    )

    assert result.candidates == (direct_candidate, context_candidate)
    assert result.filtered_candidates == ()


def test_quality_filter_keeps_uncertain_candidate_as_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="HRD score",
        relation_type="BIOMARKER_FOR",
        object_label="platinum sensitivity",
        sentence="HRD score was described as a possible biomarker for platinum sensitivity.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.filtered_candidates == ()
    assert result.candidates[0].review_status == "review_only"
    assert result.candidates[0].review_reason_codes == (
        "hedged_language",
        "possible_biomarker",
    )
    assert result.candidates[0].trusted_evidence_eligible is False


@pytest.mark.parametrize(
    ("candidate", "expected_reason_codes"),
    [
        (
            ExtractedRelationCandidate(
                subject_label="AKT activation",
                relation_type="ASSOCIATED_WITH",
                object_label="reduced survival",
                sentence="AKT activation showed a trend toward reduced survival.",
            ),
            ("hedged_language", "trend_only"),
        ),
        (
            ExtractedRelationCandidate(
                subject_label="MED13",
                relation_type="ASSOCIATED_WITH",
                object_label="congenital heart disease",
                sentence="MED13 may be linked to congenital heart disease.",
            ),
            ("hedged_language", "may_link"),
        ),
        (
            ExtractedRelationCandidate(
                subject_label="MET amplification",
                relation_type="ASSOCIATED_WITH",
                object_label="resistance",
                sentence="MET amplification correlated with resistance.",
            ),
            ("hedged_language", "correlated_only"),
        ),
    ],
)
def test_quality_filter_keeps_weak_review_candidates_as_review_only(
    candidate: ExtractedRelationCandidate,
    expected_reason_codes: tuple[str, ...],
) -> None:
    result = filter_low_value_relation_candidates((candidate,))

    assert result.filtered_candidates == ()
    assert result.candidates[0].review_status == "review_only"
    assert result.candidates[0].review_reason_codes == expected_reason_codes
    assert result.candidates[0].trusted_evidence_eligible is False


def test_quality_filter_keeps_model_review_hint_candidate_as_review_only() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ASSOCIATED_WITH",
        object_label="congenital heart disease",
        sentence="MED13 was associated with congenital heart disease.",
        review_status="review_only",
        review_reason_codes=("agent_review_hint",),
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.filtered_candidates == ()
    assert result.candidates[0].review_status == "review_only"
    assert result.candidates[0].review_reason_codes == ("agent_review_hint",)
    assert result.candidates[0].trusted_evidence_eligible is False


def test_quality_filter_removes_candidate_missing_sentence_argument() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="sotorasib",
        relation_type="PHYSICALLY_INTERACTS_WITH",
        object_label="mutant cysteine",
        sentence="The drug covalently binds the mutant cysteine residue.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == ()
    assert result.filtered_candidates[0].reason == "missing_relation_arguments"


def test_quality_filter_removes_non_entailed_canonical_candidate() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        relation_type="ACTIVATES",
        object_label="EGFR",
        sentence="MED13 and EGFR were both measured in the cohort.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == ()
    assert result.filtered_candidates[0].reason == "support_not_entailed"


def test_quality_filter_keeps_governed_relation_proposal_for_review() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="BRCA1 loss",
        relation_type="PROPOSE_NEW_RELATION_TYPE",
        object_label="cisplatin",
        sentence="BRCA1 loss reduces toxicity of cisplatin.",
        proposed_relation_type="REDUCES_TOXICITY_OF",
        relation_governance_status="requires_relation_review",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == (candidate,)
    assert result.filtered_candidates == ()
