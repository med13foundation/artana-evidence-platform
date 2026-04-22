#!/usr/bin/env python3
"""Evaluate whether guarded source+chase canary evidence is default-discussion ready."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

type JSONObject = dict[str, object]
ReadinessVerdict = Literal["pass", "hold", "rollback_required"]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INPUT_ROOT = _REPO_ROOT / "reports" / "full_ai_orchestrator_settings_canary"
_DEFAULT_OUTPUT_ROOT = _REPO_ROOT / "reports" / "full_ai_orchestrator_default_readiness"
_EXPECTED_PROFILE = "guarded_source_chase"
_EXPECTED_PROFILE_SOURCE = "space_setting"
_OPERATOR_DECISION_APPROVED = "approved_for_default_discussion"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Aggregate settings-path guarded source+chase canary reports into "
            "a default-readiness discussion gate."
        ),
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help=(
            "Path to a settings-canary summary.json, summary.md sibling "
            "directory, or report directory."
        ),
    )
    parser.add_argument(
        "--reports",
        default="",
        help="Comma-separated report paths. Useful for Makefile/env forwarding.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=_DEFAULT_INPUT_ROOT,
        help="Directory used by --latest-count. Defaults to settings-canary reports.",
    )
    parser.add_argument(
        "--latest-count",
        type=int,
        default=0,
        help="Select the latest N reports from --report-dir when no reports are passed.",
    )
    parser.add_argument(
        "--monitored-space-id",
        action="append",
        default=[],
        help="Expected monitored space ID. Repeat for every guarded canary space.",
    )
    parser.add_argument(
        "--monitored-space-ids",
        default="",
        help="Comma-separated expected monitored space IDs.",
    )
    parser.add_argument(
        "--minimum-monitored-spaces",
        type=int,
        default=7,
        help="Minimum monitored spaces required for default discussion. Defaults to 7.",
    )
    parser.add_argument(
        "--minimum-clean-runs-per-space",
        type=int,
        default=2,
        help=(
            "Minimum clean settings-path guarded runs required for each monitored "
            "space. Defaults to 2."
        ),
    )
    parser.add_argument(
        "--minimum-authority-runs-per-space",
        type=int,
        default=1,
        help=(
            "Minimum clean authority-exercised runs required for each monitored "
            "space. Defaults to 1."
        ),
    )
    parser.add_argument(
        "--operator-decision",
        choices=("not_recorded", _OPERATOR_DECISION_APPROVED),
        default="not_recorded",
        help=(
            "Explicit operator decision. The gate can only pass with "
            "approved_for_default_discussion."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for generated readiness output. Defaults to "
            "reports/full_ai_orchestrator_default_readiness/<timestamp>/."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    report_paths = _resolve_report_paths(args)
    monitored_space_ids = _resolve_monitored_space_ids(args)
    review = build_default_readiness_review(
        report_paths=report_paths,
        monitored_space_ids=monitored_space_ids,
        minimum_monitored_spaces=_positive_int(
            args.minimum_monitored_spaces,
            "minimum_monitored_spaces",
        ),
        minimum_clean_runs_per_space=_positive_int(
            args.minimum_clean_runs_per_space,
            "minimum_clean_runs_per_space",
        ),
        minimum_authority_runs_per_space=_positive_int(
            args.minimum_authority_runs_per_space,
            "minimum_authority_runs_per_space",
        ),
        operator_decision=_maybe_string(args.operator_decision) or "not_recorded",
    )
    output_dir = _resolve_output_dir(args.output_dir)
    manifest = write_default_readiness_review(review=review, output_dir=output_dir)
    print(render_default_readiness_markdown(review))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    return (
        0
        if _dict_value(review.get("default_readiness_gate")).get("verdict") == "pass"
        else 1
    )


def build_default_readiness_review(  # noqa: PLR0913
    *,
    report_paths: Sequence[Path],
    monitored_space_ids: Sequence[str],
    minimum_monitored_spaces: int,
    minimum_clean_runs_per_space: int,
    minimum_authority_runs_per_space: int,
    operator_decision: str,
) -> JSONObject:
    """Build one default-readiness review from settings-path canary reports."""

    report_entries = [_load_report_entry(path) for path in report_paths]
    run_entries = [
        run for report in report_entries for run in _list_of_dicts(report.get("runs"))
    ]
    monitored_spaces = tuple(dict.fromkeys(monitored_space_ids))
    if not monitored_spaces:
        monitored_spaces = tuple(
            sorted(
                {
                    space_id
                    for run in run_entries
                    if (space_id := _maybe_string(run.get("space_id"))) is not None
                },
            ),
        )
    summary = _aggregate_runs(
        reports=report_entries,
        runs=run_entries,
        monitored_space_ids=monitored_spaces,
    )
    thresholds: JSONObject = {
        "minimum_monitored_spaces": minimum_monitored_spaces,
        "minimum_clean_runs_per_space": minimum_clean_runs_per_space,
        "minimum_authority_runs_per_space": minimum_authority_runs_per_space,
    }
    gate = _build_default_readiness_gate(
        summary=summary,
        thresholds=thresholds,
        operator_decision=operator_decision,
    )
    return {
        "report_name": "full_ai_orchestrator_default_readiness",
        "generated_at": datetime.now(UTC).isoformat(),
        "selected_report_paths": [str(path) for path in report_paths],
        "monitored_space_ids": list(monitored_spaces),
        "operator_decision": operator_decision,
        "thresholds": thresholds,
        "summary": summary,
        "default_readiness_gate": gate,
        "reports": report_entries,
        "all_passed": _maybe_string(gate.get("verdict")) == "pass",
    }


def render_default_readiness_markdown(review: JSONObject) -> str:
    """Render a concise default-readiness report."""

    summary = _dict_value(review.get("summary"))
    gate = _dict_value(review.get("default_readiness_gate"))
    thresholds = _dict_value(review.get("thresholds"))
    lines = [
        "# Full AI Orchestrator Default Readiness Gate",
        "",
        f"- Selected settings reports: `{_int_value(summary.get('selected_report_count'))}`",
        f"- Monitored spaces: `{_int_value(summary.get('monitored_space_count'))}`",
        f"- Spaces with clean evidence: `{_int_value(summary.get('spaces_with_clean_evidence_count'))}`",
        f"- Total completed runs: `{_int_value(summary.get('completed_run_count'))}`",
        f"- Total failed runs: `{_int_value(summary.get('failed_run_count'))}`",
        f"- Timed-out runs: `{_int_value(summary.get('timed_out_run_count'))}`",
        f"- Clean settings-path runs: `{_int_value(summary.get('clean_run_count'))}`",
        f"- Authority-exercised clean runs: `{_int_value(summary.get('authority_clean_run_count'))}`",
        f"- Source interventions: `{_int_value(summary.get('source_selection_intervention_count'))}`",
        f"- Chase/stop interventions: `{_int_value(summary.get('chase_or_stop_intervention_count'))}`",
        f"- Verified proof receipts: `{_int_value(summary.get('proofs_verified'))}`",
        f"- Proof verification failures: `{_int_value(summary.get('proof_verification_failures'))}`",
        f"- Pending proof verifications: `{_int_value(summary.get('pending_proof_verifications'))}`",
        f"- Invalid outputs: `{_int_value(summary.get('invalid_output_count'))}`",
        f"- Fallback outputs: `{_int_value(summary.get('fallback_output_count'))}`",
        "",
        "## Thresholds",
        "",
        f"- Monitored spaces: `{_int_value(thresholds.get('minimum_monitored_spaces'))}`",
        f"- Clean runs per space: `{_int_value(thresholds.get('minimum_clean_runs_per_space'))}`",
        f"- Authority runs per space: `{_int_value(thresholds.get('minimum_authority_runs_per_space'))}`",
        f"- Operator decision: `{_maybe_string(review.get('operator_decision')) or 'not_recorded'}`",
        "",
        f"## Default-Readiness Verdict: `{_maybe_string(gate.get('verdict')) or 'unknown'}`",
        "",
        _maybe_string(gate.get("note")) or "No verdict note available.",
    ]
    rollback_reasons = _string_list(gate.get("rollback_reasons"))
    hold_reasons = _string_list(gate.get("hold_reasons"))
    if rollback_reasons:
        lines.extend(["", "### Rollback Reasons", ""])
        lines.extend(f"- {reason}" for reason in rollback_reasons)
    if hold_reasons:
        lines.extend(["", "### Hold Reasons", ""])
        lines.extend(f"- {reason}" for reason in hold_reasons)
    next_step = _maybe_string(gate.get("operator_next_step"))
    if next_step is not None:
        lines.extend(["", "### Next Step", "", f"- {next_step}"])
    lines.extend(["", "## Per-Space Evidence", ""])
    for space in _list_of_dicts(summary.get("space_summaries")):
        lines.append(
            "- "
            f"`{_maybe_string(space.get('space_id')) or 'unknown'}`: "
            f"clean `{_int_value(space.get('clean_run_count'))}`, "
            f"authority `{_int_value(space.get('authority_clean_run_count'))}`, "
            f"source `{_int_value(space.get('source_selection_intervention_count'))}`, "
            f"chase/stop `{_int_value(space.get('chase_or_stop_intervention_count'))}`, "
            f"status `{_maybe_string(space.get('status')) or 'unknown'}`"
        )
    return "\n".join(lines)


def write_default_readiness_review(
    *,
    review: JSONObject,
    output_dir: Path,
) -> dict[str, str]:
    """Write default-readiness JSON and Markdown files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json = output_dir / "summary.json"
    summary_markdown = output_dir / "summary.md"
    summary_json.write_text(
        json.dumps(review, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_markdown.write_text(
        render_default_readiness_markdown(review) + "\n",
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json),
        "summary_markdown": str(summary_markdown),
    }


def _aggregate_runs(
    *,
    reports: Sequence[JSONObject],
    runs: Sequence[JSONObject],
    monitored_space_ids: Sequence[str],
) -> JSONObject:
    space_summaries = [
        _build_space_summary(space_id=space_id, runs=runs)
        for space_id in monitored_space_ids
    ]
    malformed_reports = [
        report for report in reports if _bool_value(report.get("malformed"))
    ]
    non_setting_runs = [
        run
        for run in runs
        if _maybe_string(run.get("guarded_rollout_profile")) != _EXPECTED_PROFILE
        or _maybe_string(run.get("guarded_rollout_profile_source"))
        != _EXPECTED_PROFILE_SOURCE
    ]
    policy_totals = _sum_policy_violations(runs)
    return {
        "selected_report_count": len(reports),
        "malformed_report_count": len(malformed_reports),
        "monitored_space_count": len(monitored_space_ids),
        "run_count": len(runs),
        "completed_run_count": sum(
            1 for run in runs if _maybe_string(run.get("status")) == "completed"
        ),
        "failed_run_count": sum(
            1 for run in runs if _maybe_string(run.get("status")) != "completed"
        ),
        "timed_out_run_count": sum(
            1 for run in runs if _bool_value(run.get("timed_out"))
        ),
        "non_setting_run_count": len(non_setting_runs),
        "clean_run_count": sum(1 for run in runs if _is_clean_settings_run(run)),
        "authority_clean_run_count": sum(
            1
            for run in runs
            if _is_clean_settings_run(run)
            and _bool_value(run.get("profile_authority_exercised"))
        ),
        "source_selection_intervention_count": sum(
            _int_value(run.get("source_selection_interventions")) for run in runs
        ),
        "chase_or_stop_intervention_count": sum(
            _int_value(run.get("chase_or_stop_interventions")) for run in runs
        ),
        "proofs_verified": sum(_int_value(run.get("proofs_verified")) for run in runs),
        "proof_verification_failures": sum(
            _int_value(run.get("proof_verification_failures")) for run in runs
        ),
        "pending_proof_verifications": sum(
            _int_value(run.get("pending_proof_verifications")) for run in runs
        ),
        "invalid_output_count": sum(
            _int_value(run.get("invalid_outputs")) for run in runs
        ),
        "fallback_output_count": sum(
            _int_value(run.get("fallback_outputs")) for run in runs
        ),
        "source_policy_violations": policy_totals,
        "spaces_with_clean_evidence_count": sum(
            1
            for space in space_summaries
            if _int_value(space.get("clean_run_count")) > 0
        ),
        "space_summaries": space_summaries,
    }


def _build_space_summary(*, space_id: str, runs: Sequence[JSONObject]) -> JSONObject:
    space_runs = [run for run in runs if _maybe_string(run.get("space_id")) == space_id]
    clean_runs = [run for run in space_runs if _is_clean_settings_run(run)]
    authority_runs = [
        run for run in clean_runs if _bool_value(run.get("profile_authority_exercised"))
    ]
    status = "clean" if clean_runs else "missing_clean_evidence"
    if any(not _is_clean_settings_run(run) for run in space_runs):
        status = "has_unclean_run"
    return {
        "space_id": space_id,
        "run_count": len(space_runs),
        "clean_run_count": len(clean_runs),
        "authority_clean_run_count": len(authority_runs),
        "source_selection_intervention_count": sum(
            _int_value(run.get("source_selection_interventions")) for run in space_runs
        ),
        "chase_or_stop_intervention_count": sum(
            _int_value(run.get("chase_or_stop_interventions")) for run in space_runs
        ),
        "status": status,
        "run_ids": [
            run_id
            for run in space_runs
            if (run_id := _maybe_string(run.get("run_id"))) is not None
        ],
    }


def _build_default_readiness_gate(
    *,
    summary: JSONObject,
    thresholds: JSONObject,
    operator_decision: str,
) -> JSONObject:
    rollback_reasons = _build_rollback_reasons(summary)
    hold_reasons = _build_hold_reasons(
        summary=summary,
        thresholds=thresholds,
        operator_decision=operator_decision,
    )
    if rollback_reasons:
        verdict: ReadinessVerdict = "rollback_required"
        note = "Default readiness failed because one or more hard safety gates failed."
        next_step = (
            "Rollback affected spaces to deterministic and preserve failed reports "
            "before any further widening."
        )
    elif hold_reasons:
        verdict = "hold"
        note = (
            "Evidence is clean enough to continue monitoring, but not enough to "
            "discuss default adoption."
        )
        next_step = (
            "Collect more repeated settings-path runs for the monitored spaces, "
            "then record an explicit operator decision."
        )
    else:
        verdict = "pass"
        note = (
            "Monitored guarded_source_chase evidence is clean enough to discuss "
            "default adoption. This does not flip the default."
        )
        next_step = (
            "Open a separate operator decision record before any default-mode change."
        )
    return {
        "verdict": verdict,
        "note": note,
        "rollback_reasons": rollback_reasons,
        "hold_reasons": sorted(set(hold_reasons)),
        "operator_next_step": next_step,
    }


def _build_rollback_reasons(summary: JSONObject) -> list[str]:
    reasons: list[str] = []
    checks = (
        (
            "malformed_report_count",
            "one or more settings-canary reports were malformed",
        ),
        ("failed_run_count", "one or more settings-path runs did not complete"),
        ("timed_out_run_count", "one or more settings-path runs timed out"),
        (
            "non_setting_run_count",
            "one or more runs were not guarded_source_chase from space settings",
        ),
        (
            "proof_verification_failures",
            "one or more proof receipts failed verification",
        ),
        (
            "pending_proof_verifications",
            "one or more proof receipts were still pending",
        ),
        ("invalid_output_count", "one or more planner outputs were invalid"),
        ("fallback_output_count", "one or more fallback outputs were present"),
    )
    for field_name, reason in checks:
        if _int_value(summary.get(field_name)):
            reasons.append(reason)
    policy = _dict_value(summary.get("source_policy_violations"))
    for category in ("disabled", "reserved", "context_only", "grounding"):
        if _int_value(policy.get(category)):
            reasons.append(f"{category} source-policy violations were present")
    return reasons


def _build_hold_reasons(
    *,
    summary: JSONObject,
    thresholds: JSONObject,
    operator_decision: str,
) -> list[str]:
    reasons: list[str] = []
    minimum_spaces = _int_value(thresholds.get("minimum_monitored_spaces"))
    if _int_value(summary.get("monitored_space_count")) < minimum_spaces:
        reasons.append(f"fewer than {minimum_spaces} monitored spaces were reviewed")
    minimum_clean = _int_value(thresholds.get("minimum_clean_runs_per_space"))
    minimum_authority = _int_value(thresholds.get("minimum_authority_runs_per_space"))
    for space in _list_of_dicts(summary.get("space_summaries")):
        space_id = _maybe_string(space.get("space_id")) or "unknown"
        if _int_value(space.get("clean_run_count")) < minimum_clean:
            reasons.append(
                f"{space_id} has fewer than {minimum_clean} clean settings-path runs"
            )
        if _int_value(space.get("authority_clean_run_count")) < minimum_authority:
            reasons.append(
                f"{space_id} has fewer than {minimum_authority} authority-exercised clean runs"
            )
    if operator_decision != _OPERATOR_DECISION_APPROVED:
        reasons.append(
            "operator decision approved_for_default_discussion is not recorded"
        )
    return reasons


def _load_report_entry(path: Path) -> JSONObject:
    resolved_path = _resolve_summary_path(path)
    if not resolved_path.exists():
        return {
            "path": str(resolved_path),
            "malformed": True,
            "errors": [f"report not found: {resolved_path}"],
            "runs": [],
        }
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(resolved_path),
            "malformed": True,
            "errors": [f"invalid JSON: {exc}"],
            "runs": [],
        }
    if not isinstance(payload, dict):
        return {
            "path": str(resolved_path),
            "malformed": True,
            "errors": ["summary payload must be an object"],
            "runs": [],
        }
    normalized_runs = [
        _normalize_run(run) for run in _list_of_dicts(payload.get("runs"))
    ]
    return {
        "path": str(resolved_path),
        "malformed": False,
        "verdict": _maybe_string(payload.get("verdict")),
        "report_type": _maybe_string(payload.get("report_type"))
        or _maybe_string(payload.get("report_name")),
        "runs": normalized_runs,
    }


def _normalize_run(run: JSONObject) -> JSONObject:
    counts = _dict_value(run.get("intervention_counts"))
    policy = _dict_value(run.get("policy_violations"))
    return {
        "space_id": _maybe_string(run.get("space_id")),
        "run_id": _maybe_string(run.get("run_id")),
        "status": _maybe_string(run.get("status")),
        "timed_out": _bool_value(run.get("timed_out")),
        "readiness_status": _maybe_string(run.get("readiness_status"))
        or _maybe_string(run.get("guarded_readiness_status")),
        "guarded_rollout_profile": _maybe_string(run.get("guarded_rollout_profile")),
        "guarded_rollout_profile_source": _maybe_string(
            run.get("guarded_rollout_profile_source")
        ),
        "profile_authority_exercised": _bool_value(
            run.get("profile_authority_exercised")
        ),
        "source_selection_interventions": _int_value(
            run.get("source_selection_interventions"),
        )
        or _int_value(counts.get("source_selection")),
        "chase_or_stop_interventions": _int_value(
            run.get("chase_or_stop_interventions"),
        )
        or _int_value(counts.get("chase_or_stop")),
        "proof_count": _int_value(run.get("proof_count")),
        "proofs_verified": _int_value(run.get("proofs_verified"))
        or _int_value(run.get("verified_count")),
        "proof_verification_failures": _int_value(
            run.get("proof_verification_failures"),
        )
        or _int_value(run.get("verification_failed_count")),
        "pending_proof_verifications": _int_value(
            run.get("pending_proof_verifications"),
        )
        or _int_value(run.get("pending_verification_count")),
        "invalid_outputs": _int_value(run.get("invalid_outputs")),
        "fallback_outputs": _int_value(run.get("fallback_outputs")),
        "policy_violations": {
            "disabled": _int_value(policy.get("disabled")),
            "reserved": _int_value(policy.get("reserved")),
            "context_only": _int_value(policy.get("context_only")),
            "grounding": _int_value(policy.get("grounding")),
        },
    }


def _is_clean_settings_run(run: JSONObject) -> bool:
    return (
        _maybe_string(run.get("status")) == "completed"
        and not _bool_value(run.get("timed_out"))
        and _maybe_string(run.get("readiness_status")) == "ready_verified"
        and _maybe_string(run.get("guarded_rollout_profile")) == _EXPECTED_PROFILE
        and _maybe_string(run.get("guarded_rollout_profile_source"))
        == _EXPECTED_PROFILE_SOURCE
        and _int_value(run.get("proofs_verified")) > 0
        and _int_value(run.get("proof_verification_failures")) == 0
        and _int_value(run.get("pending_proof_verifications")) == 0
        and _int_value(run.get("invalid_outputs")) == 0
        and _int_value(run.get("fallback_outputs")) == 0
        and not any(_sum_policy_violations([run]).values())
    )


def _sum_policy_violations(runs: Sequence[JSONObject]) -> JSONObject:
    totals = {"disabled": 0, "reserved": 0, "context_only": 0, "grounding": 0}
    for run in runs:
        policy = _dict_value(run.get("policy_violations"))
        for category in totals:
            totals[category] += _int_value(policy.get(category))
    return totals


def _resolve_report_paths(args: argparse.Namespace) -> tuple[Path, ...]:
    paths: list[Path] = []
    for raw_path in _string_list(getattr(args, "report", [])):
        paths.append(Path(raw_path))
    reports_arg = _maybe_string(getattr(args, "reports", ""))
    if reports_arg:
        paths.extend(
            Path(part.strip()) for part in reports_arg.split(",") if part.strip()
        )
    latest_count = _int_value(getattr(args, "latest_count", 0))
    if not paths and latest_count > 0:
        paths.extend(_latest_report_paths(Path(args.report_dir), latest_count))
    if not paths:
        raise SystemExit("At least one report is required.")
    return tuple(paths)


def _resolve_monitored_space_ids(args: argparse.Namespace) -> tuple[str, ...]:
    ids: list[str] = []
    ids.extend(_string_list(getattr(args, "monitored_space_id", [])))
    ids_arg = _maybe_string(getattr(args, "monitored_space_ids", ""))
    if ids_arg:
        ids.extend(part.strip() for part in ids_arg.split(",") if part.strip())
    return tuple(dict.fromkeys(ids))


def _latest_report_paths(report_dir: Path, latest_count: int) -> list[Path]:
    if latest_count <= 0:
        return []
    if not report_dir.exists():
        raise SystemExit(f"Report directory does not exist: {report_dir}")
    summary_paths = sorted(
        report_dir.glob("*/summary.json"),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    return summary_paths[:latest_count]


def _resolve_summary_path(path: Path) -> Path:
    if path.is_dir():
        return path / "summary.json"
    if path.name == "summary.md":
        return path.with_name("summary.json")
    return path


def _resolve_output_dir(output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    return _DEFAULT_OUTPUT_ROOT / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _positive_int(value: object, field_name: str) -> int:
    int_value = _int_value(value)
    if int_value <= 0:
        raise SystemExit(f"{field_name} must be greater than zero.")
    return int_value


def _dict_value(value: object) -> JSONObject:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _maybe_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _bool_value(value: object) -> bool:
    return value is True


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
