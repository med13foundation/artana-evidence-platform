#!/usr/bin/env python3
"""Generate JSON and Markdown reports for the semantic failure corpus."""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    load_semantic_prediction_artifact,
    verify_prediction_provenance,
)
from artana_evidence_api.evidence_selection.diagnostics.report import (
    build_semantic_diagnostic_report,
    render_semantic_diagnostic_markdown,
)
from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    score_semantic_diagnostic,
)


class _PreparedOutput(NamedTuple):
    final_path: Path
    temporary_path: Path
    backup_path: Path | None


def _parse_args(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the evidence-selection semantic baseline report.",
    )
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--generated-at", required=True, type=str)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Generate reports with rollback for recoverable filesystem errors."""

    args = _parse_args(argv)
    try:
        fixture_report_path = args.fixture
        prediction_report_path = args.predictions
        fixture_path = fixture_report_path.resolve()
        prediction_path = prediction_report_path.resolve()
        json_output = args.json_output.resolve()
        markdown_output = args.markdown_output.resolve()
        _validate_paths(
            fixture_path=fixture_path,
            prediction_path=prediction_path,
            json_output=json_output,
            markdown_output=markdown_output,
        )
        fixture = load_semantic_diagnostic_fixture(fixture_path)
        prediction_artifact = load_semantic_prediction_artifact(prediction_path)
        verify_prediction_provenance(
            fixture=fixture,
            artifact=prediction_artifact,
            repository_root=Path.cwd(),
        )
        score = score_semantic_diagnostic(fixture, prediction_artifact.predictions)
        generated_at = _parse_generated_at(args.generated_at)
        report = build_semantic_diagnostic_report(
            fixture_path=fixture_report_path,
            fixture=fixture,
            prediction_path=prediction_report_path,
            prediction_artifact=prediction_artifact,
            score=score,
            generated_at=generated_at.astimezone(UTC),
        )
        content_by_path = {
            json_output: json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
            markdown_output: render_semantic_diagnostic_markdown(report),
        }
        if args.check:
            _check_outputs(content_by_path)
        else:
            _publish_outputs(content_by_path)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_semantic_baseline "
        f"cases={score.scored_case_count} "
        f"precision={score.micro.precision:.4f} end_to_end_recall={score.micro.end_to_end_recall:.4f}",
    )
    output_action = "Checked" if args.check else "Wrote"
    print(f"{output_action} JSON report: {json_output}")
    print(f"{output_action} Markdown report: {markdown_output}")
    return 0


def _validate_paths(
    *,
    fixture_path: Path,
    prediction_path: Path,
    json_output: Path,
    markdown_output: Path,
) -> None:
    if json_output.suffix.lower() != ".json":
        raise ValueError("JSON output must use a .json extension")
    if markdown_output.suffix.lower() != ".md":
        raise ValueError("Markdown output must use a .md extension")
    if _paths_alias(json_output, markdown_output):
        msg = "JSON and Markdown outputs must be different paths."
        raise ValueError(msg)
    if any(
        _paths_alias(source, output)
        for source in (fixture_path, prediction_path)
        for output in (json_output, markdown_output)
    ):
        msg = "Report outputs must not overwrite the source fixture."
        raise ValueError(msg)
    for output in (json_output, markdown_output):
        if output.exists() and output.is_dir():
            msg = f"Report output must be a file path: {output}"
            raise ValueError(msg)


def _paths_alias(left: Path, right: Path) -> bool:
    if str(left).casefold() == str(right).casefold():
        return True
    try:
        return left.samefile(right)
    except OSError:
        return False


def _parse_generated_at(value: str) -> datetime:
    generated_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        raise ValueError("--generated-at must include a timezone")
    return generated_at


def _check_outputs(content_by_path: dict[Path, str]) -> None:
    drifted = [
        path
        for path, expected in content_by_path.items()
        if not path.exists() or path.read_text(encoding="utf-8") != expected
    ]
    if drifted:
        raise ValueError(
            f"semantic baseline report drift: {[str(path) for path in drifted]}"
        )


def _publish_outputs(content_by_path: dict[Path, str]) -> None:  # noqa: PLR0912
    temporary_paths: list[Path] = []
    prepared_outputs: list[_PreparedOutput] = []
    committed = False
    try:
        for final_path, content in content_by_path.items():
            final_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = final_path.with_name(
                f".{final_path.name}.{uuid4().hex}.tmp",
            )
            temporary_path.write_text(content, encoding="utf-8")
            temporary_paths.append(temporary_path)
        for final_path, temporary_path in zip(
            content_by_path,
            temporary_paths,
            strict=True,
        ):
            backup_path = None
            if final_path.exists():
                backup_path = final_path.with_name(
                    f".{final_path.name}.{uuid4().hex}.bak",
                )
                final_path.replace(backup_path)
            prepared_outputs.append(
                _PreparedOutput(
                    final_path=final_path,
                    temporary_path=temporary_path,
                    backup_path=backup_path,
                ),
            )
        for prepared in prepared_outputs:
            prepared.temporary_path.replace(prepared.final_path)
        committed = True
        for prepared in prepared_outputs:
            _discard_backup(prepared.backup_path)
    except OSError:
        if not committed:
            for prepared in reversed(prepared_outputs):
                _remove_if_present(prepared.final_path)
                if prepared.backup_path is not None and prepared.backup_path.exists():
                    prepared.backup_path.replace(prepared.final_path)
        raise
    finally:
        for temporary_path in temporary_paths:
            _remove_if_present(temporary_path)
        if committed:
            for prepared in prepared_outputs:
                _discard_backup(prepared.backup_path)


def _remove_if_present(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)


def _discard_backup(path: Path | None) -> None:
    with suppress(OSError):
        _remove_if_present(path)


if __name__ == "__main__":
    raise SystemExit(main())
