"""CLI coverage for semantic-selection baseline report generation."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path("scripts/generate_evidence_selection_semantic_baseline.py")
FIXTURE_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_failure_corpus_v1.json",
)
PREDICTION_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_live_baseline_predictions_v1.json",
)
GENERATED_AT = "2026-07-11T00:00:00Z"


def _source_args(fixture: Path = FIXTURE_PATH) -> tuple[str, ...]:
    return (
        "--fixture",
        str(fixture),
        "--predictions",
        str(PREDICTION_PATH),
        "--generated-at",
        GENERATED_AT,
    )


def _cli_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_evidence_selection_semantic_baseline",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        pytest.fail("semantic baseline CLI module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semantic_baseline_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    cli = _cli_module()
    json_output = tmp_path / "baseline.json"
    markdown_output = tmp_path / "baseline.md"

    exit_code = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ),
    )

    assert exit_code == 0
    payload = json.loads(json_output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        "evidence_selection_semantic_diagnostic_report.v1"
    )
    assert payload["fixture_provenance"] == "ai_adjudicated_diagnostic"
    assert payload["production_readiness_claim"] is False
    assert len(payload["source_artifacts"]) == 4
    assert all(
        len(artifact["source_artifact_sha256"]) == 64
        for artifact in payload["source_artifacts"]
    )
    assert payload["score"]["scored_case_count"] == 3
    assert payload["score"]["canary_case_count"] == 1
    markdown = markdown_output.read_text(encoding="utf-8")
    assert "AI-adjudicated diagnostic" in markdown
    assert "Production readiness claim: **NO**" in markdown
    assert "Primary-only micro aggregate" in markdown
    assert "Primary-only macro aggregate" in markdown
    assert "EGFR exclusion-token canary" in markdown


def test_semantic_baseline_cli_does_not_publish_partial_outputs(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    invalid_fixture = tmp_path / "invalid.json"
    invalid_fixture.write_text("{}", encoding="utf-8")
    json_output = tmp_path / "baseline.json"
    markdown_output = tmp_path / "baseline.md"

    exit_code = cli.main(
        (
            *_source_args(invalid_fixture),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ),
    )

    assert exit_code == 1
    assert not json_output.exists()
    assert not markdown_output.exists()


def test_semantic_baseline_cli_restores_existing_outputs_on_second_publish_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    json_output = tmp_path / "baseline.json"
    markdown_output = tmp_path / "baseline.md"
    json_output.write_text("old json", encoding="utf-8")
    markdown_output.write_text("old markdown", encoding="utf-8")
    original_replace = Path.replace

    def _fail_markdown_publish(self: Path, target: Path) -> Path:
        if self.name.endswith(".tmp") and target == markdown_output:
            raise OSError("simulated second publish failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", _fail_markdown_publish)

    exit_code = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(json_output),
            "--markdown-output",
            str(markdown_output),
        ),
    )

    assert exit_code == 1
    assert json_output.read_text(encoding="utf-8") == "old json"
    assert markdown_output.read_text(encoding="utf-8") == "old markdown"
    assert not tuple(tmp_path.glob(".*.tmp"))
    assert not tuple(tmp_path.glob(".*.bak"))


def test_semantic_baseline_cli_rejects_output_collisions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    output = tmp_path / "baseline.json"

    same_output_exit = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(output),
            "--markdown-output",
            str(output),
        ),
    )
    fixture_collision_exit = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(FIXTURE_PATH),
            "--markdown-output",
            str(tmp_path / "baseline.md"),
        ),
    )
    prediction_collision_exit = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(PREDICTION_PATH),
            "--markdown-output",
            str(tmp_path / "baseline.md"),
        ),
    )

    assert same_output_exit == 1
    assert fixture_collision_exit == 1
    assert prediction_collision_exit == 1
    assert capsys.readouterr().err.count(
        "Report outputs must not overwrite source inputs.",
    ) == 2
    assert not output.exists()


def test_semantic_baseline_cli_rejects_case_alias_and_wrong_extensions(
    tmp_path: Path,
) -> None:
    cli = _cli_module()

    case_alias_exit = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(tmp_path / "Baseline.JSON"),
            "--markdown-output",
            str(tmp_path / "baseline.json"),
        ),
    )
    wrong_extension_exit = cli.main(
        (
            *_source_args(),
            "--json-output",
            str(tmp_path / "baseline.txt"),
            "--markdown-output",
            str(tmp_path / "baseline.md"),
        ),
    )

    assert case_alias_exit == 1
    assert wrong_extension_exit == 1


def test_semantic_baseline_cli_check_detects_report_drift(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _cli_module()
    json_output = tmp_path / "baseline.json"
    markdown_output = tmp_path / "baseline.md"
    args = (
        *_source_args(),
        "--json-output",
        str(json_output),
        "--markdown-output",
        str(markdown_output),
    )
    assert cli.main(args) == 0
    capsys.readouterr()
    assert cli.main((*args, "--check")) == 0
    check_output = capsys.readouterr()
    assert "Checked JSON report:" in check_output.out
    assert "Checked Markdown report:" in check_output.out
    assert "Wrote" not in check_output.out
    markdown_output.write_text("drift", encoding="utf-8")

    assert cli.main((*args, "--check")) == 1


def test_semantic_baseline_cli_normalizes_utc_z_timestamp() -> None:
    cli = _cli_module()

    assert cli._parse_generated_at("2026-07-11T00:00:00Z") == (
        cli._parse_generated_at("2026-07-11T00:00:00+00:00")
    )


@pytest.mark.parametrize("link_kind", ["hard", "symbolic"])
def test_semantic_baseline_cli_rejects_filesystem_aliases(
    tmp_path: Path,
    link_kind: str,
) -> None:
    cli = _cli_module()
    json_output = tmp_path / "baseline.json"
    markdown_output = tmp_path / "baseline.md"
    json_output.write_text("existing", encoding="utf-8")
    if link_kind == "hard":
        os.link(json_output, markdown_output)
    else:
        markdown_output.symlink_to(json_output.name)

    assert (
        cli.main(
            (
                *_source_args(),
                "--json-output",
                str(json_output),
                "--markdown-output",
                str(markdown_output),
            ),
        )
        == 1
    )
