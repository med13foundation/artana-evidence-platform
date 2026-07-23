"""Render the sealed V12 result as a deterministic 13-part report."""

from __future__ import annotations

from pathlib import Path
from typing import cast


def render_final_report(result: dict[str, object]) -> str:
    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: scientific pass `{}`, focus `{}`, source `{}`, CG `{}`, "
        "failure `{}`.".format(
            item["case_id"],
            _nested(item, "v12_metrics", "passed"),
            _nested(item, "v12_metrics", "focus_event_passed"),
            _nested(item, "v12_metrics", "source_semantic_status"),
            _nested(item, "v12_metrics", "cg_projection_status"),
            item.get("failure_classification"),
        )
        for item in cases
    )
    return (
        "# Staged Generalization V12 Exposed Gate\n\n"
        "## 1. Adjudicated root cause\n\n"
        f"`{result.get('root_cause_classification')}`.\n\n"
        "## 2. Scientific change\n\n"
        f"`{result.get('single_scientific_change')}`; the V9/V11 schema and "
        "the frozen grader were not relaxed.\n\n"
        "## 3. Source-semantic lane\n\n"
        f"Drug-sensitivity source lane: "
        f"`{result.get('drug_source_semantic_outcome')}`.\n\n"
        "## 4. Exact CG projection lane\n\n"
        f"Drug-sensitivity review-only projection: "
        f"`{result.get('drug_cg_projection_outcome')}`.\n\n"
        "## 5. Exposed case outcomes and first frontier\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        f"First failure: `{result.get('first_failure_classification')}` at "
        f"`{result.get('failed_case_id')}`.\n\n"
        "## 6. Evaluator and frozen grader\n\n"
        f"Executed `{result.get('executed_case_count')}` of "
        f"`{result.get('planned_case_count')}` cases; all admitted evaluations "
        f"persisted: `{result.get('all_evaluations_persisted')}`.\n\n"
        "## 7. Exactly-once provider evidence\n\n"
        f"Provider calls `{result.get('provider_calls')}`, retries "
        f"`{result.get('provider_retries')}`, duplicate creations "
        f"`{result.get('duplicate_creation_calls')}`, receipts valid "
        f"`{result.get('all_receipts_valid')}`.\n\n"
        "## 8. Usage, latency, and spend\n\n"
        f"Input `{result.get('input_tokens')}`, cached input "
        f"`{result.get('cached_input_tokens')}`, output "
        f"`{result.get('output_tokens')}`, reasoning "
        f"`{result.get('reasoning_tokens')}`, total "
        f"`{result.get('total_tokens')}`, latency "
        f"`{result.get('latency_seconds')}`, spend "
        f"`${result.get('cost_usd')}`.\n\n"
        "## 9. Operational budget\n\n"
        f"Limit `${result.get('global_max_cost_usd')}`; remaining "
        f"`${result.get('remaining_cost_usd')}`; exhausted "
        f"`{result.get('budget_exhausted')}`. Telemetry did not affect "
        "scientific scoring.\n\n"
        "## 10. Historical replay and sealing\n\n"
        "V9/V11 replay remained diagnostic-only with zero retroactive credit; "
        f"sealed V11 hashes preserved: `{result.get('sealed_v11_preserved')}`.\n\n"
        "## 11. Fresh-case accounting\n\n"
        f"Fresh cases consumed `{result.get('fresh_cases_consumed')}`; "
        f"untouched fresh cases `{result.get('remaining_fresh_cases_preserved')}`; "
        f"next draft `{result.get('next_fresh_preregistration')}`.\n\n"
        "## 12. Graph and promotion state\n\n"
        f"Graph writes `{result.get('graph_writes')}`; trusted promotion "
        f"`{result.get('trusted_promotion')}`.\n\n"
        "## 13. Terminal decision\n\n"
        f"`{result['decision']}`\n"
    )


def write_final_report(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_final_report(result), encoding="utf-8")


def _nested(value: dict[str, object], outer: str, inner: str) -> object:
    nested = value.get(outer)
    return nested.get(inner) if isinstance(nested, dict) else None


__all__ = ["render_final_report", "write_final_report"]
