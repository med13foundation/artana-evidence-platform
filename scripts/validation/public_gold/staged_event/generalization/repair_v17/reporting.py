"""Render a sealed V17 result without changing its scientific content."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast


def render_final_report(result: dict[str, object]) -> str:
    """Produce a compact human-readable receipt over immutable result data."""

    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: source-semantic `{}`, V17 scope `{}`, raw V16 `{}`, raw "
        "BioNLP-CG `{}`, failure `{}`.".format(
            item.get("case_id"),
            _nested(
                item,
                "v17_evaluation",
                "effective_metrics",
                "source_semantic_status",
            ),
            _scope_passed(item),
            _nested(item, "v17_evaluation", "raw_v16_metrics", "passed"),
            _nested(
                item,
                "v17_evaluation",
                "raw_v16_metrics",
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
        "# Staged Generalization V17 Exposed Gate\n\n"
        "## Scientific hypothesis\n\n"
        "`INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1`: retain a material "
        "inline restriction in the smallest complete participant span; do not "
        "decompose that inline text into an optional participant-scope node or "
        "link. Preserve V16's separately adjudicated handling of source-grounded "
        "anaphoric scope and partitives.\n\n"
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
        f"`{result.get('trusted_promotion')}`. Sealed V16 preserved "
        f"`{result.get('sealed_v16_preserved')}`.\n\n"
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


def _scope_passed(item: dict[str, object]) -> object:
    """Read the V17-local assessment without assuming its report key name."""

    for key in ("inline_scope_assessment", "participant_scope_assessment"):
        value = _nested(item, "v17_evaluation", key, "passed")
        if value is not None:
            return value
    return None


__all__ = ["render_final_report", "write_final_report"]
