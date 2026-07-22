"""Frozen configuration and artifact paths for one exposed generalization run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
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

    def case(self, case_id: str) -> CaseArtifactPaths:
        stem = f"2026-07-22-staged-generalization-v3-{case_id}"
        return CaseArtifactPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
        )


DEFAULT_PATHS = ExperimentPaths(
    panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v3.json",
    prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v3.md",
    preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-staged-generalization-v3.json",
    result=REPO / "docs/validation/results/2026-07-22-staged-generalization-v3.json",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
)


__all__ = [
    "DEFAULT_PATHS",
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
