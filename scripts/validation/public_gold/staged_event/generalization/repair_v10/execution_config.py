"""Frozen paths and operational policy for the V10 exposed execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as V5_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    GradingArtifactPaths,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v10-exposed-run-v1"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
GLOBAL_MAX_CALLS = 6
GLOBAL_MAX_COST_USD = 5.0


@dataclass(frozen=True, slots=True)
class CaseExecutionPaths:
    """Custody and evaluation paths for one exposed case."""

    attempt: Path
    bundle: Path
    receipt: Path
    raw_output: Path
    evaluation: Path


@dataclass(frozen=True, slots=True)
class V10ExecutionPaths:
    """All immutable inputs and forward-only outputs for the V10 execution."""

    panel: Path
    prompt: Path
    offline_preregistration: Path
    execution_preregistration: Path
    historical_provenance: Path
    v9_preregistration: Path
    v9_result: Path
    v9_raw_outputs: Path
    result: Path
    report: Path
    receipts: Path
    raw_outputs: Path
    evaluations: Path
    grading: GradingArtifactPaths

    def case(self, case_id: str) -> CaseExecutionPaths:
        stem = f"2026-07-22-{EXPERIMENT_ID}-{case_id}"
        return CaseExecutionPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
            evaluation=self.evaluations / f"{stem}-evaluation.json",
        )

    def v9_raw_output(self, case_id: str) -> Path:
        return self.v9_raw_outputs / (
            f"2026-07-22-staged-generalization-v9-{case_id}-raw.json"
        )


DEFAULT_PATHS = V10ExecutionPaths(
    panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v9.json",
    prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v10.md",
    offline_preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-staged-generalization-v10.json",
    execution_preregistration=REPO
    / "docs/validation/preregistrations/"
    "2026-07-22-staged-generalization-v10-exposed-run-v1.json",
    historical_provenance=REPO
    / "docs/validation/provenance/"
    "2026-07-22-v9-historical-reproducibility-isolation-v1.json",
    v9_preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-staged-generalization-v9.json",
    v9_result=REPO
    / "docs/validation/results/2026-07-22-staged-generalization-v9.json",
    v9_raw_outputs=REPO / "docs/validation/results",
    result=REPO
    / "docs/validation/results/2026-07-22-staged-generalization-v10-exposed-run-v1.json",
    report=REPO
    / "docs/validation/reports/"
    "2026-07-22-staged-generalization-v10-exposed-run-v1-final.md",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    evaluations=REPO / "docs/validation/evaluations",
    grading=V5_PATHS.grading,
)


__all__ = [
    "DEFAULT_PATHS",
    "EXPERIMENT_ID",
    "GLOBAL_MAX_CALLS",
    "GLOBAL_MAX_COST_USD",
    "MODEL",
    "REASONING_EFFORT",
    "CaseExecutionPaths",
    "V10ExecutionPaths",
]
