"""Paths for the forward-only Fresh-CG V3 exposed-case replay."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
CASE_ID = "fresh-cg-pmid-2681013-e5"


@dataclass(frozen=True, slots=True)
class FreshCGV3Paths:
    selection: Path
    v2_reference: Path
    v2_raw_output: Path
    v2_evaluation: Path
    dispute_packet: Path
    occurrence_adjudication: Path
    semantics_adjudication: Path
    consensus: Path
    reference: Path
    result: Path
    report: Path


DEFAULT_PATHS = FreshCGV3Paths(
    selection=REPO / "docs/validation/fixtures/2026-07-22-fresh-cg-selection-v2.json",
    v2_reference=REPO
    / "docs/validation/references/2026-07-22-fresh-cg-two-lane-reference-v2.json",
    v2_raw_output=REPO / "docs/validation/results/"
    "2026-07-22-fresh-cg-occurrence-v2-v2-fresh-cg-pmid-2681013-e5-raw.json",
    v2_evaluation=REPO / "docs/validation/results/"
    "2026-07-22-fresh-cg-occurrence-v2-v2-fresh-cg-pmid-2681013-e5-evaluation.json",
    dispute_packet=REPO / "docs/validation/adjudications/"
    "2026-07-22-fresh-cg-v2-root-cause-dispute-packet-v1.json",
    occurrence_adjudication=REPO / "docs/validation/adjudications/"
    "2026-07-22-fresh-cg-v2-occurrence-adjudicator-v1.json",
    semantics_adjudication=REPO / "docs/validation/adjudications/"
    "2026-07-22-fresh-cg-v2-semantics-adjudicator-v1.json",
    consensus=REPO / "docs/validation/adjudications/"
    "2026-07-22-fresh-cg-v2-root-cause-consensus-v1.json",
    reference=REPO / "docs/validation/references/"
    "2026-07-22-fresh-cg-v3-exposed-case-reference-v1.json",
    result=REPO / "docs/validation/results/"
    "2026-07-22-fresh-cg-v3-exposed-case-replay-v1.json",
    report=REPO / "docs/validation/reports/"
    "2026-07-22-fresh-cg-v2-root-cause-adjudication-final.md",
)


__all__ = ["CASE_ID", "DEFAULT_PATHS", "FreshCGV3Paths"]
