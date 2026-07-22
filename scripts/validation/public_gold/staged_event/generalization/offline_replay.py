"""Non-creditable V3 replay used to validate V4 evidence identity offline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.evaluation import (
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.panel import build_panel

REPO = Path(__file__).resolve().parents[5]
V3_RAW_OUTPUTS = (
    REPO / "docs/validation/results/"
    "2026-07-22-staged-generalization-v3-generalization-comparison-canary-raw.json",
    REPO / "docs/validation/results/"
    "2026-07-22-staged-generalization-v3-generalization-null-statistics-raw.json",
)


def replay_v3_diagnostics() -> dict[str, object]:
    cases = {case.case_id: case for case in build_panel()}
    outputs = tuple(
        StagedGeneralizationOutput.model_validate_json(path.read_text(encoding="utf-8"))
        for path in V3_RAW_OUTPUTS
    )
    metrics = tuple(evaluate_case(cases[output.case_id], output) for output in outputs)
    replay_metrics = aggregate(metrics)
    replay_passed = all(item.passed for item in metrics)
    return {
        "schema_version": "artana.staged_generalization.v4_offline_replay",
        "decision": (
            "OFFLINE_IDENTITY_HARDENING_PASS"
            if replay_passed
            else "OFFLINE_IDENTITY_HARDENING_FAIL"
        ),
        "historical_experiment": "staged-generalization-v3",
        "historical_result_changed": False,
        "qualification_credit": False,
        "provider_calls": 0,
        "graph_writes": 0,
        "trusted_promotion": False,
        "source_artifact_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in V3_RAW_OUTPUTS
        },
        "replay_metrics": replay_metrics,
    }


def write_replay(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(replay_v3_diagnostics(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = ["V3_RAW_OUTPUTS", "replay_v3_diagnostics", "write_replay"]
