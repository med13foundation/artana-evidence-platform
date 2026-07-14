"""CLI contract tests for semantic selector model comparison."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from artana_evidence_api.evidence_selection.semantic.model import (
    ArtanaEvidenceSelectionSemanticModelRunner,
)
from artana_evidence_api.llm_costs import calculate_openai_usage_cost_usd
from artana_evidence_api.runtime.model_registry import (
    ModelCapability,
    get_model_registry,
)

from .evidence_selection_semantic_repeatability_test_support import (
    BASELINE_PATH,
    CANDIDATE_MODEL,
    CURRENT_MODEL,
    FIXTURE_PATH,
)

_SCRIPT_PATH = Path("scripts/run_evidence_selection_semantic_model_comparison.py")


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "run_evidence_selection_semantic_model_comparison",
        _SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_freezes_protocol_before_executor(monkeypatch, tmp_path) -> None:
    module = _load_script()
    captured_protocols = []

    async def fake_execute(**kwargs):
        captured_protocols.append(kwargs["protocol"])
        assert kwargs["repository_root"] == module._repository_root()
        assert kwargs["runner_factory"] is (
            module.create_trusted_semantic_comparison_runner
        )
        return SimpleNamespace(
            decision=SimpleNamespace(
                outcome="keep_current",
                selected_model_id=CURRENT_MODEL,
            ),
            selected_model_repeatability_passed=True,
            production_readiness_claim=False,
        )

    monkeypatch.setattr(
        module,
        "_require_integrated_commit",
        lambda **_kwargs: "b" * 40,
    )
    monkeypatch.setattr(module, "_require_clean_worktree", lambda: None)
    monkeypatch.setattr(
        module,
        "_require_unchanged_repository_state",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        module,
        "_resolved_model_id",
        lambda requested: requested or CURRENT_MODEL,
    )
    monkeypatch.setattr(module, "execute_semantic_model_comparison", fake_execute)

    result = module.main(
        (
            "--fixture",
            str(FIXTURE_PATH),
            "--baseline-report",
            str(BASELINE_PATH),
            "--evaluated-commit",
            "a" * 40,
            "--current-model",
            CURRENT_MODEL,
            "--candidate-model",
            CANDIDATE_MODEL,
            "--generated-at",
            "2026-07-13T00:00:00+00:00",
            "--output-dir",
            str(tmp_path / "comparison"),
        ),
    )

    assert result == 0
    assert len(captured_protocols) == 1
    protocol = captured_protocols[0]
    assert protocol.current_model_id == CURRENT_MODEL
    assert protocol.candidate_model_id == CANDIDATE_MODEL
    assert protocol.runs_per_model == 3
    assert protocol.trusted_mainline_ref == "origin/main"
    assert protocol.trusted_mainline_commit == "b" * 40
    assert protocol.required_mainline_commit == module._DEFAULT_REQUIRED_MAINLINE_COMMIT
    assert len(protocol.repository_source_files) == 5
    assert protocol.repository_source_files[0].role == "baseline_predictions"
    assert protocol.production_readiness_claim is False


def test_comparison_resolves_exact_distinct_registered_models_without_runtime_override(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES", raising=False)
    monkeypatch.delenv("ARTANA_AI_JUDGE_MODEL", raising=False)
    module = _load_script()
    registry = get_model_registry()
    candidate_model_id = "openai:gpt-5.6-luna"

    assert registry.allow_runtime_model_overrides() is False
    assert registry.validate_model_for_capability(
        candidate_model_id,
        ModelCapability.JUDGE,
    )

    current_model_id = module._resolved_model_id(None)
    resolved_candidate_model_id = module._resolved_model_id(candidate_model_id)

    assert current_model_id == "openai:gpt-5.4-mini"
    assert resolved_candidate_model_id == candidate_model_id
    assert resolved_candidate_model_id != current_model_id
    assert calculate_openai_usage_cost_usd(
        model_id=candidate_model_id,
        prompt_tokens=1000,
        completion_tokens=1000,
    ) == pytest.approx(0.007)
    assert (
        ArtanaEvidenceSelectionSemanticModelRunner(
            model_id=candidate_model_id,
        ).model_id()
        == current_model_id
    )
    assert (
        module.create_trusted_semantic_comparison_runner(
            candidate_model_id,
        ).model_id()
        == candidate_model_id
    )
    with pytest.raises(ValueError, match="is not registered"):
        module._resolved_model_id("openai:not-a-registered-model")
    assert registry.allow_runtime_model_overrides() is False


def test_cli_rejects_candidate_that_resolves_to_current(monkeypatch, tmp_path) -> None:
    module = _load_script()
    monkeypatch.setattr(
        module,
        "_require_integrated_commit",
        lambda **_kwargs: "b" * 40,
    )
    monkeypatch.setattr(module, "_require_clean_worktree", lambda: None)
    monkeypatch.setattr(module, "_resolved_model_id", lambda _requested: CURRENT_MODEL)

    result = module.main(
        (
            "--fixture",
            str(FIXTURE_PATH),
            "--baseline-report",
            str(BASELINE_PATH),
            "--evaluated-commit",
            "a" * 40,
            "--candidate-model",
            CANDIDATE_MODEL,
            "--output-dir",
            str(tmp_path / "comparison"),
        ),
    )

    assert result == 1


def test_cli_requires_timezone_for_declared_generation_time() -> None:
    module = _load_script()

    with pytest.raises(ValueError, match="include a timezone"):
        module._generated_at("2026-07-13T00:00:00")


def test_integrated_commit_requires_trusted_mainline_ancestor(monkeypatch) -> None:
    module = _load_script()
    head = "a" * 40
    trusted = "b" * 40
    required = "c" * 40

    def fake_run(args, **_kwargs):
        if args[1:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=f"{head}\n", returncode=0)
        if args[1:3] == ["rev-parse", "--verify"]:
            resolved = trusted if args[-1].startswith("origin/main") else required
            return SimpleNamespace(stdout=f"{resolved}\n", returncode=0)
        if args[1:3] == ["merge-base", "--is-ancestor"]:
            return SimpleNamespace(stdout="", returncode=0)
        raise AssertionError(f"unexpected git command: {args}")

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert (
        module._require_integrated_commit(
            expected_commit=head,
            trusted_mainline_ref="origin/main",
            required_mainline_commit=required,
        )
        == trusted
    )


def test_integrated_commit_rejects_branch_without_trusted_ancestor(monkeypatch) -> None:
    module = _load_script()
    head = "a" * 40
    trusted = "b" * 40
    required = "c" * 40

    def fake_run(args, **_kwargs):
        if args[1:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=f"{head}\n", returncode=0)
        if args[1:3] == ["rev-parse", "--verify"]:
            resolved = trusted if args[-1].startswith("origin/main") else required
            return SimpleNamespace(stdout=f"{resolved}\n", returncode=0)
        if args[1:3] == ["merge-base", "--is-ancestor"]:
            return SimpleNamespace(
                stdout="",
                returncode=0 if args[-2:] == [required, trusted] else 1,
            )
        raise AssertionError(f"unexpected git command: {args}")

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="contain the trusted mainline commit"):
        module._require_integrated_commit(
            expected_commit=head,
            trusted_mainline_ref="origin/main",
            required_mainline_commit=required,
        )


def test_integrated_commit_rejects_mainline_without_required_predecessor(
    monkeypatch,
) -> None:
    module = _load_script()
    head = "a" * 40
    trusted = "b" * 40
    required = "c" * 40

    def fake_run(args, **_kwargs):
        if args[1:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=f"{head}\n", returncode=0)
        if args[1:3] == ["rev-parse", "--verify"]:
            resolved = trusted if args[-1].startswith("origin/main") else required
            return SimpleNamespace(stdout=f"{resolved}\n", returncode=0)
        if args[1:3] == ["merge-base", "--is-ancestor"]:
            return SimpleNamespace(stdout="", returncode=1)
        raise AssertionError(f"unexpected git command: {args}")

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(ValueError, match="required integrated predecessor"):
        module._require_integrated_commit(
            expected_commit=head,
            trusted_mainline_ref="origin/main",
            required_mainline_commit=required,
        )
