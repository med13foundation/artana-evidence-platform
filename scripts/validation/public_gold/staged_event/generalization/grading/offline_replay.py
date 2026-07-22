"""Non-creditable V4 replay through the frozen V5 dual-lane grader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import build_panel

V4_RAW_OUTPUT_NAMES = (
    "2026-07-22-staged-generalization-v4-generalization-comparison-canary-raw.json",
    "2026-07-22-staged-generalization-v4-generalization-null-statistics-raw.json",
)


def replay_v4_diagnostics(
    paths: ExperimentPaths = DEFAULT_PATHS,
) -> dict[str, object]:
    policy = verify_frozen_policy(paths.grading)
    cases = {case.case_id: case for case in build_panel()}
    raw_paths = tuple(paths.raw_outputs / name for name in V4_RAW_OUTPUT_NAMES)
    outputs = tuple(
        StagedGeneralizationOutput.model_validate_json(path.read_text(encoding="utf-8"))
        for path in raw_paths
    )
    metrics = tuple(
        evaluate_case(
            cases[output.case_id],
            output,
            case_policy(policy, output.case_id),
        )
        for output in outputs
    )
    replay_metrics = aggregate(metrics)
    return {
        "schema_version": "artana.staged_generalization.v5_v4_offline_replay.v1",
        "decision": (
            "OFFLINE_DUAL_LANE_GRADER_PASS"
            if all(metric.passed for metric in metrics)
            else "OFFLINE_DUAL_LANE_GRADER_FAIL"
        ),
        "historical_experiment": "staged-generalization-v4",
        "historical_terminal_decision": "PIVOT_WITH_EVIDENCE",
        "historical_result_changed": False,
        "qualification_credit": False,
        "provider_calls": 0,
        "graph_writes": 0,
        "trusted_promotion": False,
        "policy_sha256": policy_sha256(policy),
        "source_artifact_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in raw_paths
        },
        "replay_metrics": replay_metrics,
    }


def write_replay(path: Path, paths: ExperimentPaths = DEFAULT_PATHS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(replay_v4_diagnostics(paths), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = ["V4_RAW_OUTPUT_NAMES", "replay_v4_diagnostics", "write_replay"]
