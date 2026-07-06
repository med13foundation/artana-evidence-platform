"""Regression tests for relation feasibility repeatability readiness."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.relation_feasibility.readiness import (
    build_readiness_report,
    render_readiness_markdown,
)


def _write_report(
    tmp_path: Path,
    name: str,
    *,
    precision: float = 0.86,
    recall: float = 0.72,
    high_value_recall: float = 0.9,
    valuable_rate: float = 0.84,
    generic_rate: float = 0.0,
    verified_curie_rate: float = 0.96,
    trusted_eligible_curie_rate: float = 0.96,
    weak_claim_trusted_leakage_count: int = 0,
    entailment_checked_rate: float = 1.0,
    fallback_cases: int = 0,
    invalid_agent_cases: int = 0,
    negative_control_leakage_cases: int = 0,
    raw_unknown_candidate_types: int = 0,
    raw_unknown_inventory_types: int = 0,
    wrong_verified_curie_links: int = 0,
    verdict: str = "YELLOW",
    blocking_reasons: list[str] | None = None,
) -> Path:
    path = tmp_path / f"{name}.json"
    payload = {
        "summary": {
            "verdict": verdict,
            "blocking_reasons": blocking_reasons or [],
            "completed_agent_precision_against_gold": precision,
            "completed_agent_recall_against_gold": recall,
            "high_value_recall": high_value_recall,
            "completed_agent_valuable_candidate_rate": valuable_rate,
            "generic_relation_rate": generic_rate,
            "curie_linked_gold_endpoint_rate": verified_curie_rate,
            "trusted_eligible_curie_linked_gold_endpoint_rate": (
                trusted_eligible_curie_rate
            ),
            "verified_curie_match_rate": verified_curie_rate,
            "entailment_checked_rate": entailment_checked_rate,
            "fallback_case_count": fallback_cases,
            "invalid_agent_case_count": invalid_agent_cases,
            "negative_control_leakage_count": negative_control_leakage_cases,
            "raw_unknown_relation_type_count": raw_unknown_candidate_types,
            "raw_unknown_relation_type_surface_count": raw_unknown_inventory_types,
            "wrong_verified_curie_link_count": wrong_verified_curie_links,
            "weak_claim_trusted_leakage_count": weak_claim_trusted_leakage_count,
        },
    }
    path.write_text(json.dumps(payload) + "\n")
    return path


def test_readiness_gate_passes_when_repeated_strict_runs_clear_thresholds(
    tmp_path: Path,
) -> None:
    report_paths = (
        _write_report(tmp_path, "run1", precision=0.86, verified_curie_rate=0.96),
        _write_report(tmp_path, "run2", precision=0.88, verified_curie_rate=0.97),
        _write_report(tmp_path, "run3", precision=0.9, verified_curie_rate=0.98),
    )

    report = build_readiness_report(report_paths=report_paths, min_runs=3)
    markdown = render_readiness_markdown(report)

    assert report["trusted_graph_ready"] is True
    assert report["run_count"] == 3
    assert report["blocking_reasons"] == []
    assert report["worst_metrics"]["completed_agent_precision_against_gold"] == 0.86
    assert report["worst_metrics"]["trusted_eligible_curie_linked_gold_endpoint_rate"] == 0.96
    assert report["hard_failure_counts"]["fallback_case_count"] == 0
    assert "Trusted graph readiness: **READY**" in markdown


def test_readiness_gate_blocks_unstable_or_unsafe_strict_runs(tmp_path: Path) -> None:
    report_paths = (
        _write_report(
            tmp_path,
            "run1",
            precision=0.79,
            verified_curie_rate=0.74,
            trusted_eligible_curie_rate=0.74,
            fallback_cases=1,
        ),
        _write_report(
            tmp_path,
            "run2",
            precision=0.84,
            verified_curie_rate=0.76,
            trusted_eligible_curie_rate=0.76,
            raw_unknown_inventory_types=1,
        ),
    )

    report = build_readiness_report(report_paths=report_paths, min_runs=3)
    markdown = render_readiness_markdown(report)

    assert report["trusted_graph_ready"] is False
    assert report["run_count"] == 2
    assert report["hard_failure_counts"]["fallback_case_count"] == 1
    assert report["hard_failure_counts"]["raw_unknown_relation_type_surface_count"] == 1
    assert any("At least 3 strict live-agent runs" in reason for reason in report["blocking_reasons"])
    assert any("Fallback" in reason for reason in report["blocking_reasons"])
    assert any("precision" in reason for reason in report["blocking_reasons"])
    assert any("CURIE" in reason for reason in report["blocking_reasons"])
    assert "Trusted graph readiness: **NOT READY**" in markdown


def test_readiness_gate_uses_trusted_eligible_endpoint_rate(
    tmp_path: Path,
) -> None:
    report_paths = (
        _write_report(
            tmp_path,
            "run1",
            verified_curie_rate=0.8,
            trusted_eligible_curie_rate=0.96,
        ),
        _write_report(
            tmp_path,
            "run2",
            verified_curie_rate=0.81,
            trusted_eligible_curie_rate=0.97,
        ),
        _write_report(
            tmp_path,
            "run3",
            verified_curie_rate=0.82,
            trusted_eligible_curie_rate=0.98,
        ),
    )

    report = build_readiness_report(report_paths=report_paths, min_runs=3)

    assert report["trusted_graph_ready"] is True
    assert report["worst_metrics"]["curie_linked_gold_endpoint_rate"] == 0.8
    assert report["worst_metrics"]["trusted_eligible_curie_linked_gold_endpoint_rate"] == 0.96


def test_readiness_gate_blocks_weak_claim_trusted_leakage(
    tmp_path: Path,
) -> None:
    report_paths = (
        _write_report(tmp_path, "run1", weak_claim_trusted_leakage_count=1),
        _write_report(tmp_path, "run2"),
        _write_report(tmp_path, "run3"),
    )

    report = build_readiness_report(report_paths=report_paths, min_runs=3)

    assert report["trusted_graph_ready"] is False
    assert report["hard_failure_counts"]["weak_claim_trusted_leakage_count"] == 1
    assert any("Weak low-value claims" in reason for reason in report["blocking_reasons"])


def test_readiness_gate_blocks_missing_or_invalid_required_metrics(
    tmp_path: Path,
) -> None:
    valid_report = _write_report(tmp_path, "valid")
    missing_report = _write_report(tmp_path, "missing")
    invalid_report = _write_report(tmp_path, "invalid")
    missing_payload = json.loads(missing_report.read_text())
    del missing_payload["summary"]["fallback_case_count"]
    missing_report.write_text(json.dumps(missing_payload) + "\n")
    invalid_payload = json.loads(invalid_report.read_text())
    invalid_payload["summary"]["generic_relation_rate"] = "0.00"
    invalid_report.write_text(json.dumps(invalid_payload) + "\n")

    report = build_readiness_report(
        report_paths=(valid_report, missing_report, invalid_report),
        min_runs=3,
    )

    assert report["trusted_graph_ready"] is False
    assert any(
        "missing required metric fallback_case_count" in reason
        for reason in report["blocking_reasons"]
    )
    assert any(
        "invalid required metric generic_relation_rate" in reason
        for reason in report["blocking_reasons"]
    )


def test_readiness_gate_blocks_red_source_audit_verdicts(tmp_path: Path) -> None:
    report_paths = (
        _write_report(tmp_path, "run1"),
        _write_report(
            tmp_path,
            "run2",
            verdict="RED",
            blocking_reasons=["New single-run blocker."],
        ),
        _write_report(tmp_path, "run3"),
    )

    report = build_readiness_report(report_paths=report_paths, min_runs=3)

    assert report["trusted_graph_ready"] is False
    assert report["red_source_report_count"] == 1
    assert any(
        "source audit reports were RED" in reason
        for reason in report["blocking_reasons"]
    )
