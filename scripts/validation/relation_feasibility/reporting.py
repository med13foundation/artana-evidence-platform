"""Markdown reporting for relation feasibility audits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.validation.relation_feasibility.adversarial import find_quality_illusions

if TYPE_CHECKING:
    from scripts.validation.relation_feasibility.models import (
        CandidateAssessment,
        ExtractedRelation,
        FeasibilityReport,
    )


def render_markdown_report(report: FeasibilityReport) -> str:
    """Render one feasibility report as Markdown."""

    summary = report.summary
    lines = [
        "# Relation Feasibility Audit",
        "",
        "## Verdict",
        f"- Verdict: **{summary.verdict}**",
        f"- Reason: {summary.verdict_reason}",
        f"- Blocking reasons: {_reason_list(summary.blocking_reasons)}",
        f"- Warning reasons: {_reason_list(summary.warning_reasons)}",
        "",
        "## Completed-Agent Metrics",
        f"- Completed-agent candidates: {summary.completed_agent_candidate_count}",
        f"- Completed-agent gold relations: {summary.completed_agent_gold_relation_count}",
        f"- Completed-agent precision: {summary.completed_agent_precision_against_gold:.4f}",
        f"- Completed-agent recall: {summary.completed_agent_recall_against_gold:.4f}",
        f"- Completed-agent valuable rate: {summary.completed_agent_valuable_candidate_rate:.4f}",
        "",
        "## All-Candidate Metrics",
        "",
        "These comparison/triage metrics include fallback or comparison candidates "
        "and must not be used as completed-agent quality.",
        "",
        f"- Cases: {summary.case_count}",
        f"- Gold relations: {summary.gold_relation_count}",
        f"- High-value gold relations: {summary.high_value_gold_relation_count}",
        f"- High-value missed gold relations: {summary.high_value_missed_gold_count}",
        f"- High-value recall: {summary.high_value_recall:.4f}",
        f"- Trusted high-value matches: {summary.trusted_high_value_match_count}",
        f"- Trusted high-value recall: {summary.trusted_high_value_recall:.4f}",
        f"- Low-value gold relations: {summary.low_value_gold_relation_count}",
        f"- Low-value missed gold relations: {summary.low_value_missed_gold_count}",
        f"- Low-value recall: {summary.low_value_recall:.4f}",
        f"- Low-value review candidates: {summary.low_value_review_candidate_count}",
        f"- Low-value review gold matches: {summary.low_value_review_gold_match_count}",
        f"- Low-value review recall: {summary.low_value_review_recall:.4f}",
        f"- Extracted candidates: {summary.candidate_count}",
        f"- Agent-completed cases: {summary.agent_completed_case_count}",
        f"- Agent zero-candidate cases: {summary.agent_zero_candidate_case_count}",
        f"- Negative-control cases: {summary.negative_control_case_count}",
        f"- Negative-control empty completions: {summary.negative_control_empty_count}",
        f"- Negative-control empty rate: {summary.negative_control_empty_rate:.4f}",
        f"- Negative-control leakage cases: {summary.negative_control_leakage_count}",
        f"- Fallback/agent-unavailable cases: {summary.fallback_case_count}",
        f"- Fallback candidates: {summary.fallback_candidate_count}",
        f"- Fallback candidates that would look valuable: {summary.fallback_credited_as_agent_count}",
        f"- Invalid strict-agent cases: {summary.invalid_agent_case_count}",
        f"- Precision against gold: {summary.precision_against_gold:.4f}",
        f"- Recall against gold: {summary.recall_against_gold:.4f}",
        f"- Specific subject/object rate: {summary.specificity_rate:.4f}",
        f"- Relation specificity rate: {summary.relation_specificity_rate:.4f}",
        f"- Generic relation rate: {summary.generic_relation_rate:.4f}",
        f"- Pruned generic relation siblings: {summary.pruned_generic_relation_count}",
        f"- Quality-filtered candidates: {summary.quality_filtered_candidate_count}",
        f"- Raw unknown candidate relation types: {summary.raw_unknown_relation_type_count}",
        f"- Raw unknown candidate relation type rate: {summary.raw_unknown_relation_type_rate:.4f}",
        f"- Relation type inventory surfaces: {summary.relation_type_surface_count}",
        f"- Raw unknown inventory relation types: {summary.raw_unknown_relation_type_surface_count}",
        f"- Raw unknown inventory relation type rate: {summary.raw_unknown_relation_type_surface_rate:.4f}",
        f"- Governed relation proposal candidates: {summary.proposal_candidate_count}",
        f"- Governed proposal gold matches: {summary.proposal_gold_match_count}",
        f"- Governed proposal-eligible gold relations: {summary.proposal_eligible_gold_count}",
        f"- Governed proposal recall among proposal-eligible gold: {summary.proposal_recall_against_proposal_eligible_gold:.4f}",
        f"- Governed proposal matches over all gold relations: {summary.proposal_recall_against_gold:.4f}",
        f"- Gold CURIE endpoints: {summary.gold_curie_endpoint_count}",
        f"- Candidate CURIE endpoints: {summary.candidate_curie_endpoint_count}",
        f"- Candidate CURIE present rate: {summary.candidate_curie_present_rate:.4f}",
        f"- Verified CURIE matches: {summary.verified_curie_match_count}",
        f"- Verified CURIE match rate: {summary.verified_curie_match_rate:.4f}",
        f"- Model CURIE wrong count: {summary.model_curie_wrong_count}",
        f"- Wrong verified CURIE links: {summary.wrong_verified_curie_link_count}",
        f"- Verified CURIE-linked gold endpoints: {summary.curie_linked_gold_endpoint_count}",
        f"- Verified CURIE-linked gold endpoint rate: {summary.curie_linked_gold_endpoint_rate:.4f}",
        f"- Valuable candidate rate: {summary.valuable_candidate_rate:.4f}",
        f"- Grounded sentence rate: {summary.grounded_sentence_rate:.4f}",
        f"- Both-arguments-present rate: {summary.both_arguments_present_rate:.4f}",
        f"- Gold support sentence alignment rate: {summary.support_sentence_alignment_rate:.4f}",
        f"- Entailment required candidates: {summary.entailment_required_count}",
        f"- Entailment checked rate: {summary.entailment_checked_rate:.4f}",
        f"- Entailment supported rate: {summary.entailment_supported_rate:.4f}",
        f"- Missed gold relations: {summary.missed_gold_count}",
        "",
        "## Adversarial Checks",
        "",
    ]
    adversarial_findings = find_quality_illusions(report)
    if adversarial_findings:
        for finding in adversarial_findings:
            lines.append(f"- `{finding.code}`: {finding.message}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Case Details",
            "",
        ],
    )
    if not report.case_results:
        lines.append("- No benchmark cases were evaluated.")
        return "\n".join(lines) + "\n"
    for case_result in report.case_results:
        case = case_result.case
        lines.extend(
            [
                f"### {case.case_id}: {case.title}",
                "",
                f"- Category: {case.category}",
                f"- Extractor mode: {case_result.extraction_trace.extractor_mode}",
                f"- LLM status: {case_result.extraction_trace.llm_candidate_status}",
                f"- LLM candidates: {case_result.extraction_trace.llm_candidate_count}",
                f"- Fallback candidates: {case_result.extraction_trace.fallback_candidate_count}",
                f"- Gold relations: {len(case.gold_relations)}",
                f"- Extracted candidates: {len(case_result.candidate_assessments)}",
                f"- Missed gold relations: {len(case_result.missed_gold_indices)}",
                "",
            ],
        )
        if case_result.candidate_assessments:
            lines.append("Extracted candidates:")
            for assessment in case_result.candidate_assessments:
                lines.append(_candidate_line(assessment))
            lines.append("")
        if case_result.relation_type_surfaces:
            lines.append("Relation type inventory surfaces:")
            for surface in case_result.relation_type_surfaces:
                lines.append(
                    f"- `{surface.surface}` -> `{surface.relation_type}` ({surface.source_ref})",
                )
            lines.append("")
        if case_result.missed_gold_indices:
            lines.append("Missed gold relations:")
            for index in case_result.missed_gold_indices:
                gold = case.gold_relations[index]
                lines.append(
                    f"- `{gold.subject} {gold.relation_type} {gold.object}` "
                    f"({gold.value_level}): {gold.rationale}",
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def _candidate_line(assessment: CandidateAssessment) -> str:
    candidate = assessment.candidate
    flags = ", ".join(assessment.quality_flags) or "none"
    value = "valuable" if assessment.is_valuable else "not valuable"
    return (
        f"- `{candidate.subject} {candidate.relation_type} {candidate.object}` "
        f"{_proposal_suffix(candidate)}"
        f"-> {value}; supported={assessment.is_supported_by_gold}; "
        f"gold_sentence={assessment.has_gold_support_sentence}; "
        f"entailment={assessment.support_verification}; flags={flags}"
    )


def _proposal_suffix(candidate: ExtractedRelation) -> str:
    proposed_relation_type = candidate.proposed_relation_type
    if proposed_relation_type is None:
        return ""
    return f" (proposed={proposed_relation_type}) "


def _reason_list(reasons: tuple[str, ...]) -> str:
    if not reasons:
        return "none"
    return " | ".join(reasons)
