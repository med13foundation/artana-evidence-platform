"""Frozen paths, identity, and budgets for the fresh-CG experiment."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "fresh-cg-occurrence-v2-v1"
BRANCH = "alvaro/tg04-source-general-claim-verification"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
MAX_OUTPUT_TOKENS = 20_000
MAX_TOTAL_TOKENS = 24_000
MAX_LATENCY_SECONDS = 900.0
MAX_COST_USD = 0.15
GLOBAL_MAX_CALLS = 8
GLOBAL_MAX_COST_USD = 1.20


@dataclass(frozen=True, slots=True)
class CaseArtifactPaths:
    attempt: Path
    bundle: Path
    receipt: Path
    raw_output: Path


@dataclass(frozen=True, slots=True)
class ExperimentPaths:
    selection: Path
    review_packet: Path
    review_prompt: Path
    review_schema: Path
    reviewer_a: Path
    reviewer_b: Path
    tiebreak_request: Path
    tiebreaker: Path
    reference: Path
    scientific_prompt: Path
    binding_prompt: Path
    preregistration: Path
    result: Path
    report: Path
    receipts: Path
    raw_outputs: Path

    def case(self, case_id: str) -> CaseArtifactPaths:
        stem = f"2026-07-22-{EXPERIMENT_ID}-{case_id}"
        return CaseArtifactPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
        )


DEFAULT_PATHS = ExperimentPaths(
    selection=REPO / "docs/validation/fixtures/2026-07-22-fresh-cg-selection-v1.json",
    review_packet=REPO
    / "docs/validation/fixtures/2026-07-22-fresh-cg-source-semantic-review-packet-v1.json",
    review_prompt=REPO
    / "docs/validation/prompts/2026-07-22-fresh-cg-source-semantic-review-v1.md",
    review_schema=REPO
    / "docs/validation/schemas/2026-07-22-fresh-cg-source-semantic-review-v1.schema.json",
    reviewer_a=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-source-semantic-reviewer-a-v1.json",
    reviewer_b=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-source-semantic-reviewer-b-v1.json",
    tiebreak_request=REPO
    / "docs/validation/fixtures/2026-07-22-fresh-cg-source-semantic-tiebreak-request-v1.json",
    tiebreaker=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-source-semantic-tiebreaker-v1.json",
    reference=REPO
    / "docs/validation/references/2026-07-22-fresh-cg-two-lane-reference-v1.json",
    scientific_prompt=REPO
    / "docs/validation/prompts/2026-07-22-staged-generalization-v9.md",
    binding_prompt=REPO
    / "docs/validation/prompts/2026-07-22-fresh-cg-occurrence-bindings-v2.md",
    preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v1.json",
    result=REPO
    / "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v1.json",
    report=REPO
    / "docs/validation/reports/2026-07-22-fresh-cg-occurrence-v2-v1-final.md",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
)


__all__ = [
    "BRANCH",
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
