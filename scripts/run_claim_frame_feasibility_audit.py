#!/usr/bin/env python3
"""Run or compare the deterministic TG-03 ClaimFrame benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (  # noqa: E402
    CLAIM_FRAME_PIPELINE_PROMPT_VERSION,
)

from scripts.validation.claim_frames.fixture import (  # noqa: E402
    DEFAULT_FIXTURE_PATH,
    BenchmarkFixture,
    load_fixture,
)
from scripts.validation.claim_frames.metrics import (  # noqa: E402
    compare_three_reports,
)
from scripts.validation.claim_frames.provider_receipts import (  # noqa: E402
    OpenAIProviderReceiptVerifier,
)
from scripts.validation.claim_frames.reporting import (  # noqa: E402
    write_reports,
)
from scripts.validation.claim_frames.runner import (  # noqa: E402
    configured_model_id,
    run_live_benchmark,
)


def _parse_args(argv: tuple[str, ...] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or compare the strict TG-03 ClaimFrame benchmark.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=_REPO_ROOT / DEFAULT_FIXTURE_PATH,
    )
    parser.add_argument(
        "--compare",
        nargs=3,
        type=Path,
        metavar=("RUN_01", "RUN_02", "RUN_03"),
        help="Compare exactly three saved run JSON reports.",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--case-id",
        help=(
            "Run one case selected from the fully validated sealed fixture. "
            "This is a development diagnostic, not a merge-gate comparison."
        ),
    )
    return parser.parse_args(argv)


def main(argv: tuple[str, ...] | None = None) -> int:
    """Run one strict pass or compare three saved passes."""

    args = _parse_args(argv)
    try:
        fixture = load_fixture(_resolve(args.fixture))
        fixture = _select_case(
            fixture,
            case_id=args.case_id,
            comparing=args.compare is not None,
        )
        json_path, markdown_path = _report_paths(args)
        if args.compare is not None:
            report = compare_three_reports(
                tuple(_load_json(_resolve(path)) for path in args.compare),
                fixture,
                provider_receipt_verifier=(
                    OpenAIProviderReceiptVerifier.from_environment()
                ),
            )
            write_reports(
                report=report,
                json_path=json_path,
                markdown_path=markdown_path,
            )
            print(f"Wrote JSON report: {json_path}")
            print(f"Wrote Markdown report: {markdown_path}")
            return 0 if report["gate_passed"] is True else 1

        model_id = configured_model_id()
        report = run_live_benchmark(
            fixture=fixture,
            run_id=args.run_id or f"tg03-{uuid4().hex}",
            model_id=model_id,
            prompt_version=CLAIM_FRAME_PIPELINE_PROMPT_VERSION,
            generated_at=datetime.now(UTC),
        )
        write_reports(
            report=report,
            json_path=json_path,
            markdown_path=markdown_path,
        )
        print(f"Wrote JSON report: {json_path}")
        print(f"Wrote Markdown report: {markdown_path}")
        return 0 if report["gate_passed"] is True else 1
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _select_case(
    fixture: BenchmarkFixture,
    *,
    case_id: str | None,
    comparing: bool,
) -> BenchmarkFixture:
    if case_id is None:
        return fixture
    if comparing:
        raise ValueError("--case-id cannot be combined with --compare")
    matching_cases = tuple(case for case in fixture.cases if case.case_id == case_id)
    if len(matching_cases) != 1:
        raise ValueError(f"unknown benchmark case_id: {case_id}")
    return replace(fixture, cases=matching_cases)


def _report_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    explicit = (args.json_output, args.markdown_output)
    if any(path is not None for path in explicit):
        if not all(path is not None for path in explicit):
            raise ValueError("--json-output and --markdown-output must be paired")
        if args.output_dir is not None:
            raise ValueError("--output-dir cannot be combined with explicit outputs")
        return explicit[0], explicit[1]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory = args.output_dir or (
        _REPO_ROOT / "reports" / "claim_frame_feasibility" / stamp
    )
    stem = (
        "claim_frame_feasibility_comparison"
        if args.compare
        else "claim_frame_feasibility_run"
    )
    return directory / f"{stem}.json", directory / f"{stem}.md"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else _REPO_ROOT / path


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"report must be a JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
