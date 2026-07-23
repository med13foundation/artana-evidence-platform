"""Frozen V15 identities, paths, order, and operational policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    CASE_ORDER,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT_SECONDS,
    V14Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.config import (
    DEFAULT_PATHS as V14_DEFAULT_PATHS,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v15-exposed-run-v1"
EXPECTED_BRANCH = "alvaro/tg04-source-general-claim-verification-v15"
V14_SEALED_HEAD = "f4aea428aaf7105d9bb8a2f90a1dc52accab44ab"
V15_AUTHORIZATION_HEAD = "ba56285a7187199414451319cc7e448a15e78003"
V15_AUTHORIZATION_SHA256 = (
    "ae53055301947346995308a3fda01b6e547265d1e61ca3930e41d829a1b57898"
)


@dataclass(frozen=True, slots=True)
class V15Paths:
    """New V15 controls and outputs over the byte-frozen V14 package."""

    v14: V14Paths
    focus_occurrence_rule: Path
    consensus: Path
    wording_review_a: Path
    wording_review_b: Path
    offline_audit: Path
    sealed_v14_manifest: Path
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


DEFAULT_PATHS = V15Paths(
    v14=V14_DEFAULT_PATHS,
    focus_occurrence_rule=REPO / "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v15-focus-closure-and-"
    "role-bearing-occurrence-custody.md",
    consensus=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v14-to-v15-focus-closure-consensus-v1.json",
    wording_review_a=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v15-rule-wording-reviewer-a-v1.json",
    wording_review_b=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v15-rule-wording-reviewer-b-v1.json",
    offline_audit=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v15-focus-closure-offline-audit-v1.json",
    sealed_v14_manifest=REPO / "docs/validation/manifests/"
    "2026-07-23-staged-generalization-v15-sealed-v14-manifest-v1.json",
    preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v15-exposed-run-v1.json",
    package_review=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v15-complete-package-review-v1.json",
    result=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v15-exposed-run-v1.json",
    report=REPO / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v15-exposed-run-v1-final.md",
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
    "V14_SEALED_HEAD",
    "V15_AUTHORIZATION_HEAD",
    "V15_AUTHORIZATION_SHA256",
    "V15Paths",
]
