"""Frozen paths and budgets for the V5 dual-lane grading checkpoint."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v5"
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
class GradingArtifactPaths:
    packet: Path
    evidence: Path
    schema: Path
    first_review: Path
    second_review: Path
    tiebreaker_review: Path
    policy: Path


@dataclass(frozen=True, slots=True)
class ExperimentPaths:
    panel: Path
    prompt: Path
    preregistration: Path
    result: Path
    offline_replay: Path
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


_ADJUDICATIONS = REPO / "docs/validation/adjudications"
DEFAULT_PATHS = ExperimentPaths(
    panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v5.json",
    prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v3.md",
    preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-staged-generalization-v5.json",
    result=REPO / "docs/validation/results/2026-07-22-staged-generalization-v5.json",
    offline_replay=REPO
    / "docs/validation/results/2026-07-22-staged-generalization-v5-v4-offline-replay.json",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    grading=GradingArtifactPaths(
        packet=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-blinded-context-packets.json",
        evidence=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-primary-source-evidence.json",
        schema=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-context-review.schema.json",
        first_review=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-grader-a.json",
        second_review=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-grader-b.json",
        tiebreaker_review=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-grader-c.json",
        policy=_ADJUDICATIONS
        / "2026-07-22-staged-generalization-v5-dual-lane-policy.json",
    ),
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
    "GradingArtifactPaths",
]
