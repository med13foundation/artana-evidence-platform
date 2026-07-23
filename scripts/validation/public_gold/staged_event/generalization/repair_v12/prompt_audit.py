"""Verify the source-general V12 rule against every exposed case."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.panel import (
    build_panel,
)

EXPECTED_RULE = """# V12 Focus Event Anchoring

Focus-event anchoring:

- When the highlighted finding contains an explicit event-denoting noun or
  phrase, inventory that highlighted event and keep it as the root event.
- A surrounding predicate such as `associated with`, `involved in`, or
  `related to` must not replace the highlighted event merely because it connects
  contextual entities.
- This rule changes only focus-event inventory and root selection. Preserve
  every nested event required by the highlighted finding, and apply the existing
  participant, link, role, and semantic-axis rules unchanged.
- The rule does not prescribe an event type, participant identity,
  semantic-axis value, benchmark label, or expected answer.
"""

_EXPECTED_ORDER = (
    "generalization-comparison-canary",
    "generalization-drug-sensitivity",
    "generalization-explicit-nested-cause",
    "generalization-uncertainty",
    "generalization-negated-association",
    "generalization-null-statistics",
)
_FORBIDDEN_TERMS = (
    "PMID",
    "21965773",
    "carcinoma",
    "5-FU",
    "TS",
    "DPD",
    "REGULATION",
    "CANCER",
    "SIMPLE_CHEMICAL",
)


def verify_prompt_audit(
    *,
    rule_path: Path,
    audit_path: Path,
    adjudication_path: Path,
) -> dict[str, object]:
    rule = rule_path.read_text(encoding="utf-8")
    if rule != EXPECTED_RULE:
        raise ValueError("V12 focus rule differs from the reviewed wording")
    present = [term for term in _FORBIDDEN_TERMS if term in rule]
    if present:
        raise ValueError(f"V12 focus rule contains source-specific terms: {present}")
    loaded: object = json.loads(audit_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("V12 prompt audit must be a JSON object")
    cases = loaded.get("cases")
    if not isinstance(cases, list):
        raise TypeError("V12 prompt audit cases are absent")
    case_ids = tuple(
        item.get("case_id") for item in cases if isinstance(item, dict)
    )
    if case_ids != _EXPECTED_ORDER:
        raise ValueError("V12 prompt audit case order changed")
    if set(case_ids) != {case.case_id for case in build_panel()}:
        raise ValueError("V12 prompt audit does not cover the exposed panel")
    expected_hash = hashlib.sha256(adjudication_path.read_bytes()).hexdigest()
    if loaded.get("source_adjudication_sha256") != expected_hash:
        raise ValueError("V12 prompt audit adjudication hash changed")
    if loaded.get("unresolved_safety_findings") != []:
        raise ValueError("V12 prompt audit has unresolved safety findings")
    _verify_nested_and_uncertainty_audit(cases)
    return loaded


def _verify_nested_and_uncertainty_audit(cases: list[object]) -> None:
    by_id = {
        item["case_id"]: item
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    nested = by_id["generalization-explicit-nested-cause"]
    if nested.get("expected_nested_edges") != [
        "responsible->elevating",
        "elevating->levels",
    ]:
        raise ValueError("V12 audit does not preserve nested dependencies")
    uncertainty = by_id["generalization-uncertainty"]
    if uncertainty.get("expected_root_triggers") != ["classified"]:
        raise ValueError("V12 audit conflates classification trigger and value")
    if uncertainty.get("forbidden_root_triggers") != ["uncertain significance"]:
        raise ValueError("V12 audit does not exclude the classification value as root")


__all__ = ["EXPECTED_RULE", "verify_prompt_audit"]
