"""Unit coverage for evidence/value filtering of extracted candidates."""

from __future__ import annotations

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


def test_quality_filter_removes_uncertain_candidate() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="HRD score",
        relation_type="BIOMARKER_FOR",
        object_label="platinum sensitivity",
        sentence="HRD score may serve as a biomarker for platinum sensitivity.",
    )

    result = filter_low_value_relation_candidates((candidate,))

    assert result.candidates == ()
    assert result.filtered_candidates[0].reason == "uncertain_relation_claim"


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
