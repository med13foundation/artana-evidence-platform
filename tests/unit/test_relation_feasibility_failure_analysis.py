"""Regression tests for relation feasibility failure attribution."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.relation_feasibility.failure_analysis import (
    FailureAnalysisInput,
    build_failure_analysis_report,
    render_failure_analysis_markdown,
)


def _write_report(
    tmp_path: Path,
    name: str,
    *,
    missed: list[dict[str, object]] | None = None,
    assessments: list[dict[str, object]] | None = None,
    gold_relations: list[dict[str, object]] | None = None,
    summary: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / f"{name}.json"
    case: dict[str, object] = {"case_id": "case_a"}
    if gold_relations is not None:
        case["gold_relations"] = gold_relations
    payload = {
        "summary": {
            "verdict": "RED",
            "proposal_candidate_count": 0,
            "proposal_gold_match_count": 0,
            "proposal_eligible_gold_count": 0,
            "proposal_recall_against_proposal_eligible_gold": 0.0,
            **(summary or {}),
        },
        "case_results": [
            {
                "case": case,
                "candidate_assessments": assessments or [],
                "missed_gold_relations": missed or [],
            },
        ],
    }
    path.write_text(json.dumps(payload) + "\n")
    return path


def test_failure_analysis_counts_repeated_high_value_misses(tmp_path: Path) -> None:
    missed_relation = {
        "subject": "MET amplification",
        "relation_type": "CONFERS_RESISTANCE_TO",
        "object": "erlotinib",
        "value_level": "high",
    }
    inputs = tuple(
        FailureAnalysisInput(
            path=_write_report(tmp_path, f"run{index}", missed=[missed_relation]),
            label=f"run{index}",
        )
        for index in range(1, 4)
    )

    report = build_failure_analysis_report(inputs)

    assert report["run_count"] == 3
    assert report["repeated_missed_gold_relations"] == [
        {
            "case_id": "case_a",
            "subject": "MET amplification",
            "relation_type": "CONFERS_RESISTANCE_TO",
            "object": "erlotinib",
            "value_level": "high",
            "occurrence_count": 3,
            "run_labels": ["run1", "run2", "run3"],
        },
    ]


def test_failure_analysis_classifies_model_hint_curie_as_unverified(
    tmp_path: Path,
) -> None:
    assessment = {
        "candidate": {
            "subject": "BRAF V600E",
            "relation_type": "ACTIVATES",
            "object": "MAPK signaling",
            "subject_curie": "ClinVar:BRAF_V600E",
            "object_curie": "GO:0000165",
            "subject_curie_source": "verified_linker",
            "object_curie_source": "model",
        },
        "matched_gold_index": 0,
        "proposal_matched_gold_index": None,
        "is_supported_by_gold": True,
        "has_verified_subject_curie": True,
        "has_verified_object_curie": False,
        "subject_curie_matches_gold": True,
        "object_curie_matches_gold": False,
    }
    report_path = _write_report(tmp_path, "run1", assessments=[assessment])

    report = build_failure_analysis_report(
        (FailureAnalysisInput(path=report_path, label="run1"),),
    )

    assert report["curie_gaps"] == [
        {
            "case_id": "case_a",
            "endpoint_role": "object",
            "label": "MAPK signaling",
            "candidate_curie": "GO:0000165",
            "candidate_curie_source": "model",
            "gap_type": "unverified_model_hint",
            "occurrence_count": 1,
            "run_labels": ["run1"],
        },
    ]


def test_failure_analysis_reports_curie_endpoints_lost_to_missed_gold(
    tmp_path: Path,
) -> None:
    missed_relation = {
        "subject": "MED13",
        "relation_type": "ASSOCIATED_WITH",
        "object": "congenital heart disease",
        "value_level": "low",
        "subject_curie": "HGNC:22474",
        "object_curie": "MONDO:0005267",
    }
    report_path = _write_report(tmp_path, "run1", missed=[missed_relation])

    report = build_failure_analysis_report(
        (FailureAnalysisInput(path=report_path, label="run1"),),
    )

    assert report["missed_gold_curie_endpoints"] == [
        {
            "case_id": "case_a",
            "endpoint_role": "subject",
            "label": "MED13",
            "gold_curie": "HGNC:22474",
            "value_level": "low",
            "occurrence_count": 1,
            "run_labels": ["run1"],
        },
        {
            "case_id": "case_a",
            "endpoint_role": "object",
            "label": "congenital heart disease",
            "gold_curie": "MONDO:0005267",
            "value_level": "low",
            "occurrence_count": 1,
            "run_labels": ["run1"],
        },
    ]


def test_failure_analysis_keeps_governed_proposal_capture_separate_from_trust(
    tmp_path: Path,
) -> None:
    assessment = {
        "candidate": {
            "subject": "MET amplification",
            "relation_type": "PROPOSE_NEW_RELATION_TYPE",
            "proposed_relation_type": "CONFERS_RESISTANCE_TO",
            "object": "erlotinib",
            "subject_curie_source": "verified_linker",
            "object_curie_source": "verified_linker",
            "trusted_evidence_eligible": False,
        },
        "matched_gold_index": None,
        "proposal_matched_gold_index": 0,
        "is_supported_by_gold": False,
        "is_governed_relation_proposal": True,
        "is_trusted_evidence_eligible": False,
        "support_verification": "NEUTRAL",
    }
    report_path = _write_report(
        tmp_path,
        "run1",
        assessments=[assessment],
        summary={
            "proposal_candidate_count": 1,
            "proposal_gold_match_count": 1,
            "proposal_eligible_gold_count": 2,
            "proposal_recall_against_proposal_eligible_gold": 0.5,
        },
    )

    report = build_failure_analysis_report(
        (FailureAnalysisInput(path=report_path, label="run1"),),
    )

    assert report["proposal_capture"] == {
        "proposal_candidate_count": 1,
        "proposal_gold_match_count": 1,
        "proposal_eligible_gold_count": 2,
        "proposal_recall_against_proposal_eligible_gold": 0.5,
        "trusted_proposal_capture_count": 0,
    }
    assert report["governed_proposal_captures"] == [
        {
            "case_id": "case_a",
            "subject": "MET amplification",
            "proposed_relation_type": "CONFERS_RESISTANCE_TO",
            "object": "erlotinib",
            "trusted_evidence_eligible": False,
            "support_verification": "NEUTRAL",
            "run_labels": ["run1"],
            "occurrence_count": 1,
        },
    ]
    assert report["repeated_false_positive_candidates"] == []


def test_failure_analysis_does_not_call_verified_proposal_links_wrong(
    tmp_path: Path,
) -> None:
    assessment = {
        "candidate": {
            "subject": "MET amplification",
            "relation_type": "PROPOSE_NEW_RELATION_TYPE",
            "proposed_relation_type": "CONFERS_RESISTANCE_TO",
            "object": "erlotinib",
            "subject_curie": "HGNC:7029",
            "object_curie": "DrugBank:DB00530",
            "subject_curie_source": "verified_linker",
            "object_curie_source": "verified_linker",
            "trusted_evidence_eligible": False,
        },
        "matched_gold_index": None,
        "proposal_matched_gold_index": 0,
        "is_supported_by_gold": False,
        "is_governed_relation_proposal": True,
        "is_trusted_evidence_eligible": False,
        "has_verified_subject_curie": True,
        "has_verified_object_curie": True,
        "subject_curie_matches_gold": False,
        "object_curie_matches_gold": False,
        "support_verification": "NEUTRAL",
    }
    report_path = _write_report(tmp_path, "run1", assessments=[assessment])

    report = build_failure_analysis_report(
        (FailureAnalysisInput(path=report_path, label="run1"),),
    )

    assert report["curie_gaps"] == []


def test_failure_analysis_skips_curie_gap_when_gold_endpoint_has_no_curie(
    tmp_path: Path,
) -> None:
    assessment = {
        "candidate": {
            "subject": "MET amplification",
            "relation_type": "CONFERS_RESISTANCE_TO",
            "object": "erlotinib",
            "subject_curie": "HGNC:7029",
            "object_curie": "DrugBank:DB00530",
            "subject_curie_source": "verified_linker",
            "object_curie_source": "verified_linker",
        },
        "matched_gold_index": 0,
        "is_supported_by_gold": True,
        "has_verified_subject_curie": True,
        "has_verified_object_curie": True,
        "subject_curie_matches_gold": True,
        "object_curie_matches_gold": False,
    }
    report_path = _write_report(
        tmp_path,
        "run1",
        assessments=[assessment],
        gold_relations=[
            {
                "subject_curie": "HGNC:7029",
                "object_curie": None,
            },
        ],
    )

    report = build_failure_analysis_report(
        (FailureAnalysisInput(path=report_path, label="run1"),),
    )

    assert report["curie_gaps"] == []


def test_failure_analysis_model_comparison_includes_trust_lane_metrics(
    tmp_path: Path,
) -> None:
    current_report = _write_report(
        tmp_path,
        "current",
        summary={
            "model_label": "current",
            "trusted_candidate_precision_against_gold": 0.86,
            "completed_agent_precision_against_gold": 0.86,
            "trusted_eligible_high_value_recall": 0.86,
            "trusted_high_value_recall": 0.85,
            "low_value_review_recall": 0.8,
            "low_value_review_curie_endpoint_capture_rate": 0.6,
            "trusted_candidate_valuable_rate": 0.84,
            "trusted_candidate_generic_relation_rate": 0.0,
            "trusted_eligible_curie_linked_gold_endpoint_rate": 0.96,
            "entailment_checked_rate": 1.0,
            "fallback_case_count": 0,
            "wrong_verified_curie_link_count": 0,
        },
    )
    candidate_report = _write_report(
        tmp_path,
        "candidate",
        summary={
            "model_label": "candidate",
            "trusted_candidate_precision_against_gold": 0.91,
            "completed_agent_precision_against_gold": 0.9,
            "trusted_eligible_high_value_recall": 0.92,
            "trusted_high_value_recall": 0.9,
            "low_value_review_recall": 1.0,
            "low_value_review_curie_endpoint_capture_rate": 0.8,
            "trusted_candidate_valuable_rate": 0.95,
            "trusted_candidate_generic_relation_rate": 0.0,
            "trusted_eligible_curie_linked_gold_endpoint_rate": 0.98,
            "entailment_checked_rate": 1.0,
            "fallback_case_count": 0,
            "wrong_verified_curie_link_count": 0,
        },
    )

    report = build_failure_analysis_report(
        (
            FailureAnalysisInput(path=current_report, label="run1"),
            FailureAnalysisInput(path=candidate_report, label="run1"),
        ),
    )

    rows = {
        str(row["model_label"]): row
        for row in report["model_comparison"]
        if isinstance(row, dict)
    }
    candidate = rows["candidate"]
    assert candidate["worst_trusted_candidate_precision_against_gold"] == 0.91
    assert candidate["worst_trusted_eligible_high_value_recall"] == 0.92
    assert candidate["worst_trusted_high_value_recall"] == 0.9
    assert candidate["worst_low_value_review_recall"] == 1.0
    assert candidate["worst_low_value_review_curie_endpoint_capture_rate"] == 0.8
    assert candidate["worst_trusted_candidate_valuable_rate"] == 0.95
    assert candidate["worst_trusted_candidate_generic_relation_rate"] == 0.0
    assert candidate["worst_trusted_eligible_curie_linked_gold_endpoint_rate"] == 0.98
    assert candidate["worst_entailment_checked_rate"] == 1.0
    assert candidate["total_fallback_case_count"] == 0
    assert candidate["total_wrong_verified_curie_link_count"] == 0


def test_failure_analysis_uses_maximum_trusted_generic_rate_for_worst_run(
    tmp_path: Path,
) -> None:
    first_report = _write_report(
        tmp_path,
        "candidate-low-generic",
        summary={
            "model_label": "candidate",
            "trusted_candidate_generic_relation_rate": 0.02,
        },
    )
    second_report = _write_report(
        tmp_path,
        "candidate-high-generic",
        summary={
            "model_label": "candidate",
            "trusted_candidate_generic_relation_rate": 0.4,
        },
    )

    report = build_failure_analysis_report(
        (
            FailureAnalysisInput(path=first_report, label="run1"),
            FailureAnalysisInput(path=second_report, label="run2"),
        ),
    )

    candidate = report["model_comparison"][0]
    assert candidate["worst_trusted_candidate_generic_relation_rate"] == 0.4


def test_failure_analysis_reports_review_only_grounding_decision(
    tmp_path: Path,
) -> None:
    assessment = {
        "candidate": {
            "subject": "IL6",
            "relation_type": "REGULATES",
            "object": "inflammatory signaling",
            "subject_curie": "HGNC:6018",
            "object_curie": "GO:0002526",
            "subject_curie_source": "verified_linker",
            "object_curie_source": "model",
        },
        "matched_gold_index": 0,
        "proposal_matched_gold_index": None,
        "is_supported_by_gold": True,
        "has_verified_subject_curie": True,
        "has_verified_object_curie": False,
        "subject_curie_matches_gold": True,
        "object_curie_matches_gold": False,
    }
    report_path = _write_report(tmp_path, "run1", assessments=[assessment])

    report = build_failure_analysis_report(
        (FailureAnalysisInput(path=report_path, label="run1"),),
    )

    assert report["curie_gaps"] == [
        {
            "case_id": "case_a",
            "endpoint_role": "object",
            "label": "inflammatory signaling",
            "candidate_curie": "GO:0002526",
            "candidate_curie_source": "model",
            "gap_type": "review_only_endpoint",
            "grounding_curation_status": "review_only_for_relation_feasibility_v2",
            "grounding_reason_code": "broad_process_label",
            "trusted_identifier_allowed": False,
            "occurrence_count": 1,
            "run_labels": ["run1"],
        },
    ]
    markdown = render_failure_analysis_markdown(report)
    assert "grounding_reason_code" in markdown
    assert "broad_process_label" in markdown
