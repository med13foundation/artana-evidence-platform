"""Render V11 run-2 reports without losing preregistered context."""

from __future__ import annotations

from pathlib import Path
from typing import cast

_ROOT_CAUSE = "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"
_SCIENTIFIC_CHANGE = "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"


def render_final_report(result: dict[str, object]) -> str:
    """Render both scientific and invalid terminals with explicit provenance."""

    root_cause = result.get("preregistered_root_cause_classification")
    scientific_change = result.get("frozen_scientific_change")
    if root_cause != _ROOT_CAUSE or scientific_change != _SCIENTIFIC_CHANGE:
        raise ValueError("V11 run-2 report context is absent or changed")
    validated = result.get("scientific_contract_validated_during_run")
    if not isinstance(validated, bool):
        raise TypeError("scientific validation disposition is absent")
    context_disposition = (
        "The complete frozen exposed panel validated this preregistered "
        "hypothesis and change."
        if validated
        else (
            "The run did not scientifically validate either the preregistered "
            "root-cause hypothesis or the frozen V11 change."
        )
    )
    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: grader `{}`, V11 run-2 gate `{}`, failure `{}`.".format(
            item["case_id"],
            _nested(item, "scientific_grader", "passed"),
            _nested(item, "v11_acceptance", "passed"),
            _nested(item, "v11_acceptance", "failure_classification"),
        )
        for item in cases
    )
    accounting = {
        key: result.get(key)
        for key in (
            "provider_calls",
            "transport_qualification_provider_calls",
            "scientific_provider_calls",
            "provider_retries",
            "duplicate_creation_calls",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "latency_seconds",
            "cost_usd",
            "remaining_cost_usd",
        )
    }
    regressions = {
        key: result.get(key, [])
        for key in (
            "v9_regressed_fields",
            "v9_count_regressions",
            "v10_regressed_fields",
            "v10_count_regressions",
        )
    }
    return (
        "# Staged Generalization V11 Exposed Run 2\n\n"
        "## 1. Operational root cause and transport\n\n"
        f"Run 1 classification: "
        f"`{result.get('operational_root_cause_classification')}`. "
        f"Run 2 transport: `{result.get('transport')}`.\n\n"
        "## 2. Report-generation correction\n\n"
        "Invalid reports now preserve the preregistered scientific context. "
        f"Correction artifact: `{result.get('run1_report_correction_sha256')}`.\n\n"
        "## 3. Preserved scientific contract\n\n"
        f"Preregistered root cause: `{root_cause}`. Frozen V11 change: "
        f"`{scientific_change}`. {context_disposition}\n\n"
        "## 4. Exposed/public case outcomes\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        "## 5. SLC12A3 boundary\n\n"
        f"Corrected to the exact occurrence: "
        f"`{result.get('slc12a3_corrected_by_actual_model_call', False)}`.\n\n"
        "## 6. Semantic grounding\n\n"
        f"All admitted semantic evidence unique: "
        f"`{result.get('all_semantic_evidence_unique', False)}`. Negated "
        "complete sentence observed: "
        f"`{result.get('negated_complete_unique_sentence_observed', False)}`.\n\n"
        "## 7. V9 and V10 regressions\n\n"
        f"`{regressions}`\n\n"
        "## 8. Provider execution and cumulative budget\n\n"
        f"`{accounting}`\n\n"
        "## 9. Fresh-case accounting\n\n"
        f"Fresh cases consumed: `{result.get('fresh_cases_consumed', 0)}`. "
        "Untouched fresh cases preserved: "
        f"`{result.get('remaining_fresh_cases_preserved', 7)}`.\n\n"
        "## 10. Graph and promotion state\n\n"
        f"Graph writes: `{result.get('graph_writes', 0)}`. Trusted promotion: "
        f"`{result.get('trusted_promotion', False)}`.\n\n"
        "## 11. Execution validity and frontier\n\n"
        f"Failure stage: `{result.get('failure_stage')}`. Failed case: "
        f"`{result.get('failed_case_id')}`. First scientific failure: "
        f"`{result.get('first_failure_classification')}`.\n\n"
        "## 12. Terminal decision\n\n"
        f"`{result['decision']}`\n"
    )


def write_final_report(path: Path, result: dict[str, object]) -> None:
    """Persist the deterministic report for one sealed terminal result."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_final_report(result), encoding="utf-8")


def _nested(value: dict[str, object], outer: str, inner: str) -> object:
    nested = value.get(outer)
    return nested.get(inner) if isinstance(nested, dict) else None


__all__ = ["render_final_report", "write_final_report"]
