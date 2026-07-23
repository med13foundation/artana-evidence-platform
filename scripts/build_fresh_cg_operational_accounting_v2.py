#!/usr/bin/env python3
"""Build the non-scientific accounting correction for sealed fresh-CG V1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.validation.provider_receipt_boundary.operational_accounting_v2 import (  # noqa: E402
    ZERO_USAGE,
    OperationalAccountingV2,
    usage_from_rejection_diagnostics,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (  # noqa: E402
    write_json_atomic,
)

SOURCE = REPO / ("docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json")
OUTPUT = REPO / (
    "docs/validation/results/"
    "2026-07-22-fresh-cg-occurrence-v2-v1-operational-accounting-v2.json"
)


def build_artifact() -> dict[str, object]:
    loaded: object = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("sealed fresh-CG result must be an object")
    if loaded.get("decision") != "INVALID_EXPERIMENT_EXECUTION":
        raise ValueError("operational correction requires the sealed invalid result")
    if loaded.get("scientific_metrics_calculated") is not False:
        raise ValueError("sealed result unexpectedly contains scientific metrics")
    for key in ("input_tokens", "output_tokens", "total_tokens", "cost_usd"):
        if loaded.get(key) != 0:
            raise ValueError("sealed admitted scientific accounting changed")
    diagnostics = _required_dict(loaded, "diagnostics")
    rejected = usage_from_rejection_diagnostics(diagnostics)
    provider_calls = loaded.get("provider_calls")
    if not isinstance(provider_calls, int):
        raise TypeError("sealed provider call count is absent")
    accounting = OperationalAccountingV2(
        provider_creation_calls=provider_calls,
        admitted_provider_calls=0,
        admitted_scientific_usage=ZERO_USAGE,
        rejected_provider_usage=(rejected,),
        global_max_cost_usd=1.20,
    )
    return {
        **accounting.as_json(),
        "experiment_id": loaded.get("experiment_id"),
        "source_result_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "source_decision": loaded.get("decision"),
        "source_failure_stage": loaded.get("failure_stage"),
        "source_response_ids": loaded.get("response_ids"),
        "provider_boundary_root_cause_class": "B_PROVIDER_ENFORCEMENT_DEFECT",
        "scientific_admission": False,
        "scientific_credit": False,
        "provider_execution_authorized": False,
        "provider_execution_blocker": (
            "documented max_output_tokens ceiling was not enforced by provider"
        ),
        "historical_artifacts_rewritten": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = build_artifact()
    if args.check:
        actual: object = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if actual != expected:
            raise ValueError("checked-in operational accounting differs")
        print("FRESH_CG_OPERATIONAL_ACCOUNTING_V2_VERIFIED")
    else:
        write_json_atomic(OUTPUT, expected)
        print("FRESH_CG_OPERATIONAL_ACCOUNTING_V2_WRITTEN")
    return 0


def _required_dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"sealed {key} is absent")
    return item


if __name__ == "__main__":
    raise SystemExit(main())
