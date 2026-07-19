#!/usr/bin/env python3
"""Run the create-once V12 three-agent scientific diagnostic."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT, _REPO_ROOT / "services"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.runner import (  # noqa: E402
    preflight_twelfth_nested_event_holdout_trial,
    recover_twelfth_nested_event_holdout_trial,
    run_twelfth_nested_event_holdout_trial,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.sequence import (  # noqa: E402
    finalize_twelfth_repeat,
    load_executing_twelfth_authorization,
    recover_twelfth_repeat,
    reserve_twelfth_repeat,
    resume_reserved_twelfth_repeat,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat-index", type=int, choices=(1,), required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    preflight_twelfth_nested_event_holdout_trial(archive=args.archive)
    if args.output.exists():
        report = recover_twelfth_repeat(
            repository_root=_REPO_ROOT,
            run_id=args.run_id,
            repeat_index=args.repeat_index,
            output=args.output,
        )
        print(args.output)
        return twelfth_nested_holdout_exit_code(report)
    try:
        authorization = reserve_twelfth_repeat(
            repository_root=_REPO_ROOT,
            run_id=args.run_id,
            repeat_index=args.repeat_index,
            output=args.output,
        )
    except FileExistsError:
        try:
            authorization = resume_reserved_twelfth_repeat(
                repository_root=_REPO_ROOT,
                run_id=args.run_id,
                repeat_index=args.repeat_index,
                output=args.output,
            )
        except RuntimeError:
            authorization = load_executing_twelfth_authorization(
                repository_root=_REPO_ROOT,
                run_id=args.run_id,
                repeat_index=args.repeat_index,
                output=args.output,
            )
            report = recover_twelfth_nested_event_holdout_trial(
                archive=args.archive,
                run_id=args.run_id,
                repeat_index=args.repeat_index,
                authorization=authorization,
            )
            _write_report(args.output, report)
            print(args.output)
            finalize_twelfth_repeat(authorization, report=report)
            return twelfth_nested_holdout_exit_code(report)
    report = run_twelfth_nested_event_holdout_trial(
        archive=args.archive,
        run_id=args.run_id,
        repeat_index=args.repeat_index,
        authorization=authorization,
    )
    _write_report(args.output, report)
    print(args.output)
    finalize_twelfth_repeat(authorization, report=report)
    return twelfth_nested_holdout_exit_code(report)


def twelfth_nested_holdout_exit_code(report: dict[str, object]) -> int:
    gate = report.get("gate")
    return 0 if isinstance(gate, dict) and gate.get("passed") is True else 1


def _write_report(output: Path, report: dict[str, object]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output_file:
            output_file.write(
                json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
            )
            output_file.flush()
            os.fsync(output_file.fileno())
        os.link(temporary, output)
        directory_descriptor = os.open(output.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
