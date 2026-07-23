"""Frozen identity, paths, and operational policy for Fresh-CG V2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "fresh-cg-occurrence-v2-v2"
BRANCH = "alvaro/tg04-source-general-claim-verification"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
GLOBAL_MAX_CALLS = 8
GLOBAL_MAX_COST_USD = 5.0
CONSUMED_CASE_ID = "fresh-cg-pmid-21963494-e3"
REPLACEMENT_DOCUMENT_ID = "PMID-8895545"
RESERVATION_BASE_COMMIT = "6659ed66^"
RESERVATION_SALT = "artana-fresh-cg-holdout-v1:"
V1_PREREGISTRATION_SHA256 = (
    "2b26d580422efedcb44b7de8d8b7e973f2dae04bff020cdce85f3b2b8d4c1b98"
)
V1_ATTEMPT_SHA256 = "52a66f88efbda9982f7d90ff8b83b3eefcfed838e2ea622435ef867ada8538db"
V1_RESULT_SHA256 = "2a006ea527ef2f22670dd1ec61d9a39e099cac415047852a3f44cd4b8b67544a"
V1_REPORT_SHA256 = "2b350fac9cd0cdc9a1207dc85b23cb9fd833b9b4d31af6ba4d3ac71d601c8a6a"


@dataclass(frozen=True, slots=True)
class CaseArtifactPaths:
    attempt: Path
    bundle: Path
    receipt: Path
    raw_output: Path
    evaluation: Path


@dataclass(frozen=True, slots=True)
class ExperimentPaths:
    selection: Path
    review_packet: Path
    replacement_review_packet: Path
    review_prompt: Path
    review_schema: Path
    replacement_review_schema: Path
    reviewer_a: Path
    reviewer_b: Path
    replacement_reviewer_a: Path
    replacement_reviewer_b: Path
    tiebreak_request: Path
    tiebreaker: Path
    replacement_tiebreaker: Path
    reference: Path
    scientific_prompt: Path
    binding_prompt: Path
    preregistration: Path
    result: Path
    report: Path
    receipts: Path
    raw_outputs: Path
    evaluations: Path

    def case(self, case_id: str) -> CaseArtifactPaths:
        stem = f"2026-07-22-{EXPERIMENT_ID}-{case_id}"
        return CaseArtifactPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
            evaluation=self.evaluations / f"{stem}-evaluation.json",
        )


DEFAULT_PATHS = ExperimentPaths(
    selection=REPO / "docs/validation/fixtures/2026-07-22-fresh-cg-selection-v2.json",
    review_packet=REPO
    / "docs/validation/fixtures/2026-07-22-fresh-cg-source-semantic-review-packet-v2.json",
    replacement_review_packet=REPO
    / "docs/validation/fixtures/2026-07-22-fresh-cg-replacement-review-packet-v2.json",
    review_prompt=REPO
    / "docs/validation/prompts/2026-07-22-fresh-cg-source-semantic-review-v1.md",
    review_schema=REPO
    / "docs/validation/schemas/2026-07-22-fresh-cg-source-semantic-review-v1.schema.json",
    replacement_review_schema=REPO
    / "docs/validation/schemas/2026-07-22-fresh-cg-replacement-review-v2.schema.json",
    reviewer_a=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-source-semantic-reviewer-a-v2.json",
    reviewer_b=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-source-semantic-reviewer-b-v2.json",
    replacement_reviewer_a=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-replacement-reviewer-a-v2.json",
    replacement_reviewer_b=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-replacement-reviewer-b-v2.json",
    tiebreak_request=REPO
    / "docs/validation/fixtures/2026-07-22-fresh-cg-source-semantic-tiebreak-request-v2.json",
    tiebreaker=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-source-semantic-tiebreaker-v2.json",
    replacement_tiebreaker=REPO
    / "docs/validation/reviews/2026-07-22-fresh-cg-replacement-tiebreaker-v2.json",
    reference=REPO
    / "docs/validation/references/2026-07-22-fresh-cg-two-lane-reference-v2.json",
    scientific_prompt=REPO
    / "docs/validation/prompts/2026-07-22-staged-generalization-v9.md",
    binding_prompt=REPO
    / "docs/validation/prompts/2026-07-22-fresh-cg-occurrence-bindings-v2.md",
    preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-fresh-cg-occurrence-v2-v2.json",
    result=REPO / "docs/validation/results/2026-07-22-fresh-cg-occurrence-v2-v2.json",
    report=REPO
    / "docs/validation/reports/2026-07-22-fresh-cg-occurrence-v2-v2-final.md",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    evaluations=REPO / "docs/validation/results",
)


__all__ = [
    "BRANCH",
    "CONSUMED_CASE_ID",
    "DEFAULT_PATHS",
    "EXPERIMENT_ID",
    "GLOBAL_MAX_CALLS",
    "GLOBAL_MAX_COST_USD",
    "MODEL",
    "REASONING_EFFORT",
    "REPLACEMENT_DOCUMENT_ID",
    "V1_ATTEMPT_SHA256",
    "V1_PREREGISTRATION_SHA256",
    "V1_REPORT_SHA256",
    "V1_RESULT_SHA256",
    "CaseArtifactPaths",
    "ExperimentPaths",
]
