#!/usr/bin/env python3
"""Run a guarded chase rollout proof using one baseline replayed twice."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.phase1_compare import (
    Phase1CompareRequest,
    run_guarded_chase_rollout_proof_sync,
)
from artana_evidence_api.phase2_shadow_fixture_refresh import (
    Phase2ShadowFixtureSpec,
    fixture_request_from_spec,
    phase2_shadow_fixture_specs_for_set,
)

from scripts.run_phase1_guarded_eval import _phase1_guarded_preflight

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one guarded chase rollout proof by executing a baseline once "
            "and replaying the full orchestrator with guarded chase disabled "
            "and enabled."
        ),
    )
    parser.add_argument(
        "--fixture",
        default="SUPPLEMENTAL_CHASE_SELECTION",
        help="Fixture name to prove. Defaults to SUPPLEMENTAL_CHASE_SELECTION.",
    )
    parser.add_argument(
        "--all-fixtures",
        action="store_true",
        help=(
            "Run the guarded rollout proof for every fixture in the selected "
            "fixture set and emit one aggregate report."
        ),
    )
    parser.add_argument(
        "--fixture-set",
        choices=("objective", "supplemental", "all"),
        default="supplemental",
        help="Fixture family to search. Defaults to supplemental.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for generated reports. Defaults to "
            "reports/full_ai_orchestrator_guarded_rollout/<timestamp>/."
        ),
    )
    parser.add_argument(
        "--compare-timeout-seconds",
        type=float,
        default=300.0,
        help="Per-phase timeout. Defaults to 300 seconds.",
    )
    parser.add_argument(
        "--require-continue-boundary",
        action="store_true",
        help=(
            "Require at least one fixture to prove guarded rollout can continue "
            "with a chase selection."
        ),
    )
    parser.add_argument(
        "--require-stop-boundary",
        action="store_true",
        help=(
            "Require at least one fixture to prove guarded rollout can stop "
            "instead of chasing."
        ),
    )
    parser.add_argument(
        "--continue-on-fixture-error",
        action="store_true",
        help=(
            "For aggregate runs, keep evaluating remaining fixtures after a "
            "fixture error and write a failed aggregate report."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    preflight = _phase1_guarded_preflight()
    if preflight["status"] != "ready":
        model_id = preflight["model_id"]
        model_text = f" ({model_id})" if model_id is not None else ""
        raise SystemExit(
            "Guarded chase rollout proof requires live planner access before "
            f"running. Planner capability `{preflight['capability']}`{model_text}: "
            f"{preflight['detail']}",
        )
    output_dir = (
        _resolve_path(args.output_dir)
        if args.output_dir is not None
        else (
            _REPO_ROOT
            / "reports"
            / "full_ai_orchestrator_guarded_rollout"
            / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        )
    )
    fixture_specs = _resolve_fixtures(
        fixture_name=args.fixture,
        fixture_set=args.fixture_set,
        all_fixtures=args.all_fixtures,
    )
    fixture_reports: list[JSONObject] = []
    for spec in fixture_specs:
        try:
            fixture_reports.append(
                _run_fixture_rollout_proof(
                    spec,
                    fixture_set=args.fixture_set,
                    compare_timeout_seconds=args.compare_timeout_seconds,
                    preflight=preflight,
                ),
            )
        except SystemExit as exc:
            if not args.continue_on_fixture_error:
                raise
            fixture_reports.append(
                _build_fixture_failure_report(
                    spec,
                    fixture_set=args.fixture_set,
                    preflight=preflight,
                    exc=exc,
                ),
            )
        except Exception as exc:
            if not args.continue_on_fixture_error:
                raise
            fixture_reports.append(
                _build_fixture_failure_report(
                    spec,
                    fixture_set=args.fixture_set,
                    preflight=preflight,
                    exc=exc,
                ),
            )
    report = (
        _apply_single_fixture_requirements(
            fixture_reports[0],
            require_continue_boundary=args.require_continue_boundary,
            require_stop_boundary=args.require_stop_boundary,
        )
        if len(fixture_reports) == 1
        else _build_aggregate_rollout_proof_report(
            fixture_reports=fixture_reports,
            fixture_set=args.fixture_set,
            preflight=preflight,
            require_continue_boundary=args.require_continue_boundary,
            require_stop_boundary=args.require_stop_boundary,
        )
    )
    manifest = write_rollout_proof_report(report, output_dir=output_dir)
    print(render_rollout_proof_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    return 0 if _rollout_boundary_passed(report) else 1


def _resolve_fixture(name: str, fixture_set: str) -> Phase2ShadowFixtureSpec:
    normalized = name.strip().lower()
    for spec in phase2_shadow_fixture_specs_for_set(fixture_set):
        if spec.fixture_name.lower() == normalized:
            return spec
    raise SystemExit(
        f"Fixture `{name}` was not found in fixture set `{fixture_set}`.",
    )


def _resolve_fixtures(
    *,
    fixture_name: str,
    fixture_set: str,
    all_fixtures: bool,
) -> tuple[Phase2ShadowFixtureSpec, ...]:
    if all_fixtures:
        return phase2_shadow_fixture_specs_for_set(fixture_set)
    return (_resolve_fixture(fixture_name, fixture_set),)


def _guarded_rollout_request_from_spec(
    spec: Phase2ShadowFixtureSpec,
    *,
    compare_timeout_seconds: float,
) -> Phase1CompareRequest:
    request = fixture_request_from_spec(spec)
    return Phase1CompareRequest(
        objective=request.objective,
        seed_terms=request.seed_terms,
        title=request.title,
        sources=request.sources,
        max_depth=request.max_depth,
        max_hypotheses=request.max_hypotheses,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        compare_timeout_seconds=compare_timeout_seconds,
    )


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else _REPO_ROOT / path


def _dict_value(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _seam_result_stop_count(rollout_report: dict[str, object]) -> int:
    seam_results = rollout_report.get("seam_results")
    if not isinstance(seam_results, list):
        return 0
    return sum(
        1
        for result in seam_results
        if isinstance(result, dict) and bool(result.get("selection_stop_instead"))
    )


def _seam_result_continue_count(rollout_report: dict[str, object]) -> int:
    seam_results = rollout_report.get("seam_results")
    if not isinstance(seam_results, list):
        return 0
    return sum(
        1
        for result in seam_results
        if isinstance(result, dict)
        and bool(result.get("selection_returned"))
        and not bool(result.get("selection_stop_instead"))
    )


def _run_fixture_rollout_proof(
    spec: Phase2ShadowFixtureSpec,
    *,
    fixture_set: str,
    compare_timeout_seconds: float,
    preflight: dict[str, str | None],
) -> JSONObject:
    request = _guarded_rollout_request_from_spec(
        spec,
        compare_timeout_seconds=compare_timeout_seconds,
    )
    try:
        report = run_guarded_chase_rollout_proof_sync(request)
    except GraphServiceClientError as exc:
        raise SystemExit(_format_rollout_graph_error(spec, exc)) from exc
    if not isinstance(report, dict):
        msg = (
            "Guarded chase rollout proof returned a malformed report for "
            f"fixture {spec.fixture_name}: expected object, got "
            f"{type(report).__name__}."
        )
        raise TypeError(msg)
    if not isinstance(report.get("comparison"), dict):
        msg = (
            "Guarded chase rollout proof returned a malformed report for "
            f"fixture {spec.fixture_name}: missing comparison section."
        )
        raise TypeError(msg)
    report["generated_at"] = datetime.now(UTC).isoformat()
    report["fixture_name"] = spec.fixture_name
    report["fixture_set"] = fixture_set
    report["fixture_status"] = "completed"
    report["preflight"] = preflight

    rollout_off = _dict_value(report.get("rollout_off"))
    rollout_on = _dict_value(report.get("rollout_on"))
    comparison = _dict_value(report.get("comparison"))
    off_stop_count = _seam_result_stop_count(rollout_off)
    on_stop_count = _seam_result_stop_count(rollout_on)
    off_continue_count = _seam_result_continue_count(rollout_off)
    on_continue_count = _seam_result_continue_count(rollout_on)
    comparison["off_selection_returned_count"] = _int_value(
        rollout_off.get("selection_returned_count"),
    )
    comparison["on_selection_returned_count"] = _int_value(
        rollout_on.get("selection_returned_count"),
    )
    comparison["stop_boundary_observed"] = off_stop_count == 0 and on_stop_count > 0
    comparison["continue_boundary_observed"] = (
        off_continue_count == 0 and on_continue_count > 0
    )
    comparison["off_stop_selection_count"] = off_stop_count
    comparison["on_stop_selection_count"] = on_stop_count
    comparison["off_continue_selection_count"] = off_continue_count
    comparison["on_continue_selection_count"] = on_continue_count
    report["comparison"] = comparison
    report["verification_posture"] = _profile_verification_posture(report)
    return report


def _build_fixture_failure_report(
    spec: Phase2ShadowFixtureSpec,
    *,
    fixture_set: str,
    preflight: dict[str, str | None],
    exc: BaseException,
) -> JSONObject:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_name": spec.fixture_name,
        "fixture_set": fixture_set,
        "fixture_status": "failed",
        "preflight": preflight,
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
        "comparison": {
            "boundary_observed": False,
            "continue_boundary_observed": False,
            "stop_boundary_observed": False,
            "off_selection_returned_count": 0,
            "on_selection_returned_count": 0,
        },
        "verification_posture": {
            "mode": "unavailable",
            "post_execution_verification_expected": False,
            "note": "Fixture failed before verification posture could be profiled.",
        },
    }


def _build_aggregate_rollout_proof_report(
    *,
    fixture_reports: Sequence[JSONObject],
    fixture_set: str,
    preflight: dict[str, str | None],
    require_continue_boundary: bool,
    require_stop_boundary: bool,
) -> JSONObject:
    boundary_observed_count = 0
    profile_boundary_observed_count = 0
    stop_boundary_count = 0
    continue_boundary_count = 0
    completed_fixture_count = 0
    failed_fixtures: list[JSONObject] = []
    for report in fixture_reports:
        if report.get("fixture_status") == "completed":
            completed_fixture_count += 1
        else:
            error = _dict_value(report.get("error"))
            failed_fixtures.append(
                {
                    "fixture_name": str(report.get("fixture_name", "unknown")),
                    "error_type": str(error.get("type", "unknown")),
                    "error_message": str(error.get("message", "")),
                },
            )
        comparison = _dict_value(report.get("comparison"))
        if bool(comparison.get("boundary_observed")):
            boundary_observed_count += 1
        if bool(comparison.get("profile_boundaries_observed")):
            profile_boundary_observed_count += 1
        if bool(comparison.get("stop_boundary_observed")):
            stop_boundary_count += 1
        if bool(comparison.get("continue_boundary_observed")):
            continue_boundary_count += 1

    all_fixtures_completed = completed_fixture_count == len(fixture_reports)
    all_fixture_boundaries_observed = (
        all_fixtures_completed and boundary_observed_count == len(fixture_reports)
    )
    all_profile_boundaries_observed = (
        all_fixtures_completed
        and profile_boundary_observed_count == len(fixture_reports)
    )
    required_continue_boundary_observed = (
        not require_continue_boundary or continue_boundary_count > 0
    )
    required_stop_boundary_observed = (
        not require_stop_boundary or stop_boundary_count > 0
    )
    all_boundaries_observed = (
        all_fixture_boundaries_observed
        and required_continue_boundary_observed
        and required_stop_boundary_observed
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "fixture_set": fixture_set,
        "preflight": preflight,
        "fixtures": list(fixture_reports),
        "verification_posture": _aggregate_verification_posture(),
        "summary": {
            "fixture_count": len(fixture_reports),
            "completed_fixture_count": completed_fixture_count,
            "failed_fixture_count": len(failed_fixtures),
            "all_fixtures_completed": all_fixtures_completed,
            "failed_fixtures": failed_fixtures,
            "boundary_observed_count": boundary_observed_count,
            "profile_boundary_observed_count": profile_boundary_observed_count,
            "stop_boundary_count": stop_boundary_count,
            "continue_boundary_count": continue_boundary_count,
            "all_fixture_boundaries_observed": all_fixture_boundaries_observed,
            "all_profile_boundaries_observed": all_profile_boundaries_observed,
            "require_continue_boundary": require_continue_boundary,
            "require_stop_boundary": require_stop_boundary,
            "required_continue_boundary_observed": (
                required_continue_boundary_observed
            ),
            "required_stop_boundary_observed": required_stop_boundary_observed,
            "all_boundaries_observed": all_boundaries_observed,
        },
    }


def _apply_single_fixture_requirements(
    report: JSONObject,
    *,
    require_continue_boundary: bool,
    require_stop_boundary: bool,
) -> JSONObject:
    comparison = _dict_value(report.get("comparison"))
    required_continue_boundary_observed = not require_continue_boundary or bool(
        comparison.get("continue_boundary_observed")
    )
    required_stop_boundary_observed = not require_stop_boundary or bool(
        comparison.get("stop_boundary_observed")
    )
    comparison["require_continue_boundary"] = require_continue_boundary
    comparison["require_stop_boundary"] = require_stop_boundary
    comparison["required_continue_boundary_observed"] = (
        required_continue_boundary_observed
    )
    comparison["required_stop_boundary_observed"] = required_stop_boundary_observed
    comparison["required_boundaries_observed"] = (
        required_continue_boundary_observed and required_stop_boundary_observed
    )
    report["comparison"] = comparison
    return report


def _rollout_boundary_passed(report: JSONObject) -> bool:
    fixtures = report.get("fixtures")
    if isinstance(fixtures, list):
        if not isinstance(report.get("verification_posture"), dict):
            return False
        return bool(_dict_value(report.get("summary")).get("all_boundaries_observed"))
    if not isinstance(report.get("comparison"), dict) or not isinstance(
        report.get("verification_posture"),
        dict,
    ):
        return False
    comparison = _dict_value(report.get("comparison"))
    return bool(comparison.get("boundary_observed")) and bool(
        comparison.get("required_boundaries_observed", True),
    )


def _profile_verification_posture(report: JSONObject) -> JSONObject:
    profile_reports = _dict_value(report.get("profile_reports"))
    readiness_statuses: dict[str, str] = {}
    for profile_key in ("dry_run", "chase_only", "source_chase", "low_risk"):
        profile = _dict_value(profile_reports.get(profile_key))
        workspace = _dict_value(profile.get("workspace"))
        readiness = _dict_value(workspace.get("guarded_readiness"))
        status = readiness.get("status")
        readiness_statuses[profile_key] = (
            status if isinstance(status, str) else "unknown"
        )
    return {
        "mode": "profile_boundary_counterfactual",
        "post_execution_verification_expected": False,
        "readiness_statuses": readiness_statuses,
        "note": (
            "This proof reuses one deterministic baseline and replays rollout "
            "profiles counterfactually. It proves profile eligibility boundaries, "
            "not post-execution verification. Pending readiness in this report "
            "is expected when a counterfactual guarded action is not executed "
            "through a full verification pass; use the guarded graduation gate "
            "for verified rollout readiness."
        ),
    }


def _aggregate_verification_posture() -> JSONObject:
    return {
        "mode": "profile_boundary_counterfactual",
        "post_execution_verification_expected": False,
        "note": (
            "Aggregate profile proof reports prove rollout-profile boundaries "
            "across fixtures. They do not replace the guarded graduation gate, "
            "which verifies applied guarded actions after execution."
        ),
    }


def _required_boundary_markdown_status(
    *,
    required: object,
    observed: object,
) -> str:
    if not bool(required):
        return "not required"
    return "yes" if bool(observed) else "no"


def _format_rollout_graph_error(
    spec: Phase2ShadowFixtureSpec,
    exc: GraphServiceClientError,
) -> str:
    detail = exc.detail or str(exc)
    if "Signature verification failed" in detail:
        return (
            "Guarded chase rollout proof could not sync the temporary research "
            f"space for fixture `{spec.fixture_name}` because the backend and "
            "graph service JWT secrets are out of sync "
            "(signature verification failed). Restart both services with the "
            "same AUTH_JWT_SECRET and GRAPH_JWT_SECRET, then rerun the proof."
        )
    return (
        "Guarded chase rollout proof failed while syncing the temporary "
        f"research space for fixture `{spec.fixture_name}`: {exc}"
    )


def render_rollout_proof_markdown(report: JSONObject) -> str:
    fixtures = report.get("fixtures")
    if isinstance(fixtures, list):
        summary = _dict_value(report.get("summary"))
        verification_posture = _dict_value(report.get("verification_posture"))
        lines = [
            "# Guarded Chase Rollout Proof",
            "",
            f"- Generated: {report.get('generated_at', 'n/a')}",
            f"- Fixture set: {report.get('fixture_set', 'unknown')}",
            f"- Fixtures: {summary.get('fixture_count', len(fixtures))}",
            f"- Completed fixtures: {summary.get('completed_fixture_count', 0)}",
            f"- Failed fixtures: {summary.get('failed_fixture_count', 0)}",
            (
                "- All rollout boundaries observed: "
                f"{'yes' if summary.get('all_boundaries_observed') else 'no'}"
            ),
            (
                "- All fixture boundaries observed: "
                f"{'yes' if summary.get('all_fixture_boundaries_observed') else 'no'}"
            ),
            f"- Boundary-observed fixtures: {summary.get('boundary_observed_count', 0)}",
            (
                "- Profile-boundary fixtures: "
                f"{summary.get('profile_boundary_observed_count', 0)}"
            ),
            f"- Continue-boundary fixtures: {summary.get('continue_boundary_count', 0)}",
            f"- Stop-boundary fixtures: {summary.get('stop_boundary_count', 0)}",
            (
                "- Required continue boundary observed: "
                f"{_required_boundary_markdown_status(required=summary.get('require_continue_boundary'), observed=summary.get('required_continue_boundary_observed'))}"
            ),
            (
                "- Required stop boundary observed: "
                f"{_required_boundary_markdown_status(required=summary.get('require_stop_boundary'), observed=summary.get('required_stop_boundary_observed'))}"
            ),
            "",
            "## Verification Posture",
            "",
            f"- Mode: {verification_posture.get('mode', 'unknown')}",
            (
                "- Post-execution verification expected here: "
                f"{'yes' if verification_posture.get('post_execution_verification_expected') else 'no'}"
            ),
            f"- Note: {verification_posture.get('note', '')}",
        ]
        failed_fixtures = summary.get("failed_fixtures")
        if isinstance(failed_fixtures, list) and failed_fixtures:
            lines.extend(["", "## Failed Fixtures", ""])
            for failure in failed_fixtures:
                if not isinstance(failure, dict):
                    continue
                fixture_name = failure.get("fixture_name", "unknown")
                error_type = failure.get("error_type", "unknown")
                error_message = failure.get("error_message", "")
                lines.append(f"- {fixture_name}: {error_type}: {error_message}")
        lines.extend(
            [
                "",
                "## Fixture Summary",
                "",
                "| Fixture | Status | Boundary | Continue boundary | Stop boundary | Off selections | On selections |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ],
        )
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            comparison = _dict_value(fixture.get("comparison"))
            lines.append(
                "| "
                f"{fixture.get('fixture_name', 'unknown')} | "
                f"{fixture.get('fixture_status', 'unknown')} | "
                f"{'yes' if comparison.get('boundary_observed') else 'no'} | "
                f"{'yes' if comparison.get('continue_boundary_observed') else 'no'} | "
                f"{'yes' if comparison.get('stop_boundary_observed') else 'no'} | "
                f"{comparison.get('off_selection_returned_count', 0)} | "
                f"{comparison.get('on_selection_returned_count', 0)} |"
            )
        return "\n".join(lines)

    comparison = _dict_value(report.get("comparison"))
    verification_posture = _dict_value(report.get("verification_posture"))
    rollout_off = _dict_value(report.get("rollout_off"))
    rollout_on = _dict_value(report.get("rollout_on"))
    profile_reports = _dict_value(report.get("profile_reports"))
    off_guarded = _dict_value(rollout_off.get("guarded_evaluation"))
    on_guarded = _dict_value(rollout_on.get("guarded_evaluation"))
    lines = [
        "# Guarded Chase Rollout Proof",
        "",
        f"- Generated: {report.get('generated_at', 'n/a')}",
        f"- Fixture: {report.get('fixture_name', 'unknown')}",
        f"- Baseline run: {_dict_value(report.get('baseline')).get('run_id', 'n/a')}",
        (
            "- Boundary observed: "
            f"{'yes' if comparison.get('boundary_observed') else 'no'}"
        ),
        (
            "- Profile boundaries observed: "
            f"{'yes' if comparison.get('profile_boundaries_observed') else 'no'}"
        ),
        "",
        "## Rollout Off",
        "",
        f"- Run: {rollout_off.get('run_id', 'n/a')}",
        f"- Guarded chase rollout enabled: {rollout_off.get('guarded_chase_rollout_enabled', False)}",
        f"- Guarded candidate actions: {_int_value(off_guarded.get('candidate_count'))}",
        f"- Guarded seam selections returned: {_int_value(rollout_off.get('selection_returned_count'))}",
        "",
        "## Rollout On",
        "",
        f"- Run: {rollout_on.get('run_id', 'n/a')}",
        f"- Guarded chase rollout enabled: {rollout_on.get('guarded_chase_rollout_enabled', False)}",
        f"- Guarded candidate actions: {_int_value(on_guarded.get('candidate_count'))}",
        f"- Guarded seam selections returned: {_int_value(rollout_on.get('selection_returned_count'))}",
        "",
        "## Comparison",
        "",
        f"- Off seam selection count: {comparison.get('off_selection_returned_count', 0)}",
        f"- On seam selection count: {comparison.get('on_selection_returned_count', 0)}",
        (
            "- Chase-only structured selections: "
            f"{comparison.get('chase_only_structured_selection_returned_count', 0)}"
        ),
        (
            "- Low-risk structured selections: "
            f"{comparison.get('low_risk_structured_selection_returned_count', 0)}"
        ),
        (
            "- Low-risk chase selections: "
            f"{comparison.get('low_risk_chase_selection_returned_count', 0)}"
        ),
        (
            "- Continue boundary observed: "
            f"{'yes' if comparison.get('continue_boundary_observed') else 'no'}"
        ),
        (
            "- Stop boundary observed: "
            f"{'yes' if comparison.get('stop_boundary_observed') else 'no'}"
        ),
        (
            "- Required continue boundary observed: "
            f"{_required_boundary_markdown_status(required=comparison.get('require_continue_boundary'), observed=comparison.get('required_continue_boundary_observed'))}"
        ),
        (
            "- Required stop boundary observed: "
            f"{_required_boundary_markdown_status(required=comparison.get('require_stop_boundary'), observed=comparison.get('required_stop_boundary_observed'))}"
        ),
        "",
        "## Verification Posture",
        "",
        f"- Mode: {verification_posture.get('mode', 'unknown')}",
        (
            "- Post-execution verification expected here: "
            f"{'yes' if verification_posture.get('post_execution_verification_expected') else 'no'}"
        ),
        f"- Note: {verification_posture.get('note', '')}",
    ]
    if profile_reports:
        lines.extend(
            [
                "",
                "## Profile Summary",
                "",
                "| Profile | Chase enabled | Applied actions | Structured selections | Chase selections | Readiness |",
                "| --- | --- | --- | --- | --- | --- |",
            ],
        )
        for profile_key in ("dry_run", "chase_only", "source_chase", "low_risk"):
            profile = _dict_value(profile_reports.get(profile_key))
            workspace = _dict_value(profile.get("workspace"))
            readiness = _dict_value(workspace.get("guarded_readiness"))
            guarded = _dict_value(profile.get("guarded_evaluation"))
            lines.append(
                "| "
                f"{profile.get('guarded_rollout_profile', profile_key)} | "
                f"{profile.get('guarded_chase_rollout_enabled', False)} | "
                f"{guarded.get('applied_count', 0)} | "
                f"{profile.get('structured_selection_returned_count', 0)} | "
                f"{profile.get('selection_returned_count', 0)} | "
                f"{readiness.get('status', 'unknown')} |"
            )
    return "\n".join(lines)


def write_rollout_proof_report(
    report: JSONObject,
    *,
    output_dir: str | Path,
) -> JSONObject:
    _validate_rollout_proof_report_payload(report)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    summary_json_path = output_dir_path / "summary.json"
    summary_markdown_path = output_dir_path / "summary.md"
    summary_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    summary_markdown_path.write_text(
        render_rollout_proof_markdown(report),
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json_path),
        "summary_markdown": str(summary_markdown_path),
    }


def _validate_rollout_proof_report_payload(report: JSONObject) -> None:
    if not isinstance(report, dict):
        msg = (
            "Guarded chase rollout proof report must be a JSON object, got "
            f"{type(report).__name__}."
        )
        raise TypeError(msg)
    fixtures = report.get("fixtures")
    if isinstance(fixtures, list):
        if not isinstance(report.get("summary"), dict):
            msg = (
                "Guarded chase rollout proof aggregate report is malformed: "
                "missing summary section."
            )
            raise TypeError(msg)
        for index, fixture in enumerate(fixtures):
            if isinstance(fixture, dict):
                continue
            msg = (
                "Guarded chase rollout proof aggregate report is malformed: "
                f"fixture entry {index} must be an object, got "
                f"{type(fixture).__name__}."
            )
            raise TypeError(msg)
    if not isinstance(report.get("comparison"), dict) and not isinstance(
        fixtures,
        list,
    ):
        msg = (
            "Guarded chase rollout proof report is malformed: missing comparison "
            "section."
        )
        raise TypeError(msg)
    if not isinstance(report.get("verification_posture"), dict):
        msg = (
            "Guarded chase rollout proof report is malformed: missing "
            "verification_posture section."
        )
        raise TypeError(msg)


if __name__ == "__main__":
    raise SystemExit(main())
