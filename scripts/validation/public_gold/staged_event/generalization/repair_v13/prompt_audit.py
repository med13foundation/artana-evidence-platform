"""Verify the independently reviewed V13 root-selection rule."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    DEFAULT_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)

EXPECTED_RULE_SHA256 = (
    "0ab67bfea1ed75028a4771bc9a1b2f8d00f56bcc228d305a3650e3ae2d0e86f7"
)
EXPECTED_RULE = """# V13 Compositional Focus Root Selection

Compositional focus root selection:

- Select the root only after constructing event links.
- In the focus-internal event subgraph, when exactly one inventoried event is
  not the target of another focus-internal inventoried event, choose it as root.
- Predicates outside the highlighted finding cannot disqualify or replace that
  root, and a nested effect cannot replace its explicit focus-internal parent.
- Otherwise apply the existing root and completeness rules unchanged; do not
  alter inventory or links to force uniqueness.
- This rule changes root selection only. Preserve inventory, trigger
  boundaries, participants, links, roles, semantic axes, evidence, and
  completeness rules unchanged.
- The rule does not prescribe an event count, event type, participant, role,
  semantic-axis value, benchmark label, or expected answer.

Non-scientific transport clarification for this exposed V13:

- Every preregistered focus is upstream-eligible because it contains at least
  one explicit source-supported event. An input with no such event is outside
  this experiment and must not be sent to the provider.
- When `completeness` is not `COMPLETE`, `root_event_id` is a required transport
  anchor, not an asserted scientific root. Set it to the earliest
  source-supported focus-internal inventoried event in source order.
- Do not add, delete, relabel, or link events to create that transport anchor.
  The universal schema still cannot represent a truly eventless abstention;
  V13 does not claim to solve that residual limitation.
"""

_EXPECTED_ORDER = (
    "generalization-comparison-canary",
    "generalization-drug-sensitivity",
    "generalization-explicit-nested-cause",
    "generalization-uncertainty",
    "generalization-negated-association",
    "generalization-null-statistics",
)
_FORBIDDEN_SOURCE_TERMS = (
    "PMID",
    "7966592",
    "HCMV",
    "p53",
    "fibroblast",
    "responsible",
    "elevating",
    "GENE_EXPRESSION",
    "POSITIVE_REGULATION",
    "REGULATION",
)


class V13PromptAuditError(ValueError):
    """The reviewed V13 prompt rule or its six-case audit changed."""


def verify_prompt_audit(
    *,
    rule_path: Path,
    audit_path: Path,
    adjudication_path: Path,
    panel_path: Path = DEFAULT_PATHS.panel,
) -> dict[str, object]:
    """Validate exact wording, source generality, panel coverage, and custody."""

    rule = rule_path.read_text(encoding="utf-8")
    if rule != EXPECTED_RULE or _sha256(rule_path) != EXPECTED_RULE_SHA256:
        raise V13PromptAuditError(
            "V13 root rule differs from independently reviewed wording"
        )
    present = [term for term in _FORBIDDEN_SOURCE_TERMS if term in rule]
    if present:
        raise V13PromptAuditError(
            f"V13 root rule contains source-specific terms: {present}"
        )

    loaded = _object(json.loads(audit_path.read_text(encoding="utf-8")))
    if loaded.get("rule_sha256") != EXPECTED_RULE_SHA256:
        raise V13PromptAuditError("V13 prompt audit rule hash changed")
    if loaded.get("source_adjudication_sha256") != _sha256(adjudication_path):
        raise V13PromptAuditError("V13 prompt audit adjudication hash changed")
    if loaded.get("single_scientific_change") != ("COMPOSITIONAL_FOCUS_ROOT_SELECTION"):
        raise V13PromptAuditError("V13 prompt audit change scope changed")
    if loaded.get("source_general") is not True:
        raise V13PromptAuditError("V13 prompt audit is not source-general")
    if loaded.get("leakage_findings") != []:
        raise V13PromptAuditError("V13 prompt audit contains leakage")
    if loaded.get("unresolved_safety_findings") != []:
        raise V13PromptAuditError("V13 prompt audit has unresolved safety findings")
    _verify_transport_clarification(loaded)

    cases = loaded.get("cases")
    if not isinstance(cases, list):
        raise V13PromptAuditError("V13 prompt audit cases are absent")
    case_ids = tuple(item.get("case_id") for item in cases if isinstance(item, dict))
    if case_ids != _EXPECTED_ORDER:
        raise V13PromptAuditError("V13 prompt audit case order changed")
    if set(case_ids) != {case.case_id for case in load_frozen_panel(panel_path)}:
        raise V13PromptAuditError("V13 prompt audit does not cover the exposed panel")
    if loaded.get("case_count") != len(_EXPECTED_ORDER):
        raise V13PromptAuditError("V13 prompt audit case count changed")
    _verify_targeted_case(cast("list[object]", cases))
    return loaded


def _verify_targeted_case(cases: list[object]) -> None:
    by_id = {
        item["case_id"]: item
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    nested = by_id["generalization-explicit-nested-cause"]
    if nested.get("expected_nested_edges") != ["responsible->elevating"]:
        raise V13PromptAuditError(
            "V13 audit changed the source-semantic nested dependency"
        )
    if nested.get("expected_root_triggers") != [
        "responsible",
        "responsible for",
    ]:
        raise V13PromptAuditError("V13 audit changed the corrected root")
    if nested.get("forbidden_root_triggers") != [
        "elevating",
        "elevating p53 levels",
    ]:
        raise V13PromptAuditError("V13 audit no longer excludes the inner root")
    if nested.get("inventory_policy") != ("UNCHANGED_SOURCE_SEMANTIC_TWO_EVENT_LANE"):
        raise V13PromptAuditError("V13 audit changes nested event inventory")
    if any(
        isinstance(item, dict) and item.get("risk_findings") != [] for item in cases
    ):
        raise V13PromptAuditError("V13 prompt audit has a case-level risk")


def _verify_transport_clarification(audit: dict[str, object]) -> None:
    transport = _object(audit.get("non_scientific_transport_clarification"))
    expected: dict[str, object] = {
        "scope": "V13_EXPOSED_PANEL_ONLY",
        "panel_focus_event_eligibility_required": True,
        "zero_event_inputs_sent_to_provider": False,
        "non_complete_root_event_id_semantics": "TRANSPORT_ANCHOR_ONLY",
        "inventory_or_links_may_change_to_create_anchor": False,
        "eventless_abstention_supported": False,
    }
    if transport != expected:
        raise V13PromptAuditError("V13 transport clarification audit changed")
    limitation = audit.get("residual_capability_limitation")
    if not isinstance(limitation, str) or "eventless abstention" not in limitation:
        raise V13PromptAuditError(
            "V13 eventless-abstention limitation is not disclosed"
        )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V13PromptAuditError("expected JSON object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "EXPECTED_RULE",
    "EXPECTED_RULE_SHA256",
    "V13PromptAuditError",
    "verify_prompt_audit",
]
