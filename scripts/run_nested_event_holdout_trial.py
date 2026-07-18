#!/usr/bin/env python3
"""Run one create-once hidden nested-event holdout repeat."""

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
    run_nested_event_holdout_trial,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat-index", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_nested_event_holdout_trial(
        archive=args.archive,
        run_id=args.run_id,
        repeat_index=args.repeat_index,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        )
    print(args.output)
    return nested_holdout_trial_exit_code(report)


def nested_holdout_trial_exit_code(report: dict[str, object]) -> int:
    gate = report.get("gate")
    return 0 if isinstance(gate, dict) and gate.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
