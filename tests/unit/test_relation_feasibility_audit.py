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
    assert report.case_results[0].candidate_assessments[0].is_valuable is True


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
    assert assessment.is_valuable is False
    assert "missing_relation_arguments" in assessment.quality_flags
    assert "support_sentence_mismatch" in assessment.quality_flags


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
            subject_label="MET amplification",
            relation_type="PROPOSE_NEW_RELATION_TYPE",
            proposed_relation_type="CONFERS_RESISTANCE_TO",
            new_relation_type_rationale="Specific resistance relation.",
            relation_governance_status="requires_relation_review",
            object_label="erlotinib",
            sentence="MET amplification confers resistance to erlotinib.",
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
    assert result.relations[1].proposed_relation_type == "CONFERS_RESISTANCE_TO"
    assert result.relations[1].new_relation_type_rationale == (
        "Specific resistance relation."
    )
    assert result.relations[1].relation_governance_status == (
        "requires_relation_review"
    )
    assert result.relations[1].trusted_evidence_eligible is False


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
        if "activates" not in text:
            return []
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
    assert report.summary.low_value_missed_gold_count == 1
    assert report.summary.low_value_recall == 0.0
    assert "High-value recall: 1.0000" in markdown
    assert "Low-value recall: 0.0000" in markdown


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
            text="MET amplification confers resistance to erlotinib.",
            gold=(),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MET amplification",
                relation_type="CONFERS_RESISTANCE_TO",
                object="erlotinib",
                sentence="MET amplification confers resistance to erlotinib.",
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


def test_governed_relation_proposal_counts_proposal_recall_without_trusted_recall() -> None:
    cases = (
        _case(
            case_id="governed_relation_proposal",
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
                    rationale="Specific resistance relation proposed for governance.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> list[ExtractedRelation]:
        return [
            ExtractedRelation(
                subject="MET amplification",
                relation_type="PROPOSE_NEW_RELATION_TYPE",
                proposed_relation_type="CONFERS_RESISTANCE_TO",
                new_relation_type_rationale=(
                    "Specific resistance relation not covered by canonical types."
                ),
                relation_governance_status="requires_relation_review",
                object="erlotinib",
                sentence="MET amplification confers resistance to erlotinib.",
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
                    rationale="Relation needs dictionary governance.",
                ),
            ),
        ),
    )

    def extractor(text: str) -> list[ExtractedRelation]:
        if "MET amplification" not in text:
            return []
        return [
            ExtractedRelation(
                subject="MET amplification",
                relation_type="PROPOSE_NEW_RELATION_TYPE",
                proposed_relation_type="CONFERS_RESISTANCE_TO",
                new_relation_type_rationale="Governed resistance relation.",
                relation_governance_status="requires_relation_review",
                object="erlotinib",
                sentence="MET amplification confers resistance to erlotinib.",
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
    assert "generic_relation_rate_high" in markdown


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
        "generic_relation_rate_high",
    }
    assert "entailment_not_checked" not in finding_codes
    assert report.summary.entailment_checked_rate == 1.0


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
    assert {finding.code for finding in findings} >= {
        "entailment_not_checked",
        "relation_arguments_missing_from_sentence",
    }


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
