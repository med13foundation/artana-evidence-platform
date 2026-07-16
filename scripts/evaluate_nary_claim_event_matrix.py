#!/usr/bin/env python3
"""Evaluate six TG-04 arm reports and emit the deterministic decision."""

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

from scripts.validation.claim_events.evaluation import evaluate_matrix
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    load_fixture,
    require_frozen_development_fixture,
)
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs=6, type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH)
    require_frozen_development_fixture(fixture)
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    result = evaluate_matrix(
        fixture,
        reports,
        provider_receipt_verifier=OpenAIProviderReceiptVerifier.from_environment(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        )
    print(args.output)
    return 0 if result["gate_passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
