#!/usr/bin/env python3
"""Run the live semantic selector against the frozen PR 1 diagnostic corpus."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    evaluate_semantic_selection_agent,
    render_semantic_agent_evaluation_markdown,
)
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    EvidenceSelectionSemanticDiagnosticReport,
)
from artana_evidence_api.evidence_selection.output_paths import paths_alias
from artana_evidence_api.evidence_selection.semantic.model import (
    ArtanaEvidenceSelectionSemanticModelRunner,
)


def _parse_args(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate the live agent-first semantic evidence selector.",
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--baseline-report", required=True, type=Path)
    parser.add_argument("--evaluated-commit", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--model")
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--minimum-precision", type=float, default=0.8)
    parser.add_argument("--minimum-recall", type=float, default=0.8)
    return parser.parse_args(argv)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Run the live evaluation and publish its machine/human reports."""

    args = _parse_args(argv)
    try:
        generated_at = _parse_generated_at(args.generated_at)
        _validate_paths(
            fixture=args.fixture,
            baseline_report=args.baseline_report,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
        fixture = load_semantic_diagnostic_fixture(args.fixture)
        baseline_report = EvidenceSelectionSemanticDiagnosticReport.model_validate_json(
            args.baseline_report.read_text(encoding="utf-8"),
        )
        _verify_baseline_fixture(
            baseline_report=baseline_report,
            fixture=args.fixture,
        )
        _require_current_commit(args.evaluated_commit)
        evaluation = asyncio.run(
            evaluate_semantic_selection_agent(
                fixture_path=args.fixture,
                fixture=fixture,
                runner=ArtanaEvidenceSelectionSemanticModelRunner(
                    model_id=args.model,
                ),
                evaluated_commit=args.evaluated_commit,
                generated_at=generated_at.astimezone(UTC),
                baseline_report_path=args.baseline_report,
                baseline_precision=baseline_report.score.micro.precision,
                baseline_end_to_end_recall=(
                    baseline_report.score.micro.end_to_end_recall
                ),
                minimum_precision=args.minimum_precision,
                minimum_end_to_end_recall=args.minimum_recall,
            ),
        )
        _publish_reports(
            json_output=args.json_output,
            markdown_output=args.markdown_output,
            json_content=(
                json.dumps(evaluation.model_dump(mode="json"), indent=2) + "\n"
            ),
            markdown_content=render_semantic_agent_evaluation_markdown(evaluation),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_semantic_agent_evaluation "
        f"precision={evaluation.score.micro.precision:.4f} "
        f"end_to_end_recall={evaluation.score.micro.end_to_end_recall:.4f} "
        f"canary_passed={str(evaluation.canary_passed).lower()} "
        f"quality_gate_passed={str(evaluation.quality_gate_passed).lower()}",
    )
    return 0 if evaluation.quality_gate_passed else 1


def _validate_paths(
    *,
    fixture: Path,
    baseline_report: Path,
    json_output: Path,
    markdown_output: Path,
) -> None:
    if json_output.suffix.lower() != ".json":
        raise ValueError("JSON output must use a .json extension")
    if markdown_output.suffix.lower() != ".md":
        raise ValueError("Markdown output must use a .md extension")
    if paths_alias(json_output, markdown_output):
        raise ValueError("JSON and Markdown outputs must be different paths")
    source_inputs = (fixture, baseline_report)
    if any(
        paths_alias(source, output)
        for source in source_inputs
        for output in (json_output, markdown_output)
    ):
        raise ValueError("Evaluation outputs must not overwrite source inputs")


def _parse_generated_at(value: str) -> datetime:
    generated_at = datetime.fromisoformat(value)
    if generated_at.tzinfo is None:
        raise ValueError("--generated-at must include a timezone")
    return generated_at


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_baseline_fixture(
    *,
    baseline_report: EvidenceSelectionSemanticDiagnosticReport,
    fixture: Path,
) -> None:
    if baseline_report.fixture_sha256 != _sha256(fixture):
        raise ValueError("baseline report does not match the evaluation fixture")


def _require_current_commit(expected_commit: str) -> None:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to verify --evaluated-commit")
    result = subprocess.run(  # noqa: S603 - executable is resolved by shutil.which.
        [git, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    current_commit = result.stdout.strip()
    if current_commit != expected_commit:
        raise ValueError(
            "--evaluated-commit must equal the current checked-out HEAD",
        )


def _publish_reports(
    *,
    json_output: Path,
    markdown_output: Path,
    json_content: str,
    markdown_content: str,
) -> None:
    outputs = (
        (json_output, json_content),
        (markdown_output, markdown_content),
    )
    temporary_paths: list[Path] = []
    try:
        for output, content in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
            temporary.write_text(content, encoding="utf-8")
            temporary_paths.append(temporary)
        for (output, _content), temporary in zip(outputs, temporary_paths, strict=True):
            temporary.replace(output)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
