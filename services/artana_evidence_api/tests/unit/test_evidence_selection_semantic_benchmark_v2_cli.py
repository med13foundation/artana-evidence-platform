"""CLI coverage for semantic benchmark v2 validation reports."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = Path("scripts/validate_evidence_selection_semantic_benchmark_v2.py")
FIXTURE_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/semantic_relevance_benchmark_v2.json",
)
PREDICTION_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/semantic_relevance_live_baseline_predictions_v1.json",
)


def test_cli_writes_and_checks_pending_expert_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    json_output = tmp_path / "benchmark.json"
    markdown_output = tmp_path / "benchmark.md"
    args = (
        "--fixture",
        str(FIXTURE_PATH),
        "--predictions",
        str(PREDICTION_PATH),
        "--generated-at",
        "2026-07-13T00:00:00Z",
        "--json-output",
        str(json_output),
        "--markdown-output",
        str(markdown_output),
    )

    assert module.main(args) == 0
    assert module.main((*args, "--check")) == 0
    output = capsys.readouterr().out

    assert "visible=33" in output
    assert "score_eligible=0" in output
    assert "canary_gate=unavailable" in output
    assert "Human/expert approval claim: **NO**" in markdown_output.read_text()


def _load_script() -> ModuleType:
    module_name = "validate_evidence_selection_semantic_benchmark_v2"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load benchmark v2 CLI")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
