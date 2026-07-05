"""Regression tests for relation feasibility failure attribution."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.relation_feasibility.failure_analysis import (
    FailureAnalysisInput,
    build_failure_analysis_report,
)


def _write_report(
    tmp_path: Path,
    name: str,
    *,
    missed: list[dict[str, object]] | None = None,
    assessments: list[dict[str, object]] | None = None,
    summary: dict[str, object] | None = None,
) -> Path:
    path = tmp_path / f"{name}.json"
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
                "case": {"case_id": "case_a"},
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
