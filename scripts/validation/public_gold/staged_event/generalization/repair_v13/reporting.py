"""Render the sealed V13 result as a deterministic scientific report."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast


def render_final_report(result: dict[str, object]) -> str:
    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: source-scientific pass `{}`, root selection `{}`, "
        "completeness `{}`, source `{}`, review-only benchmark projection "
        "`{}` (`{}`), full-focus CG `{}`, failure `{}`.".format(
            item["case_id"],
            _nested(item, "v13_metrics", "passed"),
            _nested(item, "v13_metrics", "root_selection_status"),
            _nested(item, "v13_metrics", "completeness"),
            _nested(item, "v13_metrics", "source_semantic_status"),
            _nested(item, "v13_metrics", "benchmark_projection_status"),
            _nested(item, "v13_metrics", "benchmark_projection_scope"),
            _nested(item, "v13_metrics", "full_focus_cg_status"),
            item.get("failure_classification"),
        )
        for item in cases
    )
    diagnostics = result.get("diagnostics")
    diagnostic_text = json.dumps(
        diagnostics if isinstance(diagnostics, dict) else {},
        sort_keys=True,
        separators=(",", ":"),
    )
    per_call = cast("list[dict[str, object]]", result.get("per_call", []))
    call_lines = "\n".join(
        "- `{}`: status `{}`, failure stage `{}`, response IDs `{}`, usage `{}`.".format(
            item.get("case_id"),
            item.get("status"),
            item.get("failure_stage"),
            item.get("response_ids"),
            json.dumps(item.get("usage"), sort_keys=True, separators=(",", ":")),
        )
        for item in per_call
    )
    return (
        "# Staged Generalization V13 Exposed Gate\n\n"
        "## 1. Adjudicated root cause\n\n"
        f"`{result.get('root_cause_classification')}`.\n\n"
        "## 2. Scientific change\n\n"
        f"`{result.get('single_scientific_change')}`; inventory, links, "
        "semantic fields, and the frozen grader were not relaxed. V12 drug "
        "source metrics were reused unchanged; V13's versioned decision "
        "policy makes the review-only CG metric nonblocking.\n\n"
        "## 3. Nested source-semantic lane\n\n"
        f"Nested source lane: "
        f"`{result.get('nested_source_semantic_outcome')}`.\n\n"
        "## 4. Exact BioNLP-CG projection lane\n\n"
        f"Nested benchmark projection: "
        f"`{result.get('nested_benchmark_projection_outcome')}` over "
        f"`{result.get('nested_benchmark_projection_scope')}`. Full-focus CG "
        f"measurement: `{result.get('nested_full_focus_cg_outcome')}`. The "
        "official additional focus event is E28 `Infection`; V9 cannot "
        "represent `INFECTION`, `CELL`, or `ORGANISM`. This lane is "
        "review-only and cannot fail source-scientific qualification.\n\n"
        "## 5. Exposed case outcomes and first frontier\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        f"First scientific failure: "
        f"`{result.get('first_failure_classification')}` at "
        f"`{result.get('failed_case_id')}`. Execution failure stage: "
        f"`{result.get('failure_stage')}`; root cause: "
        f"`{result.get('root_cause')}`; diagnostics: "
        f"`{diagnostic_text}`.\n\n"
        "## 6. Evaluator and frozen grader\n\n"
        f"Provider-called `{result.get('executed_case_count')}` of "
        f"`{result.get('planned_case_count')}` cases; scientifically evaluated "
        f"`{result.get('scientifically_evaluated_case_count')}`; called but "
        f"unevaluated `{result.get('called_but_unevaluated_case_ids')}`; "
        f"admitted evaluations persisted: "
        f"`{result.get('all_evaluations_persisted')}`.\n\n"
        "## 7. Exactly-once provider evidence\n\n"
        f"Attempted `{result.get('attempted_provider_calls')}`, completed "
        f"`{result.get('completed_provider_calls')}`, admitted "
        f"`{result.get('admitted_provider_calls')}`, rejected "
        f"`{result.get('rejected_provider_calls')}`, unaccounted "
        f"`{result.get('unaccounted_provider_calls')}`; retries "
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
        f"`${result.get('cost_usd')}`; observed accounted spend "
        f"`${result.get('observed_accounted_cost_usd')}`; accounting "
        f"`{result.get('budget_accounting_status')}`.\n\n"
        f"{call_lines or '- No provider creation was attempted.'}\n\n"
        "## 9. Operational budget\n\n"
        f"Limit `${result.get('global_max_cost_usd')}`; remaining "
        f"`${result.get('remaining_cost_usd')}`; exhausted "
        f"`{result.get('budget_exhausted')}`. Token count, answer length, "
        "latency, and cost did not affect scientific scoring.\n\n"
        "## 10. Historical sealing\n\n"
        "V12 remains sealed and diagnostic-only with zero retroactive credit: "
        f"`{result.get('sealed_v12_preserved')}`.\n\n"
        "## 11. Fresh-case accounting\n\n"
        f"Fresh cases consumed `{result.get('fresh_cases_consumed')}`; "
        f"untouched fresh cases "
        f"`{result.get('remaining_fresh_cases_preserved')}`; fresh "
        f"qualification `{result.get('fresh_qualification_status')}`; "
        f"automatic draft generated "
        f"`{result.get('automatic_fresh_draft_generated')}`.\n\n"
        "## 12. Graph and promotion state\n\n"
        f"Graph writes `{result.get('graph_writes')}`; trusted promotion "
        f"`{result.get('trusted_promotion')}`.\n\n"
        "## 13. Terminal decision\n\n"
        f"`{result['decision']}`\n"
    )


def write_final_report(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    completed = False
    try:
        target = path.open("x", encoding="utf-8")
        created = True
        with target:
            target.write(render_final_report(result))
            target.flush()
            os.fsync(target.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        completed = True
    finally:
        if created and not completed:
            path.unlink(missing_ok=True)


def _nested(value: dict[str, object], outer: str, inner: str) -> object:
    nested = value.get(outer)
    return nested.get(inner) if isinstance(nested, dict) else None


__all__ = ["render_final_report", "write_final_report"]
