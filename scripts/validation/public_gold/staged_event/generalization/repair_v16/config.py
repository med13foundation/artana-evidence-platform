"""Frozen V16 identities, paths, order, and operational policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    CASE_ORDER,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT_SECONDS,
    V15Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    DEFAULT_PATHS as V15_DEFAULT_PATHS,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v16-exposed-run-v1"
EXPECTED_BRANCH = "alvaro/tg04-source-general-claim-verification-v16"
V15_SEALED_HEAD = "06fd697b4dac60fad396e104c8cf7f7005746fdc"


@dataclass(frozen=True, slots=True)
class V16Paths:
    """New V16 controls and outputs over the byte-frozen V15 package."""

    v15: V15Paths
    scope_rule: Path
    source_tiebreak: Path
    schema_review: Path
    sealed_v15_manifest: Path
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


DEFAULT_PATHS = V16Paths(
    v15=V15_DEFAULT_PATHS,
    scope_rule=REPO / "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v16-participant-scope-and-partitive.md",
    source_tiebreak=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v16-source-scope-tiebreak-v1.json",
    schema_review=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v16-minimal-schema-review-v1.json",
    sealed_v15_manifest=REPO / "docs/validation/manifests/"
    "2026-07-23-staged-generalization-v16-sealed-v15-manifest-v1.json",
    preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v16-exposed-run-v1.json",
    package_review=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v16-complete-package-review-v1.json",
    result=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v16-exposed-run-v1.json",
    report=REPO / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v16-exposed-run-v1-final.md",
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
    "V15_SEALED_HEAD",
    "V16Paths",
]
