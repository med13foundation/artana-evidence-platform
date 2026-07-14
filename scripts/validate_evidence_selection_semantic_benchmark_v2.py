#!/usr/bin/env python3
"""Validate and report the integrity-first semantic benchmark v2."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2 import (
    build_benchmark_v2_report,
    evaluate_benchmark_v2,
    load_benchmark_v2,
    render_benchmark_v2_markdown,
    score_benchmark_v2,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    load_semantic_prediction_artifact,
    verify_prediction_provenance,
)
from artana_evidence_api.evidence_selection.output_paths import paths_alias


def _parse_args(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate semantic benchmark v2 provenance, eligibility, and reports.",
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Validate immutable inputs and either write or check deterministic reports."""

    args = _parse_args(argv)
    try:
        _validate_output_paths(args)
        loaded = load_benchmark_v2(
            fixture_path=args.fixture,
            repository_root=Path.cwd(),
        )
        prediction_artifact = load_semantic_prediction_artifact(args.predictions)
        verify_prediction_provenance(
            fixture=loaded.historical_v1,
            artifact=prediction_artifact,
            repository_root=Path.cwd(),
        )
        evaluation = evaluate_benchmark_v2(loaded)
        score = score_benchmark_v2(
            evaluation=evaluation,
            predictions=prediction_artifact.predictions,
        )
        report = build_benchmark_v2_report(
            fixture_path=args.fixture,
            prediction_path=args.predictions,
            evaluation=evaluation,
            score=score,
            generated_at=_parse_generated_at(args.generated_at),
        )
        content_by_path = {
            args.json_output: json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
            args.markdown_output: render_benchmark_v2_markdown(report),
        }
        if args.check:
            _check_outputs(content_by_path)
        else:
            _write_outputs(content_by_path)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_semantic_benchmark_v2 "
        f"visible={score.total_record_count} "
        f"score_eligible={score.score_eligible_record_count} "
        f"canary_gate={score.canary_gate_status} "
        f"expert_study={evaluation.expert_study_status}",
    )
    action = "Checked" if args.check else "Wrote"
    print(f"{action} JSON report: {args.json_output}")
    print(f"{action} Markdown report: {args.markdown_output}")
    return 0


def _validate_output_paths(args: argparse.Namespace) -> None:
    if args.json_output.suffix.lower() != ".json":
        raise ValueError("JSON output must use a .json extension")
    if args.markdown_output.suffix.lower() != ".md":
        raise ValueError("Markdown output must use a .md extension")
    outputs = (args.json_output, args.markdown_output)
    if paths_alias(*outputs):
        raise ValueError("JSON and Markdown outputs must be different paths")
    if any(
        paths_alias(source, output)
        for source in (args.fixture, args.predictions)
        for output in outputs
    ):
        raise ValueError("benchmark reports must not overwrite source inputs")


def _parse_generated_at(value: str) -> datetime:
    generated_at = datetime.fromisoformat(value)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("--generated-at must include a timezone")
    return generated_at.astimezone(UTC)


def _check_outputs(content_by_path: dict[Path, str]) -> None:
    drifted = [
        str(path)
        for path, expected in content_by_path.items()
        if not path.exists() or path.read_text(encoding="utf-8") != expected
    ]
    if drifted:
        raise ValueError(f"semantic benchmark v2 report drift: {drifted}")


def _write_outputs(content_by_path: dict[Path, str]) -> None:
    for path, content in content_by_path.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
