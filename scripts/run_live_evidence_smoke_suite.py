#!/usr/bin/env python3
"""Run a repeatable live evidence smoke suite across multiple scenarios."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from scripts.run_live_evidence_session_audit import (  # noqa: E402
    LiveEvidenceSessionAuditConfig,
    _dict_value,
    _load_environment_overrides,
    _maybe_string,
    _normalize_log_commands,
    _normalize_positive_float,
    _normalize_positive_int,
    _request_json_with_status,
    _resolve_auth_headers,
    _resolve_path,
    _round_float,
    _safe_filename,
    _string_list,
    run_live_evidence_session_audit,
    write_live_evidence_session_audit_report,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject


_DEFAULT_BASE_URL = "http://localhost:8091"
_DEFAULT_OUTPUT_SUBDIR = "live_evidence_smoke_suite"
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_POLL_TIMEOUT_SECONDS = 900.0
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_GRAPH_SETTLE_SECONDS = 20.0
_DEFAULT_REPEAT_COUNT = 1
_DEFAULT_SPACE_NAME_PREFIX = "Live Evidence Smoke"
_DEFAULT_SPACE_DESCRIPTION_PREFIX = "Fresh space for live evidence smoke suite"
_DEFAULT_LABEL = "live-evidence-smoke-suite"
_DEFAULT_PROMOTION_REASON = "Live evidence smoke suite promotion"
_DEFAULT_SPACE_SOURCES = {"pubmed": True, "clinvar": True}
_DEFAULT_RESEARCH_SOURCES = {
    "pubmed": True,
    "clinvar": True,
    "marrvel": True,
    "mondo": True,
    "pdf": True,
    "text": True,
    "drugbank": False,
    "alphafold": False,
    "uniprot": False,
    "hgnc": False,
    "clinical_trials": False,
    "mgi": False,
    "zfin": False,
}
_HTTP_CREATED = 201
_SPACE_CREATE_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True, slots=True)
class LiveEvidenceSmokeScenario:
    key: str
    name: str
    description: str
    objective: str
    seed_terms: tuple[str, ...]
    research_init_title: str
    bootstrap_title: str
    bootstrap_objective: str
    bootstrap_source_type: str = "pubmed"
    space_sources: dict[str, bool] | None = None
    research_sources: dict[str, bool] | None = None


@dataclass(frozen=True, slots=True)
class LiveEvidenceSmokeSuiteConfig:
    base_url: str
    auth_headers: dict[str, str]
    output_dir: Path
    label: str
    scenarios: tuple[LiveEvidenceSmokeScenario, ...]
    repeat_count: int
    poll_timeout_seconds: float
    poll_interval_seconds: float
    graph_settle_seconds: float
    promote_first_proposal: bool
    promotion_reason: str
    require_graph_activity: bool
    log_commands: tuple[object, ...]
    log_error_patterns: tuple[str, ...]
    log_ignore_patterns: tuple[str, ...]
    fail_on_log_match: bool
    space_name_prefix: str
    space_description_prefix: str


_DEFAULT_SCENARIOS: tuple[LiveEvidenceSmokeScenario, ...] = (
    LiveEvidenceSmokeScenario(
        key="med13_regulation",
        name="MED13 Regulation",
        description="Rare-disease-style MED13 evidence promotion flow.",
        objective=(
            "Find evidence-backed MED13 regulatory relations and promote one "
            "supported claim."
        ),
        seed_terms=("MED13", "cardiomyopathy"),
        research_init_title="MED13 Smoke Audit",
        bootstrap_title="MED13 Smoke Bootstrap",
        bootstrap_objective="Bootstrap MED13 evidence-backed graph claims.",
        space_sources=dict(_DEFAULT_SPACE_SOURCES),
        research_sources=dict(_DEFAULT_RESEARCH_SOURCES),
    ),
    LiveEvidenceSmokeScenario(
        key="ceruloplasmin_neurodegeneration",
        name="Ceruloplasmin Iron Homeostasis",
        description="Iron-homeostasis evidence promotion flow around ceruloplasmin.",
        objective=(
            "Find evidence-backed ceruloplasmin and aceruloplasminemia relations "
            "about iron homeostasis and promote one supported claim."
        ),
        seed_terms=("Ceruloplasmin", "Aceruloplasminemia", "iron homeostasis"),
        research_init_title="Ceruloplasmin Iron Smoke Audit",
        bootstrap_title="Ceruloplasmin Iron Smoke Bootstrap",
        bootstrap_objective=(
            "Bootstrap ceruloplasmin and iron-homeostasis evidence-backed claims."
        ),
        space_sources=dict(_DEFAULT_SPACE_SOURCES),
        research_sources=dict(_DEFAULT_RESEARCH_SOURCES),
    ),
    LiveEvidenceSmokeScenario(
        key="cdc27_congenital_findings",
        name="CDC27 Developmental Findings",
        description="Developmental phenotype evidence promotion flow around CDC27.",
        objective=(
            "Find evidence-backed CDC27 relations tied to developmental findings "
            "and promote one supported claim."
        ),
        seed_terms=("CDC27", "developmental delay", "hypotonia"),
        research_init_title="CDC27 Developmental Smoke Audit",
        bootstrap_title="CDC27 Developmental Smoke Bootstrap",
        bootstrap_objective="Bootstrap CDC27 developmental finding evidence-backed claims.",
        space_sources=dict(_DEFAULT_SPACE_SOURCES),
        research_sources=dict(_DEFAULT_RESEARCH_SOURCES),
    ),
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the live smoke suite."""

    parser = argparse.ArgumentParser(
        description=(
            "Create fresh spaces, run a small set of live evidence session audits, "
            "and roll them into one end-to-end smoke-suite report."
        ),
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario key to run. Repeat to select multiple scenarios.",
    )
    parser.add_argument(
        "--scenarios",
        default="",
        help="Comma-separated scenario keys.",
    )
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="Print the available built-in scenario keys and exit.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=_DEFAULT_REPEAT_COUNT,
        help="Repeat each scenario audit this many times. Defaults to 1.",
    )
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=_DEFAULT_POLL_TIMEOUT_SECONDS,
        help="Maximum time to wait for one queued run. Defaults to 900 seconds.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=_DEFAULT_POLL_INTERVAL_SECONDS,
        help="Polling interval between run status checks. Defaults to 2 seconds.",
    )
    parser.add_argument(
        "--graph-settle-seconds",
        type=float,
        default=_DEFAULT_GRAPH_SETTLE_SECONDS,
        help="Time to wait for graph write visibility. Defaults to 20 seconds.",
    )
    parser.add_argument(
        "--promote-first-proposal",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Promote the first bootstrap proposal for each scenario.",
    )
    parser.add_argument(
        "--require-graph-activity",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require graph claim and evidence writes for the scenario to pass.",
    )
    parser.add_argument(
        "--promotion-reason",
        default=_DEFAULT_PROMOTION_REASON,
        help="Promotion reason recorded on each promoted proposal.",
    )
    parser.add_argument(
        "--space-name-prefix",
        default=_DEFAULT_SPACE_NAME_PREFIX,
        help="Prefix for newly created smoke-suite spaces.",
    )
    parser.add_argument(
        "--space-description-prefix",
        default=_DEFAULT_SPACE_DESCRIPTION_PREFIX,
        help="Prefix for newly created smoke-suite space descriptions.",
    )
    parser.add_argument(
        "--log-command",
        action="append",
        default=[],
        help="Optional log tail command forwarded to each scenario audit.",
    )
    parser.add_argument(
        "--log-error-pattern",
        action="append",
        default=[],
        help="Repeatable regex treated as suspicious in captured logs.",
    )
    parser.add_argument(
        "--log-ignore-pattern",
        action="append",
        default=[],
        help="Repeatable regex ignored even if it matches an error pattern.",
    )
    parser.add_argument(
        "--fail-on-log-match",
        action="store_true",
        help="Fail the suite when suspicious log lines are captured.",
    )
    parser.add_argument(
        "--label",
        default=_DEFAULT_LABEL,
        help="Human-readable report label.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for generated smoke-suite reports. Defaults to "
            "reports/live_evidence_smoke_suite/<timestamp>/."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=_DEFAULT_BASE_URL,
        help=f"Artana Evidence API base URL. Defaults to {_DEFAULT_BASE_URL}.",
    )
    parser.add_argument("--api-key", default="", help="Artana API key to send.")
    parser.add_argument(
        "--bearer-token",
        default="",
        help="Bearer token to send as Authorization header.",
    )
    parser.add_argument(
        "--use-test-auth",
        action="store_true",
        help="Use local X-TEST-* auth headers when test auth is enabled.",
    )
    parser.add_argument(
        "--test-user-id",
        default="11111111-1111-1111-1111-111111111111",
        help="User ID for --use-test-auth.",
    )
    parser.add_argument(
        "--test-user-email",
        default="researcher@example.com",
        help="User email for --use-test-auth.",
    )
    parser.add_argument(
        "--test-user-role",
        default="researcher",
        help="User role for --use-test-auth.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    loaded_env_keys = _load_environment_overrides()
    args = parse_args(argv)
    if bool(args.list_scenarios):
        print(render_available_scenarios_markdown())
        return 0
    config = _config_from_args(args)
    with httpx.Client(
        base_url=config.base_url,
        timeout=_DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        report = run_live_evidence_smoke_suite(config=config, client=client)
    report["loaded_env_keys"] = loaded_env_keys
    manifest = write_live_evidence_smoke_suite_report(
        report=report,
        output_dir=config.output_dir,
    )
    print(render_live_evidence_smoke_suite_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")
    return 0 if report.get("all_passed") is True else 1


def run_live_evidence_smoke_suite(
    *,
    config: LiveEvidenceSmokeSuiteConfig,
    client: httpx.Client,
) -> JSONObject:
    """Run all requested smoke scenarios and return a suite report."""

    scenario_reports = [
        _run_smoke_scenario(config=config, scenario=scenario, client=client)
        for scenario in config.scenarios
    ]
    return build_live_evidence_smoke_suite_report(
        config=config,
        scenario_reports=scenario_reports,
    )


def build_live_evidence_smoke_suite_report(
    *,
    config: LiveEvidenceSmokeSuiteConfig,
    scenario_reports: Sequence[JSONObject],
) -> JSONObject:
    """Aggregate scenario reports into one suite-level summary."""

    reports = [dict(report) for report in scenario_reports]
    completed_scenarios = sum(
        1 for report in reports if _maybe_string(report.get("status")) == "completed"
    )
    failed_scenarios = len(reports) - completed_scenarios
    graph_claim_deltas = sum(
        _audit_int_value(report.get("audit_report"), "graph_claim_deltas")
        for report in reports
    )
    graph_evidence_rows = sum(
        _audit_int_value(report.get("audit_report"), "graph_evidence_rows")
        for report in reports
    )
    suspicious_log_lines = sum(
        _audit_int_value(report.get("audit_report"), "suspicious_log_lines")
        for report in reports
    )
    all_errors = [
        error
        for report in reports
        for error in _string_list(report.get("errors"))
    ]
    return {
        "report_name": "live_evidence_smoke_suite",
        "generated_at": datetime.now(UTC).isoformat(),
        "label": config.label,
        "base_url": config.base_url,
        "requested_scenario_count": len(config.scenarios),
        "completed_scenarios": completed_scenarios,
        "failed_scenarios": failed_scenarios,
        "graph_claim_deltas": graph_claim_deltas,
        "graph_evidence_rows": graph_evidence_rows,
        "suspicious_log_lines": suspicious_log_lines,
        "all_passed": failed_scenarios == 0,
        "errors": all_errors,
        "scenario_keys": [scenario.key for scenario in config.scenarios],
        "scenarios": reports,
    }


def write_live_evidence_smoke_suite_report(
    *,
    report: JSONObject,
    output_dir: Path,
) -> dict[str, str]:
    """Write the suite summary and per-scenario JSON reports."""

    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir = output_dir / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)

    for scenario in _list_of_dicts(report.get("scenarios")):
        scenario_key = _maybe_string(scenario.get("scenario_key")) or "scenario"
        scenario_path = scenarios_dir / f"{_safe_filename(scenario_key)}.json"
        scenario_path.write_text(
            json.dumps(scenario, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    summary_json_path = output_dir / "summary.json"
    summary_md_path = output_dir / "summary.md"
    summary_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text(
        render_live_evidence_smoke_suite_markdown(report),
        encoding="utf-8",
    )
    return {
        "summary_json": str(summary_json_path),
        "summary_markdown": str(summary_md_path),
    }


def render_live_evidence_smoke_suite_markdown(report: JSONObject) -> str:
    """Render the suite summary as markdown."""

    lines = [
        "# Live Evidence Smoke Suite",
        "",
        f"- All passed: {'yes' if report.get('all_passed') is True else 'no'}",
        f"- Requested scenarios: {_int_value(report.get('requested_scenario_count'))}",
        f"- Completed scenarios: {_int_value(report.get('completed_scenarios'))}",
        f"- Failed scenarios: {_int_value(report.get('failed_scenarios'))}",
        f"- Graph claim delta: {_int_value(report.get('graph_claim_deltas'))}",
        f"- Graph evidence rows: {_int_value(report.get('graph_evidence_rows'))}",
        f"- Suspicious log lines: {_int_value(report.get('suspicious_log_lines'))}",
        "",
        "## Scenarios",
        "",
    ]
    for scenario in _list_of_dicts(report.get("scenarios")):
        audit_report = _dict_value(scenario.get("audit_report"))
        lines.extend(
            [
                f"### {_maybe_string(scenario.get('scenario_name')) or 'scenario'}",
                f"- Key: {_maybe_string(scenario.get('scenario_key')) or 'unknown'}",
                f"- Status: {_maybe_string(scenario.get('status')) or 'unknown'}",
                f"- Space: {_maybe_string(scenario.get('space_id')) or 'unknown'}",
                f"- Claim delta: {_int_value(audit_report.get('graph_claim_deltas'))}",
                f"- Evidence rows: {_int_value(audit_report.get('graph_evidence_rows'))}",
            ]
        )
        scenario_errors = _string_list(scenario.get("errors"))
        if scenario_errors:
            lines.append("- Errors:")
            for error in scenario_errors:
                lines.append(f"  - {error}")
        manifest = _dict_value(scenario.get("audit_manifest"))
        summary_markdown = _maybe_string(manifest.get("summary_markdown"))
        if summary_markdown is not None:
            lines.append(f"- Audit markdown: `{summary_markdown}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_available_scenarios_markdown() -> str:
    """Render the built-in scenario catalog."""

    lines = ["# Live Evidence Smoke Scenarios", ""]
    for scenario in _DEFAULT_SCENARIOS:
        lines.extend(
            [
                f"## {scenario.name}",
                "",
                f"- Key: `{scenario.key}`",
                f"- Description: {scenario.description}",
                f"- Objective: {scenario.objective}",
                f"- Seed terms: {', '.join(scenario.seed_terms)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _run_smoke_scenario(
    *,
    config: LiveEvidenceSmokeSuiteConfig,
    scenario: LiveEvidenceSmokeScenario,
    client: httpx.Client,
) -> JSONObject:
    """Create a fresh space for one scenario, run the audit, and capture the result."""

    started_at = time.perf_counter()
    errors: list[str] = []
    created_space: JSONObject | None = None
    audit_report: JSONObject | None = None
    audit_manifest: dict[str, str] | None = None
    space_id: str | None = None
    scenario_output_dir = config.output_dir / "scenario_reports" / scenario.key
    scenario_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        created_space = _create_research_space(
            client=client,
            auth_headers=config.auth_headers,
            scenario=scenario,
            space_name_prefix=config.space_name_prefix,
            space_description_prefix=config.space_description_prefix,
        )
        space_id = _required_string(created_space, "id", "created space")
        audit_config = _scenario_audit_config(
            suite_config=config,
            scenario=scenario,
            space_id=space_id,
            output_dir=scenario_output_dir,
        )
        audit_report = run_live_evidence_session_audit(
            config=audit_config,
            client=client,
        )
        audit_manifest = write_live_evidence_session_audit_report(
            report=audit_report,
            output_dir=scenario_output_dir,
        )
        errors.extend(_string_list(audit_report.get("errors")))
        if audit_report.get("all_passed") is not True:
            errors.append(
                f"Scenario '{scenario.key}' live audit did not pass cleanly.",
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))

    status = "completed" if not errors else "failed"
    return {
        "scenario_key": scenario.key,
        "scenario_name": scenario.name,
        "description": scenario.description,
        "status": status,
        "runtime_seconds": _round_float(time.perf_counter() - started_at),
        "space_id": space_id,
        "space": created_space,
        "audit_report": audit_report,
        "audit_manifest": audit_manifest or {},
        "errors": errors,
    }


def _create_research_space(
    *,
    client: httpx.Client,
    auth_headers: dict[str, str],
    scenario: LiveEvidenceSmokeScenario,
    space_name_prefix: str,
    space_description_prefix: str,
) -> JSONObject:
    """Create one fresh space for a smoke scenario."""

    payload = {
        "name": f"{space_name_prefix} - {scenario.name}",
        "description": f"{space_description_prefix}: {scenario.description}",
        "sources": dict(scenario.space_sources or _DEFAULT_SPACE_SOURCES),
    }
    _, response_payload = _request_json_with_status(
        client=client,
        method="POST",
        path="/v2/spaces",
        headers=auth_headers,
        json_body=payload,
        acceptable_statuses=(_HTTP_CREATED,),
        timeout_seconds=_SPACE_CREATE_TIMEOUT_SECONDS,
    )
    return response_payload


def _scenario_audit_config(
    *,
    suite_config: LiveEvidenceSmokeSuiteConfig,
    scenario: LiveEvidenceSmokeScenario,
    space_id: str,
    output_dir: Path,
) -> LiveEvidenceSessionAuditConfig:
    """Build the child session-audit config for one scenario."""

    return LiveEvidenceSessionAuditConfig(
        base_url=suite_config.base_url,
        auth_headers=dict(suite_config.auth_headers),
        output_dir=output_dir,
        label=f"{suite_config.label}-{scenario.key}",
        space_ids=(space_id,),
        objective=scenario.objective,
        seed_terms=scenario.seed_terms,
        research_init_title=scenario.research_init_title,
        research_init_max_depth=2,
        research_init_max_hypotheses=20,
        sources=dict(scenario.research_sources) if scenario.research_sources is not None else None,
        bootstrap_objective=scenario.bootstrap_objective,
        bootstrap_title=scenario.bootstrap_title,
        bootstrap_seed_entity_ids=(),
        bootstrap_source_type=scenario.bootstrap_source_type,
        bootstrap_max_depth=2,
        bootstrap_max_hypotheses=20,
        repeat_count=suite_config.repeat_count,
        promote_first_proposal=suite_config.promote_first_proposal,
        promotion_reason=suite_config.promotion_reason,
        require_graph_activity=suite_config.require_graph_activity,
        poll_timeout_seconds=suite_config.poll_timeout_seconds,
        poll_interval_seconds=suite_config.poll_interval_seconds,
        graph_settle_seconds=suite_config.graph_settle_seconds,
        log_commands=suite_config.log_commands,
        log_error_patterns=suite_config.log_error_patterns,
        log_ignore_patterns=suite_config.log_ignore_patterns,
        fail_on_log_match=suite_config.fail_on_log_match,
    )


def _config_from_args(args: argparse.Namespace) -> LiveEvidenceSmokeSuiteConfig:
    output_dir = (
        _resolve_path(args.output_dir)
        if args.output_dir is not None
        else (
            _REPO_ROOT
            / "reports"
            / _DEFAULT_OUTPUT_SUBDIR
            / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        )
    )
    return LiveEvidenceSmokeSuiteConfig(
        base_url=_maybe_string(args.base_url) or _DEFAULT_BASE_URL,
        auth_headers=_resolve_auth_headers(args),
        output_dir=output_dir,
        label=_maybe_string(args.label) or _DEFAULT_LABEL,
        scenarios=_resolve_requested_scenarios(
            explicit_scenarios=list(args.scenario),
            csv_scenarios=str(args.scenarios),
        ),
        repeat_count=_normalize_positive_int(args.repeat_count, name="repeat_count"),
        poll_timeout_seconds=_normalize_positive_float(
            args.poll_timeout_seconds,
            name="poll_timeout_seconds",
        ),
        poll_interval_seconds=_normalize_positive_float(
            args.poll_interval_seconds,
            name="poll_interval_seconds",
        ),
        graph_settle_seconds=_normalize_positive_float(
            args.graph_settle_seconds,
            name="graph_settle_seconds",
        ),
        promote_first_proposal=bool(args.promote_first_proposal),
        promotion_reason=_maybe_string(args.promotion_reason) or _DEFAULT_PROMOTION_REASON,
        require_graph_activity=bool(args.require_graph_activity),
        log_commands=_normalize_log_commands(list(args.log_command)),
        log_error_patterns=tuple(args.log_error_pattern or ()),
        log_ignore_patterns=tuple(args.log_ignore_pattern or ()),
        fail_on_log_match=bool(args.fail_on_log_match),
        space_name_prefix=(
            _maybe_string(args.space_name_prefix) or _DEFAULT_SPACE_NAME_PREFIX
        ),
        space_description_prefix=(
            _maybe_string(args.space_description_prefix)
            or _DEFAULT_SPACE_DESCRIPTION_PREFIX
        ),
    )


def _resolve_requested_scenarios(
    *,
    explicit_scenarios: list[str],
    csv_scenarios: str,
) -> tuple[LiveEvidenceSmokeScenario, ...]:
    requested_keys: list[str] = []
    for raw_value in explicit_scenarios:
        normalized = raw_value.strip()
        if normalized and normalized not in requested_keys:
            requested_keys.append(normalized)
    for raw_value in csv_scenarios.split(","):
        normalized = raw_value.strip()
        if normalized and normalized not in requested_keys:
            requested_keys.append(normalized)
    if not requested_keys:
        return _DEFAULT_SCENARIOS

    scenario_by_key = {scenario.key: scenario for scenario in _DEFAULT_SCENARIOS}
    unknown = [key for key in requested_keys if key not in scenario_by_key]
    if unknown:
        available = ", ".join(sorted(scenario_by_key))
        raise SystemExit(
            f"Unknown smoke scenario(s): {', '.join(unknown)}. Available: {available}.",
        )
    return tuple(scenario_by_key[key] for key in requested_keys)


def _required_string(payload: JSONObject, key: str, label: str) -> str:
    value = _maybe_string(payload.get(key))
    if value is None:
        raise RuntimeError(f"{label} is missing required field '{key}'")
    return value


def _audit_int_value(report: object, key: str) -> int:
    return _int_value(_dict_value(report).get(key))


def _int_value(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
