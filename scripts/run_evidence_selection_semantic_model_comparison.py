#!/usr/bin/env python3
"""Run the source-locked semantic-selector repeatability and model A/B proof."""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.repeatability.executor import (
    execute_semantic_model_comparison,
)
from artana_evidence_api.evidence_selection.repeatability.model_resolution import (
    create_trusted_semantic_comparison_runner,
    resolve_trusted_semantic_comparison_model_id,
)
from artana_evidence_api.evidence_selection.repeatability.protocol import (
    build_semantic_model_comparison_protocol,
    sha256_path,
)

_GIT_SHA_LENGTH = 40
_DEFAULT_REQUIRED_MAINLINE_COMMIT = "d23b1dea194d7fc6f116de84738fdf720c536a71"


def _parse_args(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two semantic selector models over repeated, source-locked runs."
        ),
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--evaluated-commit", required=True)
    parser.add_argument("--trusted-mainline-ref", default="origin/main")
    parser.add_argument(
        "--required-mainline-commit",
        default=_DEFAULT_REQUIRED_MAINLINE_COMMIT,
    )
    parser.add_argument("--current-model")
    parser.add_argument("--candidate-model", required=True)
    parser.add_argument("--runs-per-model", type=int, default=3)
    parser.add_argument("--generated-at")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Validate, freeze, execute, and report one model-comparison protocol."""

    args = _parse_args(argv)
    try:
        generated_at = _generated_at(args.generated_at)
        trusted_mainline_commit = _require_integrated_commit(
            expected_commit=args.evaluated_commit,
            trusted_mainline_ref=args.trusted_mainline_ref,
            required_mainline_commit=args.required_mainline_commit,
        )
        _require_clean_worktree()
        _validate_output_path(
            output_dir=args.output_dir,
            source_paths=(args.fixture, args.baseline_report),
        )
        load_semantic_diagnostic_fixture(args.fixture)
        baseline = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
            args.baseline_report.read_text(encoding="utf-8"),
        )
        fixture_sha256 = sha256_path(args.fixture)
        _verify_baseline_fixture(
            baseline=baseline,
            fixture_sha256=fixture_sha256,
        )
        current_model_id = _resolved_model_id(args.current_model)
        candidate_model_id = _resolved_model_id(args.candidate_model)
        protocol = build_semantic_model_comparison_protocol(
            generated_at=generated_at,
            evaluated_commit=args.evaluated_commit,
            trusted_mainline_ref=args.trusted_mainline_ref,
            trusted_mainline_commit=trusted_mainline_commit,
            required_mainline_commit=args.required_mainline_commit,
            fixture_path=args.fixture,
            fixture_sha256=fixture_sha256,
            baseline_report_path=args.baseline_report,
            baseline_report_sha256=sha256_path(args.baseline_report),
            current_model_id=current_model_id,
            candidate_model_id=candidate_model_id,
            runs_per_model=args.runs_per_model,
        )
        report = asyncio.run(
            execute_semantic_model_comparison(
                protocol=protocol,
                output_dir=args.output_dir,
                runner_factory=create_trusted_semantic_comparison_runner,
                finalization_guard=lambda: _require_unchanged_repository_state(
                    expected_commit=args.evaluated_commit,
                    trusted_mainline_ref=args.trusted_mainline_ref,
                    trusted_mainline_commit=trusted_mainline_commit,
                    required_mainline_commit=args.required_mainline_commit,
                ),
            ),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_semantic_model_comparison "
        f"decision={report.decision.outcome} "
        f"selected_model={report.decision.selected_model_id or 'none'} "
        "selected_model_repeatability_passed="
        f"{str(report.selected_model_repeatability_passed).lower()} "
        f"production_readiness_claim={str(report.production_readiness_claim).lower()}",
    )
    return 0 if report.selected_model_repeatability_passed else 1


def _resolved_model_id(requested_model_id: str | None) -> str:
    return resolve_trusted_semantic_comparison_model_id(requested_model_id)


def _verify_baseline_fixture(
    *,
    baseline: EvidenceSelectionSemanticDiagnosticReport,
    fixture_sha256: str,
) -> None:
    if baseline.fixture_sha256 != fixture_sha256:
        raise ValueError("baseline report does not match the comparison fixture")


def _generated_at(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    generated_at = datetime.fromisoformat(value)
    if generated_at.tzinfo is None:
        raise ValueError("--generated-at must include a timezone")
    return generated_at.astimezone(UTC)


def _require_integrated_commit(
    *,
    expected_commit: str,
    trusted_mainline_ref: str,
    required_mainline_commit: str,
) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to verify --evaluated-commit")
    result = subprocess.run(  # noqa: S603 - executable resolved by shutil.which.
        [git, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() != expected_commit:
        raise ValueError("--evaluated-commit must equal the checked-out HEAD")
    trusted_commit = _resolve_git_commit(git=git, ref=trusted_mainline_ref)
    required_commit = _resolve_git_commit(git=git, ref=required_mainline_commit)
    required_ancestor = subprocess.run(  # noqa: S603 - git path is trusted.
        [git, "merge-base", "--is-ancestor", required_commit, trusted_commit],
        check=False,
        capture_output=True,
        text=True,
    )
    if required_ancestor.returncode != 0:
        raise ValueError(
            "trusted mainline must contain the required integrated predecessor",
        )
    ancestor = subprocess.run(  # noqa: S603 - executable resolved by shutil.which.
        [git, "merge-base", "--is-ancestor", trusted_commit, expected_commit],
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        raise ValueError("evaluated commit must contain the trusted mainline commit")
    return trusted_commit


def _require_unchanged_repository_state(
    *,
    expected_commit: str,
    trusted_mainline_ref: str,
    trusted_mainline_commit: str,
    required_mainline_commit: str,
) -> None:
    observed_mainline = _require_integrated_commit(
        expected_commit=expected_commit,
        trusted_mainline_ref=trusted_mainline_ref,
        required_mainline_commit=required_mainline_commit,
    )
    if observed_mainline != trusted_mainline_commit:
        raise ValueError("trusted mainline ref moved during model comparison")
    _require_clean_worktree()


def _resolve_git_commit(*, git: str, ref: str) -> str:
    result = subprocess.run(  # noqa: S603 - executable resolved by shutil.which.
        [git, "rev-parse", "--verify", f"{ref}^{{commit}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if len(commit) != _GIT_SHA_LENGTH:
        raise ValueError("trusted mainline ref did not resolve to a commit")
    return commit


def _require_clean_worktree() -> None:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to verify the comparison worktree")
    result = subprocess.run(  # noqa: S603 - executable resolved by shutil.which.
        [git, "status", "--porcelain", "--untracked-files=normal"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        raise ValueError("model comparison requires a clean worktree")


def _validate_output_path(
    *,
    output_dir: Path,
    source_paths: tuple[Path, ...],
) -> None:
    resolved_output = output_dir.resolve()
    if resolved_output.exists():
        raise ValueError("--output-dir must not already exist")
    if any(source.resolve() == resolved_output for source in source_paths):
        raise ValueError("comparison output cannot overwrite a source artifact")


if __name__ == "__main__":
    raise SystemExit(main())
