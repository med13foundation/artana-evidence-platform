"""Frozen paths and budgets for the V6 referential-grounding checkpoint."""

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
EXPERIMENT_ID = "staged-generalization-v6"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 20_000
MAX_TOTAL_TOKENS = 24_000
MAX_LATENCY_SECONDS = 900.0
MAX_COST_USD = 0.15
GLOBAL_MAX_CALLS = 6
GLOBAL_MAX_COST_USD = 0.90


@dataclass(frozen=True, slots=True)
class CaseArtifactPaths:
    attempt: Path
    bundle: Path
    receipt: Path
    raw_output: Path


@dataclass(frozen=True, slots=True)
class ExperimentPaths:
    panel: Path
    prompt: Path
    preregistration: Path
    result: Path
    receipts: Path
    raw_outputs: Path
    grading: GradingArtifactPaths

    def case(self, case_id: str) -> CaseArtifactPaths:
        stem = f"2026-07-22-{EXPERIMENT_ID}-{case_id}"
        return CaseArtifactPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
        )


DEFAULT_PATHS = ExperimentPaths(
    panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v6.json",
    prompt=REPO
    / "docs/validation/prompts/2026-07-22-staged-generalization-v6.md",
    preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-staged-generalization-v6.json",
    result=REPO / "docs/validation/results/2026-07-22-staged-generalization-v6.json",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    grading=V5_PATHS.grading,
)


__all__ = [
    "DEFAULT_PATHS",
    "EXPERIMENT_ID",
    "GLOBAL_MAX_CALLS",
    "GLOBAL_MAX_COST_USD",
    "MAX_COST_USD",
    "MAX_LATENCY_SECONDS",
    "MAX_OUTPUT_TOKENS",
    "MAX_TOTAL_TOKENS",
    "MODEL",
    "REASONING_EFFORT",
    "CaseArtifactPaths",
    "ExperimentPaths",
]
