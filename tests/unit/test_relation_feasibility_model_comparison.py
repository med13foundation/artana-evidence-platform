"""Regression tests for relation feasibility model comparison."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

import scripts.run_relation_model_comparison as comparison_script
from scripts.run_relation_model_comparison import main as comparison_main
from scripts.validation.relation_feasibility.model_comparison import (
    build_model_comparison_report,
    compare_model_reports,
    render_model_comparison_markdown,
    write_model_comparison_report,
)


def _write_report(
    tmp_path: Path,
    name: str,
    *,
    model_label: str,
    precision: float = 0.86,
    recall: float = 0.72,
    high_value_recall: float = 0.9,
    trusted_high_value_recall: float = 0.85,
    valuable_rate: float = 0.84,
    generic_rate: float = 0.0,
    trusted_precision: float | None = None,
    trusted_eligible_high_value_recall: float | None = None,
    trusted_valuable_rate: float | None = None,
    trusted_generic_rate: float | None = None,
    trusted_endpoint_rate: float = 0.96,
    verified_curie_rate: float = 0.96,
    trusted_candidate_score_calibration_sample_count: int = 10,
    candidate_score_calibration_sample_count: int = 20,
    trusted_candidate_score_ece: float = 0.0,
    candidate_score_ece: float = 0.0,
    entailment_checked_rate: float = 1.0,
    fallback_cases: int = 0,
    invalid_agent_cases: int = 0,
    negative_control_leakage_cases: int = 0,
    raw_unknown_candidate_types: int = 0,
    raw_unknown_inventory_types: int = 0,
    wrong_verified_curie_links: int = 0,
    weak_claim_trusted_leakage_count: int = 0,
    review_only_gold_trusted_leakage_count: int = 0,
    verdict: str = "YELLOW",
) -> Path:
    path = tmp_path / f"{name}.json"
    payload = {
        "summary": {
            "model_label": model_label,
            "verdict": verdict,
            "blocking_reasons": [],
            "trusted_candidate_precision_against_gold": (
                precision if trusted_precision is None else trusted_precision
            ),
            "completed_agent_precision_against_gold": precision,
            "completed_agent_recall_against_gold": recall,
            "trusted_eligible_high_value_recall": (
                trusted_high_value_recall
                if trusted_eligible_high_value_recall is None
                else trusted_eligible_high_value_recall
            ),
            "high_value_recall": high_value_recall,
            "trusted_high_value_recall": trusted_high_value_recall,
            "trusted_candidate_valuable_rate": (
                valuable_rate if trusted_valuable_rate is None else trusted_valuable_rate
            ),
            "completed_agent_valuable_candidate_rate": valuable_rate,
            "trusted_candidate_generic_relation_rate": (
                generic_rate if trusted_generic_rate is None else trusted_generic_rate
            ),
            "generic_relation_rate": generic_rate,
            "curie_linked_gold_endpoint_rate": verified_curie_rate,
            "trusted_eligible_curie_linked_gold_endpoint_rate": (
                trusted_endpoint_rate
            ),
            "verified_curie_match_rate": verified_curie_rate,
            "trusted_candidate_score_calibration_sample_count": (
                trusted_candidate_score_calibration_sample_count
            ),
            "candidate_score_calibration_sample_count": (
                candidate_score_calibration_sample_count
            ),
            "trusted_candidate_score_ece": trusted_candidate_score_ece,
            "candidate_score_ece": candidate_score_ece,
            "entailment_checked_rate": entailment_checked_rate,
            "fallback_case_count": fallback_cases,
            "invalid_agent_case_count": invalid_agent_cases,
            "negative_control_leakage_count": negative_control_leakage_cases,
            "raw_unknown_relation_type_count": raw_unknown_candidate_types,
            "raw_unknown_relation_type_surface_count": raw_unknown_inventory_types,
            "wrong_verified_curie_link_count": wrong_verified_curie_links,
            "weak_claim_trusted_leakage_count": weak_claim_trusted_leakage_count,
            "review_only_gold_trusted_leakage_count": (
                review_only_gold_trusted_leakage_count
            ),
        },
    }
    path.write_text(json.dumps(payload) + "\n")
    return path


def test_model_comparison_adopts_candidate_when_worst_run_readiness_improves(
    tmp_path: Path,
) -> None:
    current_reports = (
        _write_report(
            tmp_path,
            "current1",
            model_label="current",
            precision=0.86,
            trusted_candidate_score_ece=0.03,
        ),
        _write_report(
            tmp_path,
            "current2",
            model_label="current",
            precision=0.88,
            trusted_candidate_score_ece=0.03,
        ),
        _write_report(
            tmp_path,
            "current3",
            model_label="current",
            precision=0.9,
            trusted_candidate_score_ece=0.03,
        ),
    )
    candidate_reports = (
        _write_report(
            tmp_path,
            "candidate1",
            model_label="candidate",
            precision=0.9,
            trusted_endpoint_rate=0.98,
            trusted_candidate_score_ece=0.01,
        ),
        _write_report(
            tmp_path,
            "candidate2",
            model_label="candidate",
            precision=0.91,
            trusted_endpoint_rate=0.99,
            trusted_candidate_score_ece=0.01,
        ),
        _write_report(
            tmp_path,
            "candidate3",
            model_label="candidate",
            precision=0.92,
            trusted_endpoint_rate=0.99,
            trusted_candidate_score_ece=0.01,
        ),
    )

    decision = compare_model_reports(
        current_model_label="current",
        candidate_model_label="candidate",
        current_report_paths=current_reports,
        candidate_report_paths=candidate_reports,
    )
    report = build_model_comparison_report(
        current_model_label="current",
        candidate_model_label="candidate",
        current_report_paths=current_reports,
        candidate_report_paths=candidate_reports,
    )
    markdown = render_model_comparison_markdown(report)

    assert decision.adopted_model_label == "candidate"
    assert decision.blocking_reasons == ()
    assert decision.safety_failures == ()
    assert decision.metric_deltas[
        "worst_completed_agent_precision_against_gold"
    ] == pytest.approx(0.04)
    assert decision.metric_deltas[
        "worst_trusted_eligible_curie_linked_gold_endpoint_rate"
    ] == pytest.approx(0.02)
    assert decision.metric_deltas["worst_trusted_candidate_score_ece"] == pytest.approx(
        -0.02,
    )
    assert report["decision"]["adopted_model_label"] == "candidate"
    assert report["candidate_readiness"]["readiness_status"] == "ready"
    assert "Decision: **ADOPT_CANDIDATE**" in markdown


def test_model_comparison_blocks_candidate_safety_failures(
    tmp_path: Path,
) -> None:
    current_reports = tuple(
        _write_report(tmp_path, f"current{index}", model_label="current")
        for index in range(1, 4)
    )
    candidate_reports = (
        _write_report(
            tmp_path,
            "candidate1",
            model_label="candidate",
            wrong_verified_curie_links=1,
        ),
        _write_report(tmp_path, "candidate2", model_label="candidate"),
        _write_report(tmp_path, "candidate3", model_label="candidate"),
    )

    decision = compare_model_reports(
        current_model_label="current",
        candidate_model_label="candidate",
        current_report_paths=current_reports,
        candidate_report_paths=candidate_reports,
    )

    assert decision.adopted_model_label is None
    assert "candidate wrong_verified_curie_link_count=1" in decision.safety_failures
    assert any("safety failures" in reason for reason in decision.blocking_reasons)


def test_model_comparison_blocks_endpoint_regression_even_when_candidate_ready(
    tmp_path: Path,
) -> None:
    current_reports = tuple(
        _write_report(
            tmp_path,
            f"current{index}",
            model_label="current",
            trusted_endpoint_rate=0.99,
        )
        for index in range(1, 4)
    )
    candidate_reports = tuple(
        _write_report(
            tmp_path,
            f"candidate{index}",
            model_label="candidate",
            trusted_endpoint_rate=0.96,
        )
        for index in range(1, 4)
    )

    decision = compare_model_reports(
        current_model_label="current",
        candidate_model_label="candidate",
        current_report_paths=current_reports,
        candidate_report_paths=candidate_reports,
    )

    assert decision.adopted_model_label is None
    assert any(
        "trusted-eligible endpoint recovery regressed" in reason
        for reason in decision.blocking_reasons
    )


def test_model_comparison_uses_worst_run_not_average(tmp_path: Path) -> None:
    current_reports = tuple(
        _write_report(tmp_path, f"current{index}", model_label="current")
        for index in range(1, 4)
    )
    candidate_reports = (
        _write_report(tmp_path, "candidate1", model_label="candidate", precision=0.95),
        _write_report(tmp_path, "candidate2", model_label="candidate", precision=0.95),
        _write_report(tmp_path, "candidate3", model_label="candidate", precision=0.79),
    )

    decision = compare_model_reports(
        current_model_label="current",
        candidate_model_label="candidate",
        current_report_paths=current_reports,
        candidate_report_paths=candidate_reports,
    )

    assert decision.adopted_model_label is None
    assert any(
        "candidate readiness gate is not ready" in reason
        for reason in decision.blocking_reasons
    )


def test_model_comparison_requires_distinct_model_labels(tmp_path: Path) -> None:
    report_paths = tuple(
        _write_report(tmp_path, f"run{index}", model_label="current")
        for index in range(1, 4)
    )

    with pytest.raises(ValueError, match="distinct model labels"):
        compare_model_reports(
            current_model_label="current",
            candidate_model_label="current",
            current_report_paths=report_paths,
            candidate_report_paths=report_paths,
        )

    with pytest.raises(ValueError, match="current model label is required"):
        compare_model_reports(
            current_model_label="",
            candidate_model_label="candidate",
            current_report_paths=report_paths,
            candidate_report_paths=report_paths,
        )


def test_model_comparison_writes_json_and_markdown(tmp_path: Path) -> None:
    current_reports = tuple(
        _write_report(tmp_path, f"current{index}", model_label="current")
        for index in range(1, 4)
    )
    candidate_reports = tuple(
        _write_report(tmp_path, f"candidate{index}", model_label="candidate")
        for index in range(1, 4)
    )
    report = build_model_comparison_report(
        current_model_label="current",
        candidate_model_label="candidate",
        current_report_paths=current_reports,
        candidate_report_paths=candidate_reports,
    )

    manifest = write_model_comparison_report(report=report, output_dir=tmp_path / "out")

    assert Path(str(manifest["json_path"])).exists()
    assert Path(str(manifest["markdown_path"])).exists()
    assert Path(str(manifest["json_path"])).name == (
        "relation_model_comparison_report.json"
    )
    assert Path(str(manifest["markdown_path"])).name == (
        "relation_model_comparison_report.md"
    )


def test_model_comparison_cli_writes_artifacts_from_repeated_reports(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current_reports = tuple(
        _write_report(tmp_path, f"current{index}", model_label="current")
        for index in range(1, 4)
    )
    candidate_reports = tuple(
        _write_report(
            tmp_path,
            f"candidate{index}",
            model_label="candidate",
            precision=0.9,
            trusted_endpoint_rate=0.98,
        )
        for index in range(1, 4)
    )
    output_dir = tmp_path / "comparison"

    exit_code = comparison_main(
        [
            "--current-model-label",
            "current",
            "--candidate-model-label",
            "candidate",
            "--runs-per-model",
            "3",
            "--output-dir",
            str(output_dir),
            *[
                item
                for report_path in current_reports
                for item in ("--current-report", str(report_path))
            ],
            *[
                item
                for report_path in candidate_reports
                for item in ("--candidate-report", str(report_path))
            ],
        ],
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "relation_model_comparison decision=adopt_candidate" in output
    assert (output_dir / "relation_model_comparison_report.json").exists()
    assert (output_dir / "relation_model_comparison_report.md").exists()


def test_model_comparison_cli_refuses_incomplete_run_groups(tmp_path: Path) -> None:
    current_reports = tuple(
        _write_report(tmp_path, f"current{index}", model_label="current")
        for index in range(1, 4)
    )
    candidate_reports = tuple(
        _write_report(tmp_path, f"candidate{index}", model_label="candidate")
        for index in range(1, 3)
    )

    with pytest.raises(SystemExit, match="candidate report count"):
        comparison_main(
            [
                "--current-model-label",
                "current",
                "--candidate-model-label",
                "candidate",
                "--runs-per-model",
                "3",
                *[
                    item
                    for report_path in current_reports
                    for item in ("--current-report", str(report_path))
                ],
                *[
                    item
                    for report_path in candidate_reports
                    for item in ("--candidate-report", str(report_path))
                ],
            ],
        )


def test_model_comparison_cli_refuses_run_mode_without_candidate_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARTANA_STRONGER_MODEL_CANDIDATE", raising=False)

    with pytest.raises(SystemExit, match="ARTANA_STRONGER_MODEL_CANDIDATE"):
        comparison_main(
            [
                "--current-model-label",
                "current",
                "--candidate-model-label",
                "candidate",
                "--runs-per-model",
                "3",
                "--run-audits",
                "--output-dir",
                str(tmp_path / "comparison"),
            ],
        )


def test_model_comparison_cli_orchestrates_repeated_audit_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_calls: list[tuple[Path, str | None]] = []
    monkeypatch.setenv("ARTANA_STRONGER_MODEL_CANDIDATE", "openai:gpt-5.5")

    def _fake_run_audit(*, output_dir: Path, env: Mapping[str, str]) -> None:
        run_calls.append(
            (
                output_dir.relative_to(tmp_path / "comparison"),
                env.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL"),
            ),
        )
        _write_report(
            output_dir,
            "relation_feasibility_report",
            model_label="candidate"
            if env.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL") == "openai:gpt-5.5"
            else "current",
        )

    monkeypatch.setattr(comparison_script, "_run_single_audit", _fake_run_audit)
    output_dir = tmp_path / "comparison"
    original_model = os.environ.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL")

    exit_code = comparison_main(
        [
            "--current-model-label",
            "current",
            "--candidate-model-label",
            "candidate",
            "--runs-per-model",
            "3",
            "--run-audits",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert exit_code == 0
    assert os.environ.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL") == original_model
    assert run_calls == [
        (Path("runs/current/run1"), original_model),
        (Path("runs/current/run2"), original_model),
        (Path("runs/current/run3"), original_model),
        (Path("runs/candidate/run1"), "openai:gpt-5.5"),
        (Path("runs/candidate/run2"), "openai:gpt-5.5"),
        (Path("runs/candidate/run3"), "openai:gpt-5.5"),
    ]
    assert (output_dir / "relation_model_comparison_report.json").exists()


def test_model_comparison_cli_passes_cases_to_repeated_audit_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_cases: list[Path | None] = []
    cases_path = tmp_path / "benchmark_v3.json"
    cases_path.write_text("[]\n")
    monkeypatch.setenv("ARTANA_STRONGER_MODEL_CANDIDATE", "openai:gpt-5.5")

    def _fake_run_audit(
        *,
        output_dir: Path,
        env: Mapping[str, str],
        cases_path: Path | None = None,
    ) -> None:
        run_cases.append(cases_path)
        _write_report(
            output_dir,
            "relation_feasibility_report",
            model_label="candidate"
            if env.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL") == "openai:gpt-5.5"
            else "current",
        )

    monkeypatch.setattr(comparison_script, "_run_single_audit", _fake_run_audit)

    exit_code = comparison_main(
        [
            "--current-model-label",
            "current",
            "--candidate-model-label",
            "candidate",
            "--runs-per-model",
            "3",
            "--run-audits",
            "--cases",
            str(cases_path),
            "--output-dir",
            str(tmp_path / "comparison"),
        ],
    )

    assert exit_code == 0
    assert run_cases == [cases_path] * 6


def test_model_comparison_cli_writes_fail_closed_report_for_failed_candidate_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_STRONGER_MODEL_CANDIDATE", "openai:gpt-5.5")

    def _fake_run_audit(*, output_dir: Path, env: Mapping[str, str]) -> None:
        relative_output = output_dir.relative_to(tmp_path / "comparison")
        if relative_output == Path("runs/candidate/run2"):
            raise subprocess.CalledProcessError(
                returncode=2,
                cmd=("run_relation_feasibility_audit.py", "--extractor", "agent"),
            )
        _write_report(
            output_dir,
            "relation_feasibility_report",
            model_label="candidate"
            if env.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL") == "openai:gpt-5.5"
            else "current",
        )

    monkeypatch.setattr(comparison_script, "_run_single_audit", _fake_run_audit)
    output_dir = tmp_path / "comparison"

    exit_code = comparison_main(
        [
            "--current-model-label",
            "current",
            "--candidate-model-label",
            "candidate",
            "--runs-per-model",
            "3",
            "--run-audits",
            "--output-dir",
            str(output_dir),
        ],
    )

    report = json.loads(
        (output_dir / "relation_model_comparison_report.json").read_text(),
    )
    markdown = (output_dir / "relation_model_comparison_report.md").read_text()

    assert exit_code == 0
    assert report["decision"]["adopted_model_label"] is None
    assert "candidate audit run failed." in report["decision"]["blocking_reasons"]
    assert report["audit_failures"] == [
        {
            "model_label": "candidate",
            "run_index": 2,
            "exit_code": 2,
            "command": "run_relation_feasibility_audit.py --extractor agent",
        },
    ]
    assert "## Audit Failures" in markdown
    assert "- candidate run2 exited 2" in markdown


def test_model_comparison_cli_writes_fail_closed_report_for_failed_current_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_STRONGER_MODEL_CANDIDATE", "openai:gpt-5.5")

    def _fake_run_audit(*, output_dir: Path, env: Mapping[str, str]) -> None:
        relative_output = output_dir.relative_to(tmp_path / "comparison")
        if relative_output == Path("runs/current/run2"):
            raise subprocess.CalledProcessError(
                returncode=2,
                cmd=("run_relation_feasibility_audit.py", "--extractor", "agent"),
            )
        _write_report(
            output_dir,
            "relation_feasibility_report",
            model_label="candidate"
            if env.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL") == "openai:gpt-5.5"
            else "current",
        )

    monkeypatch.setattr(comparison_script, "_run_single_audit", _fake_run_audit)
    output_dir = tmp_path / "comparison"

    exit_code = comparison_main(
        [
            "--current-model-label",
            "current",
            "--candidate-model-label",
            "candidate",
            "--runs-per-model",
            "3",
            "--run-audits",
            "--output-dir",
            str(output_dir),
        ],
    )

    report = json.loads(
        (output_dir / "relation_model_comparison_report.json").read_text(),
    )
    markdown = (output_dir / "relation_model_comparison_report.md").read_text()

    assert exit_code == 0
    assert report["decision"]["adopted_model_label"] is None
    assert "current audit run failed." in report["decision"]["blocking_reasons"]
    assert report["decision"]["blocking_reasons"] == [
        "current audit run failed.",
        "current report count must match --runs-per-model; expected 3, got 1.",
    ]
    assert report["audit_failures"] == [
        {
            "model_label": "current",
            "run_index": 2,
            "exit_code": 2,
            "command": "run_relation_feasibility_audit.py --extractor agent",
        },
    ]
    assert report["candidate_readiness"]["readiness_status"] == "ready"
    assert "- current run2 exited 2" in markdown
