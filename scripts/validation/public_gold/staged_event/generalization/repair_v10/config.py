"""Paths for the non-executed V10 preregistration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]


@dataclass(frozen=True, slots=True)
class V10Paths:
    v9_prompt: Path
    prompt: Path
    preregistration: Path
    exposed_panel: Path
    exposed_raw_outputs: Path
    exposed_audit_result: Path
    consensus: Path
    v3_reference: Path
    v3_replay: Path


DEFAULT_PATHS = V10Paths(
    v9_prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v9.md",
    prompt=REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v10.md",
    preregistration=REPO
    / "docs/validation/preregistrations/2026-07-22-staged-generalization-v10.json",
    exposed_panel=REPO
    / "docs/validation/fixtures/2026-07-22-staged-generalization-panel-v9.json",
    exposed_raw_outputs=REPO / "docs/validation/results",
    exposed_audit_result=REPO / "docs/validation/results/"
    "2026-07-22-staged-generalization-v10-exposed-boundary-audit.json",
    consensus=REPO / "docs/validation/adjudications/"
    "2026-07-22-fresh-cg-v2-root-cause-consensus-v1.json",
    v3_reference=REPO / "docs/validation/references/"
    "2026-07-22-fresh-cg-v3-exposed-case-reference-v1.json",
    v3_replay=REPO / "docs/validation/results/"
    "2026-07-22-fresh-cg-v3-exposed-case-replay-v1.json",
)


__all__ = ["DEFAULT_PATHS", "V10Paths"]
