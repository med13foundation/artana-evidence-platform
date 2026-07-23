"""Frozen V14 identities, paths, order, and operational policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    DEFAULT_PATHS as V13_DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    V13Paths,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v14-exposed-run-v1"
EXPECTED_BRANCH = "alvaro/tg04-source-general-claim-verification-v14"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
REQUEST_TIMEOUT_SECONDS = 1800.0
GLOBAL_MAX_CALLS = 6
GLOBAL_MAX_COST_USD = 5.0
V13_SEALED_HEAD = "cb9b912c83c773032e3b14971a9a7a8103900f0f"

# The participant-boundary regression is observed before the repaired target.
CASE_ORDER = (
    "generalization-comparison-canary",
    "generalization-drug-sensitivity",
    "generalization-uncertainty",
    "generalization-explicit-nested-cause",
    "generalization-negated-association",
    "generalization-null-statistics",
)


@dataclass(frozen=True, slots=True)
class V14Paths:
    """New V14 controls and outputs over the byte-frozen V13 package."""

    v13: V13Paths
    participant_rule: Path
    consensus: Path
    span_review_a: Path
    span_review_b: Path
    role_review_a: Path
    role_review_b: Path
    rule_audit: Path
    wording_review_a: Path
    wording_review_b: Path
    sealed_v13_manifest: Path
    preregistration: Path
    package_review: Path
    result: Path
    report: Path
    receipts: Path
    raw_outputs: Path
    evaluations: Path

    def case(self, case_id: str) -> CaseExecutionPaths:
        stem = f"2026-07-23-{EXPERIMENT_ID}-{case_id}"
        return CaseExecutionPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
            evaluation=self.evaluations / f"{stem}-evaluation.json",
        )


DEFAULT_PATHS = V14Paths(
    v13=V13_DEFAULT_PATHS,
    participant_rule=REPO / "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v14-complete-participant-denotation.md",
    consensus=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v14-participant-and-role-consensus-v1.json",
    span_review_a=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-participant-span-reviewer-a-v1.json",
    span_review_b=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-participant-span-reviewer-b-v1.json",
    role_review_a=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-inner-role-reviewer-a-v1.json",
    role_review_b=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-inner-role-reviewer-b-v1.json",
    rule_audit=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v14-participant-rule-offline-audit-v1.json",
    wording_review_a=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-rule-wording-reviewer-a-v1.json",
    wording_review_b=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-rule-wording-reviewer-b-v1.json",
    sealed_v13_manifest=REPO / "docs/validation/manifests/"
    "2026-07-23-staged-generalization-v14-sealed-v13-manifest-v1.json",
    preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v14-exposed-run-v1.json",
    package_review=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v14-complete-package-review-v1.json",
    result=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v14-exposed-run-v1.json",
    report=REPO / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v14-exposed-run-v1-final.md",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    evaluations=REPO / "docs/validation/evaluations",
)


__all__ = [
    "CASE_ORDER",
    "DEFAULT_PATHS",
    "EXPECTED_BRANCH",
    "EXPERIMENT_ID",
    "GLOBAL_MAX_CALLS",
    "GLOBAL_MAX_COST_USD",
    "MODEL",
    "REASONING_EFFORT",
    "REPO",
    "REQUEST_TIMEOUT_SECONDS",
    "V13_SEALED_HEAD",
    "V14Paths",
]
