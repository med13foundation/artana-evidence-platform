"""Frozen V13 identities, paths, case order, and operational policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as GRADING_DEFAULTS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    GradingArtifactPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    CaseExecutionPaths,
)

REPO = Path(__file__).resolve().parents[6]
EXPERIMENT_ID = "staged-generalization-v13-exposed-run-v1"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
REQUEST_TIMEOUT_SECONDS = 1800.0
GLOBAL_MAX_CALLS = 6
GLOBAL_MAX_COST_USD = 5.0
CASE_ORDER = (
    "generalization-comparison-canary",
    "generalization-drug-sensitivity",
    "generalization-explicit-nested-cause",
    "generalization-uncertainty",
    "generalization-negated-association",
    "generalization-null-statistics",
)


@dataclass(frozen=True, slots=True)
class V13Paths:
    """Every frozen input and forward-only output used by V13."""

    panel: Path
    panel_source_custody: Path
    v11_prompt: Path
    v12_focus_rule: Path
    root_rule: Path
    root_rule_audit: Path
    wording_review_a: Path
    wording_review_b: Path
    nested_adjudication: Path
    nested_two_lane_contract: Path
    v12_drug_adjudication: Path
    v12_drug_two_lane_contract: Path
    preregistration: Path
    v12_preregistration: Path
    v12_result: Path
    v12_report: Path
    v12_nested_raw: Path
    v12_drug_raw: Path
    qualified_transport_result: Path
    offline_replay: Path
    result: Path
    report: Path
    next_fresh_preregistration: Path
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


DEFAULT_PATHS = V13Paths(
    panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v9.json",
    panel_source_custody=REPO / "docs/validation/fixtures/"
    "2026-07-23-staged-generalization-v13-panel-source-custody-v1.json",
    v11_prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v11.md",
    v12_focus_rule=REPO / "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v12-focus-event-anchoring.md",
    root_rule=REPO / "docs/validation/prompts/"
    "2026-07-23-staged-generalization-v13-compositional-focus-root.md",
    root_rule_audit=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v13-root-rule-offline-audit-v1.json",
    wording_review_a=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v13-root-wording-reviewer-a-v1.json",
    wording_review_b=REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v13-root-wording-reviewer-b-v1.json",
    nested_adjudication=REPO / "docs/validation/adjudications/"
    "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.json",
    nested_two_lane_contract=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v13-nested-two-lane-contract-v1.json",
    v12_drug_adjudication=REPO / "docs/validation/adjudications/"
    "2026-07-23-pmid-21965773-drug-sensitivity-two-lane-adjudication-v1.json",
    v12_drug_two_lane_contract=REPO / "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v12-two-lane-contract-v1.json",
    preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v13-exposed-run-v1.json",
    v12_preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1.json",
    v12_result=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1.json",
    v12_report=REPO / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-final.md",
    v12_nested_raw=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-explicit-nested-cause-raw.json",
    v12_drug_raw=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-drug-sensitivity-raw.json",
    qualified_transport_result=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-foreground-qualification-v3.json",
    offline_replay=REPO / "docs/validation/evaluations/"
    "2026-07-23-staged-generalization-v13-v12-offline-replay.json",
    result=REPO / "docs/validation/results/"
    "2026-07-23-staged-generalization-v13-exposed-run-v1.json",
    report=REPO / "docs/validation/reports/"
    "2026-07-23-staged-generalization-v13-exposed-run-v1-final.md",
    next_fresh_preregistration=REPO / "docs/validation/preregistrations/"
    "2026-07-23-fresh-cg-after-v13-draft.json",
    receipts=REPO / "docs/validation/receipts",
    raw_outputs=REPO / "docs/validation/results",
    evaluations=REPO / "docs/validation/evaluations",
    grading=GRADING_DEFAULTS.grading,
)


__all__ = [
    "CASE_ORDER",
    "DEFAULT_PATHS",
    "EXPERIMENT_ID",
    "GLOBAL_MAX_CALLS",
    "GLOBAL_MAX_COST_USD",
    "MODEL",
    "REASONING_EFFORT",
    "REPO",
    "REQUEST_TIMEOUT_SECONDS",
    "V13Paths",
]
