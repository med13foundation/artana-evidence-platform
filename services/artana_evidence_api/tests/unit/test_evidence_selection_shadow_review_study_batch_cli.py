"""Tests for the completed shadow-review study batch CLI."""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest
from artana_evidence_api.evidence_selection.shadow_review_completion import (
    machine_packet_sidecar_path,
)

from services.artana_evidence_api.tests.unit.evidence_selection_review_fixtures import (
    inadequate_explanation_assessment,
)
from services.artana_evidence_api.tests.unit.test_evidence_selection_shadow_review_study_pipeline import (  # noqa: E501
    _calibrated_probability,
    _completed_packet,
    _machine_packet_for_completed_packet,
    _operational_ranking,
)


def test_shadow_review_study_batch_cli_writes_reports_and_fails_on_failed_entry(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    assert exit_code == 1
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    assert batch_report["entry_count"] == 2
    assert batch_report["passed_entry_count"] == 1
    assert batch_report["failed_entry_count"] == 1
    assert (output_dir / "shadow-review-study-batch.md").exists()
    assert (
        output_dir / "good-study" / "gate" / "evidence_selection_expert_study_gate.json"
    ).exists()
    weak_gate_report = json.loads(
        (
            output_dir
            / "weak-study"
            / "gate"
            / "evidence_selection_expert_study_gate.json"
        ).read_text(),
    )
    assert weak_gate_report["gate"]["passed"] is False
    assert weak_gate_report["gate"]["blocking_reasons"]
    assert (
        output_dir / "weak-study" / "gate" / "evidence_selection_expert_study_gate.md"
    ).exists()


def test_shadow_review_study_batch_cli_allows_failed_gate_when_requested(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--allow-failed-gate",
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    assert exit_code == 0
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    assert batch_report["failed_entry_count"] == 1


@pytest.mark.parametrize(
    "failing_writer",
    [
        "_write_entry_gate_reports",
        "write_evidence_selection_shadow_review_study_batch_report",
    ],
)
def test_shadow_review_study_batch_cli_rolls_back_report_phase_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_writer: str,
) -> None:
    cli = _cli_module()
    manifest_path = _write_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"
    args = (
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir),
        "--allow-failed-gate",
        "--min-selection-review-count",
        "1",
        "--min-distinct-selection-goals",
        "1",
        "--min-review-ranking-sample-count",
        "2",
        "--min-distinct-ranking-goals",
        "1",
        "--min-distinct-evidence-shapes",
        "2",
    )

    def _fail_report_write(*_args: object, **_kwargs: object) -> None:
        partial_output = (
            output_dir / "shadow-review-study-batch.json"
            if failing_writer.startswith("write_")
            else output_dir / "good-study" / "gate" / "partial.json"
        )
        partial_output.parent.mkdir(parents=True, exist_ok=True)
        partial_output.write_text("partial report\n")
        raise OSError("simulated report publication failure")

    with monkeypatch.context() as patch_context:
        patch_context.setattr(cli, failing_writer, _fail_report_write)
        assert cli.main(args) == 1

    assert output_dir.is_dir()
    assert list(output_dir.iterdir()) == []
    assert cli.main(args) == 0
    assert (output_dir / "shadow-review-study-batch.json").exists()


def test_shadow_review_study_batch_cli_does_not_relax_production_suite_floor(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_single_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
            "--min-batch-entry-count",
            "1",
            "--min-batch-passed-entry-count",
            "1",
            "--max-batch-failed-entry-count",
            "0",
            "--min-batch-passed-entry-rate",
            "1.0",
            "--min-batch-distinct-selection-goals",
            "1",
            "--min-batch-distinct-review-ranking-goals",
            "1",
            "--min-batch-distinct-evidence-shapes",
            "2",
        ),
    )

    assert exit_code == 1
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    assert batch_report["suite_gate"]["passed"] is False
    assert batch_report["suite_gate"]["thresholds"]["min_entry_count"] == 3
    assert batch_report["suite_gate"]["summary"]["entry_count"] == 1
    assert any(
        "At least 3 batch entries" in reason
        for reason in batch_report["suite_gate"]["blocking_reasons"]
    )
    markdown_report = (output_dir / "shadow-review-study-batch.md").read_text()
    assert "## Suite Gate" in markdown_report
    assert "- Status: **FAILED**" in markdown_report
    assert "- Production floor applied: yes" in markdown_report
    assert "## Suite Thresholds" in markdown_report
    assert "| min_entry_count | 1 | 3 |" in markdown_report


def test_shadow_review_study_batch_cli_relaxed_entry_thresholds_still_need_suite_sample_floor(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_three_entry_thin_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    assert exit_code == 1
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    assert (
        batch_report["suite_gate"]["summary"]["total_review_ranking_decision_count"]
        == 6
    )
    assert any(
        "review-ranking decisions" in reason
        for reason in batch_report["suite_gate"]["blocking_reasons"]
    )


def test_shadow_review_study_batch_cli_help_mentions_suite_gate_override(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()

    with pytest.raises(SystemExit) as exc_info:
        cli.parse_args(("--help",))

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    normalized_help = " ".join(captured.out.split())
    assert "entry or suite gate fails" in normalized_help


def test_shadow_review_study_batch_markdown_marks_missing_production_floor_unknown() -> (
    None
):
    cli = _cli_module()

    markdown = cli.render_evidence_selection_shadow_review_study_batch_markdown(
        {
            "batch_id": "batch-1",
            "passed": False,
            "entry_count": 0,
            "passed_entry_count": 0,
            "failed_entry_count": 0,
            "suite_gate": {
                "passed": False,
                "blocking_reasons": [],
                "summary": {},
                "requested_thresholds": {},
                "thresholds": {},
            },
            "entries": [],
        },
    )

    assert "- Production floor applied: unknown" in markdown


def test_shadow_review_study_batch_cli_relaxed_quality_thresholds_still_need_suite_quality_floor(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    manifest_path = _write_three_entry_bad_quality_manifest(tmp_path)
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
            "--min-mean-precision",
            "0",
            "--min-mean-recall",
            "0",
            "--min-explanation-adequacy-rate",
            "0",
        ),
    )

    assert exit_code == 1
    batch_report = json.loads(
        (output_dir / "shadow-review-study-batch.json").read_text(),
    )
    assert batch_report["passed"] is False
    summary = batch_report["suite_gate"]["summary"]
    assert summary["suite_mean_precision"] == 0.0
    assert summary["suite_mean_recall"] == 0.0
    assert summary["suite_explanation_adequacy_rate"] == 0.0
    assert summary["all_entry_observed_quality"] == {
        "suite_mean_precision": 0.0,
        "suite_mean_recall": 0.0,
        "suite_explanation_adequacy_rate": 0.0,
        "max_review_ranking_expected_calibration_error": 0.0,
        "unavailable_review_ranking_calibration_count": 0,
    }
    assert summary["passed_entry_production_quality"] == {
        "suite_mean_precision": 0.0,
        "suite_mean_recall": 0.0,
        "suite_explanation_adequacy_rate": 0.0,
        "max_review_ranking_expected_calibration_error": 0.0,
        "unavailable_review_ranking_calibration_count": 0,
    }
    markdown_report = (output_dir / "shadow-review-study-batch.md").read_text()
    assert "Passed-entry production mean precision" in markdown_report
    assert "All-entry observed mean precision" in markdown_report
    assert "All-entry observed explanation adequacy rate" in markdown_report
    assert any(
        "suite mean precision" in reason
        for reason in batch_report["suite_gate"]["blocking_reasons"]
    )


def test_shadow_review_study_batch_cli_rejects_report_manifest_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    output_dir = tmp_path / "batch-output"
    output_dir.mkdir()
    manifest_path = output_dir / "shadow-review-study-batch.json"
    manifest_payload = _manifest_payload(tmp_path)
    manifest_path.write_text(json.dumps(manifest_payload))
    original_manifest_text = manifest_path.read_text()

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not overwrite manifest" in captured.err
    assert "Traceback" not in captured.err
    assert manifest_path.read_text() == original_manifest_text


def test_shadow_review_study_batch_cli_rejects_report_packet_collision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    output_dir = tmp_path / "batch-output"
    output_dir.mkdir()
    packet_path = output_dir / "shadow-review-study-batch.json"
    _write_packet(packet_path, _completed_packet())
    original_packet_text = packet_path.read_text()
    manifest_path = tmp_path / "shadow-review-batch.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="study-a",
                        packet_path=packet_path,
                        output_subdir="study-a",
                        export_id="shadow-export-study-a",
                    ),
                ],
            },
        ),
    )

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--min-selection-review-count",
            "1",
            "--min-distinct-selection-goals",
            "1",
            "--min-review-ranking-sample-count",
            "2",
            "--min-distinct-ranking-goals",
            "1",
            "--min-distinct-evidence-shapes",
            "2",
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must not overwrite source packet" in captured.err
    assert "Traceback" not in captured.err
    assert packet_path.read_text() == original_packet_text


@pytest.mark.parametrize(
    "output_subdir",
    ["shadow-review-study-batch.json", "shadow-review-study-batch.json/study"],
)
def test_shadow_review_study_batch_cli_rejects_nested_report_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_subdir: str,
) -> None:
    cli = _cli_module()
    packet_path = tmp_path / "packet.json"
    _write_packet(packet_path, _completed_packet())
    manifest_path = tmp_path / "shadow-review-batch.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="study-a",
                        packet_path=packet_path,
                        output_subdir=output_subdir,
                        export_id="shadow-export-study-a",
                    ),
                ],
            },
        ),
    )
    output_dir = tmp_path / "batch-output"

    exit_code = cli.main(
        (
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "report output paths must be unique and not nested" in captured.err
    assert not output_dir.exists()


def _cli_module() -> object:
    try:
        return importlib.import_module(
            "scripts.build_evidence_selection_shadow_review_study_batch",
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"shadow review study batch CLI is missing: {exc}")


def _write_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "shadow-review-batch.json"
    manifest_path.write_text(json.dumps(_manifest_payload(tmp_path)))
    return manifest_path


def _write_packet(path: Path, packet: dict[str, object]) -> Path:
    machine_packet = _machine_packet_for_completed_packet(packet)
    packet["machine_packet_sha256"] = machine_packet["machine_packet_sha256"]
    packet["machine_packet_signature"] = machine_packet["machine_packet_signature"]
    path.write_text(json.dumps(packet))
    machine_packet_sidecar_path(path).write_text(json.dumps(machine_packet))
    return path


def _write_single_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "single-shadow-review-batch.json"
    packet_path = tmp_path / "single-packet.json"
    _write_packet(packet_path, _completed_packet())
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": "single-batch-2026-07-07",
                "entries": [
                    _manifest_entry(
                        entry_id="single-study",
                        packet_path=packet_path,
                        output_subdir="single-study",
                        export_id="shadow-export-single",
                    ),
                ],
            },
        ),
    )
    return manifest_path


def _write_three_entry_thin_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "thin-shadow-review-batch.json"
    return _write_three_entry_manifest(
        tmp_path=tmp_path,
        manifest_path=manifest_path,
        batch_id="thin-batch-2026-07-07",
        review_ranking_counts=(2, 2, 2),
        bad_quality=False,
    )


def _write_three_entry_bad_quality_manifest(tmp_path: Path) -> Path:
    manifest_path = tmp_path / "bad-quality-shadow-review-batch.json"
    return _write_three_entry_manifest(
        tmp_path=tmp_path,
        manifest_path=manifest_path,
        batch_id="bad-quality-batch-2026-07-07",
        review_ranking_counts=(4, 3, 3),
        bad_quality=True,
    )


def _write_three_entry_manifest(
    *,
    tmp_path: Path,
    manifest_path: Path,
    batch_id: str,
    review_ranking_counts: tuple[int, int, int],
    bad_quality: bool,
) -> Path:
    packet_specs = (
        (
            "first",
            "11111111-1111-4111-8111-111111111111",
            "Assess BRAF targeted therapy evidence.",
            "variant_drug_response",
            "background_context",
        ),
        (
            "second",
            "22222222-2222-4222-8222-222222222222",
            "Assess EGFR resistance evidence.",
            "drug_resistance",
            "mechanistic_context",
        ),
        (
            "third",
            "33333333-3333-4333-8333-333333333333",
            "Assess BRCA1 pathogenicity evidence.",
            "gene_disease_association",
            "variant_pathogenicity",
        ),
    )
    entries: list[dict[str, object]] = []
    for index, (label, run_id, goal, first_shape, second_shape) in enumerate(
        packet_specs,
        start=1,
    ):
        packet_path = tmp_path / f"{label}-packet.json"
        _write_packet(
            packet_path,
            _completed_packet_for_cli_batch(
                study_id=f"shadow-study-{label}",
                source_run_id=run_id,
                goal=goal,
                first_shape=first_shape,
                second_shape=second_shape,
                review_ranking_decision_count=review_ranking_counts[index - 1],
                bad_quality=bad_quality,
            ),
        )
        entries.append(
            _manifest_entry(
                entry_id=f"study-{index}",
                packet_path=packet_path,
                output_subdir=f"study-{index}",
                export_id=f"shadow-export-{index}",
            ),
        )
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "evidence_selection_shadow_review_study_batch.v1",
                "batch_id": batch_id,
                "entries": entries,
            },
        ),
    )
    return manifest_path


def _manifest_payload(tmp_path: Path) -> dict[str, object]:
    good_packet_path = tmp_path / "good-packet.json"
    weak_packet_path = tmp_path / "weak-packet.json"
    _write_packet(good_packet_path, _completed_packet())
    _write_packet(weak_packet_path, _low_quality_packet())
    return {
        "schema_version": "evidence_selection_shadow_review_study_batch.v1",
        "batch_id": "batch-2026-07-07",
        "entries": [
            _manifest_entry(
                entry_id="good-study",
                packet_path=good_packet_path,
                output_subdir="good-study",
                export_id="shadow-export-good",
            ),
            _manifest_entry(
                entry_id="weak-study",
                packet_path=weak_packet_path,
                output_subdir="weak-study",
                export_id="shadow-export-weak",
            ),
        ],
    }


def _manifest_entry(
    *,
    entry_id: str,
    packet_path: Path,
    output_subdir: str,
    export_id: str,
) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "packet_path": str(packet_path),
        "output_subdir": output_subdir,
        "adjudication_note": f"{entry_id} labels completed by reviewer.",
        "source_system": "artana-shadow-review",
        "export_id": export_id,
        "exported_at": "2026-07-07T14:00:00Z",
        "exporter_id": "review-ops-a",
        "redaction_statement": "No PHI or raw patient text included.",
        "study_evidence_kind": "real_shadow_review",
        "description": f"{entry_id} completed shadow-review packet.",
    }


def _low_quality_packet() -> dict[str, object]:
    packet = copy.deepcopy(_completed_packet())
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    first_form = selection_forms[0]
    assert isinstance(first_form, dict)
    first_form["explanation_assessment"] = (
        inadequate_explanation_assessment().model_dump(mode="json")
    )
    return packet


def _completed_packet_for_cli_batch(
    *,
    study_id: str,
    source_run_id: str,
    goal: str,
    first_shape: str,
    second_shape: str,
    review_ranking_decision_count: int = 2,
    bad_quality: bool = False,
) -> dict[str, object]:
    packet = copy.deepcopy(_completed_packet())
    packet["study_id"] = study_id
    packet["source_run_id"] = source_run_id
    packet["goal"] = goal
    selection_forms = packet["selection_review_forms"]
    assert isinstance(selection_forms, list)
    for form in selection_forms:
        assert isinstance(form, dict)
        form["run_id"] = source_run_id
        form["goal"] = goal
        if bad_quality:
            form["human_selected_record_ids"] = ["pubmed:search-1:1"]
            form["explanation_assessment"] = (
                inadequate_explanation_assessment().model_dump(mode="json")
            )
    ranking_forms = packet["review_ranking_forms"]
    assert isinstance(ranking_forms, list)
    shapes = (first_shape, second_shape)
    question_offset = ((int(source_run_id[0], 16) - 1) * 3) % 8
    while len(ranking_forms) < review_ranking_decision_count:
        index = len(ranking_forms)
        positive = index % 2 == 0
        ranking_forms.append(
            {
                "source_kind": "proposal" if positive else "review_item",
                "item_id": f"ranking-{study_id}-{index}",
                "research_question_id": (
                    f"heldout-rq-{((question_offset + index) % 8) + 1:02d}"
                ),
                "operational_ranking": _operational_ranking(
                    1.0 if positive else 0.0,
                ),
                "calibrated_probability": _calibrated_probability(
                    1.0 if positive else 0.0,
                ),
                "outcome": "positive" if positive else "negative",
                "reviewer_id": "reviewer-a",
                "goal": goal,
                "evidence_shape": shapes[index % len(shapes)],
            },
        )
    for index, form in enumerate(ranking_forms):
        assert isinstance(form, dict)
        form["research_question_id"] = (
            f"heldout-rq-{((question_offset + index) % 8) + 1:02d}"
        )
        form["goal"] = goal
        form["evidence_shape"] = shapes[index % len(shapes)]
    return packet
