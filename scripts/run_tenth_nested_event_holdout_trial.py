#!/usr/bin/env python3
"""Run one create-once V10 scientific-quality holdout repeat."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT, _REPO_ROOT / "services"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.runner import (  # noqa: E402
    preflight_tenth_nested_event_holdout_trial,
    run_tenth_nested_event_holdout_trial,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.sequence import (  # noqa: E402
    finalize_tenth_repeat,
    reserve_tenth_repeat,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat-index", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-report", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    preflight_tenth_nested_event_holdout_trial(archive=args.archive)
    authorization = reserve_tenth_repeat(
        repository_root=_REPO_ROOT,
        run_id=args.run_id,
        repeat_index=args.repeat_index,
        output=args.output,
        previous_report=args.previous_report,
    )
    report = run_tenth_nested_event_holdout_trial(
        archive=args.archive,
        run_id=args.run_id,
        repeat_index=args.repeat_index,
        authorization=authorization,
    )
    with args.output.open("x", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        )
    print(args.output)
    finalize_tenth_repeat(authorization, report=report)
    return tenth_nested_holdout_exit_code(report)


def tenth_nested_holdout_exit_code(report: dict[str, object]) -> int:
    gate = report.get("gate")
    return 0 if isinstance(gate, dict) and gate.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
