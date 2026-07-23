"""Frozen identities, paths, and operational policy for V11 exposed run 2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as V5_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    GradingArtifactPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v11-exposed-run-v2"
QUALIFICATION_ID = "staged-generalization-v11-foreground-qualification-v1"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
FOREGROUND_REQUEST_TIMEOUT_SECONDS = 1800.0
QUALIFICATION_TIMEOUT_SECONDS = 600.0
GLOBAL_MAX_CALLS = 6
GLOBAL_MAX_COST_USD = 5.0
CASE_ORDER = (
    "generalization-comparison-canary",
    "generalization-uncertainty",
    "generalization-negated-association",
    "generalization-null-statistics",
    "generalization-drug-sensitivity",
    "generalization-explicit-nested-cause",
)


@dataclass(frozen=True, slots=True)
class QualificationPaths:
    preregistration: Path
    attempt: Path
    bundle: Path
    receipt: Path
    raw_output: Path
    result: Path


@dataclass(frozen=True, slots=True)
class V11Run2Paths:
    """Immutable scientific inputs and forward-only run-2 outputs."""

    panel: Path
    prompt: Path
    preregistration: Path
    operational_diagnosis: Path
    report_correction: Path
    run1_preregistration: Path
    run1_result: Path
    run1_report: Path
    run1_seal: Path
    run1_attempt: Path
    run1_late_status: Path
    v9_result: Path
    v10_result: Path
    qualification: QualificationPaths
    result: Path
    report: Path
    fresh_preregistration: Path
    receipts: Path
    raw_outputs: Path
    evaluations: Path
    grading: GradingArtifactPaths

    def case(self, case_id: str) -> CaseExecutionPaths:
        stem = f"2026-07-23-{EXPERIMENT_ID}-{case_id}"
        return CaseExecutionPaths(
            attempt=self.receipts / f"{stem}-attempt.json",
            bundle=self.receipts / f"{stem}-custody.json",
            receipt=self.receipts / f"{stem}.json",
            raw_output=self.raw_outputs / f"{stem}-raw.json",
            evaluation=self.evaluations / f"{stem}-evaluation.json",
        )


DEFAULT_PATHS = V11Run2Paths(
    panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v9.json",
    prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v11.md",
    preregistration=REPO
    / "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2.json",
    operational_diagnosis=REPO
    / "docs/validation/provenance/"
    "2026-07-23-staged-generalization-v11-run1-queue-diagnosis-v1.json",
    report_correction=REPO
    / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v11-run1-report-correction.md",
    run1_preregistration=REPO
    / "docs/validation/preregistrations/"
    "2026-07-22-staged-generalization-v11-exposed-run-v1.json",
    run1_result=REPO
    / "docs/validation/results/"
    "2026-07-22-staged-generalization-v11-exposed-run-v1.json",
    run1_report=REPO
    / "docs/validation/reports/"
    "2026-07-22-staged-generalization-v11-exposed-run-v1-final.md",
    run1_seal=REPO
    / "docs/validation/reports/"
    "2026-07-22-staged-generalization-v11-exposed-run-v1-seal.md",
    run1_attempt=REPO
    / "docs/validation/receipts/"
    "2026-07-22-staged-generalization-v11-exposed-run-v1-"
    "generalization-comparison-canary-attempt.json",
    run1_late_status=REPO
    / "docs/validation/receipts/"
    "2026-07-22-staged-generalization-v11-exposed-run-v1-"
    "generalization-comparison-canary-late-status.json",
    v9_result=REPO
    / "docs/validation/results/2026-07-22-staged-generalization-v9.json",
    v10_result=REPO
    / "docs/validation/results/"
    "2026-07-22-staged-generalization-v10-exposed-run-v1.json",
    qualification=QualificationPaths(
        preregistration=REPO
        / "docs/validation/preregistrations/"
        "2026-07-23-staged-generalization-v11-foreground-qualification-v1.json",
        attempt=REPO
        / "docs/validation/receipts/"
        "2026-07-23-staged-generalization-v11-foreground-qualification-v1-"
        "attempt.json",
        bundle=REPO
        / "docs/validation/receipts/"
        "2026-07-23-staged-generalization-v11-foreground-qualification-v1-"
        "custody.json",
        receipt=REPO
        / "docs/validation/receipts/"
        "2026-07-23-staged-generalization-v11-foreground-qualification-v1.json",
        raw_output=REPO
        / "docs/validation/results/"
        "2026-07-23-staged-generalization-v11-foreground-qualification-v1-"
        "raw.json",
        result=REPO
        / "docs/validation/results/"
        "2026-07-23-staged-generalization-v11-foreground-qualification-v1.json",
    ),
    result=REPO
    / "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2.json",
    report=REPO
    / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-final.md",
    fresh_preregistration=REPO
    / "docs/validation/preregistrations/"
    "2026-07-23-fresh-cg-after-v11-pass-v1.json",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    evaluations=REPO / "docs/validation/evaluations",
    grading=V5_PATHS.grading,
)


__all__ = [
    "CASE_ORDER",
    "DEFAULT_PATHS",
    "EXPERIMENT_ID",
    "FOREGROUND_REQUEST_TIMEOUT_SECONDS",
    "GLOBAL_MAX_CALLS",
    "GLOBAL_MAX_COST_USD",
    "MODEL",
    "QUALIFICATION_ID",
    "QUALIFICATION_TIMEOUT_SECONDS",
    "REASONING_EFFORT",
    "REPO",
    "QualificationPaths",
    "V11Run2Paths",
]
