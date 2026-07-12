"""Worktree-integrity tests for the live semantic-agent evaluation CLI."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path("scripts/run_evidence_selection_semantic_agent_evaluation.py")


def _cli_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_evidence_selection_semantic_agent_evaluation",
        _SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        pytest.fail("semantic agent evaluation CLI module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repository: Path, *args: str) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run(
        [git, *args],
        cwd=repository,
        check=True,
        capture_output=True,
    )


def _initialize_repository(repository: Path) -> tuple[Path, Path, Path]:
    _git(repository, "init")
    _git(repository, "config", "user.email", "semantic-evaluation@example.test")
    _git(repository, "config", "user.name", "Semantic Evaluation Test")
    tracked = repository / "tracked.py"
    json_output = repository / "report.json"
    markdown_output = repository / "report.md"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    json_output.write_text("{}\n", encoding="utf-8")
    markdown_output.write_text("# Existing report\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return tracked, json_output, markdown_output


def test_live_evaluation_allows_only_dirty_report_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    tracked, json_output, markdown_output = _initialize_repository(tmp_path)
    json_output.write_text("updated report\n", encoding="utf-8")
    markdown_output.write_text("updated report\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cli._require_clean_worktree(
        allowed_outputs=(json_output, markdown_output),
    )

    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean worktree"):
        cli._require_clean_worktree(
            allowed_outputs=(json_output, markdown_output),
        )


@pytest.mark.parametrize("dirty_kind", ["staged", "untracked"])
def test_live_evaluation_rejects_other_dirty_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dirty_kind: str,
) -> None:
    cli = _cli_module()
    tracked, json_output, markdown_output = _initialize_repository(tmp_path)
    monkeypatch.chdir(tmp_path)
    if dirty_kind == "staged":
        tracked.write_text("VALUE = 2\n", encoding="utf-8")
        _git(tmp_path, "add", tracked.name)
    else:
        (tmp_path / "untracked.py").write_text("VALUE = 2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="clean worktree"):
        cli._require_clean_worktree(
            allowed_outputs=(json_output, markdown_output),
        )
