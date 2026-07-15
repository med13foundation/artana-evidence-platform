"""Contracts for the relation feasibility audit loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction import (
    DocumentCandidateExtractionDiagnostics,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    TripleSupportResult,
)

from scripts.run_relation_feasibility_audit import (
    _agent_relation_extraction_result_from_candidates,
    extract_with_agent,
    main,
    parse_args,
)
from scripts.validation.relation_feasibility.adversarial import find_quality_illusions
from scripts.validation.relation_feasibility.io import load_benchmark_cases
from scripts.validation.relation_feasibility.live_agent_preflight import (
    LiveAgentPreflightError,
    LiveAgentPreflightSnapshot,
)
from scripts.validation.relation_feasibility.models import (
    BenchmarkCase,
    ExtractedRelation,
    ExtractionTrace,
    GoldRelation,
    RelationExtractionResult,
    RelationTypeSurface,
)
from scripts.validation.relation_feasibility.reporting import render_markdown_report
from scripts.validation.relation_feasibility.runner import run_feasibility_audit


class _EntailingAgentSupportVerifier:
    model_id = "test:independent-agent-verifier"

    def verify(
        self,
        *,
        sentence: str,
        subject: str,
        relation_type: str,
        object_: str,
    ) -> TripleSupportResult:
        del sentence, subject, relation_type, object_
        return TripleSupportResult(
            support="ENTAILS",
            rationale="The test verifier found direct categorical support.",
        )


_AGENT_SUPPORT_VERIFIER = _EntailingAgentSupportVerifier()


def _case(
    *,
    case_id: str,
    text: str,
    gold: tuple[GoldRelation, ...],
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        title=case_id.replace("_", " ").title(),
        category="unit",
        text=text,
        gold_relations=gold,
    )


def test_audit_scores_specific_supported_relations_as_valuable() -> None:
    cases = (
        _case(
            case_id="specific_relation",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific gene-to-process mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                sentence="MED13 activates cardiac septal development.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.case_count == 1
    assert report.summary.candidate_count == 1
    assert report.summary.precision_against_gold == 1.0
    assert report.summary.recall_against_gold == 1.0
    assert report.summary.valuable_candidate_rate == 1.0
    assert report.summary.generic_relation_rate == 0.0
    assessment = report.case_results[0].candidate_assessments[0]
    assert assessment.is_valuable is True
    assert assessment.support_verification_method == "heuristic"
    assert assessment.is_trusted_evidence_eligible is False
    assert report.summary.trusted_candidate_count == 0
    assert report.summary.trusted_high_value_match_count == 0
    assert report.summary.trusted_candidate_valuable_count == 0


def test_audit_reports_candidate_score_calibration_error() -> None:
    cases = (
        _case(
            case_id="calibration_pair",
            text=(
                "MED13 activates cardiac septal development. "
                "BRAF activates MAPK signaling in melanoma cells."
            ),
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific gene-to-process mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                sentence="MED13 activates cardiac septal development.",
            ),
            ExtractedRelation(
                subject="BRAF",
                relation_type="ACTIVATES",
                object="MAPK signaling",
                sentence="BRAF activates MAPK signaling in melanoma cells.",
            ),
        ]

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    summary_payload = report.summary.to_json()

    assert report.summary.candidate_score_calibration_sample_count == 2
    assert report.summary.trusted_candidate_score_calibration_sample_count == 2
    assert report.summary.candidate_score_ece == 0.5
    assert report.summary.trusted_candidate_score_ece == 0.5
    assert summary_payload["candidate_score_ece"] == 0.5
    assert summary_payload["trusted_candidate_score_ece"] == 0.5


def test_audit_calibrates_supported_low_value_relation_as_negative() -> None:
    cases = (
        _case(
            case_id="low_value_calibration",
            text="MED13 activates broad cellular signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="broad cellular signaling",
                    support_sentence="MED13 activates broad cellular signaling.",
                    value_level="low",
                    rationale="Correct but too broad to promote as valuable evidence.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="broad cellular signaling",
                sentence="MED13 activates broad cellular signaling.",
            ),
        ]

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.is_supported_by_gold is True
    assert assessment.is_trusted_evidence_eligible is True
    assert assessment.is_valuable is False
    assert report.summary.candidate_score_ece == 1.0
    assert report.summary.trusted_candidate_score_ece == 1.0


def test_audit_rejects_off_target_support_sentence_for_matching_triple() -> None:
    cases = (
        _case(
            case_id="off_target_support_sentence",
            text=(
                "KRAS G12C is targeted by sotorasib in lung cancer models. "
                "The drug covalently binds the mutant cysteine residue."
            ),
            gold=(
                GoldRelation(
                    subject="Sotorasib",
                    relation_type="TARGETS",
                    object="KRAS G12C",
                    support_sentence=(
                        "KRAS G12C is targeted by sotorasib in lung cancer models."
                    ),
                    value_level="high",
                    rationale="The first sentence contains the named drug and variant.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="Sotorasib",
                relation_type="TARGETS",
                object="KRAS G12C",
                sentence="The drug covalently binds the mutant cysteine residue.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.is_supported_by_gold is True
    assert assessment.has_grounded_sentence is True
    assert assessment.has_subject_in_sentence is False
    assert assessment.has_object_in_sentence is False
    assert assessment.has_both_arguments_in_sentence is False
    assert assessment.has_gold_support_sentence is False
    assert assessment.support_verification is None
    assert assessment.has_support_verification is False
    assert assessment.has_entailment_support is False
    assert assessment.is_valuable is False
    assert "missing_relation_arguments" in assessment.quality_flags
    assert "support_sentence_mismatch" in assessment.quality_flags
    assert "support_not_entailed" not in assessment.quality_flags
    assert "support_not_checked" in assessment.quality_flags
    assert report.summary.entailment_checked_rate == 0.0


def test_audit_requires_entailment_support_for_valuable_candidate() -> None:
    cases = (
        _case(
            case_id="co_mentioned_not_entailed",
            text="MED13 and EGFR were both measured in the cohort.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="EGFR",
                    support_sentence="MED13 and EGFR were both measured in the cohort.",
                    value_level="high",
                    rationale="The triple matches, but the sentence does not express activation.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="EGFR",
                sentence="MED13 and EGFR were both measured in the cohort.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.is_supported_by_gold is True
    assert assessment.has_both_arguments_in_sentence is True
    assert assessment.has_gold_support_sentence is True
    assert assessment.support_verification == "NEUTRAL"
    assert assessment.has_entailment_support is False
    assert assessment.is_valuable is False
    assert "support_not_entailed" in assessment.quality_flags
    assert report.summary.entailment_checked_rate == 1.0
    assert report.summary.entailment_supported_rate == 0.0


def test_audit_flags_generic_and_unsupported_relations_as_low_value() -> None:
    cases = (
        _case(
            case_id="generic_relation",
            text="MED13 was associated with clinical features.",
            gold=(),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                object="clinical features",
                sentence="MED13 was associated with clinical features.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert report.summary.precision_against_gold == 0.0
    assert report.summary.generic_relation_rate == 1.0
    assert report.summary.valuable_candidate_rate == 0.0
    assert assessment.is_supported_by_gold is False
    assert assessment.is_relation_specific is False
    assert assessment.has_specific_object is False
    assert assessment.is_valuable is False
    assert "unsupported_by_gold" in assessment.quality_flags
    assert "generic_relation_type" in assessment.quality_flags
    assert "generic_object" in assessment.quality_flags


def test_audit_counts_pruned_generic_relation_siblings() -> None:
    cases = (
        _case(
            case_id="generic_sibling_pruned",
            text="MED13 activates EGFR and is associated with EGFR.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="EGFR",
                    support_sentence="MED13 activates EGFR and is associated with EGFR.",
                    value_level="high",
                    rationale="Specific mechanism should suppress redundant generic association.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="EGFR",
                    sentence="MED13 activates EGFR and is associated with EGFR.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="custom",
                pruned_generic_relation_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    markdown = render_markdown_report(report)

    assert report.summary.candidate_count == 1
    assert report.summary.generic_relation_count == 0
    assert report.summary.pruned_generic_relation_count == 1
    assert report.summary.generic_relation_rate == 0.0
    assert "Pruned generic relation siblings: 1" in markdown


def test_audit_requires_curie_linked_gold_entities() -> None:
    cases = (
        _case(
            case_id="curie_linked_relation",
            text="MED13 causes developmental delay.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="CAUSES",
                    object="developmental delay",
                    support_sentence="MED13 causes developmental delay.",
                    value_level="high",
                    rationale="Gold endpoints include stable ontology identifiers.",
                    subject_curie="HGNC:22474",
                    object_curie="HP:0001263",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    relation_type="CAUSES",
                    object="developmental delay",
                    object_curie="HP:0001263",
                    object_curie_source="verified_linker",
                    sentence="MED13 causes developmental delay.",
                ),
            ),
            trace=ExtractionTrace(extractor_mode="custom"),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    markdown = render_markdown_report(report)

    assert report.summary.gold_curie_endpoint_count == 2
    assert report.summary.curie_linked_gold_endpoint_count == 2
    assert report.summary.curie_linked_gold_endpoint_rate == 1.0
    assert "CURIE-linked gold endpoint rate: 1.0000" in markdown


def test_model_curie_hints_do_not_count_as_verified_gold_endpoint_links() -> None:
    cases = (
        _case(
            case_id="model_curie_hint",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific gene-to-process mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0031070",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                subject_curie="HGNC:29186",
                subject_curie_source="model",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                object_curie="GO:0031070",
                object_curie_source="model",
                sentence="MED13 activates cardiac septal development.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.has_subject_curie is True
    assert assessment.subject_curie_matches_gold is False
    assert assessment.has_verified_subject_curie is False
    assert assessment.has_verified_object_curie is False
    assert assessment.is_valuable is True
    assert "unverified_subject_curie" in assessment.quality_flags
    assert "unverified_object_curie" in assessment.quality_flags
    assert "wrong_subject_curie" not in assessment.quality_flags
    assert report.summary.candidate_curie_present_rate == 1.0
    assert report.summary.verified_curie_match_count == 0
    assert report.summary.verified_curie_match_rate == 0.0
    assert report.summary.model_curie_wrong_count == 1
    assert report.summary.high_value_recall == 1.0
    assert report.summary.trusted_high_value_recall == 0.0


def test_verified_curie_match_can_support_curated_endpoint_alias() -> None:
    cases = (
        _case(
            case_id="curated_endpoint_alias",
            text="BRCA1 regulates homologous recombination DNA repair.",
            gold=(
                GoldRelation(
                    subject="BRCA1",
                    relation_type="REGULATES",
                    object="homologous recombination DNA repair",
                    support_sentence=(
                        "BRCA1 regulates homologous recombination DNA repair."
                    ),
                    value_level="high",
                    rationale="Specific gene-to-process regulatory relation.",
                    subject_curie="HGNC:1100",
                    object_curie="GO:0000724",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="BRCA1",
                    subject_curie="HGNC:1100",
                    subject_curie_source="verified_linker",
                    relation_type="REGULATES",
                    object="homologous recombination",
                    object_curie="GO:0000724",
                    object_curie_source="verified_linker",
                    sentence="BRCA1 regulates homologous recombination DNA repair.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.is_supported_by_gold is True
    assert assessment.object_curie_matches_gold is True
    assert "unsupported_by_gold" not in assessment.quality_flags
    assert report.summary.high_value_recall == 1.0
    assert report.summary.trusted_high_value_recall == 1.0
    assert report.summary.curie_linked_gold_endpoint_rate == 1.0


def test_review_only_grounding_labels_are_flagged_without_gold_curie() -> None:
    cases = (
        _case(
            case_id="review_only_grounding",
            text="PD-L1 expression is a biomarker for response to pembrolizumab.",
            gold=(
                GoldRelation(
                    subject="PD-L1 expression",
                    relation_type="BIOMARKER_FOR",
                    object="response to pembrolizumab",
                    support_sentence=(
                        "PD-L1 expression is a biomarker for response to "
                        "pembrolizumab."
                    ),
                    value_level="high",
                    rationale="Specific biomarker-to-response relation.",
                    subject_curie="HGNC:17635",
                    object_curie=None,
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="PD-L1 expression",
                    subject_curie="HGNC:17635",
                    subject_curie_source="verified_linker",
                    relation_type="BIOMARKER_FOR",
                    object="response to pembrolizumab",
                    sentence=(
                        "PD-L1 expression is a biomarker for response to "
                        "pembrolizumab."
                    ),
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.is_supported_by_gold is True
    assert assessment.is_valuable is True
    assert "review_only_object_grounding" in assessment.quality_flags
    assert report.summary.high_value_recall == 1.0
    assert report.summary.trusted_high_value_recall == 0.0


def test_trusted_high_value_recall_requires_completed_agent_and_verified_curies() -> None:
    cases = (
        _case(
            case_id="trusted_high_value",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific gene-to-process mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0031070",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    object_curie="GO:0031070",
                    object_curie_source="verified_linker",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )

    assert report.summary.high_value_recall == 1.0
    assert report.summary.trusted_high_value_match_count == 1
    assert report.summary.trusted_high_value_recall == 1.0


def test_context_relations_do_not_count_as_trusted_high_value_recall() -> None:
    cases = (
        _case(
            case_id="context_relation_review_only",
            text="ERK phosphorylation is downstream of MEK.",
            gold=(
                GoldRelation(
                    subject="ERK phosphorylation",
                    relation_type="DOWNSTREAM_OF",
                    object="MEK",
                    support_sentence="ERK phosphorylation is downstream of MEK.",
                    value_level="high",
                    rationale="Pathway context should not auto-promote as trusted evidence.",
                    subject_curie="GO:0001932",
                    object_curie="HGNC:6840",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="ERK phosphorylation",
                    subject_curie="GO:0001932",
                    subject_curie_source="verified_linker",
                    relation_type="DOWNSTREAM_OF",
                    object="MEK",
                    object_curie="HGNC:6840",
                    object_curie_source="verified_linker",
                    sentence="ERK phosphorylation is downstream of MEK.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.high_value_recall == 1.0
    assert report.summary.trusted_high_value_match_count == 0
    assert report.summary.trusted_high_value_recall == 0.0
    assert report.summary.trusted_eligible_high_value_gold_relation_count == 0
    assert report.summary.trusted_eligible_high_value_match_count == 0
    assert report.summary.trusted_eligible_high_value_recall == 0.0
    assert report.summary.trusted_candidate_count == 0
    assert report.summary.trusted_candidate_score_calibration_sample_count == 0
    assert report.summary.trusted_eligible_gold_curie_endpoint_count == 0
    assert report.summary.trusted_eligible_curie_linked_gold_endpoint_count == 0
    assert report.summary.verdict == "YELLOW"
    assert any(
        "no trusted-eligible high-value" in reason.lower()
        for reason in report.summary.warning_reasons
    )


def test_wrong_verified_curie_links_are_reported_as_blocking() -> None:
    cases = (
        _case(
            case_id="wrong_verified_curie",
            text="MED13 causes developmental delay.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="CAUSES",
                    object="developmental delay",
                    support_sentence="MED13 causes developmental delay.",
                    value_level="high",
                    rationale="Gold endpoints include stable ontology identifiers.",
                    subject_curie="HGNC:22474",
                    object_curie="HP:0001263",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                subject_curie="HGNC:99999",
                subject_curie_source="verified_linker",
                relation_type="CAUSES",
                object="developmental delay",
                object_curie="HP:0001263",
                object_curie_source="verified_linker",
                sentence="MED13 causes developmental delay.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]
    markdown = render_markdown_report(report)

    assert "wrong_subject_curie" in assessment.quality_flags
    assert report.summary.wrong_verified_curie_link_count == 1
    assert "Wrong verified CURIE links: 1" in markdown
    assert report.summary.verdict == "RED"
    assert "Wrong verified CURIE links were emitted." in (
        report.summary.verdict_reason
    )


def test_quality_filtered_candidate_count_is_reported() -> None:
    cases = (
        _case(
            case_id="quality_filter_telemetry",
            text="HRD score may serve as a biomarker for platinum sensitivity.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="llm_empty",
                quality_filtered_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    markdown = render_markdown_report(report)

    assert report.summary.quality_filtered_candidate_count == 1
    assert report.summary.to_json()["quality_filtered_candidate_count"] == 1
    assert "Quality-filtered candidates: 1" in markdown


def test_agent_adapter_preserves_candidate_provenance_and_governance_fields() -> None:
    candidates = [
        ExtractedRelationCandidate(
            subject_label="MED13",
            subject_curie="HGNC:22474",
            subject_curie_source="verified_linker",
            relation_type="CAUSES",
            object_label="developmental delay",
            object_curie="HP:0001263",
            object_curie_source="model",
            sentence="MED13 causes developmental delay.",
        ),
        ExtractedRelationCandidate(
            subject_label="BRCA1 loss",
            relation_type="PROPOSE_NEW_RELATION_TYPE",
            proposed_relation_type="REDUCES_TOXICITY_OF",
            new_relation_type_rationale="Toxicity-specific effect relation.",
            relation_governance_status="requires_relation_review",
            object_label="cisplatin",
            sentence="BRCA1 loss reduces toxicity of cisplatin.",
        ),
        ExtractedRelationCandidate(
            subject_label="IL6",
            relation_type="REGULATES",
            object_label="inflammatory signaling",
            sentence=(
                "IL6 may regulate inflammatory signaling in stressed epithelial "
                "cells."
            ),
            review_status="review_only",
            review_reason_codes=("hedged_language", "may_regulate"),
        ),
    ]
    diagnostics = DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=2,
    )

    result = _agent_relation_extraction_result_from_candidates(
        candidates=candidates,
        diagnostics=diagnostics,
    )

    assert result.relations[0].subject_curie_source == "verified_linker"
    assert result.relations[0].object_curie_source == "model"
    assert result.relations[1].proposed_relation_type == "REDUCES_TOXICITY_OF"
    assert result.relations[1].new_relation_type_rationale == (
        "Toxicity-specific effect relation."
    )
    assert result.relations[1].relation_governance_status == (
        "requires_relation_review"
    )
    assert result.relations[1].trusted_evidence_eligible is False
    assert result.relations[2].review_status == "review_only"
    assert result.relations[2].review_reason_codes == (
        "hedged_language",
        "may_regulate",
    )
    assert result.relations[2].trusted_evidence_eligible is False


def test_agent_adapter_inventory_indexes_governed_proposed_relation_type() -> None:
    candidates = [
        ExtractedRelationCandidate(
            subject_label="BRCA1 loss",
            relation_type="PROPOSE_NEW_RELATION_TYPE",
            proposed_relation_type="REDUCES_TOXICITY_OF",
            new_relation_type_rationale="Toxicity-specific effect relation.",
            relation_governance_status="requires_relation_review",
            object_label="cisplatin",
            sentence="BRCA1 loss reduces toxicity of cisplatin.",
        ),
    ]
    diagnostics = DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=1,
    )

    result = _agent_relation_extraction_result_from_candidates(
        candidates=candidates,
        diagnostics=diagnostics,
    )
    case = _case(
        case_id="governed_proposal_inventory",
        text="BRCA1 loss reduces toxicity of cisplatin.",
        gold=(
            GoldRelation(
                subject="BRCA1 loss",
                relation_type="REDUCES_TOXICITY_OF",
                object="cisplatin",
                support_sentence="BRCA1 loss reduces toxicity of cisplatin.",
                value_level="high",
                rationale="Relation needs dictionary governance.",
            ),
        ),
    )

    report = run_feasibility_audit(cases=(case,), extractor=lambda _: result)
    markdown = render_markdown_report(report)
    surfaces = {
        (surface.surface, surface.relation_type)
        for surface in report.case_results[0].relation_type_surfaces
    }

    assert surfaces == {
        ("candidate_relation.relation_type", "PROPOSE_NEW_RELATION_TYPE"),
        ("candidate_relation.proposed_relation_type", "REDUCES_TOXICITY_OF"),
    }
    proposed_surfaces = tuple(
        surface
        for surface in report.case_results[0].relation_type_surfaces
        if surface.surface == "candidate_relation.proposed_relation_type"
    )

    assert proposed_surfaces[0].governance_status == "requires_relation_review"
    assert report.summary.relation_type_surface_count == 2
    assert report.summary.raw_unknown_relation_type_surface_count == 0
    assert report.summary.proposal_recall_against_proposal_eligible_gold == 1.0
    assert (
        "`candidate_relation.proposed_relation_type` -> `REDUCES_TOXICITY_OF`"
        in markdown
    )


def test_agent_adapter_inventory_blocks_ungoverned_proposed_relation_type() -> None:
    candidates = [
        ExtractedRelationCandidate(
            subject_label="BRCA1",
            relation_type="ACTIVATES",
            proposed_relation_type="PROTECTS_AGAINST",
            object_label="TP53",
            sentence="BRCA1 activates TP53.",
        ),
    ]
    diagnostics = DocumentCandidateExtractionDiagnostics(
        llm_candidate_status="completed",
        llm_candidate_count=1,
    )

    result = _agent_relation_extraction_result_from_candidates(
        candidates=candidates,
        diagnostics=diagnostics,
    )
    case = _case(
        case_id="ungoverned_proposed_type_inventory",
        text="BRCA1 activates TP53.",
        gold=(),
    )

    report = run_feasibility_audit(cases=(case,), extractor=lambda _: result)
    proposed_surfaces = tuple(
        surface
        for surface in report.case_results[0].relation_type_surfaces
        if surface.surface == "candidate_relation.proposed_relation_type"
    )

    assert len(proposed_surfaces) == 1
    assert proposed_surfaces[0].relation_type == "PROTECTS_AGAINST"
    assert proposed_surfaces[0].governance_status == "canonical"
    assert report.summary.relation_type_surface_count == 2
    assert report.summary.raw_unknown_relation_type_surface_count == 1
    assert report.summary.verdict == "RED"
    assert "raw unknown relation type" in report.summary.verdict_reason


def test_summary_reports_high_value_and_low_value_recall_separately() -> None:
    high_value_case = _case(
        case_id="high_value_mechanism",
        text="MED13 activates cardiac septal development.",
        gold=(
            GoldRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                support_sentence="MED13 activates cardiac septal development.",
                value_level="high",
                rationale="Specific mechanism.",
            ),
        ),
    )
    low_value_case = _case(
        case_id="low_value_association",
        text="MED13 was associated with clinical features.",
        gold=(
            GoldRelation(
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                object="clinical features",
                support_sentence="MED13 was associated with clinical features.",
                value_level="low",
                rationale="Weak association should not hide high-value recall.",
                requires_entailment=False,
            ),
        ),
    )

    def extractor(text: str) -> list[ExtractedRelation]:
        if "associated" in text:
            return [
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="clinical features",
                    sentence="MED13 was associated with clinical features.",
                ),
            ]
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                sentence="MED13 activates cardiac septal development.",
            ),
        ]

    report = run_feasibility_audit(
        cases=(high_value_case, low_value_case),
        extractor=extractor,
    )
    markdown = render_markdown_report(report)

    assert report.summary.high_value_gold_relation_count == 1
    assert report.summary.high_value_missed_gold_count == 0
    assert report.summary.high_value_recall == 1.0
    assert report.summary.low_value_gold_relation_count == 1
    assert report.summary.low_value_missed_gold_count == 0
    assert report.summary.low_value_recall == 1.0
    assert report.summary.trusted_high_value_recall == 0.0
    assert report.summary.low_value_review_candidate_count == 0
    assert report.summary.low_value_review_recall == 0.0
    summary_json = report.summary.to_json()
    assert summary_json["trusted_high_value_recall"] == 0.0
    assert summary_json["low_value_review_candidate_count"] == 0
    assert summary_json["low_value_review_recall"] == 0.0
    assert "High-value recall: 1.0000" in markdown
    assert "Low-value recall: 1.0000" in markdown
    assert "Trusted high-value recall: 0.0000" in markdown
    assert "Low-value review candidates: 0" in markdown
    assert "Low-value review recall: 0.0000" in markdown


def test_low_value_review_metrics_require_review_only_candidate() -> None:
    cases = (
        _case(
            case_id="low_value_review_proposal",
            text="MED13 had a weak exploratory connection to clinical features.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="WEAKLY_LINKED_TO",
                    object="clinical features",
                    support_sentence=(
                        "MED13 had a weak exploratory connection to clinical features."
                    ),
                    value_level="low",
                    rationale="Weak relation should be review-only.",
                    requires_entailment=False,
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="PROPOSE_NEW_RELATION_TYPE",
                    proposed_relation_type="WEAKLY_LINKED_TO",
                    relation_governance_status="requires_relation_review",
                    object="clinical features",
                    sentence=(
                        "MED13 had a weak exploratory connection to clinical features."
                    ),
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.low_value_gold_relation_count == 1
    assert report.summary.low_value_recall == 0.0
    assert report.summary.low_value_review_candidate_count == 1
    assert report.summary.low_value_review_gold_match_count == 1
    assert report.summary.low_value_review_recall == 1.0


def test_low_value_review_metrics_count_review_only_canonical_candidate() -> None:
    cases = (
        _case(
            case_id="low_value_review_canonical",
            text="IL6 may regulate inflammatory signaling in stressed epithelial cells.",
            gold=(
                GoldRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    support_sentence=(
                        "IL6 may regulate inflammatory signaling in stressed "
                        "epithelial cells."
                    ),
                    value_level="low",
                    rationale="Hedged regulatory language is review-only.",
                    subject_curie="HGNC:6018",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    sentence=(
                        "IL6 may regulate inflammatory signaling in stressed "
                        "epithelial cells."
                    ),
                    subject_curie="HGNC:6018",
                    subject_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("hedged_language", "may_regulate"),
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]
    markdown = render_markdown_report(report)

    assert assessment.matched_gold_index == 0
    assert assessment.is_trusted_evidence_eligible is False
    assert "review_only_candidate" in assessment.quality_flags
    assert "review_reason:may_regulate" in assessment.quality_flags
    assert report.summary.low_value_gold_relation_count == 1
    assert report.summary.low_value_missed_gold_count == 0
    assert report.summary.low_value_review_candidate_count == 1
    assert report.summary.low_value_review_gold_match_count == 1
    assert report.summary.low_value_review_recall == 1.0
    assert "Low-value review candidates: 1" in markdown


def test_high_value_review_metrics_count_review_only_canonical_candidate() -> None:
    cases = (
        _case(
            case_id="high_value_review_canonical",
            text="IL6 regulates inflammatory signaling through JAK-STAT activation.",
            gold=(
                GoldRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    support_sentence=(
                        "IL6 regulates inflammatory signaling through JAK-STAT "
                        "activation."
                    ),
                    value_level="high",
                    rationale=(
                        "High-value relation with a broad endpoint that must stay "
                        "review-only."
                    ),
                    subject_curie="HGNC:6018",
                    object_curie=None,
                    review_status="review_only",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    sentence=(
                        "IL6 regulates inflammatory signaling through JAK-STAT "
                        "activation."
                    ),
                    subject_curie="HGNC:6018",
                    subject_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("review_only_object_grounding",),
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    summary_json = report.summary.to_json()
    markdown = render_markdown_report(report)

    assert report.summary.high_value_recall == 1.0
    assert report.summary.trusted_high_value_recall == 0.0
    assert report.summary.high_value_review_gold_relation_count == 1
    assert report.summary.high_value_review_candidate_count == 1
    assert report.summary.high_value_review_gold_match_count == 1
    assert report.summary.high_value_review_recall == 1.0
    assert summary_json["high_value_review_gold_relation_count"] == 1
    assert summary_json["high_value_review_candidate_count"] == 1
    assert summary_json["high_value_review_gold_match_count"] == 1
    assert summary_json["high_value_review_recall"] == 1.0
    assert "High-value review-only candidates: 1" in markdown


def test_trusted_eligible_high_value_recall_excludes_high_value_review_only_gold() -> None:
    cases = (
        _case(
            case_id="trusted_high_value_mechanism",
            text="MED13 activates MAPK signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    support_sentence="MED13 activates MAPK signaling.",
                    value_level="high",
                    rationale="Trusted-eligible mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0000165",
                ),
            ),
        ),
        _case(
            case_id="review_only_high_value_disease_context",
            text=(
                "FBN1 loss-of-function variants are associated with Marfan "
                "syndrome."
            ),
            gold=(
                GoldRelation(
                    subject="FBN1 loss-of-function variants",
                    relation_type="ASSOCIATED_WITH",
                    object="Marfan syndrome",
                    support_sentence=(
                        "FBN1 loss-of-function variants are associated with "
                        "Marfan syndrome."
                    ),
                    value_level="high",
                    rationale=(
                        "The disease context is high-value for review, but the "
                        "composite variant label must not auto-promote."
                    ),
                    object_curie="MONDO:0007947",
                    review_status="review_only",
                ),
            ),
        ),
    )

    def extractor(text: str) -> RelationExtractionResult:
        if "FBN1" in text:
            relations = (
                ExtractedRelation(
                    subject="FBN1 loss-of-function variants",
                    relation_type="ASSOCIATED_WITH",
                    object="Marfan syndrome",
                    sentence=(
                        "FBN1 loss-of-function variants are associated with "
                        "Marfan syndrome."
                    ),
                    object_curie="MONDO:0007947",
                    object_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("review_only_subject_grounding",),
                ),
            )
        else:
            relations = (
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    sentence="MED13 activates MAPK signaling.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="GO:0000165",
                    object_curie_source="verified_linker",
                ),
            )
        return RelationExtractionResult(
            relations=relations,
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=len(relations),
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    summary_json = report.summary.to_json()

    assert report.summary.high_value_recall == 1.0
    assert report.summary.high_value_review_recall == 1.0
    assert report.summary.trusted_eligible_high_value_gold_relation_count == 1
    assert report.summary.trusted_eligible_high_value_match_count == 1
    assert report.summary.trusted_eligible_high_value_recall == 1.0
    assert summary_json["trusted_eligible_high_value_recall"] == 1.0
    assert not any(
        "high-value recall" in reason.lower()
        for reason in report.summary.warning_reasons
    )


def test_review_only_generic_candidates_do_not_drive_trusted_readiness_warnings() -> None:
    cases = (
        _case(
            case_id="trusted_specific_candidate",
            text="MED13 activates MAPK signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    support_sentence="MED13 activates MAPK signaling.",
                    value_level="high",
                    rationale="Trusted-eligible mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0000165",
                ),
            ),
        ),
        _case(
            case_id="review_only_generic_one",
            text="MECP2 pathogenic variants are associated with Rett syndrome.",
            gold=(
                GoldRelation(
                    subject="MECP2 pathogenic variants",
                    relation_type="ASSOCIATED_WITH",
                    object="Rett syndrome",
                    support_sentence=(
                        "MECP2 pathogenic variants are associated with Rett syndrome."
                    ),
                    value_level="high",
                    rationale="High-value disease context requiring review.",
                    object_curie="MONDO:0010726",
                    review_status="review_only",
                ),
            ),
        ),
        _case(
            case_id="review_only_generic_two",
            text="PAH pathogenic variants are associated with phenylketonuria.",
            gold=(
                GoldRelation(
                    subject="PAH pathogenic variants",
                    relation_type="ASSOCIATED_WITH",
                    object="phenylketonuria",
                    support_sentence=(
                        "PAH pathogenic variants are associated with phenylketonuria."
                    ),
                    value_level="high",
                    rationale="High-value disease context requiring review.",
                    object_curie="MONDO:0009861",
                    review_status="review_only",
                ),
            ),
        ),
    )

    def extractor(text: str) -> RelationExtractionResult:
        if "MED13" in text:
            relations = (
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    sentence="MED13 activates MAPK signaling.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="GO:0000165",
                    object_curie_source="verified_linker",
                ),
            )
        elif "MECP2" in text:
            relations = (
                ExtractedRelation(
                    subject="MECP2 pathogenic variants",
                    relation_type="ASSOCIATED_WITH",
                    object="Rett syndrome",
                    sentence=(
                        "MECP2 pathogenic variants are associated with Rett syndrome."
                    ),
                    object_curie="MONDO:0010726",
                    object_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("review_only_subject_grounding",),
                ),
            )
        else:
            relations = (
                ExtractedRelation(
                    subject="PAH pathogenic variants",
                    relation_type="ASSOCIATED_WITH",
                    object="phenylketonuria",
                    sentence=(
                        "PAH pathogenic variants are associated with phenylketonuria."
                    ),
                    object_curie="MONDO:0009861",
                    object_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("review_only_subject_grounding",),
                ),
            )
        return RelationExtractionResult(
            relations=relations,
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=len(relations),
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    summary_json = report.summary.to_json()

    assert report.summary.generic_relation_rate > 0.25
    assert report.summary.valuable_candidate_rate < 0.7
    assert report.summary.trusted_candidate_count == 1
    assert report.summary.trusted_candidate_valuable_count == 1
    assert report.summary.trusted_candidate_valuable_rate == 1.0
    assert report.summary.trusted_candidate_generic_relation_count == 0
    assert report.summary.trusted_candidate_generic_relation_rate == 0.0
    assert summary_json["trusted_candidate_generic_relation_rate"] == 0.0
    assert not any("valuable" in reason.lower() for reason in report.summary.warning_reasons)
    assert not any("generic" in reason.lower() for reason in report.summary.warning_reasons)


def test_trusted_candidate_matching_review_only_gold_is_hard_leakage() -> None:
    cases = (
        _case(
            case_id="trusted_anchor",
            text="MED13 activates MAPK signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    support_sentence="MED13 activates MAPK signaling.",
                    value_level="high",
                    rationale="Trusted-eligible mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0000165",
                ),
            ),
        ),
        _case(
            case_id="review_only_gold_without_candidate_review_flag",
            text="IL6 regulates inflammatory signaling.",
            gold=(
                GoldRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    support_sentence="IL6 regulates inflammatory signaling.",
                    value_level="high",
                    rationale="Broad endpoint must stay review-only.",
                    subject_curie="HGNC:6018",
                    review_status="review_only",
                ),
            ),
        ),
    )

    def extractor(text: str) -> RelationExtractionResult:
        if "IL6" in text:
            relations = (
                ExtractedRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    sentence="IL6 regulates inflammatory signaling.",
                    subject_curie="HGNC:6018",
                    subject_curie_source="verified_linker",
                ),
            )
        else:
            relations = (
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    sentence="MED13 activates MAPK signaling.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="GO:0000165",
                    object_curie_source="verified_linker",
                ),
            )
        return RelationExtractionResult(
            relations=relations,
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=len(relations),
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    summary_json = report.summary.to_json()

    assert report.summary.review_only_gold_trusted_leakage_count == 1
    assert report.summary.trusted_candidate_count == 2
    assert report.summary.trusted_candidate_supported_count == 1
    assert report.summary.trusted_candidate_valuable_count == 1
    assert report.summary.trusted_candidate_precision_against_gold == 0.5
    assert report.summary.trusted_candidate_valuable_rate == 0.5
    assert report.summary.verdict == "RED"
    assert "Review-only gold evidence leaked into trusted candidates." in (
        report.summary.blocking_reasons
    )
    assert summary_json["review_only_gold_trusted_leakage_count"] == 1


def test_low_value_review_metrics_ignore_fallback_review_only_candidates() -> None:
    cases = (
        _case(
            case_id="fallback_low_value_review",
            text="MED13 may be linked to congenital heart disease.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="congenital heart disease",
                    support_sentence=(
                        "MED13 may be linked to congenital heart disease."
                    ),
                    value_level="low",
                    rationale="Fallback review-only output is not agent evidence.",
                    requires_entailment=False,
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="congenital heart disease",
                    sentence="MED13 may be linked to congenital heart disease.",
                    review_status="review_only",
                    review_reason_codes=("hedged_language", "may_link"),
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="fallback_error",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.fallback_case_count == 1
    assert report.summary.low_value_review_candidate_count == 0
    assert report.summary.low_value_review_gold_match_count == 0
    assert report.summary.low_value_review_recall == 0.0


def test_low_value_review_recall_captures_pr23_weak_cases_without_trust_leakage() -> None:
    cases = (
        _case(
            case_id="trusted_high_value_anchor",
            text="MED13 activates MAPK signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    support_sentence="MED13 activates MAPK signaling.",
                    value_level="high",
                    rationale="High-value trusted mechanism anchor.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0000165",
                ),
            ),
        ),
        _case(
            case_id="weak_med13_may_link_chd",
            text="MED13 may be linked to congenital heart disease in a subset of families.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="congenital heart disease",
                    support_sentence=(
                        "MED13 may be linked to congenital heart disease in a "
                        "subset of families."
                    ),
                    value_level="low",
                    rationale="Hedged association belongs in review lane.",
                    subject_curie="HGNC:22474",
                    object_curie="MONDO:0005267",
                    requires_entailment=False,
                ),
            ),
        ),
        _case(
            case_id="weak_met_correlated_resistance",
            text=(
                "MET amplification was correlated with resistance in a small "
                "exploratory cohort."
            ),
            gold=(
                GoldRelation(
                    subject="MET amplification",
                    relation_type="ASSOCIATED_WITH",
                    object="resistance",
                    support_sentence=(
                        "MET amplification was correlated with resistance in a "
                        "small exploratory cohort."
                    ),
                    value_level="low",
                    rationale="Exploratory correlation belongs in review lane.",
                    subject_curie="HGNC:7029",
                    requires_entailment=False,
                ),
            ),
        ),
        _case(
            case_id="weak_akt_trend_survival",
            text="AKT activation showed a trend toward association with reduced survival.",
            gold=(
                GoldRelation(
                    subject="AKT activation",
                    relation_type="ASSOCIATED_WITH",
                    object="reduced survival",
                    support_sentence=(
                        "AKT activation showed a trend toward association with "
                        "reduced survival."
                    ),
                    value_level="low",
                    rationale="Trend language belongs in review lane.",
                    subject_curie="HGNC:391",
                    requires_entailment=False,
                ),
            ),
        ),
    )

    def agent_result(relation: ExtractedRelation) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(relation,),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    def extractor(text: str) -> RelationExtractionResult:
        if "MED13 activates" in text:
            return agent_result(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    sentence="MED13 activates MAPK signaling.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="GO:0000165",
                    object_curie_source="verified_linker",
                ),
            )
        if "may be linked" in text:
            return agent_result(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="congenital heart disease",
                    sentence=(
                        "MED13 may be linked to congenital heart disease in a "
                        "subset of families."
                    ),
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="MONDO:0005267",
                    object_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("hedged_language", "may_link"),
                ),
            )
        if "MET amplification" in text:
            return agent_result(
                ExtractedRelation(
                    subject="MET amplification",
                    relation_type="ASSOCIATED_WITH",
                    object="resistance",
                    sentence=(
                        "MET amplification was correlated with resistance in a "
                        "small exploratory cohort."
                    ),
                    subject_curie="HGNC:7029",
                    subject_curie_source="verified_linker",
                    review_status="review_only",
                    review_reason_codes=("hedged_language", "correlated_only"),
                ),
            )
        return agent_result(
            ExtractedRelation(
                subject="AKT activation",
                relation_type="ASSOCIATED_WITH",
                object="reduced survival",
                sentence=(
                    "AKT activation showed a trend toward association with "
                    "reduced survival."
                ),
                subject_curie="HGNC:391",
                subject_curie_source="verified_linker",
                review_status="review_only",
                review_reason_codes=("hedged_language", "trend_only"),
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    low_value_flags = {
        result.case.case_id: result.candidate_assessments[0].quality_flags
        for result in report.case_results
        if result.case.case_id.startswith("weak_")
    }

    assert report.summary.low_value_review_recall >= 0.8
    assert report.summary.weak_claim_trusted_leakage_count == 0
    assert report.summary.trusted_high_value_recall >= 0.85
    assert report.summary.precision_against_gold == 1.0
    assert "review_only_candidate" in low_value_flags["weak_med13_may_link_chd"]
    assert "review_reason:may_link" in low_value_flags["weak_med13_may_link_chd"]
    assert "review_reason:correlated_only" in low_value_flags[
        "weak_met_correlated_resistance"
    ]
    assert "review_reason:trend_only" in low_value_flags["weak_akt_trend_survival"]


def test_endpoint_metrics_split_trusted_eligible_from_low_value_review() -> None:
    cases = (
        _case(
            case_id="endpoint_metric_split_high",
            text="MED13 activates MAPK signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    support_sentence="MED13 activates MAPK signaling.",
                    value_level="high",
                    rationale="Trusted-eligible mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0000165",
                ),
            ),
        ),
        _case(
            case_id="endpoint_metric_split_low",
            text="IL6 may regulate inflammatory signaling.",
            gold=(
                GoldRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    support_sentence="IL6 may regulate inflammatory signaling.",
                    value_level="low",
                    rationale="Weak claim belongs in review lane.",
                    subject_curie="HGNC:6018",
                    object_curie="GO:0006954",
                ),
            ),
        ),
    )

    def extractor(text: str) -> RelationExtractionResult:
        if "IL6" in text:
            relations = (
                ExtractedRelation(
                        subject="IL6",
                        relation_type="REGULATES",
                        object="inflammatory signaling",
                        sentence="IL6 may regulate inflammatory signaling.",
                        subject_curie="HGNC:6018",
                        subject_curie_source="verified_linker",
                        object_curie="GO:0006954",
                        object_curie_source="verified_linker",
                        review_status="review_only",
                        review_reason_codes=("hedged_language", "may_regulate"),
                ),
            )
        else:
            relations = (
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    sentence="MED13 activates MAPK signaling.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="GO:0000165",
                    object_curie_source="verified_linker",
                ),
            )
        return RelationExtractionResult(
            relations=relations,
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=len(relations),
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    summary_json = report.summary.to_json()

    assert report.summary.trusted_eligible_gold_curie_endpoint_count == 2
    assert report.summary.trusted_eligible_curie_linked_gold_endpoint_count == 2
    assert report.summary.trusted_eligible_curie_linked_gold_endpoint_rate == 1.0
    assert report.summary.low_value_review_curie_endpoint_capture_rate == 1.0
    assert report.summary.weak_claim_trusted_leakage_count == 0
    assert summary_json["trusted_eligible_curie_linked_gold_endpoint_rate"] == 1.0
    assert summary_json["low_value_review_curie_endpoint_capture_rate"] == 1.0
    assert summary_json["weak_claim_trusted_leakage_count"] == 0


def test_weak_low_value_claim_trusted_leakage_is_counted() -> None:
    cases = (
        _case(
            case_id="weak_claim_leakage",
            text="IL6 may regulate inflammatory signaling.",
            gold=(
                GoldRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    support_sentence="IL6 may regulate inflammatory signaling.",
                    value_level="low",
                    rationale="Weak claim belongs in review lane.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    sentence="IL6 may regulate inflammatory signaling.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )

    assert report.summary.weak_claim_trusted_leakage_count == 1
    assert report.summary.low_value_review_candidate_count == 0


def test_fallback_low_value_claim_does_not_count_as_trusted_leakage() -> None:
    cases = (
        _case(
            case_id="fallback_weak_claim",
            text="IL6 may regulate inflammatory signaling.",
            gold=(
                GoldRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    support_sentence="IL6 may regulate inflammatory signaling.",
                    value_level="low",
                    rationale="Fallback output is not trusted agent evidence.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="IL6",
                    relation_type="REGULATES",
                    object="inflammatory signaling",
                    sentence="IL6 may regulate inflammatory signaling.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="fallback",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.fallback_case_count == 1
    assert report.summary.weak_claim_trusted_leakage_count == 0


def test_verdict_uses_trusted_eligible_endpoint_rate_not_all_gold_rate() -> None:
    cases = (
        _case(
            case_id="trusted_endpoint_verdict_high",
            text="MED13 activates MAPK signaling.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    support_sentence="MED13 activates MAPK signaling.",
                    value_level="high",
                    rationale="Trusted-eligible mechanism.",
                    subject_curie="HGNC:22474",
                    object_curie="GO:0000165",
                ),
            ),
        ),
        _case(
            case_id="trusted_endpoint_verdict_low",
            text="MET amplification was correlated with resistance.",
            gold=(
                GoldRelation(
                    subject="MET amplification",
                    relation_type="ASSOCIATED_WITH",
                    object="resistance",
                    support_sentence="MET amplification was correlated with resistance.",
                    value_level="low",
                    rationale="Weak evidence belongs in review lane.",
                    subject_curie="HGNC:7029",
                ),
            ),
        ),
    )

    def extractor(text: str) -> RelationExtractionResult:
        if "MED13" not in text:
            return RelationExtractionResult(
                relations=(),
                trace=ExtractionTrace(
                    extractor_mode="agent",
                    llm_candidate_status="completed",
                    llm_candidate_count=0,
                ),
            )
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="MAPK signaling",
                    sentence="MED13 activates MAPK signaling.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="GO:0000165",
                    object_curie_source="verified_linker",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )

    assert report.summary.curie_linked_gold_endpoint_rate < 0.95
    assert report.summary.trusted_eligible_curie_linked_gold_endpoint_rate == 1.0
    assert report.summary.weak_claim_trusted_leakage_count == 0
    assert report.summary.verdict != "RED"
    assert "Too few CURIE-linked gold endpoints" not in report.summary.blocking_reasons


def test_summary_counts_negative_control_empty_agent_completions() -> None:
    cases = (
        _case(
            case_id="negative_control_methods",
            text="Libraries were sequenced on an Illumina instrument.",
            gold=(),
        ),
    )
    negative_control_case = BenchmarkCase(
        case_id=cases[0].case_id,
        title=cases[0].title,
        category="negative_control",
        text=cases[0].text,
        gold_relations=cases[0].gold_relations,
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="llm_empty",
                llm_candidate_count=0,
            ),
        )

    report = run_feasibility_audit(
        cases=(negative_control_case,),
        extractor=extractor,
        require_agent_completion=True,
    )
    markdown = render_markdown_report(report)

    assert report.summary.negative_control_empty_count == 1
    assert report.summary.negative_control_case_count == 1
    assert report.summary.negative_control_empty_rate == 1.0
    assert report.summary.negative_control_leakage_count == 0
    assert "Negative-control empty completions: 1" in markdown
    assert "Negative-control leakage cases: 0" in markdown


def test_negative_control_candidate_leakage_is_reported_as_blocking() -> None:
    negative_control_case = BenchmarkCase(
        case_id="negative_control_leak",
        title="Negative Control Leak",
        category="negative_control",
        text="Libraries were sequenced on an Illumina instrument.",
        gold_relations=(),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="Illumina",
                    relation_type="ASSOCIATED_WITH",
                    object="instrument",
                    sentence="Libraries were sequenced on an Illumina instrument.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=(negative_control_case,),
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.negative_control_case_count == 1
    assert report.summary.negative_control_empty_count == 0
    assert report.summary.negative_control_leakage_count == 1
    assert report.summary.verdict == "RED"
    assert any(
        "negative-control" in reason
        for reason in report.summary.blocking_reasons
    )


def test_audit_turns_red_when_gold_curie_endpoints_are_missing() -> None:
    cases = (
        _case(
            case_id="missing_curie_link",
            text="MED13 causes developmental delay.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="CAUSES",
                    object="developmental delay",
                    support_sentence="MED13 causes developmental delay.",
                    value_level="high",
                    rationale="Gold endpoints include stable ontology identifiers.",
                    subject_curie="HGNC:22474",
                    object_curie="HP:0001263",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="CAUSES",
                    object="developmental delay",
                    sentence="MED13 causes developmental delay.",
                ),
            ),
            trace=ExtractionTrace(extractor_mode="custom"),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert report.summary.curie_linked_gold_endpoint_rate == 0.0
    assert report.summary.verdict == "RED"
    assert "CURIE-linked gold endpoints" in report.summary.verdict_reason
    assert "missing_subject_curie" in assessment.quality_flags
    assert "missing_object_curie" in assessment.quality_flags


def test_audit_counts_raw_unknown_relation_types_as_blocking_quality_issue() -> None:
    cases = (
        _case(
            case_id="raw_unknown_relation_type",
            text="MET amplification protects against erlotinib.",
            gold=(),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MET amplification",
                relation_type="PROTECTS_AGAINST",
                object="erlotinib",
                sentence="MET amplification protects against erlotinib.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert report.summary.raw_unknown_relation_type_count == 1
    assert report.summary.raw_unknown_relation_type_rate == 1.0
    assert report.summary.verdict == "RED"
    assert "raw unknown relation type" in report.summary.verdict_reason
    assert assessment.has_known_relation_type is False
    assert "raw_unknown_relation_type" in assessment.quality_flags


def test_canonical_confers_resistance_counts_as_known_valuable_relation() -> None:
    cases = (
        _case(
            case_id="canonical_confers_resistance",
            text="MET amplification confers resistance to erlotinib.",
            gold=(
                GoldRelation(
                    subject="MET amplification",
                    relation_type="CONFERS_RESISTANCE_TO",
                    object="erlotinib",
                    support_sentence=(
                        "MET amplification confers resistance to erlotinib."
                    ),
                    value_level="high",
                    rationale="Specific drug-resistance relation.",
                    subject_curie="HGNC:7029",
                    object_curie="DrugBank:DB00530",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MET amplification",
                subject_curie="HGNC:7029",
                subject_curie_source="verified_linker",
                relation_type="CONFERS_RESISTANCE_TO",
                object="erlotinib",
                object_curie="DrugBank:DB00530",
                object_curie_source="verified_linker",
                sentence="MET amplification confers resistance to erlotinib.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.is_supported_by_gold is True
    assert assessment.is_valuable is True
    assert assessment.has_known_relation_type is True
    assert report.summary.raw_unknown_relation_type_count == 0
    assert report.summary.high_value_recall == 1.0
    assert report.summary.curie_linked_gold_endpoint_rate == 1.0


def test_governed_relation_proposal_counts_proposal_recall_without_trusted_recall() -> None:
    cases = (
        _case(
            case_id="governed_relation_proposal",
            text="BRCA1 loss reduces toxicity of cisplatin.",
            gold=(
                GoldRelation(
                    subject="BRCA1 loss",
                    relation_type="REDUCES_TOXICITY_OF",
                    object="cisplatin",
                    support_sentence=(
                        "BRCA1 loss reduces toxicity of cisplatin."
                    ),
                    value_level="high",
                    rationale="Specific toxicity relation proposed for governance.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="BRCA1 loss",
                relation_type="PROPOSE_NEW_RELATION_TYPE",
                proposed_relation_type="REDUCES_TOXICITY_OF",
                new_relation_type_rationale=(
                    "Toxicity-specific effect relation not covered by canonical types."
                ),
                relation_governance_status="requires_relation_review",
                object="cisplatin",
                sentence="BRCA1 loss reduces toxicity of cisplatin.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    assessment = report.case_results[0].candidate_assessments[0]
    markdown = render_markdown_report(report)

    assert assessment.is_supported_by_gold is False
    assert assessment.proposal_matched_gold_index == 0
    assert assessment.is_governed_relation_proposal is True
    assert assessment.is_trusted_evidence_eligible is False
    assert assessment.is_valuable is False
    assert "requires_relation_review" in assessment.quality_flags
    assert report.summary.proposal_candidate_count == 1
    assert report.summary.proposal_gold_match_count == 1
    assert report.summary.proposal_eligible_gold_count == 1
    assert report.summary.proposal_recall_against_gold == 1.0
    assert report.summary.proposal_recall_against_proposal_eligible_gold == 1.0
    assert report.summary.raw_unknown_relation_type_count == 0
    assert report.summary.high_value_recall == 0.0
    assert "Governed proposal recall among proposal-eligible gold: 1.0000" in markdown


def test_governed_proposal_recall_uses_proposal_eligible_denominator() -> None:
    cases = (
        _case(
            case_id="canonical_gold",
            text="MED13 activates EGFR.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="EGFR",
                    support_sentence="MED13 activates EGFR.",
                    value_level="high",
                    rationale="Canonical mechanism.",
                ),
            ),
        ),
        _case(
            case_id="proposal_eligible_gold",
            text="BRCA1 loss reduces toxicity of cisplatin.",
            gold=(
                GoldRelation(
                    subject="BRCA1 loss",
                    relation_type="REDUCES_TOXICITY_OF",
                    object="cisplatin",
                    support_sentence=(
                        "BRCA1 loss reduces toxicity of cisplatin."
                    ),
                    value_level="high",
                    rationale="Relation needs dictionary governance.",
                ),
            ),
        ),
    )

    def extractor(text: str) -> list[ExtractedRelation]:
        if "BRCA1 loss" not in text:
            return []
        return [
            ExtractedRelation(
                subject="BRCA1 loss",
                relation_type="PROPOSE_NEW_RELATION_TYPE",
                proposed_relation_type="REDUCES_TOXICITY_OF",
                new_relation_type_rationale="Governed toxicity relation.",
                relation_governance_status="requires_relation_review",
                object="cisplatin",
                sentence="BRCA1 loss reduces toxicity of cisplatin.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.proposal_gold_match_count == 1
    assert report.summary.proposal_eligible_gold_count == 1
    assert report.summary.proposal_recall_against_proposal_eligible_gold == 1.0
    assert report.summary.proposal_recall_against_gold == 0.5


def test_audit_counts_raw_unknown_relation_type_inventory_surfaces() -> None:
    cases = (
        _case(
            case_id="raw_unknown_relation_type_surface",
            text="MED13 was proposed with an ungoverned relation surface.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(extractor_mode="custom"),
            relation_type_surfaces=(
                RelationTypeSurface(
                    surface="review_item.proposal_draft.payload.proposed_claim_type",
                    relation_type="PROTECTS_AGAINST",
                    source_ref="review_item:raw-relation",
                ),
            ),
        )

    report = run_feasibility_audit(cases=cases, extractor=extractor)

    assert report.summary.raw_unknown_relation_type_count == 0
    assert report.summary.relation_type_surface_count == 1
    assert report.summary.raw_unknown_relation_type_surface_count == 1
    assert report.summary.raw_unknown_relation_type_surface_rate == 1.0
    assert report.summary.verdict == "RED"
    assert "review, proposal, graph, or dictionary surface" in (
        report.summary.verdict_reason
    )
    assert (
        report.case_results[0].relation_type_surfaces[0].surface
        == "review_item.proposal_draft.payload.proposed_claim_type"
    )


def test_markdown_report_includes_decision_verdict() -> None:
    report = run_feasibility_audit(cases=(), extractor=lambda _: [])

    markdown = render_markdown_report(report)

    assert "# Relation Feasibility Audit" in markdown
    assert "Verdict" in markdown
    assert "RED" in markdown


def test_markdown_report_includes_adversarial_findings() -> None:
    cases = (
        _case(
            case_id="generic_relation",
            text="MED13 was associated with clinical features.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="clinical features",
                    sentence="MED13 was associated with clinical features.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="unavailable",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    markdown = render_markdown_report(report)

    assert "## Adversarial Checks" in markdown
    assert "fallback_only_report" in markdown
    assert "all_candidate_generic_relation_rate_high" in markdown


def test_adversarial_findings_detect_quality_illusions() -> None:
    cases = (
        _case(
            case_id="generic_relation",
            text="MED13 was associated with clinical features.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="clinical features",
                    sentence="MED13 was associated with clinical features.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="unavailable",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    findings = find_quality_illusions(report)

    finding_codes = {finding.code for finding in findings}

    assert finding_codes >= {
        "fallback_only_report",
        "all_candidate_generic_relation_rate_high",
    }
    assert "entailment_not_checked" not in finding_codes
    assert report.summary.entailment_checked_rate == 1.0


def test_adversarial_findings_distinguish_trusted_generic_candidates() -> None:
    cases = (
        _case(
            case_id="trusted_generic_candidate",
            text="MED13 was associated with developmental delay.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="developmental delay",
                    support_sentence="MED13 was associated with developmental delay.",
                    value_level="high",
                    rationale="Generic relation should be visible if trusted.",
                    subject_curie="HGNC:22474",
                    object_curie="HP:0001263",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ASSOCIATED_WITH",
                    object="developmental delay",
                    sentence="MED13 was associated with developmental delay.",
                    subject_curie="HGNC:22474",
                    subject_curie_source="verified_linker",
                    object_curie="HP:0001263",
                    object_curie_source="verified_linker",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        support_verifier=_AGENT_SUPPORT_VERIFIER,
    )
    findings = find_quality_illusions(report)
    finding_codes = {finding.code for finding in findings}

    assert report.summary.trusted_candidate_generic_relation_rate == 1.0
    assert "trusted_candidate_generic_relation_rate_high" in finding_codes
    assert "all_candidate_generic_relation_rate_high" not in finding_codes


def test_adversarial_findings_warn_when_relation_arguments_are_missing() -> None:
    cases = (
        _case(
            case_id="mixed_grounding",
            text="MED13 activates cardiac septal development.",
            gold=(),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                sentence="MED13 activates cardiac septal development.",
            ),
            ExtractedRelation(
                subject="BRCA1",
                relation_type="REGULATES",
                object="DNA repair",
                sentence="This sentence is not in the source.",
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    findings = find_quality_illusions(report)

    assert report.summary.grounded_sentence_rate == 0.5
    assert report.summary.both_arguments_present_rate == 0.5
    finding_codes = {finding.code for finding in findings}

    assert "entailment_not_checked" in finding_codes
    assert "relation_arguments_missing_from_sentence" in finding_codes
    assert report.summary.entailment_checked_rate == 0.5


def test_adversarial_findings_warn_when_source_sentence_is_not_grounded() -> None:
    cases = (
        _case(
            case_id="ungrounded_sentence",
            text="MED13 activates cardiac septal development.",
            gold=(),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                sentence=(
                    "MED13 activates cardiac septal development in a separate "
                    "unpublished note."
                ),
            ),
        ]

    report = run_feasibility_audit(cases=cases, extractor=extractor)
    findings = find_quality_illusions(report)
    finding_codes = {finding.code for finding in findings}
    assessment = report.case_results[0].candidate_assessments[0]

    assert assessment.has_grounded_sentence is False
    assert assessment.has_both_arguments_in_sentence is False
    assert assessment.support_verification is None
    assert "missing_source_sentence" in assessment.quality_flags
    assert "support_not_entailed" not in assessment.quality_flags
    assert "support_not_checked" in assessment.quality_flags
    assert report.summary.grounded_sentence_rate == 0.0
    assert report.summary.both_arguments_present_rate == 0.0
    assert report.summary.entailment_checked_rate == 0.0
    assert "source_sentence_not_grounded" in finding_codes
    assert "entailment_not_checked" in finding_codes
    assert "relation_arguments_missing_from_sentence" in finding_codes


def test_report_serializes_to_json(tmp_path: Path) -> None:
    report = run_feasibility_audit(cases=(), extractor=lambda _: [])
    output_path = tmp_path / "report.json"

    output_path.write_text(json.dumps(report.to_json(), indent=2) + "\n")

    payload = json.loads(output_path.read_text())
    assert payload["summary"]["case_count"] == 0
    assert payload["summary"]["verdict"] == "RED"


def test_v2_fixture_has_required_categories_and_richer_labels() -> None:
    cases = load_benchmark_cases(
        Path("scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json"),
    )

    categories = {case.category for case in cases}
    gold_relations = tuple(
        relation for case in cases for relation in case.gold_relations
    )

    assert len(cases) >= 30
    assert categories >= {
        "strong_specific",
        "weak_association",
        "negative_control",
        "complex_mispairing",
        "generic_sibling",
        "long_document",
    }
    assert any(relation.subject_curie for relation in gold_relations)
    assert any(relation.object_curie for relation in gold_relations)
    assert any(not relation.requires_entailment for relation in gold_relations)


def test_v2_fixture_pins_pr21_verified_grounding_policy() -> None:
    cases = load_benchmark_cases(
        Path("scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json"),
    )

    gold_by_case = {
        case.case_id: case.gold_relations[0]
        for case in cases
        if case.case_id
        in {
            "strong_med13_activates_septal_development",
            "strong_brca1_regulates_dna_repair",
            "strong_mek_inhibits_erk",
            "strong_pdl1_biomarker_immunotherapy",
            "strong_braf_v600e_activates_mapk",
            "complex_ret_variant_alias",
            "complex_her2_amplification_growth",
            "long_document_tail_relation_braf",
        }
    }

    assert (
        gold_by_case["strong_med13_activates_septal_development"].object_curie
        == "GO:0003279"
    )
    assert (
        gold_by_case["strong_brca1_regulates_dna_repair"].object_curie
        == "GO:0000724"
    )
    assert gold_by_case["strong_mek_inhibits_erk"].object_curie is None
    assert (
        gold_by_case["strong_braf_v600e_activates_mapk"].object_curie
        == "GO:0000165"
    )
    assert gold_by_case["complex_ret_variant_alias"].object_curie == "GO:0000165"
    assert (
        gold_by_case["long_document_tail_relation_braf"].object_curie
        == "GO:0000165"
    )
    assert gold_by_case["strong_pdl1_biomarker_immunotherapy"].object_curie is None
    assert gold_by_case["complex_her2_amplification_growth"].object_curie is None


def test_v2_fixture_uses_canonical_drug_resistance_relation_shape() -> None:
    cases = load_benchmark_cases(
        Path("scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json"),
    )

    gold_by_case = {
        case.case_id: case.gold_relations[0]
        for case in cases
        if case.case_id
        in {
            "complex_nsclc_alias",
            "generic_sibling_met_resistance",
            "generic_sibling_egfr_t790m_resistance",
        }
    }

    for case_id in ("complex_nsclc_alias", "generic_sibling_met_resistance"):
        relation = gold_by_case[case_id]
        assert relation.relation_type == "CONFERS_RESISTANCE_TO"
        assert relation.object == "erlotinib"
        assert relation.object_curie == "DrugBank:DB00530"

    egfr_relation = gold_by_case["generic_sibling_egfr_t790m_resistance"]
    assert egfr_relation.relation_type == "CONFERS_RESISTANCE_TO"
    assert egfr_relation.object == "gefitinib"
    assert egfr_relation.object_curie == "DrugBank:DB00317"


def test_agent_trace_counts_completed_agent_cases() -> None:
    cases = (
        _case(
            case_id="specific_relation",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific gene-to-process mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.agent_completed_case_count == 1
    assert report.summary.fallback_case_count == 0
    assert report.summary.invalid_agent_case_count == 0
    assert report.summary.completed_agent_candidate_count == 1
    assert report.summary.completed_agent_precision_against_gold == 1.0
    assert report.summary.completed_agent_recall_against_gold == 1.0
    assert report.summary.completed_agent_valuable_candidate_rate == 1.0
    assert report.summary.both_arguments_present_rate == 1.0
    assert report.case_results[0].extraction_trace.extractor_mode == "agent"


def test_strict_agent_mode_marks_fallback_as_invalid() -> None:
    cases = (
        _case(
            case_id="fallback_relation",
            text="MED13 activates cardiac septal development.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="unavailable",
                llm_candidate_error="OPENAI_API_KEY not configured",
                fallback_candidate_count=0,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.verdict == "RED"
    assert report.summary.fallback_case_count == 1
    assert report.summary.invalid_agent_case_count == 1
    assert "agent extraction did not complete" in report.summary.verdict_reason


def test_llm_empty_without_fallback_is_not_counted_as_fallback_case() -> None:
    cases = (
        _case(
            case_id="empty_agent_relation",
            text="No relation is asserted here.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="llm_empty",
                fallback_candidate_count=0,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.verdict == "RED"
    assert report.summary.agent_completed_case_count == 1
    assert report.summary.agent_zero_candidate_case_count == 1
    assert report.summary.invalid_agent_case_count == 0
    assert report.summary.fallback_case_count == 0


@pytest.mark.parametrize("status", ["fallback", "fallback_error"])
def test_strict_agent_mode_marks_fallback_statuses_as_invalid(
    status: str,
) -> None:
    cases = (
        _case(
            case_id=f"{status}_relation",
            text="MED13 activates cardiac septal development.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status=status,
                fallback_candidate_count=0,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.verdict == "RED"
    assert report.summary.agent_completed_case_count == 0
    assert report.summary.agent_zero_candidate_case_count == 0
    assert report.summary.invalid_agent_case_count == 1
    assert report.summary.fallback_case_count == 1


def test_malformed_llm_empty_with_nonzero_llm_count_is_invalid() -> None:
    trace = ExtractionTrace(
        extractor_mode="agent",
        llm_candidate_status="llm_empty",
        llm_candidate_count=1,
        fallback_candidate_count=0,
    )

    assert trace.agent_completed is False
    assert trace.fallback_used is False


def test_malformed_llm_empty_with_candidates_is_invalid() -> None:
    cases = (
        _case(
            case_id="malformed_empty_agent_relation",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="llm_empty",
                llm_candidate_count=0,
                fallback_candidate_count=0,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.agent_completed_case_count == 0
    assert report.summary.agent_zero_candidate_case_count == 0
    assert report.summary.invalid_agent_case_count == 1
    assert report.summary.completed_agent_candidate_count == 0
    assert (
        report.to_json()["case_results"][0]["extraction_trace"]["agent_completed"]
        is False
    )


def test_llm_empty_with_fallback_candidates_is_counted_as_fallback_case() -> None:
    cases = (
        _case(
            case_id="empty_agent_with_fallback_relation",
            text="No relation is asserted here.",
            gold=(),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="llm_empty",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.verdict == "RED"
    assert report.summary.agent_completed_case_count == 0
    assert report.summary.invalid_agent_case_count == 1
    assert report.summary.fallback_case_count == 1


def test_gold_relation_accepts_grounding_and_curie_labels() -> None:
    relation = GoldRelation(
        subject="MED13",
        relation_type="ACTIVATES",
        object="cardiac septal development",
        support_sentence="MED13 activates cardiac septal development.",
        value_level="high",
        rationale="Specific gene-to-process mechanism.",
        subject_curie="HGNC:22474",
        object_curie=None,
        requires_entailment=True,
    )

    assert relation.subject_curie == "HGNC:22474"
    assert relation.object_curie is None
    assert relation.requires_entailment is True


def test_summary_reports_missing_agent_completion_as_red_even_with_candidates() -> None:
    cases = (
        _case(
            case_id="fallback_with_candidate",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="unavailable",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.verdict == "RED"
    assert report.summary.invalid_agent_case_count == 1
    assert report.summary.candidate_count == 1
    assert report.summary.valuable_candidate_count == 1
    assert report.summary.completed_agent_candidate_count == 0
    assert report.summary.completed_agent_valuable_candidate_rate == 0.0
    assert report.summary.fallback_credited_as_agent_count == 1


def test_llm_empty_without_fallback_counts_as_agent_completed() -> None:
    trace = ExtractionTrace(
        extractor_mode="agent",
        llm_candidate_status="llm_empty",
        llm_candidate_count=0,
        fallback_candidate_count=0,
    )

    assert trace.agent_completed is True
    assert trace.fallback_used is False


def test_strict_agent_summary_treats_llm_empty_as_valid_zero_candidate_run() -> None:
    positive_case = _case(
        case_id="positive_specific",
        text="MED13 activates cardiac septal development.",
        gold=(
            GoldRelation(
                subject="MED13",
                relation_type="ACTIVATES",
                object="cardiac septal development",
                support_sentence="MED13 activates cardiac septal development.",
                value_level="high",
                rationale="Specific mechanism.",
            ),
        ),
    )
    negative_case = _case(
        case_id="negative_methods",
        text="RNA sequencing libraries were prepared using standard protocols.",
        gold=(),
    )

    def extractor(text: str) -> RelationExtractionResult:
        if "RNA sequencing" in text:
            return RelationExtractionResult(
                relations=(),
                trace=ExtractionTrace(
                    extractor_mode="agent",
                    llm_candidate_status="llm_empty",
                    llm_candidate_count=0,
                    fallback_candidate_count=0,
                ),
            )
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=(positive_case, negative_case),
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.agent_completed_case_count == 2
    assert report.summary.agent_zero_candidate_case_count == 1
    assert report.summary.invalid_agent_case_count == 0
    assert report.summary.fallback_case_count == 0
    assert report.summary.completed_agent_candidate_count == 1
    assert report.summary.verdict != "RED" or "invalid" not in (
        report.summary.verdict_reason.lower()
    )

    markdown = render_markdown_report(report)
    assert "comparison/triage metrics" in markdown
    assert "Agent zero-candidate cases: 1" in markdown
    assert "Invalid strict-agent cases: 0" in markdown


def test_cli_labels_all_candidate_and_completed_agent_metrics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    cases = (
        _case(
            case_id="fallback_with_candidate",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="fallback_error",
                fallback_candidate_count=1,
            ),
        )

    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.ensure_live_agent_ready",
        lambda: LiveAgentPreflightSnapshot(
            status="healthy",
            model_id="openai/gpt-5.4-mini",
            capability="evidence_extraction",
            timeout_seconds=10.0,
            detail="ready",
        ),
    )
    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.load_benchmark_cases",
        lambda _path: cases,
    )
    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.extract_with_agent",
        extractor,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_relation_feasibility_audit.py",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert main() == 0

    captured = capsys.readouterr()
    assert "all_candidate_precision=" in captured.out
    assert "all_candidate_recall=" in captured.out
    assert "all_candidate_valuable_rate=" in captured.out
    assert "all_candidate_generic_relation_rate=" in captured.out
    assert "all_candidate_curie_linked_gold_endpoint_rate=" in captured.out
    assert "completed_agent_precision=" in captured.out
    assert "completed_agent_recall=" in captured.out
    assert "completed_agent_valuable_rate=" in captured.out
    assert " precision=" not in captured.out
    assert " recall=" not in captured.out
    assert " valuable_rate=" not in captured.out
    assert " generic_relation_rate=" not in captured.out
    assert " curie_linked_gold_endpoint_rate=" not in captured.out


def test_cli_defaults_to_strict_agent_mode() -> None:
    args = parse_args([])

    assert args.extractor == "agent"
    assert args.allow_fallback is False
    assert args.cases.name == "biomedical_relation_goldset_v2.json"


def test_strict_agent_extractor_uses_no_fallback_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _strict_discovery(
        text: str,
        *,
        space_context: str,
    ):
        assert text == "MED13 activates cardiac septal development."
        assert space_context == "Relation feasibility audit benchmark."
        return (
            [
                ExtractedRelationCandidate(
                    subject_label="MED13",
                    relation_type="ACTIVATES",
                    object_label="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ],
            DocumentCandidateExtractionDiagnostics(
                llm_candidate_status="completed",
                llm_candidate_count=1,
            ),
        )

    async def _unexpected_fallback_discovery(*_args: object, **_kwargs: object):
        raise AssertionError("strict agent extractor must not use fallback discovery")

    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.discover_relation_candidates_strict",
        _strict_discovery,
    )
    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.discover_relation_candidates",
        _unexpected_fallback_discovery,
    )

    result = extract_with_agent("MED13 activates cardiac septal development.")

    assert result.trace.agent_completed is True
    assert result.trace.fallback_used is False


def test_strict_agent_main_fails_preflight_before_loading_cases(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "strict-agent-report"

    def _unhealthy_preflight() -> LiveAgentPreflightSnapshot:
        raise LiveAgentPreflightError(
            LiveAgentPreflightSnapshot(
                status="degraded",
                model_id="openai/gpt-5.4-mini",
                capability="evidence_extraction",
                timeout_seconds=10.0,
                detail="OPENAI_API_KEY is not configured.",
            ),
        )

    def _unexpected_case_load(_path: Path) -> tuple[BenchmarkCase, ...]:
        raise AssertionError("strict preflight must run before benchmark loading")

    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.ensure_live_agent_ready",
        _unhealthy_preflight,
    )
    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.load_benchmark_cases",
        _unexpected_case_load,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_relation_feasibility_audit.py",
            "--output-dir",
            str(output_dir),
        ],
    )

    exit_code = main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Live agent preflight failed" in captured.err
    assert "OPENAI_API_KEY" in captured.err
    assert "ARTANA_OPENAI_API_KEY" in captured.err
    assert "openai/gpt-5.4-mini" in captured.err
    assert not output_dir.exists()


def test_allow_fallback_mode_skips_live_agent_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _unexpected_preflight() -> LiveAgentPreflightSnapshot:
        raise AssertionError("--allow-fallback should skip live-agent preflight")

    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.ensure_live_agent_ready",
        _unexpected_preflight,
    )
    monkeypatch.setattr(
        "scripts.run_relation_feasibility_audit.load_benchmark_cases",
        lambda _path: (),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_relation_feasibility_audit.py",
            "--allow-fallback",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert main() == 0
