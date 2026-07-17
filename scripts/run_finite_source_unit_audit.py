#!/usr/bin/env python3
"""Run the one-shot TG-04 finite source-unit scientific diagnostic."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.validation.claim_events.finite_source_unit.runner import (  # noqa: E402
    run_finite_source_unit_pilot,
)
from scripts.validation.claim_events.fixture import (  # noqa: E402
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    load_fixture,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=_REPO_ROOT / DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    )
    args = parser.parse_args()
    report = run_finite_source_unit_pilot(
        fixture=load_fixture(args.fixture),
        run_id=args.run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
