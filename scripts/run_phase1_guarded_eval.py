#!/usr/bin/env python3
"""Run the manual guarded-evaluation workflow for Phase 1 compare fixtures."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Literal

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
    run_phase1_comparison_sync,
)
from artana_evidence_api.phase2_shadow_fixture_refresh import (
    Phase2ShadowFixtureSet,
    Phase2ShadowFixtureSpec,
    fixture_request_from_spec,
    phase2_shadow_fixture_specs_for_set,
)
from artana_evidence_api.runtime_support import (
    ModelCapability,
    get_model_registry,
    has_configured_openai_api_key,
    normalize_litellm_model_id,
)

from scripts.phase1_guarded_eval_common import _round_runtime_seconds
from scripts.phase1_guarded_eval_render import (
    _render_filtered_chase_summary,
    _selected_action_display,
    render_phase1_guarded_evaluation_markdown,
    write_phase1_guarded_evaluation_report,
)
from scripts.phase1_guarded_eval_report import (
    _build_guarded_graduation_gate,
    _build_guarded_report,
)
from scripts.phase1_guarded_eval_review import (
    _build_fixture_guarded_graduation_review,
    _build_fixture_review_summary,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

__all__ = [
    "_build_fixture_failure_compare_payload",
    "_build_fixture_guarded_graduation_review",
    "_build_fixture_review_summary",
    "_build_guarded_graduation_gate",
    "_build_guarded_report",
    "_render_filtered_chase_summary",
    "_selected_action_display",
    "render_phase1_guarded_evaluation_markdown",
]

Phase1GuardedCompareMode = Literal["shared_baseline_replay", "dual_live_guarded"]
Phase1GuardedReportMode = Literal["standard", "canary"]

_LOCAL_DEV_ENV_DEFAULTS: dict[str, str] = {
    "AUTH_JWT_SECRET": "artana-platform-backend-jwt-secret-for-development-2026-01",
    "GRAPH_JWT_SECRET": "artana-platform-backend-jwt-secret-for-development-2026-01",
    "GRAPH_JWT_ISSUER": "artana-platform",
    "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY": (
        "artana-evidence-api-bootstrap-key-for-development-2026-03"
    ),
}
_PUBMED_BACKEND_ENV = "ARTANA_PUBMED_SEARCH_BACKEND"
_GUARDED_CHASE_ROLLOUT_ENV = "ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT"
_GUARDED_ROLLOUT_PROFILE_ENV = "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE"
_GUARDED_ROLLOUT_PROFILES = frozenset(
    {
        "guarded_dry_run",
        "guarded_chase_only",
        "guarded_source_chase",
        "guarded_low_risk",
    },
)
_GUARDED_SOURCE_CHASE_PROFILE = "guarded_source_chase"
_GUARDED_SOURCE_STRATEGY = "prioritized_structured_sequence"
_GUARDED_CHASE_STRATEGY = "chase_selection"
_GUARDED_TERMINAL_STRATEGY = "terminal_control_flow"
_LIVE_EVIDENCE_SOURCE_KEYS = frozenset(
    {
        "pubmed",
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
        "mgi",
        "zfin",
        "marrvel",
    },
)
_CONTEXT_ONLY_SOURCE_KEYS = frozenset({"pdf", "text"})
_GROUNDING_SOURCE_KEYS = frozenset({"mondo"})
_RESERVED_SOURCE_KEYS = frozenset({"uniprot", "hgnc"})
_ACTION_DEFAULT_SOURCE_KEYS: dict[str, str] = {
    "QUERY_PUBMED": "pubmed",
    "INGEST_AND_EXTRACT_PUBMED": "pubmed",
    "REVIEW_PDF_WORKSET": "pdf",
    "REVIEW_TEXT_WORKSET": "text",
    "LOAD_MONDO_GROUNDING": "mondo",
    "RUN_UNIPROT_GROUNDING": "uniprot",
    "RUN_HGNC_GROUNDING": "hgnc",
}
_ROLLBACK_REQUIRED_CANARY_GATES = frozenset(
    {
        "no_fixture_failures",
        "no_timeouts",
        "proof_receipts_present_and_verified",
        "no_invalid_outputs",
        "no_fallback_outputs",
        "no_budget_violations",
        "no_disabled_source_violations",
        "no_reserved_source_violations",
        "no_context_only_source_violations",
        "no_grounding_source_violations",
        "qualitative_rationale_present_everywhere",
    },
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the manual guarded-evaluation workflow for the objective "
            "compare fixtures and, when requested, the supplemental chase "
            "coverage fixtures."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for generated reports. Defaults to "
            "reports/full_ai_orchestrator_guarded/<timestamp>/ in standard mode "
            "or reports/full_ai_orchestrator_guarded_canary/<timestamp>/ in "
            "canary mode."
        ),
    )
    parser.add_argument(
        "--report-mode",
        choices=("standard", "canary"),
        default="standard",
        help=(
            "Choose the report posture. `standard` preserves the existing guarded "
            "graduation summary; `canary` adds operator-facing canary verdicts, "
            "runtime aggregates, and rollout review gates."
        ),
    )
    parser.add_argument(
        "--canary-label",
        type=str,
        default="",
        help=(
            "Optional human-readable label for one canary report, for example "
            "`low_risk_space_a`."
        ),
    )
    parser.add_argument(
        "--expected-run-count",
        type=int,
        default=None,
        help=(
            "Optional expected run count for canary reports. Canary mode fails "
            "loudly when actual run coverage is lower than this value."
        ),
    )
    parser.add_argument(
        "--fixtures",
        type=str,
        default="",
        help=(
            "Optional comma-separated fixture names to evaluate "
            "(for example: BRCA1,PCSK9)."
        ),
    )
    parser.add_argument(
        "--fixture-set",
        choices=("objective", "supplemental", "all"),
        default="objective",
        help=(
            "Choose which fixture family to evaluate. "
            "`objective` uses the four main compare fixtures, "
            "`supplemental` uses the chase-focused scenarios, and "
            "`all` runs both."
        ),
    )
    parser.add_argument(
        "--pubmed-backend",
        choices=("current", "deterministic", "ncbi"),
        default="deterministic",
        help=(
            "Override ARTANA_PUBMED_SEARCH_BACKEND for the guarded compare run. "
            "Defaults to deterministic."
        ),
    )
    parser.add_argument(
        "--compare-mode",
        choices=("shared_baseline_replay", "dual_live_guarded"),
        default="dual_live_guarded",
        help=(
            "Choose whether guarded evaluation replays the shared baseline or "
            "runs a true dual-live comparison. Defaults to dual_live_guarded."
        ),
    )
    parser.add_argument(
        "--fixture-timeout-seconds",
        type=float,
        default=300.0,
        help=(
            "Per-fixture timeout for the in-process compare run. "
            "Defaults to 300 seconds."
        ),
    )
    parser.add_argument(
        "--guarded-rollout-profile",
        choices=tuple(sorted(_GUARDED_ROLLOUT_PROFILES)),
        default="guarded_low_risk",
        help=(
            "Guarded authority profile to use for live guarded evaluation. "
            "Defaults to guarded_low_risk for backwards-compatible proof runs."
        ),
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=1,
        help=(
            "Repeat each selected fixture this many times. Defaults to 1. "
            "Use 2 for source+chase graduation proof runs."
        ),
    )
    parser.add_argument(
        "--require-graduation-gate",
        action="store_true",
        help=(
            "Exit non-zero unless the proof-based guarded graduation gate also "
            "passes. This is intended for pre-widening review runs, not routine "
            "diagnostic guarded evaluation."
        ),
    )
    parser.add_argument(
        "--continue-on-fixture-error",
        action="store_true",
        help=(
            "Keep evaluating remaining fixtures after a fixture timeout or "
            "runtime error, then write a failed aggregate report with the "
            "fixture errors included."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    """CLI entry point."""

    args = parse_args(argv)
    compare_mode = _normalize_compare_mode(args.compare_mode)
    report_mode = _normalize_report_mode(args.report_mode)
    guarded_rollout_profile = _normalize_guarded_rollout_profile(
        args.guarded_rollout_profile,
    )
    repeat_count = _normalize_repeat_count(args.repeat_count)
    expected_run_count = _normalize_expected_run_count(args.expected_run_count)
    canary_label = _normalize_canary_label(
        args.canary_label,
        report_mode=report_mode,
        guarded_rollout_profile=guarded_rollout_profile,
    )
    output_dir = (
        _resolve_path(args.output_dir)
        if args.output_dir is not None
        else _default_output_dir(report_mode=report_mode)
    )
    fixture_specs = _repeat_fixture_specs(
        _select_fixture_specs(args.fixtures, args.fixture_set),
        repeat_count=repeat_count,
    )
    preflight = _phase1_guarded_preflight()
    if preflight["status"] != "ready":
        model_id = preflight["model_id"]
        model_text = f" ({model_id})" if model_id is not None else ""
        raise SystemExit(
            "Phase 1 guarded evaluation requires live planner access before running. "
            f"Planner capability `{preflight['capability']}`{model_text}: "
            f"{preflight['detail']}",
        )

    _apply_local_dev_env_defaults()
    previous_pubmed_backend = os.getenv(_PUBMED_BACKEND_ENV)
    previous_guarded_rollout_profile = os.getenv(_GUARDED_ROLLOUT_PROFILE_ENV)
    os.environ[_PUBMED_BACKEND_ENV] = args.pubmed_backend
    os.environ[_GUARDED_ROLLOUT_PROFILE_ENV] = guarded_rollout_profile
    try:
        compare_payloads: list[JSONObject] = []
        for spec in fixture_specs:
            print(
                f"Running guarded compare for {spec.fixture_name}...",
                file=sys.stderr,
            )
            started_at = perf_counter()
            request = _guarded_request_from_spec(
                spec,
                compare_mode=compare_mode,
                compare_timeout_seconds=args.fixture_timeout_seconds,
            )
            try:
                compare_payload = run_phase1_comparison_sync(request)
            except GraphServiceClientError as exc:
                elapsed_seconds = perf_counter() - started_at
                if args.continue_on_fixture_error:
                    compare_payloads.append(
                        _build_fixture_failure_compare_payload(
                            spec=spec,
                            exc=exc,
                            compare_mode=compare_mode,
                            guarded_rollout_profile=guarded_rollout_profile,
                            runtime_seconds=elapsed_seconds,
                        ),
                    )
                    continue
                raise SystemExit(_format_guarded_graph_error(spec, exc)) from exc
            except TimeoutError as exc:
                elapsed_seconds = perf_counter() - started_at
                if args.continue_on_fixture_error:
                    compare_payloads.append(
                        _build_fixture_failure_compare_payload(
                            spec=spec,
                            exc=exc,
                            compare_mode=compare_mode,
                            guarded_rollout_profile=guarded_rollout_profile,
                            runtime_seconds=elapsed_seconds,
                        ),
                    )
                    continue
                raise SystemExit(
                    f"Guarded compare timed out for {spec.fixture_name}: {exc}",
                ) from exc
            except Exception as exc:  # noqa: BLE001
                elapsed_seconds = perf_counter() - started_at
                if args.continue_on_fixture_error:
                    compare_payloads.append(
                        _build_fixture_failure_compare_payload(
                            spec=spec,
                            exc=exc,
                            compare_mode=compare_mode,
                            guarded_rollout_profile=guarded_rollout_profile,
                            runtime_seconds=elapsed_seconds,
                        ),
                    )
                    continue
                raise
            compare_payloads.append(
                _compare_payload_with_runtime(
                    compare_payload=compare_payload,
                    runtime_seconds=perf_counter() - started_at,
                ),
            )

        report = _build_guarded_report(
            compare_payloads=compare_payloads,
            fixture_specs=fixture_specs,
            fixture_set=args.fixture_set,
            pubmed_backend=args.pubmed_backend,
            compare_mode=compare_mode,
            report_mode=report_mode,
            guarded_rollout_profile=guarded_rollout_profile,
            repeat_count=repeat_count,
            canary_label=canary_label,
            expected_run_count=expected_run_count,
            preflight=preflight,
        )
        manifest = write_phase1_guarded_evaluation_report(report, output_dir=output_dir)
    finally:
        if previous_pubmed_backend is None:
            os.environ.pop(_PUBMED_BACKEND_ENV, None)
        else:
            os.environ[_PUBMED_BACKEND_ENV] = previous_pubmed_backend
        if previous_guarded_rollout_profile is None:
            os.environ.pop(_GUARDED_ROLLOUT_PROFILE_ENV, None)
        else:
            os.environ[_GUARDED_ROLLOUT_PROFILE_ENV] = previous_guarded_rollout_profile

    print(render_phase1_guarded_evaluation_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")

    automated_gates = report.get("automated_gates")
    if not isinstance(automated_gates, dict):
        raise SystemExit("Phase 1 guarded evaluation did not produce automated gates.")
    automated_gates_passed = bool(automated_gates.get("all_passed"))
    graduation_gate = report.get("guarded_graduation_gate")
    graduation_gate_passed = isinstance(graduation_gate, dict) and bool(
        graduation_gate.get("all_passed")
    )
    canary_gate = report.get("canary_gate")
    canary_gate_passed = isinstance(canary_gate, dict) and bool(
        canary_gate.get("all_passed")
    )
    if report_mode == "canary":
        if automated_gates_passed and graduation_gate_passed and canary_gate_passed:
            return 0
        if automated_gates_passed and graduation_gate_passed and not canary_gate_passed:
            raise SystemExit(
                "Phase 1 guarded canary evaluation passed baseline guarded gates "
                f"but failed the canary gate. See {manifest['summary_json']}.",
            )
    if automated_gates_passed and (
        not args.require_graduation_gate or graduation_gate_passed
    ):
        return 0
    if automated_gates_passed and args.require_graduation_gate:
        raise SystemExit(
            "Phase 1 guarded evaluation passed routine gates but failed the "
            f"guarded graduation gate. See {manifest['summary_json']}.",
        )
    raise SystemExit(
        "Phase 1 guarded evaluation failed automated gates. "
        f"See {manifest['summary_json']}.",
    )


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else _REPO_ROOT / path


def _normalize_compare_mode(value: str) -> Phase1GuardedCompareMode:
    if value == "shared_baseline_replay":
        return "shared_baseline_replay"
    return "dual_live_guarded"


def _normalize_report_mode(value: str) -> Phase1GuardedReportMode:
    if value == "canary":
        return "canary"
    return "standard"


def _normalize_guarded_rollout_profile(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _GUARDED_ROLLOUT_PROFILES:
        msg = f"Unsupported guarded rollout profile: {value}"
        raise SystemExit(msg)
    return normalized


def _normalize_repeat_count(value: int) -> int:
    if value < 1:
        raise SystemExit("--repeat-count must be at least 1.")
    return value


def _normalize_expected_run_count(value: int | None) -> int | None:
    if value is None:
        return None
    if value < 1:
        raise SystemExit("--expected-run-count must be at least 1.")
    return value


def _normalize_canary_label(
    value: str,
    *,
    report_mode: Phase1GuardedReportMode,
    guarded_rollout_profile: str,
) -> str | None:
    normalized = value.strip()
    if normalized != "":
        return normalized
    if report_mode == "canary":
        return f"{guarded_rollout_profile}_canary"
    return None


def _default_output_dir(*, report_mode: Phase1GuardedReportMode) -> Path:
    report_root = (
        "full_ai_orchestrator_guarded_canary"
        if report_mode == "canary"
        else "full_ai_orchestrator_guarded"
    )
    return (
        _REPO_ROOT
        / "reports"
        / report_root
        / datetime.now(UTC).strftime(
            "%Y%m%d_%H%M%S",
        )
    )


def _guarded_chase_rollout_enabled() -> bool:
    return os.getenv(_GUARDED_CHASE_ROLLOUT_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _select_fixture_specs(
    fixtures_arg: str,
    fixture_set: Phase2ShadowFixtureSet,
) -> tuple[Phase2ShadowFixtureSpec, ...]:
    selected_names = {
        item.strip().casefold()
        for item in fixtures_arg.split(",")
        if item.strip() != ""
    }
    specs = tuple(
        spec
        for spec in phase2_shadow_fixture_specs_for_set(fixture_set)
        if not selected_names or spec.fixture_name.casefold() in selected_names
    )
    if not specs:
        raise SystemExit("No guarded-evaluation fixtures matched the requested names.")
    return specs


def _repeat_fixture_specs(
    specs: tuple[Phase2ShadowFixtureSpec, ...],
    *,
    repeat_count: int,
) -> tuple[Phase2ShadowFixtureSpec, ...]:
    if repeat_count == 1:
        return specs
    repeated: list[Phase2ShadowFixtureSpec] = []
    for repeat_index in range(1, repeat_count + 1):
        for spec in specs:
            repeated.append(
                replace(
                    spec,
                    fixture_name=f"{spec.fixture_name}__repeat_{repeat_index}",
                    runs=tuple(
                        replace(run, run_id=f"{run.run_id}-repeat-{repeat_index}")
                        for run in spec.runs
                    ),
                ),
            )
    return tuple(repeated)


def _guarded_request_from_spec(
    spec: Phase2ShadowFixtureSpec,
    *,
    compare_mode: Phase1GuardedCompareMode = "dual_live_guarded",
    compare_timeout_seconds: float | None = None,
) -> Phase1CompareRequest:
    base_request = fixture_request_from_spec(spec)
    return Phase1CompareRequest(
        objective=base_request.objective,
        seed_terms=base_request.seed_terms,
        title=base_request.title,
        sources=base_request.sources,
        max_depth=base_request.max_depth,
        max_hypotheses=base_request.max_hypotheses,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        compare_mode=compare_mode,
        compare_timeout_seconds=compare_timeout_seconds,
    )


def _apply_local_dev_env_defaults() -> None:
    for key, value in _LOCAL_DEV_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def _format_guarded_graph_error(
    spec: Phase2ShadowFixtureSpec,
    exc: GraphServiceClientError,
) -> str:
    detail = exc.detail or str(exc)
    if "Signature verification failed" in detail:
        return (
            "Phase 1 guarded evaluation could not sync the temporary research "
            f"space for fixture `{spec.fixture_name}` because the backend and "
            "graph service JWT secrets are out of sync "
            "(signature verification failed). Restart both services with the "
            "same AUTH_JWT_SECRET and GRAPH_JWT_SECRET, then rerun the "
            "guarded evaluation."
        )
    return (
        "Phase 1 guarded evaluation failed while syncing the temporary "
        f"research space for fixture `{spec.fixture_name}`: {exc}"
    )


def _fixture_request_payload(
    *,
    spec: Phase2ShadowFixtureSpec,
    compare_mode: Phase1GuardedCompareMode,
    guarded_rollout_profile: str,
) -> JSONObject:
    base_request = fixture_request_from_spec(spec)
    return {
        "objective": spec.objective,
        "seed_terms": list(spec.seed_terms),
        "title": spec.title,
        "sources": dict(base_request.sources),
        "max_depth": spec.max_depth,
        "max_hypotheses": spec.max_hypotheses,
        "planner_mode": FullAIOrchestratorPlannerMode.GUARDED.value,
        "compare_mode": compare_mode,
        "guarded_rollout_profile": guarded_rollout_profile,
    }


def _build_fixture_failure_compare_payload(
    *,
    spec: Phase2ShadowFixtureSpec,
    exc: BaseException,
    compare_mode: Phase1GuardedCompareMode,
    guarded_rollout_profile: str,
    runtime_seconds: float | None = None,
) -> JSONObject:
    error_message = (
        _format_guarded_graph_error(spec, exc)
        if isinstance(
            exc,
            GraphServiceClientError,
        )
        else str(exc)
    )
    return {
        "request": _fixture_request_payload(
            spec=spec,
            compare_mode=compare_mode,
            guarded_rollout_profile=guarded_rollout_profile,
        ),
        "baseline": {"workspace": {"present": False}},
        "orchestrator": {"workspace": {"present": False}},
        "mismatches": [],
        "advisories": [f"Fixture failed before comparison completed: {error_message}"],
        "guarded_evaluation": {
            "status": "fixture_failed",
            "applied_count": 0,
            "candidate_count": 0,
            "identified_count": 0,
            "verified_count": 0,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "applied_actions": [],
            "candidate_actions": [],
        },
        "fixture_error": {
            "fixture_name": spec.fixture_name,
            "error_type": type(exc).__name__,
            "error_message": error_message,
        },
        "fixture_runtime_seconds": _round_runtime_seconds(runtime_seconds),
    }


def _compare_payload_with_runtime(
    *,
    compare_payload: JSONObject,
    runtime_seconds: float,
) -> JSONObject:
    payload = dict(compare_payload)
    payload["fixture_runtime_seconds"] = _round_runtime_seconds(runtime_seconds)
    return payload


def _phase1_guarded_preflight() -> dict[str, str | None]:
    capability = ModelCapability.QUERY_GENERATION
    try:
        model_spec = get_model_registry().get_default_model(capability)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unknown",
            "capability": capability.value,
            "model_id": None,
            "detail": str(exc),
        }

    model_id = normalize_litellm_model_id(model_spec.model_id)
    if not has_configured_openai_api_key():
        return {
            "status": "unavailable",
            "capability": capability.value,
            "model_id": model_id,
            "detail": "OPENAI_API_KEY is not configured.",
        }
    return {
        "status": "ready",
        "capability": capability.value,
        "model_id": model_id,
        "detail": "Planner model configuration is present.",
    }




if __name__ == "__main__":
    raise SystemExit(main())
