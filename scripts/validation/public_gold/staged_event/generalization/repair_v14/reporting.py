"""Render the sealed V14 result without changing its scientific content."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast


def render_final_report(result: dict[str, object]) -> str:
    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: source `{}`, root `{}`, optional edge accepted `{}`, raw CG "
        "`{}`, failure `{}`.".format(
            item.get("case_id"),
            _nested(
                item, "v14_evaluation", "effective_metrics", "source_semantic_status"
            ),
            _nested(
                item, "v14_evaluation", "effective_metrics", "root_selection_status"
            ),
            _nested(
                item,
                "v14_evaluation",
                "optional_source_entailed_edge",
                "accepted_count",
            ),
            _nested(
                item,
                "v14_evaluation",
                "raw_v13_metrics",
                "benchmark_projection_status",
            ),
            item.get("failure_classification"),
        )
        for item in cases
    )
    per_call = cast("list[dict[str, object]]", result.get("per_call", []))
    call_lines = "\n".join(
        "- `{}`: `{}`, response IDs `{}`, usage `{}`.".format(
            item.get("case_id"),
            item.get("status"),
            item.get("response_ids"),
            json.dumps(item.get("usage"), sort_keys=True, separators=(",", ":")),
        )
        for item in per_call
    )
    diagnostics = result.get("diagnostics")
    diagnostic_text = json.dumps(
        diagnostics if isinstance(diagnostics, dict) else {},
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "# Staged Generalization V14 Exposed Gate\n\n"
        "## Scientific change\n\n"
        "`COMPLETE_PARTICIPANT_DENOTATION_V1`: retain the entity-denoting "
        "noun head and restrictive identity unless the retained span "
        "independently denotes the same participant. No event, role, root, "
        "axis, grounding, completeness, or CG rule changed.\n\n"
        "## V14-local evaluator correction\n\n"
        "At most one independently adjudicated, source-entailed redundant "
        "inner causal-agent edge may be normalized in the source lane. It "
        "cannot replace a mandatory link. Raw BioNLP-CG projection remains "
        "unchanged and review-only.\n\n"
        "## Exposed outcomes\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        f"First failure: `{result.get('first_failure_classification')}` at "
        f"`{result.get('failed_case_id')}`. Execution stage "
        f"`{result.get('failure_stage')}`; root cause "
        f"`{result.get('root_cause')}`; diagnostics `{diagnostic_text}`.\n\n"
        "## Provider custody\n\n"
        f"Attempted `{result.get('attempted_provider_calls')}`, completed "
        f"`{result.get('completed_provider_calls')}`, admitted "
        f"`{result.get('admitted_provider_calls')}`, rejected "
        f"`{result.get('rejected_provider_calls')}`, retries "
        f"`{result.get('provider_retries')}`, duplicate creations "
        f"`{result.get('duplicate_creation_calls')}`.\n\n"
        f"{call_lines or '- No provider creation was attempted.'}\n\n"
        "## Cost and stopping budget\n\n"
        f"Spend `${result.get('cost_usd')}` of "
        f"`${result.get('global_max_cost_usd')}`; remaining "
        f"`${result.get('remaining_cost_usd')}`; accounting "
        f"`{result.get('budget_accounting_status')}`. Tokens, latency, and "
        "cost did not affect scientific scoring.\n\n"
        "## Qualification state\n\n"
        f"Fresh cases consumed `{result.get('fresh_cases_consumed')}`; "
        f"untouched `{result.get('remaining_fresh_cases_preserved')}`; graph "
        f"writes `{result.get('graph_writes')}`; trusted promotion "
        f"`{result.get('trusted_promotion')}`. V13 sealed "
        f"`{result.get('sealed_v13_preserved')}`.\n\n"
        "## Terminal decision\n\n"
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


def _nested(value: dict[str, object], *keys: str) -> object:
    current: object = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


__all__ = ["render_final_report", "write_final_report"]
