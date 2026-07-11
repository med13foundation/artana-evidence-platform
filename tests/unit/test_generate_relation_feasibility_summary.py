from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_relation_feasibility_summary import (
    GenerateSummaryInput,
    generate_summary_markdown,
    write_generated_summary,
)


def test_generated_summary_includes_run_context_hashes_and_blockers(
    tmp_path: Path,
) -> None:
    relation_report = tmp_path / "relation_feasibility_report.json"
    relation_report.write_text(
        json.dumps(
            {
                "summary": {
                    "verdict": "RED",
                    "blocking_reasons": ["fallback_case_count > 0"],
                    "warning_reasons": ["generic relation rate high"],
                    "case_count": 3,
                    "gold_relation_count": 2,
                    "completed_agent_precision_against_gold": 0.75,
                    "completed_agent_recall_against_gold": 0.5,
                    "high_value_recall": 0.5,
                    "low_value_review_recall": 1.0,
                    "trusted_eligible_curie_linked_gold_endpoint_rate": 0.5,
                    "completed_agent_valuable_candidate_rate": 0.4,
                    "generic_relation_rate": 0.2,
                    "model_curie_wrong_count": 2,
                    "raw_unknown_relation_type_count": 0,
                    "raw_unknown_relation_type_surface_count": 0,
                    "fallback_case_count": 1,
                    "invalid_agent_case_count": 0,
                    "negative_control_leakage_count": 0,
                    "weak_claim_trusted_leakage_count": 0,
                    "wrong_verified_curie_link_count": 0,
                },
                "case_results": [
                    {
                        "case": {"case_id": "missed_case"},
                        "missed_gold_relations": [
                            {
                                "subject": "MED13",
                                "relation_type": "ASSOCIATED_WITH",
                                "object": "developmental delay",
                            },
                        ],
                    },
                ],
            },
        )
        + "\n",
    )
    failure_report = tmp_path / "relation_feasibility_failure_analysis_report.json"
    failure_report.write_text(
        json.dumps(
            {
                "repeated_missed_gold_relations": [
                    {
                        "case_id": "missed_case",
                        "subject": "MED13",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "developmental delay",
                        "count": 2,
                    },
                ],
                "repeated_false_positive_candidates": [],
            },
        )
        + "\n",
    )
    readiness_report = tmp_path / "relation_feasibility_readiness_report.json"
    readiness_report.write_text(
        json.dumps(
            {
                "readiness_status": "not_ready",
                "blocking_reasons": ["Minimum run count not met."],
                "hard_failure_counts": {"fallback_case_count": 1},
                "worst_metrics": {
                    "completed_agent_precision_against_gold": 0.75,
                },
            },
        )
        + "\n",
    )

    markdown = generate_summary_markdown(
        GenerateSummaryInput(
            relation_report=relation_report,
            failure_analysis_report=failure_report,
            readiness_report=readiness_report,
            branch="alvaro/evidence-pr27-benchmark-v3-doc-proof",
            commit="abc1234",
            command="scripts/run_relation_feasibility_audit.py --extractor agent",
            model_label="current",
            fixture_path=Path(
                "scripts/validation/relation_feasibility/fixtures/"
                "biomedical_relation_goldset_v3.json",
            ),
        ),
    )

    assert "# Relation Feasibility Generated Summary" in markdown
    assert "- Branch: `alvaro/evidence-pr27-benchmark-v3-doc-proof`" in markdown
    assert "- Commit: `abc1234`" in markdown
    assert "- Model label: `current`" in markdown
    assert "biomedical_relation_goldset_v3.json" in markdown
    assert "relation_feasibility_report.json`:" in markdown
    assert "fallback_case_count > 0" in markdown
    assert "generic relation rate high" in markdown
    assert "Minimum run count not met." in markdown
    assert "completed_agent_precision_against_gold: 0.75" in markdown
    assert "completed_agent_valuable_candidate_rate: 0.4" in markdown
    assert "model_curie_wrong_count: 2" in markdown
    assert "wrong_verified_curie_link_count: 0" in markdown
    assert "MED13 ASSOCIATED_WITH developmental delay" in markdown


def test_generated_summary_renders_curie_gap_endpoint_rows(tmp_path: Path) -> None:
    relation_report = tmp_path / "relation_feasibility_report.json"
    relation_report.write_text(
        json.dumps({"summary": {"verdict": "RED"}}) + "\n",
        encoding="utf-8",
    )
    failure_report = tmp_path / "relation_feasibility_failure_analysis_report.json"
    failure_report.write_text(
        json.dumps(
            {
                "curie_gaps": [
                    {
                        "case_id": "gap_case",
                        "gap_type": "missing_curie",
                        "endpoint_role": "object",
                        "label": "EGFR exon 19 deletion lung adenocarcinoma",
                        "gold_curie": "MONDO:0005061",
                    },
                    {
                        "case_id": "hint_case",
                        "gap_type": "unverified_model_hint",
                        "endpoint_role": "subject",
                        "label": "Alectinib",
                        "candidate_curie": "CHEBI:71267",
                        "candidate_curie_source": "model",
                    },
                ],
            },
        )
        + "\n",
        encoding="utf-8",
    )

    markdown = generate_summary_markdown(
        GenerateSummaryInput(
            relation_report=relation_report,
            failure_analysis_report=failure_report,
            branch="branch",
            commit="commit",
            command="command",
            model_label="model",
            fixture_path=Path("fixture.json"),
        ),
    )

    assert (
        "curie_gaps: gap_case: missing_curie object "
        "EGFR exon 19 deletion lung adenocarcinoma -> MONDO:0005061"
    ) in markdown
    assert (
        "curie_gaps: hint_case: unverified_model_hint subject "
        "Alectinib -> CHEBI:71267 (model)"
    ) in markdown
    assert "unknown_subject unknown_relation unknown_object" not in markdown


def test_write_generated_summary_creates_markdown_file(tmp_path: Path) -> None:
    relation_report = tmp_path / "relation.json"
    relation_report.write_text(json.dumps({"summary": {"verdict": "GREEN"}}) + "\n")
    output = tmp_path / "summary.md"

    written = write_generated_summary(
        GenerateSummaryInput(
            relation_report=relation_report,
            output_path=output,
            branch="branch",
            commit="commit",
            command="command",
            model_label="model",
            fixture_path=Path("fixture.json"),
        ),
    )

    assert written == output
    assert output.exists()
    assert "- Verdict: `GREEN`" in output.read_text(encoding="utf-8")


def test_pr27_committed_generated_summaries_are_reproducible() -> None:
    reports_dir = Path("docs/validation/reports")
    cases = (
        (
            "2026-07-06-pr27-v2-relation-feasibility-report.json",
            None,
            "2026-07-06-pr27-v2-generated-summary.md",
            (
                "scripts/run_relation_feasibility_audit.py --extractor agent "
                "--cases scripts/validation/relation_feasibility/fixtures/"
                "biomedical_relation_goldset_v2.json --output-dir "
                "reports/relation_feasibility/2026-07-06-pr27-v2-run1"
            ),
            "scripts/validation/relation_feasibility/fixtures/"
            "biomedical_relation_goldset_v2.json",
        ),
        (
            "2026-07-06-pr27-v3-relation-feasibility-report.json",
            "2026-07-06-pr27-v3-failure-analysis-report.json",
            "2026-07-06-pr27-v3-generated-summary.md",
                (
                    "scripts/run_relation_feasibility_audit.py --extractor agent "
                    "--cases scripts/validation/relation_feasibility/fixtures/"
                    "biomedical_relation_goldset_v3.json --output-dir "
                    "reports/relation_feasibility/2026-07-06-pr27-v3-run2"
                ),
            "scripts/validation/relation_feasibility/fixtures/"
            "biomedical_relation_goldset_v3.json",
        ),
    )

    for report_name, failure_name, summary_name, command, fixture_path in cases:
        relation_report = reports_dir / report_name
        failure_report = reports_dir / failure_name if failure_name is not None else None
        generated = generate_summary_markdown(
            GenerateSummaryInput(
                relation_report=relation_report,
                failure_analysis_report=failure_report,
                branch="alvaro/evidence-pr27-benchmark-v3-doc-proof",
                commit="6e67477+pr27-working-tree",
                command=command,
                model_label="current-agent",
                fixture_path=Path(fixture_path),
            ),
        )

        assert generated == (reports_dir / summary_name).read_text(encoding="utf-8")
