"""Render a sealed V16 result without changing its scientific content."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast


def render_final_report(result: dict[str, object]) -> str:
    """Produce a compact, human-readable receipt over immutable result data."""

    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: source-semantic `{}`, V16 scope `{}`, raw V14 `{}`, raw "
        "BioNLP-CG `{}`, failure `{}`.".format(
            item.get("case_id"),
            _nested(
                item,
                "v16_evaluation",
                "effective_metrics",
                "source_semantic_status",
            ),
            _nested(
                item,
                "v16_evaluation",
                "participant_scope_assessment",
                "passed",
            ),
            _nested(
                item,
                "v16_evaluation",
                "raw_v14_metrics",
                "passed",
            ),
            _nested(
                item,
                "v16_evaluation",
                "raw_v14_metrics",
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
        "# Staged Generalization V16 Exposed Gate\n\n"
        "## Scientific hypothesis\n\n"
        "`PARTICIPANT_SCOPE_AND_PARTITIVE_REPRESENTATION_V1`: when a source "
        "condition narrows a participant set inherited by a focused event, "
        "represent it as a grounded participant scope link; when the source "
        "states a partitive applicability, retain it on the existing event "
        "argument. A direct event-to-restrictor edge remains optional and cannot "
        "substitute for either relation.\n\n"
        "## Exposed outcomes\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        f"First scientific failure: `{result.get('first_failure_classification')}` "
        f"at `{result.get('failed_case_id')}`. Execution stage "
        f"`{result.get('failure_stage')}`; diagnostics `{diagnostic_text}`.\n\n"
        "## Provider custody\n\n"
        f"Attempted `{result.get('attempted_provider_calls')}`, completed "
        f"`{result.get('completed_provider_calls')}`, admitted "
        f"`{result.get('admitted_provider_calls')}`, rejected "
        f"`{result.get('rejected_provider_calls')}`, retries "
        f"`{result.get('provider_retries')}`, duplicate creations "
        f"`{result.get('duplicate_creation_calls')}`.\n\n"
        f"{call_lines or '- No provider creation was attempted.'}\n\n"
        "## Cost and stopping budget\n\n"
        f"Spend `${result.get('cost_usd')}` of `${result.get('global_max_cost_usd')}`; "
        f"remaining `${result.get('remaining_cost_usd')}`; accounting "
        f"`{result.get('budget_accounting_status')}`. Tokens, latency, and cost "
        "did not affect scientific scoring.\n\n"
        "## Qualification state\n\n"
        f"Fresh cases consumed `{result.get('fresh_cases_consumed')}`; untouched "
        f"`{result.get('remaining_fresh_cases_preserved')}`; graph writes "
        f"`{result.get('graph_writes')}`; trusted promotion "
        f"`{result.get('trusted_promotion')}`. Sealed V15 preserved "
        f"`{result.get('sealed_v15_preserved')}`.\n\n"
        "## Terminal decision\n\n"
        f"`{result['decision']}`\n"
    )


def write_final_report(path: Path, result: dict[str, object]) -> None:
    """Write the report exactly once, mirroring the result's exclusive custody."""

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
