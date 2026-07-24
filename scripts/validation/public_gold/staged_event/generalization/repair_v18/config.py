"""Frozen V18 identities, paths, order, and operational policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    CASE_ORDER,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT_SECONDS,
    V17Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    DEFAULT_PATHS as V17_DEFAULT_PATHS,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v18-exposed-run-v1"
EXPECTED_BRANCH = "claude/artana-improvement-process-8f2719"
V17_SEALED_HEAD = "db96b23d36513f38c8bd9904292c6406ec33d934"


@dataclass(frozen=True, slots=True)
class V18Paths:
    """New V18 controls and outputs over the byte-frozen V17 package."""

    v17: V17Paths
    anaphoric_locus_rule: Path
    source_tiebreak: Path
    sealed_v17_manifest: Path
    preregistration: Path
    package_review: Path
    result: Path
    report: Path
    receipts: Path
    raw_outputs: Path
    evaluations: Path

    def case(self, case_id: str) -> CaseExecutionPaths:
        stem = f"2026-07-24-{EXPERIMENT_ID}-{case_id}"
        return CaseExecutionPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
            evaluation=self.evaluations / f"{stem}-evaluation.json",
        )


DEFAULT_PATHS = V18Paths(
    v17=V17_DEFAULT_PATHS,
    anaphoric_locus_rule=REPO / "docs/validation/prompts/"
    "2026-07-24-staged-generalization-v18-anaphoric-locus-completeness.md",
    source_tiebreak=REPO / "docs/validation/adjudications/"
    "2026-07-24-staged-generalization-v18-anaphoric-locus-completeness-"
    "tiebreak-v1.json",
    sealed_v17_manifest=REPO / "docs/validation/manifests/"
    "2026-07-24-staged-generalization-v18-sealed-v17-manifest-v1.json",
    preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-24-staged-generalization-v18-exposed-run-v1.json",
    package_review=REPO / "docs/validation/reviews/"
    "2026-07-24-staged-generalization-v18-complete-package-review-v1.json",
    result=REPO / "docs/validation/results/"
    "2026-07-24-staged-generalization-v18-exposed-run-v1.json",
    report=REPO / "docs/validation/reports/"
    "2026-07-24-staged-generalization-v18-exposed-run-v1-final.md",
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
    "V17_SEALED_HEAD",
    "V18Paths",
]
