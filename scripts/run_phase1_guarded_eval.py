#!/usr/bin/env python3
"""Run the manual guarded-evaluation workflow for Phase 1 compare fixtures."""

from __future__ import annotations

import argparse
import json
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

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

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


def _extract_guarded_decision_proofs(compare_payload: JSONObject) -> JSONObject:
    orchestrator = _dict_value(compare_payload.get("orchestrator"))
    workspace = _dict_value(orchestrator.get("workspace"))
    return _dict_value(workspace.get("guarded_decision_proofs"))


def _extract_guarded_readiness(compare_payload: JSONObject) -> JSONObject:
    orchestrator = _dict_value(compare_payload.get("orchestrator"))
    workspace = _dict_value(orchestrator.get("workspace"))
    return _dict_value(workspace.get("guarded_readiness"))


def _proof_display_id(proof: JSONObject) -> str:
    proof_id = _maybe_string(proof.get("proof_id"))
    if proof_id is not None:
        return proof_id
    checkpoint_key = _maybe_string(proof.get("checkpoint_key"))
    if checkpoint_key is not None:
        return checkpoint_key
    return "unknown-proof"


def _proof_display_ids(proofs: list[JSONObject]) -> list[str]:
    return [_proof_display_id(proof) for proof in proofs]


def _build_fixture_guarded_graduation_review(  # noqa: PLR0912, PLR0915
    *,
    fixture_name: str,
    proof_summary: JSONObject,
    readiness_summary: JSONObject | None = None,
) -> JSONObject:
    proofs = _list_of_dicts(proof_summary.get("proofs"))
    proof_count = _int_value(proof_summary.get("proof_count"))
    if proof_count == 0 and proofs:
        proof_count = len(proofs)
    allowed_proofs = [
        proof for proof in proofs if proof.get("decision_outcome") == "allowed"
    ]
    blocked_proofs = [
        proof for proof in proofs if proof.get("decision_outcome") == "blocked"
    ]
    ignored_proofs = [
        proof for proof in proofs if proof.get("decision_outcome") == "ignored"
    ]
    fallback_proofs = [proof for proof in proofs if proof.get("used_fallback") is True]
    invalid_proofs = [
        proof
        for proof in proofs
        if _maybe_string(proof.get("validation_error")) is not None
        or proof.get("planner_status") in {"failed", "invalid"}
    ]
    budget_violation_proofs = [
        proof for proof in proofs if proof.get("budget_violation") is True
    ]
    disabled_source_violation_proofs = [
        proof for proof in proofs if proof.get("disabled_source_violation") is True
    ]
    reserved_source_violation_proofs = [
        proof
        for proof in proofs
        if _proof_source_policy_violation_category(proof) == "reserved"
    ]
    context_only_source_violation_proofs = [
        proof
        for proof in proofs
        if _proof_source_policy_violation_category(proof) == "context_only"
    ]
    grounding_source_violation_proofs = [
        proof
        for proof in proofs
        if _proof_source_policy_violation_category(proof) == "grounding"
    ]
    missing_rationale_proofs = [
        proof
        for proof in proofs
        if proof.get("qualitative_rationale_present") is not True
    ]
    verification_failed_proofs = [
        proof
        for proof in proofs
        if proof.get("verification_status") == "verification_failed"
    ]
    pending_verification_proofs = [
        proof for proof in proofs if proof.get("verification_status") == "pending"
    ]
    allowed_unverified_proofs = [
        proof
        for proof in allowed_proofs
        if proof.get("verification_status") != "verified"
    ]
    allowed_without_policy_proofs = [
        proof for proof in allowed_proofs if proof.get("policy_allowed") is not True
    ]
    allowed_without_applied_action_proofs = [
        proof
        for proof in allowed_proofs
        if _maybe_string(proof.get("applied_action_type")) is None
    ]
    blocked_without_reason_proofs = [
        proof
        for proof in blocked_proofs
        if _maybe_string(proof.get("outcome_reason")) is None
    ]
    source_selection_intervention_proofs = [
        proof
        for proof in allowed_proofs
        if proof.get("guarded_strategy") == _GUARDED_SOURCE_STRATEGY
    ]
    chase_or_stop_intervention_proofs = [
        proof
        for proof in allowed_proofs
        if proof.get("guarded_strategy") == _GUARDED_CHASE_STRATEGY
        or (
            proof.get("guarded_strategy") == _GUARDED_TERMINAL_STRATEGY
            and proof.get("applied_action_type") == "STOP"
        )
    ]
    proof_summary_present = bool(proof_summary)
    reviewable_proofs_present = proof_count > 0
    gate_passed = all(
        (
            proof_summary_present,
            reviewable_proofs_present,
            len(allowed_proofs) > 0,
            len(blocked_proofs) == 0,
            len(ignored_proofs) == 0,
            len(fallback_proofs) == 0,
            len(invalid_proofs) == 0,
            len(budget_violation_proofs) == 0,
            len(disabled_source_violation_proofs) == 0,
            len(missing_rationale_proofs) == 0,
            len(verification_failed_proofs) == 0,
            len(pending_verification_proofs) == 0,
            len(allowed_unverified_proofs) == 0,
            len(allowed_without_policy_proofs) == 0,
            len(allowed_without_applied_action_proofs) == 0,
            len(blocked_without_reason_proofs) == 0,
        ),
    )
    notes: list[str] = []
    if not proof_summary_present:
        notes.append("missing guarded decision proof summary")
    elif not reviewable_proofs_present:
        notes.append("guarded decision proof summary has no proof receipts")
    if not allowed_proofs:
        notes.append("no allowed guarded action proof")
    if blocked_proofs or ignored_proofs:
        notes.append("planner influence was blocked or ignored")
    if fallback_proofs:
        notes.append("planner fallback was present")
    if invalid_proofs:
        notes.append("invalid planner output was present")
    if budget_violation_proofs:
        notes.append("budget violation was present")
    if disabled_source_violation_proofs:
        notes.append("disabled-source violation was present")
    if missing_rationale_proofs:
        notes.append("qualitative rationale was missing")
    if verification_failed_proofs:
        notes.append("verification failure was present")
    if pending_verification_proofs or allowed_unverified_proofs:
        notes.append("allowed proof was not verified")
    if allowed_without_policy_proofs:
        notes.append("allowed proof missed policy approval")
    if allowed_without_applied_action_proofs:
        notes.append("allowed proof missed applied action")
    if blocked_without_reason_proofs:
        notes.append("blocked proof missed outcome reason")

    return {
        "fixture_name": fixture_name,
        "proof_summary_present": proof_summary_present,
        "reviewable_proofs_present": reviewable_proofs_present,
        "gate_passed": gate_passed,
        "proof_count": proof_count,
        "allowed_count": len(allowed_proofs),
        "blocked_count": len(blocked_proofs),
        "ignored_count": len(ignored_proofs),
        "verified_count": len(
            [
                proof
                for proof in proofs
                if proof.get("verification_status") == "verified"
            ]
        ),
        "verification_failed_count": len(verification_failed_proofs),
        "pending_verification_count": len(pending_verification_proofs),
        "fallback_count": len(fallback_proofs),
        "invalid_output_count": len(invalid_proofs),
        "budget_violation_count": len(budget_violation_proofs),
        "disabled_source_violation_count": len(disabled_source_violation_proofs),
        "reserved_source_violation_count": len(reserved_source_violation_proofs),
        "context_only_source_violation_count": len(
            context_only_source_violation_proofs,
        ),
        "grounding_source_violation_count": len(grounding_source_violation_proofs),
        "missing_rationale_count": len(missing_rationale_proofs),
        "allowed_unverified_count": len(allowed_unverified_proofs),
        "allowed_without_policy_count": len(allowed_without_policy_proofs),
        "allowed_without_applied_action_count": len(
            allowed_without_applied_action_proofs,
        ),
        "blocked_without_reason_count": len(blocked_without_reason_proofs),
        "blocked_or_ignored_count": len(blocked_proofs) + len(ignored_proofs),
        "source_selection_intervention_count": len(
            source_selection_intervention_proofs,
        ),
        "chase_or_stop_intervention_count": len(chase_or_stop_intervention_proofs),
        "proof_ids": _proof_display_ids(proofs),
        "blocked_or_ignored_proof_ids": _proof_display_ids(
            blocked_proofs + ignored_proofs,
        ),
        "fallback_proof_ids": _proof_display_ids(fallback_proofs),
        "invalid_proof_ids": _proof_display_ids(invalid_proofs),
        "budget_violation_proof_ids": _proof_display_ids(budget_violation_proofs),
        "disabled_source_violation_proof_ids": _proof_display_ids(
            disabled_source_violation_proofs,
        ),
        "reserved_source_violation_proof_ids": _proof_display_ids(
            reserved_source_violation_proofs,
        ),
        "context_only_source_violation_proof_ids": _proof_display_ids(
            context_only_source_violation_proofs,
        ),
        "grounding_source_violation_proof_ids": _proof_display_ids(
            grounding_source_violation_proofs,
        ),
        "missing_rationale_proof_ids": _proof_display_ids(
            missing_rationale_proofs,
        ),
        "allowed_unverified_proof_ids": _proof_display_ids(
            allowed_unverified_proofs,
        ),
        "source_selection_intervention_proof_ids": _proof_display_ids(
            source_selection_intervention_proofs,
        ),
        "chase_or_stop_intervention_proof_ids": _proof_display_ids(
            chase_or_stop_intervention_proofs,
        ),
        "readiness_summary_present": readiness_summary is not None
        and bool(readiness_summary),
        "readiness_profile_authority_exercised": (
            readiness_summary.get("profile_authority_exercised")
            if isinstance(readiness_summary, dict)
            else None
        ),
        "readiness_intervention_counts": _readiness_intervention_counts(
            readiness_summary,
        ),
        "notes": notes,
    }


def _readiness_intervention_counts(
    readiness_summary: JSONObject | None,
) -> JSONObject:
    raw = (
        _dict_value(readiness_summary.get("intervention_counts"))
        if isinstance(readiness_summary, dict)
        else {}
    )
    return {
        "source_selection": _int_value(raw.get("source_selection")),
        "chase_or_stop": _int_value(raw.get("chase_or_stop")),
        "brief_generation": _int_value(raw.get("brief_generation")),
    }


def _build_guarded_graduation_gate(
    *,
    fixture_reports: list[JSONObject],
    require_source_chase_interventions: bool = False,
) -> JSONObject:
    fixture_reviews = [
        _dict_value(fixture.get("guarded_graduation_review"))
        for fixture in fixture_reports
    ]
    fixture_count = len(fixture_reviews)
    fixtures_with_proof_summary = sum(
        1 for review in fixture_reviews if review.get("proof_summary_present") is True
    )
    fixtures_with_reviewable_proofs = sum(
        1
        for review in fixture_reviews
        if review.get("reviewable_proofs_present") is True
    )
    proof_count = sum(
        _int_value(review.get("proof_count")) for review in fixture_reviews
    )
    allowed_count = sum(
        _int_value(review.get("allowed_count")) for review in fixture_reviews
    )
    blocked_count = sum(
        _int_value(review.get("blocked_count")) for review in fixture_reviews
    )
    ignored_count = sum(
        _int_value(review.get("ignored_count")) for review in fixture_reviews
    )
    verified_count = sum(
        _int_value(review.get("verified_count")) for review in fixture_reviews
    )
    verification_failed_count = sum(
        _int_value(review.get("verification_failed_count"))
        for review in fixture_reviews
    )
    pending_verification_count = sum(
        _int_value(review.get("pending_verification_count"))
        for review in fixture_reviews
    )
    fallback_count = sum(
        _int_value(review.get("fallback_count")) for review in fixture_reviews
    )
    invalid_output_count = sum(
        _int_value(review.get("invalid_output_count")) for review in fixture_reviews
    )
    budget_violation_count = sum(
        _int_value(review.get("budget_violation_count")) for review in fixture_reviews
    )
    disabled_source_violation_count = sum(
        _int_value(review.get("disabled_source_violation_count"))
        for review in fixture_reviews
    )
    reserved_source_violation_count = sum(
        _int_value(review.get("reserved_source_violation_count"))
        for review in fixture_reviews
    )
    context_only_source_violation_count = sum(
        _int_value(review.get("context_only_source_violation_count"))
        for review in fixture_reviews
    )
    grounding_source_violation_count = sum(
        _int_value(review.get("grounding_source_violation_count"))
        for review in fixture_reviews
    )
    missing_rationale_count = sum(
        _int_value(review.get("missing_rationale_count")) for review in fixture_reviews
    )
    allowed_unverified_count = sum(
        _int_value(review.get("allowed_unverified_count")) for review in fixture_reviews
    )
    allowed_without_policy_count = sum(
        _int_value(review.get("allowed_without_policy_count"))
        for review in fixture_reviews
    )
    allowed_without_applied_action_count = sum(
        _int_value(review.get("allowed_without_applied_action_count"))
        for review in fixture_reviews
    )
    blocked_without_reason_count = sum(
        _int_value(review.get("blocked_without_reason_count"))
        for review in fixture_reviews
    )
    source_selection_intervention_count = sum(
        _int_value(review.get("source_selection_intervention_count"))
        for review in fixture_reviews
    )
    chase_or_stop_intervention_count = sum(
        _int_value(review.get("chase_or_stop_intervention_count"))
        for review in fixture_reviews
    )
    readiness_summaries_present = sum(
        1
        for review in fixture_reviews
        if review.get("readiness_summary_present") is True
    )
    readiness_profile_authority_exercised_count = sum(
        1
        for review in fixture_reviews
        if review.get("readiness_profile_authority_exercised") is True
    )
    fixtures_missing_profile_authority = [
        str(review.get("fixture_name", "unknown"))
        for review in fixture_reviews
        if review.get("readiness_profile_authority_exercised") is not True
    ]
    readiness_source_selection_intervention_count = sum(
        _int_value(
            _dict_value(review.get("readiness_intervention_counts")).get(
                "source_selection",
            ),
        )
        for review in fixture_reviews
    )
    readiness_chase_or_stop_intervention_count = sum(
        _int_value(
            _dict_value(review.get("readiness_intervention_counts")).get(
                "chase_or_stop",
            ),
        )
        for review in fixture_reviews
    )
    readiness_brief_generation_intervention_count = sum(
        _int_value(
            _dict_value(review.get("readiness_intervention_counts")).get(
                "brief_generation",
            ),
        )
        for review in fixture_reviews
    )
    blocked_or_ignored_count = blocked_count + ignored_count
    automated_gates = {
        "proof_summaries_present": (
            fixture_count > 0 and fixtures_with_proof_summary == fixture_count
        ),
        "reviewable_proofs_present": (
            fixture_count > 0 and fixtures_with_reviewable_proofs == fixture_count
        ),
        "at_least_one_allowed_proof": allowed_count > 0,
        "no_blocked_or_ignored_proofs": blocked_or_ignored_count == 0,
        "all_allowed_proofs_verified": allowed_unverified_count == 0,
        "no_verification_failures": verification_failed_count == 0,
        "no_pending_verifications": pending_verification_count == 0,
        "no_fallback_recommendations": fallback_count == 0,
        "no_invalid_outputs": invalid_output_count == 0,
        "no_budget_violations": budget_violation_count == 0,
        "no_disabled_source_violations": disabled_source_violation_count == 0,
        "qualitative_rationale_present_everywhere": missing_rationale_count == 0,
        "all_allowed_proofs_policy_allowed": allowed_without_policy_count == 0,
        "all_allowed_proofs_have_applied_action": (
            allowed_without_applied_action_count == 0
        ),
        "blocked_proofs_have_reasons": blocked_without_reason_count == 0,
    }
    if require_source_chase_interventions:
        automated_gates["at_least_one_source_selection_intervention"] = (
            source_selection_intervention_count > 0
        )
        automated_gates["at_least_one_chase_or_stop_intervention"] = (
            chase_or_stop_intervention_count > 0
        )
        automated_gates["profile_authority_exercised_everywhere"] = (
            fixture_count > 0
            and readiness_profile_authority_exercised_count == fixture_count
        )
    automated_gates["all_passed"] = all(automated_gates.values())
    fixtures_needing_review = [
        str(review.get("fixture_name", "unknown"))
        for review in fixture_reviews
        if review.get("gate_passed") is not True
    ]
    return {
        "all_passed": automated_gates["all_passed"],
        "automated_gates": automated_gates,
        "summary": {
            "fixture_count": fixture_count,
            "fixtures_with_proof_summary": fixtures_with_proof_summary,
            "fixtures_with_reviewable_proofs": fixtures_with_reviewable_proofs,
            "proof_count": proof_count,
            "allowed_count": allowed_count,
            "blocked_count": blocked_count,
            "ignored_count": ignored_count,
            "verified_count": verified_count,
            "verification_failed_count": verification_failed_count,
            "pending_verification_count": pending_verification_count,
            "fallback_count": fallback_count,
            "invalid_output_count": invalid_output_count,
            "budget_violation_count": budget_violation_count,
            "disabled_source_violation_count": disabled_source_violation_count,
            "reserved_source_violation_count": reserved_source_violation_count,
            "context_only_source_violation_count": (
                context_only_source_violation_count
            ),
            "grounding_source_violation_count": grounding_source_violation_count,
            "missing_rationale_count": missing_rationale_count,
            "allowed_unverified_count": allowed_unverified_count,
            "allowed_without_policy_count": allowed_without_policy_count,
            "allowed_without_applied_action_count": (
                allowed_without_applied_action_count
            ),
            "blocked_without_reason_count": blocked_without_reason_count,
            "blocked_or_ignored_count": blocked_or_ignored_count,
            "source_selection_intervention_count": (
                source_selection_intervention_count
            ),
            "chase_or_stop_intervention_count": chase_or_stop_intervention_count,
            "readiness_summaries_present": readiness_summaries_present,
            "readiness_profile_authority_exercised_count": (
                readiness_profile_authority_exercised_count
            ),
            "readiness_source_selection_intervention_count": (
                readiness_source_selection_intervention_count
            ),
            "readiness_chase_or_stop_intervention_count": (
                readiness_chase_or_stop_intervention_count
            ),
            "readiness_brief_generation_intervention_count": (
                readiness_brief_generation_intervention_count
            ),
            "fixtures_missing_profile_authority": fixtures_missing_profile_authority,
            "fixtures_needing_review": fixtures_needing_review,
        },
        "fixtures": fixture_reviews,
    }


def _build_guarded_report(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    compare_payloads: list[JSONObject],
    fixture_specs: tuple[Phase2ShadowFixtureSpec, ...],
    fixture_set: Phase2ShadowFixtureSet,
    pubmed_backend: str,
    compare_mode: Phase1GuardedCompareMode,
    report_mode: Phase1GuardedReportMode = "standard",
    preflight: dict[str, str | None],
    guarded_rollout_profile: str = "guarded_low_risk",
    repeat_count: int = 1,
    canary_label: str | None = None,
    expected_run_count: int | None = None,
) -> JSONObject:
    _validate_compare_payload_count(
        compare_payloads=compare_payloads,
        fixture_specs=fixture_specs,
    )
    fixture_reports: list[JSONObject] = []
    total_applied = 0
    total_identified = 0
    total_candidates = 0
    total_verified = 0
    total_failed = 0
    total_pending = 0
    total_chase_actions = 0
    total_chase_verified = 0
    total_chase_exact_selection_matches = 0
    total_chase_candidate_count = 0
    total_chase_candidate_exact_selection_matches = 0
    total_chase_selected_entity_overlap_total = 0
    total_chase_selection_mismatch_count = 0
    total_terminal_control_actions = 0
    total_terminal_control_verified = 0
    total_chase_checkpoint_stops = 0
    total_orchestrator_filtered_chase_candidates = 0
    matched_count = 0
    diverged_count = 0
    rationale_present_count = 0
    expected_match_count = 0
    acceptable_divergence_count = 0
    accepted_conservative_stop_count = 0
    needs_review_count = 0
    execution_drift_count = 0
    live_source_jitter_count = 0
    downstream_state_drift_count = 0
    guarded_narrowing_drift_count = 0
    expected_follow_on_drift_count = 0
    total_runtime_seconds = 0.0
    runtime_fixture_count = 0
    failed_fixtures: list[JSONObject] = []
    for spec, compare_payload in zip(fixture_specs, compare_payloads, strict=True):
        _validate_compare_payload_shape(
            fixture_name=spec.fixture_name,
            compare_payload=compare_payload,
        )
        fixture_runtime_seconds = _optional_float(
            compare_payload.get("fixture_runtime_seconds"),
        )
        fixture_error = _dict_value(compare_payload.get("fixture_error"))
        if fixture_error:
            failed_fixture = {
                "fixture_name": spec.fixture_name,
                "error_type": _maybe_string(fixture_error.get("error_type"))
                or "unknown",
                "error_message": _maybe_string(
                    fixture_error.get("error_message"),
                )
                or "",
            }
            rounded_runtime_seconds = _round_runtime_seconds(fixture_runtime_seconds)
            if rounded_runtime_seconds is not None:
                failed_fixture["runtime_seconds"] = rounded_runtime_seconds
            failed_fixtures.append(failed_fixture)
        if fixture_runtime_seconds is not None:
            total_runtime_seconds += fixture_runtime_seconds
            runtime_fixture_count += 1
        guarded_evaluation = (
            dict(compare_payload.get("guarded_evaluation"))
            if isinstance(compare_payload.get("guarded_evaluation"), dict)
            else {}
        )
        review_summary = _build_fixture_review_summary(
            fixture_name=spec.fixture_name,
            compare_payload=compare_payload,
            guarded_evaluation=guarded_evaluation,
            compare_mode=compare_mode,
        )
        guarded_decision_proofs = _extract_guarded_decision_proofs(compare_payload)
        guarded_readiness = _extract_guarded_readiness(compare_payload)
        guarded_graduation_review = _build_fixture_guarded_graduation_review(
            fixture_name=spec.fixture_name,
            proof_summary=guarded_decision_proofs,
            readiness_summary=guarded_readiness,
        )
        total_applied += _int_value(guarded_evaluation.get("applied_count"))
        total_candidates += _int_value(guarded_evaluation.get("candidate_count"))
        total_identified += _int_value(guarded_evaluation.get("identified_count"))
        total_verified += _int_value(guarded_evaluation.get("verified_count"))
        total_failed += _int_value(
            guarded_evaluation.get("verification_failed_count"),
        )
        total_pending += _int_value(
            guarded_evaluation.get("pending_verification_count"),
        )
        total_chase_actions += _int_value(guarded_evaluation.get("chase_action_count"))
        total_chase_verified += _int_value(
            guarded_evaluation.get("chase_verified_count"),
        )
        total_chase_exact_selection_matches += _int_value(
            guarded_evaluation.get("chase_exact_selection_match_count"),
        )
        total_chase_candidate_count += _int_value(
            guarded_evaluation.get("chase_candidate_count"),
        )
        total_chase_candidate_exact_selection_matches += _int_value(
            guarded_evaluation.get(
                "chase_candidate_exact_selection_match_count",
            ),
        )
        total_chase_selected_entity_overlap_total += _int_value(
            guarded_evaluation.get("chase_selected_entity_overlap_total"),
        ) + _int_value(guarded_evaluation.get("chase_candidate_overlap_total"))
        total_chase_selection_mismatch_count += _int_value(
            guarded_evaluation.get("chase_selection_mismatch_count"),
        )
        total_terminal_control_actions += _int_value(
            guarded_evaluation.get("terminal_control_action_count"),
        )
        total_terminal_control_verified += _int_value(
            guarded_evaluation.get("terminal_control_verified_count"),
        )
        total_chase_checkpoint_stops += _int_value(
            guarded_evaluation.get("chase_checkpoint_stop_count"),
        )
        total_orchestrator_filtered_chase_candidates += _int_value(
            review_summary.get("orchestrator_filtered_chase_candidate_count"),
        )
        comparison_status = review_summary.get("comparison_status")
        if comparison_status == "matched":
            matched_count += 1
        elif comparison_status in {"diverged", "mismatch"}:
            diverged_count += 1
        if bool(review_summary.get("qualitative_rationale_present")):
            rationale_present_count += 1
        review_verdict = review_summary.get("review_verdict")
        if review_verdict == "expected_match":
            expected_match_count += 1
        elif review_verdict == "acceptable_divergence":
            acceptable_divergence_count += 1
        elif review_verdict == "accepted_conservative_stop":
            accepted_conservative_stop_count += 1
        elif review_verdict == "needs_review":
            needs_review_count += 1
        drift_class = review_summary.get("drift_class")
        if drift_class == "execution_drift":
            execution_drift_count += 1
        elif drift_class == "live_source_jitter":
            live_source_jitter_count += 1
        elif drift_class == "downstream_state_drift":
            downstream_state_drift_count += 1
        elif drift_class == "guarded_narrowing_drift":
            guarded_narrowing_drift_count += 1
        elif drift_class == "expected_follow_on_drift":
            expected_follow_on_drift_count += 1
        fixture_reports.append(
            {
                "fixture_name": spec.fixture_name,
                "fixture_status": "failed" if fixture_error else "completed",
                "fixture_error": fixture_error or None,
                "objective": spec.objective,
                "request": compare_payload.get("request"),
                "mismatches": _string_list(compare_payload.get("mismatches")),
                "advisories": _string_list(compare_payload.get("advisories")),
                "guarded_evaluation": guarded_evaluation,
                "guarded_decision_proofs": guarded_decision_proofs,
                "guarded_graduation_review": guarded_graduation_review,
                "review_summary": review_summary,
                "fixture_runtime_seconds": _round_runtime_seconds(
                    fixture_runtime_seconds,
                ),
                "orchestrator_run_id": _maybe_string(
                    _dict_value(compare_payload.get("orchestrator")).get("run_id"),
                ),
                "baseline_run_id": _maybe_string(
                    _dict_value(compare_payload.get("baseline")).get("run_id"),
                ),
            },
        )
    guarded_graduation_gate = _build_guarded_graduation_gate(
        fixture_reports=fixture_reports,
        require_source_chase_interventions=(
            guarded_rollout_profile == _GUARDED_SOURCE_CHASE_PROFILE
        ),
    )
    automated_gates = {
        "no_fixture_errors": len(failed_fixtures) == 0,
        "no_verification_failures": total_failed == 0,
        "no_pending_verifications": total_pending == 0,
        "at_least_one_guarded_action_applied": total_applied > 0,
        "at_least_one_guarded_intervention_identified": total_identified > 0,
    }
    automated_gates["all_passed"] = all(
        (
            automated_gates["no_fixture_errors"],
            automated_gates["no_verification_failures"],
            automated_gates["no_pending_verifications"],
            (
                automated_gates["at_least_one_guarded_action_applied"]
                if compare_mode == "dual_live_guarded"
                else automated_gates["at_least_one_guarded_intervention_identified"]
            ),
        ),
    )
    report_summary: JSONObject = {
        "fixture_count": len(fixture_reports),
        "run_count": len(fixture_reports),
        "unique_fixture_count": len(
            {
                _base_fixture_name(str(fixture.get("fixture_name", "unknown")))
                for fixture in fixture_reports
            },
        ),
        "repeat_count": repeat_count,
        "completed_fixture_count": len(fixture_reports) - len(failed_fixtures),
        "failed_fixture_count": len(failed_fixtures),
        "failed_fixtures": failed_fixtures,
        "timed_out_fixture_count": sum(
            1
            for fixture in failed_fixtures
            if fixture.get("error_type") == "TimeoutError"
        ),
        "timed_out_fixtures": [
            str(fixture.get("fixture_name"))
            for fixture in failed_fixtures
            if fixture.get("error_type") == "TimeoutError"
        ],
        "total_runtime_seconds": _round_runtime_seconds(total_runtime_seconds),
        "average_runtime_seconds": _round_runtime_seconds(
            (
                total_runtime_seconds / runtime_fixture_count
                if runtime_fixture_count > 0
                else None
            ),
        ),
        "applied_count": total_applied,
        "candidate_count": total_candidates,
        "identified_count": total_identified,
        "verified_count": total_verified,
        "verification_failed_count": total_failed,
        "pending_verification_count": total_pending,
        "chase_action_count": total_chase_actions,
        "chase_verified_count": total_chase_verified,
        "chase_exact_selection_match_count": total_chase_exact_selection_matches,
        "chase_candidate_count": total_chase_candidate_count,
        "chase_candidate_exact_selection_match_count": (
            total_chase_candidate_exact_selection_matches
        ),
        "chase_selected_entity_overlap_total": (
            total_chase_selected_entity_overlap_total
        ),
        "chase_selection_mismatch_count": total_chase_selection_mismatch_count,
        "terminal_control_action_count": total_terminal_control_actions,
        "terminal_control_verified_count": total_terminal_control_verified,
        "chase_checkpoint_stop_count": total_chase_checkpoint_stops,
        "orchestrator_filtered_chase_candidate_count": (
            total_orchestrator_filtered_chase_candidates
        ),
        "matched_count": matched_count,
        "diverged_count": diverged_count,
        "qualitative_rationale_present_count": rationale_present_count,
        "expected_match_count": expected_match_count,
        "acceptable_divergence_count": acceptable_divergence_count,
        "accepted_conservative_stop_count": accepted_conservative_stop_count,
        "needs_review_count": needs_review_count,
        "execution_drift_count": execution_drift_count,
        "live_source_jitter_count": live_source_jitter_count,
        "downstream_state_drift_count": downstream_state_drift_count,
        "guarded_narrowing_drift_count": guarded_narrowing_drift_count,
        "expected_follow_on_drift_count": expected_follow_on_drift_count,
        "fixtures_with_guarded_actions": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "applied_count",
                ),
            )
            > 0
        ],
        "fixtures_with_guarded_chase_actions": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "chase_action_count",
                ),
            )
            > 0
        ],
        "fixtures_with_guarded_terminal_control": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "terminal_control_action_count",
                ),
            )
            > 0
        ],
        "fixtures_with_guarded_chase_checkpoint_stops": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "chase_checkpoint_stop_count",
                ),
            )
            > 0
        ],
        "fixtures_with_replay_only_chase_candidates": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "chase_candidate_count",
                ),
            )
            > 0
        ],
        "fixtures_with_filtered_chase_candidates": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("review_summary")).get(
                    "orchestrator_filtered_chase_candidate_count",
                ),
            )
            > 0
        ],
        "fixtures_with_failures": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _int_value(
                _dict_value(fixture.get("guarded_evaluation")).get(
                    "verification_failed_count",
                ),
            )
            > 0
        ],
        "fixtures_without_actions": [
            fixture["fixture_name"]
            for fixture in fixture_reports
            if _dict_value(fixture.get("guarded_evaluation")).get("status")
            == "no_guarded_actions_applied"
        ],
    }
    report: JSONObject = {
        "generated_at": datetime.now(UTC).isoformat(),
        "planner_mode": FullAIOrchestratorPlannerMode.GUARDED.value,
        "compare_mode": compare_mode,
        "report_mode": report_mode,
        "canary_label": canary_label,
        "expected_run_count": expected_run_count,
        "fixture_set": fixture_set,
        "pubmed_backend": pubmed_backend,
        "guarded_rollout_profile": guarded_rollout_profile,
        "repeat_count": repeat_count,
        "guarded_chase_rollout_enabled": _guarded_chase_rollout_enabled(),
        "preflight": preflight,
        "summary": report_summary,
        "automated_gates": automated_gates,
        "guarded_graduation_gate": guarded_graduation_gate,
        "canary_gate": None,
        "fixtures": fixture_reports,
    }
    if report_mode == "canary":
        report["canary_gate"] = _build_canary_gate(
            fixture_reports=fixture_reports,
            report_summary=report_summary,
            guarded_graduation_gate=guarded_graduation_gate,
            expected_run_count=expected_run_count,
        )
    return report


def _validate_compare_payload_count(
    *,
    compare_payloads: list[JSONObject],
    fixture_specs: tuple[Phase2ShadowFixtureSpec, ...],
) -> None:
    if len(compare_payloads) != len(fixture_specs):
        msg = (
            "Phase 1 guarded evaluation received "
            f"{len(compare_payloads)} compare payload(s) for "
            f"{len(fixture_specs)} fixture(s)."
        )
        raise ValueError(msg)


def _validate_compare_payload_shape(
    *,
    fixture_name: str,
    compare_payload: JSONObject,
) -> None:
    if not isinstance(compare_payload, dict):
        msg = (
            "Phase 1 guarded evaluation received a malformed compare payload "
            f"for fixture {fixture_name}: expected object, got "
            f"{type(compare_payload).__name__}."
        )
        raise TypeError(msg)
    fixture_error = compare_payload.get("fixture_error")
    if isinstance(fixture_error, dict):
        return
    missing_sections = [
        section
        for section in ("baseline", "orchestrator", "guarded_evaluation")
        if not isinstance(compare_payload.get(section), dict)
    ]
    if missing_sections:
        msg = (
            "Phase 1 guarded evaluation received a malformed compare payload "
            f"for fixture {fixture_name}: missing object section(s): "
            f"{', '.join(missing_sections)}."
        )
        raise ValueError(msg)


def _build_canary_gate(
    *,
    fixture_reports: list[JSONObject],
    report_summary: JSONObject,
    guarded_graduation_gate: JSONObject,
    expected_run_count: int | None,
) -> JSONObject:
    graduation_summary = _dict_value(guarded_graduation_gate.get("summary"))
    graduation_gates = _dict_value(guarded_graduation_gate.get("automated_gates"))
    timed_out_fixtures = _string_list(report_summary.get("timed_out_fixtures"))
    run_count = _int_value(report_summary.get("run_count"))
    source_policy_violation_counts = {
        "disabled": _int_value(
            graduation_summary.get("disabled_source_violation_count")
        ),
        "reserved": _int_value(
            graduation_summary.get("reserved_source_violation_count")
        ),
        "context_only": _int_value(
            graduation_summary.get("context_only_source_violation_count"),
        ),
        "grounding": _int_value(
            graduation_summary.get("grounding_source_violation_count"),
        ),
    }
    proof_clean_run_count = sum(
        1
        for fixture in fixture_reports
        if _dict_value(fixture.get("guarded_graduation_review")).get("gate_passed")
        is True
    )
    expected_run_count_met = (
        expected_run_count is None or run_count >= expected_run_count
    )
    automated_gates = {
        "guarded_graduation_gate_passed": guarded_graduation_gate.get("all_passed")
        is True,
        "proof_receipts_present_and_verified": all(
            (
                graduation_gates.get("proof_summaries_present") is True,
                graduation_gates.get("reviewable_proofs_present") is True,
                graduation_gates.get("at_least_one_allowed_proof") is True,
                graduation_gates.get("no_blocked_or_ignored_proofs") is True,
                graduation_gates.get("all_allowed_proofs_verified") is True,
                graduation_gates.get("no_verification_failures") is True,
                graduation_gates.get("no_pending_verifications") is True,
                graduation_gates.get("all_allowed_proofs_policy_allowed") is True,
                graduation_gates.get("all_allowed_proofs_have_applied_action") is True,
                graduation_gates.get("blocked_proofs_have_reasons") is True,
            ),
        ),
        "no_fixture_failures": _int_value(report_summary.get("failed_fixture_count"))
        == 0,
        "no_timeouts": len(timed_out_fixtures) == 0,
        "expected_run_count_met": expected_run_count_met,
        "no_invalid_outputs": _int_value(graduation_summary.get("invalid_output_count"))
        == 0,
        "no_fallback_outputs": _int_value(graduation_summary.get("fallback_count"))
        == 0,
        "no_budget_violations": _int_value(
            graduation_summary.get("budget_violation_count"),
        )
        == 0,
        "no_disabled_source_violations": source_policy_violation_counts["disabled"]
        == 0,
        "no_reserved_source_violations": source_policy_violation_counts["reserved"]
        == 0,
        "no_context_only_source_violations": (
            source_policy_violation_counts["context_only"] == 0
        ),
        "no_grounding_source_violations": (
            source_policy_violation_counts["grounding"] == 0
        ),
        "qualitative_rationale_present_everywhere": (
            graduation_gates.get("qualitative_rationale_present_everywhere") is True
        ),
        "profile_authority_exercised_everywhere": (
            graduation_gates.get("profile_authority_exercised_everywhere") is True
        ),
        "at_least_one_source_selection_intervention": (
            _int_value(graduation_summary.get("source_selection_intervention_count"))
            > 0
        ),
        "at_least_one_chase_or_stop_intervention": (
            _int_value(graduation_summary.get("chase_or_stop_intervention_count")) > 0
        ),
    }
    all_passed = all(automated_gates.values())
    rollback_required = any(
        automated_gates.get(gate_name) is False
        for gate_name in _ROLLBACK_REQUIRED_CANARY_GATES
    )
    verdict = (
        "pass" if all_passed else "rollback_required" if rollback_required else "hold"
    )
    notes: list[str] = []
    if expected_run_count is not None and run_count != expected_run_count:
        notes.append(
            "run_count differed from the expected coverage target "
            f"(expected {expected_run_count}, observed {run_count})",
        )
    if timed_out_fixtures:
        notes.append("one or more canary runs timed out")
    if proof_clean_run_count != len(fixture_reports):
        notes.append("one or more runs had non-clean guarded proof receipts")
    return {
        "all_passed": all_passed,
        "verdict": verdict,
        "automated_gates": automated_gates,
        "summary": {
            "run_count": run_count,
            "unique_fixture_count": _int_value(
                report_summary.get("unique_fixture_count"),
            ),
            "repeat_count": _int_value(report_summary.get("repeat_count")),
            "expected_run_count": expected_run_count,
            "expected_run_count_met": expected_run_count_met,
            "timeout_count": len(timed_out_fixtures),
            "timed_out_fixtures": timed_out_fixtures,
            "total_runtime_seconds": _optional_float(
                report_summary.get("total_runtime_seconds"),
            ),
            "average_runtime_seconds": _optional_float(
                report_summary.get("average_runtime_seconds"),
            ),
            "proof_clean_run_count": proof_clean_run_count,
            "proof_receipt_count": _int_value(graduation_summary.get("proof_count")),
            "verified_proof_receipt_count": _int_value(
                graduation_summary.get("verified_count"),
            ),
            "fallback_count": _int_value(graduation_summary.get("fallback_count")),
            "invalid_output_count": _int_value(
                graduation_summary.get("invalid_output_count"),
            ),
            "budget_violation_count": _int_value(
                graduation_summary.get("budget_violation_count"),
            ),
            "source_selection_intervention_count": _int_value(
                graduation_summary.get("source_selection_intervention_count"),
            ),
            "chase_or_stop_intervention_count": _int_value(
                graduation_summary.get("chase_or_stop_intervention_count"),
            ),
            "profile_authority_exercised_count": _int_value(
                graduation_summary.get("readiness_profile_authority_exercised_count"),
            ),
            "fixtures_missing_profile_authority": _string_list(
                graduation_summary.get("fixtures_missing_profile_authority"),
            ),
            "source_policy_violation_counts": source_policy_violation_counts,
            "source_policy_violation_total": sum(
                source_policy_violation_counts.values(),
            ),
        },
        "notes": notes,
    }


def render_phase1_guarded_evaluation_markdown(  # noqa: PLR0912, PLR0915
    report: JSONObject,
) -> str:
    """Render a concise Markdown summary for human review."""

    summary = _dict_value(report.get("summary"))
    automated_gates = _dict_value(report.get("automated_gates"))
    guarded_graduation_gate = _dict_value(report.get("guarded_graduation_gate"))
    graduation_summary = _dict_value(guarded_graduation_gate.get("summary"))
    graduation_gates = _dict_value(guarded_graduation_gate.get("automated_gates"))
    canary_gate = _dict_value(report.get("canary_gate"))
    canary_summary = _dict_value(canary_gate.get("summary"))
    canary_gates = _dict_value(canary_gate.get("automated_gates"))
    source_policy_violation_counts = _dict_value(
        canary_summary.get("source_policy_violation_counts"),
    )
    fixtures = _list_of_dicts(report.get("fixtures"))
    report_mode = _maybe_string(report.get("report_mode")) or "standard"
    lines = [
        (
            "# Guarded Source+Chase Canary Evaluation"
            if report_mode == "canary"
            else "# Phase 1 Guarded Evaluation"
        ),
        "",
        f"- Generated: {report.get('generated_at', 'n/a')}",
        f"- Planner mode: {report.get('planner_mode', 'guarded')}",
        f"- Compare mode: {report.get('compare_mode', 'unknown')}",
        f"- Report mode: {report_mode}",
        f"- Fixture set: {report.get('fixture_set', 'objective')}",
        f"- PubMed backend: {report.get('pubmed_backend', 'unknown')}",
        f"- Guarded rollout profile: {report.get('guarded_rollout_profile', 'unknown')}",
        f"- Repeat count: {report.get('repeat_count', 1)}",
    ]
    canary_label = _maybe_string(report.get("canary_label"))
    if canary_label is not None:
        lines.append(f"- Canary label: {canary_label}")
    if report.get("expected_run_count") is not None:
        lines.append(f"- Expected run count: {report.get('expected_run_count')}")
    lines.extend(
        [
            (
                "- Guarded chase rollout: "
                f"{'enabled' if report.get('guarded_chase_rollout_enabled') else 'disabled'}"
            ),
            f"- Automated gates: {'PASS' if automated_gates.get('all_passed') else 'FAIL'}",
            (
                "- Guarded graduation gate: "
                f"{'PASS' if guarded_graduation_gate.get('all_passed') else 'FAIL'}"
            ),
        ]
    )
    if report_mode == "canary":
        lines.append(
            "- Canary gate: "
            f"{'PASS' if canary_gate.get('all_passed') else 'FAIL'}"
            f" ({_canary_verdict_label(canary_gate.get('verdict'))})",
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Fixtures: {summary.get('fixture_count', 0)}",
            f"- Runs: {summary.get('run_count', summary.get('fixture_count', 0))}",
            f"- Unique fixtures: {summary.get('unique_fixture_count', 0)}",
            f"- Completed fixtures: {summary.get('completed_fixture_count', 0)}",
            f"- Failed fixtures: {summary.get('failed_fixture_count', 0)}",
            f"- Timed-out fixtures: {summary.get('timed_out_fixture_count', 0)}",
            (
                "- Timed-out fixture names: "
                f"{_fixture_list_text(summary.get('timed_out_fixtures'))}"
            ),
            (
                "- Total runtime (s): "
                f"{_display_float(summary.get('total_runtime_seconds'))}"
            ),
            (
                "- Average runtime (s): "
                f"{_display_float(summary.get('average_runtime_seconds'))}"
            ),
            f"- Guarded actions applied: {summary.get('applied_count', 0)}",
            f"- Guarded interventions identified: {summary.get('identified_count', 0)}",
            f"- Replay-only guarded candidates: {summary.get('candidate_count', 0)}",
            f"- Guarded actions verified: {summary.get('verified_count', 0)}",
            f"- Verification failures: {summary.get('verification_failed_count', 0)}",
            f"- Pending verifications: {summary.get('pending_verification_count', 0)}",
            f"- Guarded chase actions: {summary.get('chase_action_count', 0)}",
            f"- Verified guarded chase actions: {summary.get('chase_verified_count', 0)}",
            (
                f"- Replay-only chase candidates: {summary.get('chase_candidate_count', 0)}"
            ),
        ],
    )
    lines.extend(
        [
            (
                "- Exact chase selection matches: "
                f"{summary.get('chase_exact_selection_match_count', 0)}"
            ),
            (
                "- Replay exact chase selection matches: "
                f"{summary.get('chase_candidate_exact_selection_match_count', 0)}"
            ),
            (
                "- Chase selected-entity overlap total: "
                f"{summary.get('chase_selected_entity_overlap_total', 0)}"
            ),
            (
                "- Chase selection mismatches: "
                f"{summary.get('chase_selection_mismatch_count', 0)}"
            ),
            (
                "- Guarded terminal-control actions: "
                f"{summary.get('terminal_control_action_count', 0)}"
            ),
            (
                "- Verified terminal-control actions: "
                f"{summary.get('terminal_control_verified_count', 0)}"
            ),
            (
                "- Guarded chase checkpoint stops: "
                f"{summary.get('chase_checkpoint_stop_count', 0)}"
            ),
            (
                "- Orchestrator filtered chase candidates: "
                f"{summary.get('orchestrator_filtered_chase_candidate_count', 0)}"
            ),
            (
                "- Fixtures with guarded chase actions: "
                f"{_fixture_list_text(summary.get('fixtures_with_guarded_chase_actions'))}"
            ),
            (
                "- Fixtures with guarded terminal control: "
                f"{_fixture_list_text(summary.get('fixtures_with_guarded_terminal_control'))}"
            ),
            (
                "- Fixtures with guarded chase checkpoint stops: "
                f"{_fixture_list_text(summary.get('fixtures_with_guarded_chase_checkpoint_stops'))}"
            ),
            (
                "- Fixtures with replay-only chase candidates: "
                f"{_fixture_list_text(summary.get('fixtures_with_replay_only_chase_candidates'))}"
            ),
            (
                "- Fixtures with filtered chase candidates: "
                f"{_fixture_list_text(summary.get('fixtures_with_filtered_chase_candidates'))}"
            ),
            f"- Source matches: {summary.get('matched_count', 0)}",
            f"- Source divergences: {summary.get('diverged_count', 0)}",
            f"- Expected matches: {summary.get('expected_match_count', 0)}",
            f"- Acceptable divergences: {summary.get('acceptable_divergence_count', 0)}",
            (
                "- Accepted conservative stops: "
                f"{summary.get('accepted_conservative_stop_count', 0)}"
            ),
            f"- Needs review: {summary.get('needs_review_count', 0)}",
            f"- Execution drift after match: {summary.get('execution_drift_count', 0)}",
            (
                "- Downstream state drift after match: "
                f"{summary.get('downstream_state_drift_count', 0)}"
            ),
            (
                "- Expected guarded narrowing after match: "
                f"{summary.get('guarded_narrowing_drift_count', 0)}"
            ),
            (
                "- Expected downstream drift after accepted divergence: "
                f"{summary.get('expected_follow_on_drift_count', 0)}"
            ),
            (
                "- Qualitative rationale present: "
                f"{summary.get('qualitative_rationale_present_count', 0)}/"
                f"{summary.get('fixture_count', 0)}"
            ),
            (f"- Guarded proof receipts: {graduation_summary.get('proof_count', 0)}"),
            (
                "- Allowed guarded proof receipts: "
                f"{graduation_summary.get('allowed_count', 0)}"
            ),
            (
                "- Blocked or ignored guarded proof receipts: "
                f"{graduation_summary.get('blocked_or_ignored_count', 0)}"
            ),
            (
                "- Source-selection interventions: "
                f"{graduation_summary.get('source_selection_intervention_count', 0)}"
            ),
            (
                "- Chase-or-stop interventions: "
                f"{graduation_summary.get('chase_or_stop_intervention_count', 0)}"
            ),
            "",
            "## Automated Gates",
            "",
            f"- No fixture errors: {_gate_label(automated_gates.get('no_fixture_errors'))}",
            f"- No verification failures: {_gate_label(automated_gates.get('no_verification_failures'))}",
            f"- No pending verifications: {_gate_label(automated_gates.get('no_pending_verifications'))}",
            f"- At least one guarded action applied: {_gate_label(automated_gates.get('at_least_one_guarded_action_applied'))}",
            f"- At least one guarded intervention identified: {_gate_label(automated_gates.get('at_least_one_guarded_intervention_identified'))}",
            "",
            "## Guarded Graduation Gate",
            "",
        ],
    )
    lines.extend(
        [
            (
                "- Proof summaries present: "
                f"{_gate_label(graduation_gates.get('proof_summaries_present'))}"
            ),
            (
                "- Reviewable proof receipts present: "
                f"{_gate_label(graduation_gates.get('reviewable_proofs_present'))}"
            ),
            (
                "- At least one allowed proof receipt: "
                f"{_gate_label(graduation_gates.get('at_least_one_allowed_proof'))}"
            ),
            (
                "- No blocked or ignored proof receipts: "
                f"{_gate_label(graduation_gates.get('no_blocked_or_ignored_proofs'))}"
            ),
            (
                "- All allowed proof receipts verified: "
                f"{_gate_label(graduation_gates.get('all_allowed_proofs_verified'))}"
            ),
            (
                "- No fallback recommendations: "
                f"{_gate_label(graduation_gates.get('no_fallback_recommendations'))}"
            ),
            (
                "- No invalid outputs: "
                f"{_gate_label(graduation_gates.get('no_invalid_outputs'))}"
            ),
            (
                "- No budget violations: "
                f"{_gate_label(graduation_gates.get('no_budget_violations'))}"
            ),
            (
                "- No disabled-source violations: "
                f"{_gate_label(graduation_gates.get('no_disabled_source_violations'))}"
            ),
            (
                "- Qualitative rationale present everywhere: "
                f"{_gate_label(graduation_gates.get('qualitative_rationale_present_everywhere'))}"
            ),
            (
                "- At least one source-selection intervention: "
                f"{_optional_gate_label(graduation_gates.get('at_least_one_source_selection_intervention'))}"
            ),
            (
                "- At least one chase-or-stop intervention: "
                f"{_optional_gate_label(graduation_gates.get('at_least_one_chase_or_stop_intervention'))}"
            ),
            (
                "- Profile authority exercised everywhere: "
                f"{_optional_gate_label(graduation_gates.get('profile_authority_exercised_everywhere'))}"
            ),
            (
                "- Readiness source-selection interventions: "
                f"{graduation_summary.get('readiness_source_selection_intervention_count', 0)}"
            ),
            (
                "- Readiness chase-or-stop interventions: "
                f"{graduation_summary.get('readiness_chase_or_stop_intervention_count', 0)}"
            ),
            (
                "- Readiness brief-generation interventions: "
                f"{graduation_summary.get('readiness_brief_generation_intervention_count', 0)}"
            ),
            (
                "- Fixtures missing profile authority: "
                f"{_fixture_list_text(graduation_summary.get('fixtures_missing_profile_authority'))}"
            ),
            (
                "- Fixtures needing review: "
                f"{_fixture_list_text(graduation_summary.get('fixtures_needing_review'))}"
            ),
        ],
    )
    if report_mode == "canary":
        lines.extend(
            [
                "",
                "## Canary Gate",
                "",
                f"- Verdict: {_canary_verdict_label(canary_gate.get('verdict'))}",
                (
                    "- Proof-clean runs: "
                    f"{canary_summary.get('proof_clean_run_count', 0)}/"
                    f"{canary_summary.get('run_count', 0)}"
                ),
                (
                    "- Expected run count met: "
                    f"{_gate_label(canary_gates.get('expected_run_count_met'))}"
                ),
                (
                    "- No fixture failures: "
                    f"{_gate_label(canary_gates.get('no_fixture_failures'))}"
                ),
                f"- No timeouts: {_gate_label(canary_gates.get('no_timeouts'))}",
                (
                    "- Proof receipts present and verified: "
                    f"{_gate_label(canary_gates.get('proof_receipts_present_and_verified'))}"
                ),
                (
                    "- No invalid outputs: "
                    f"{_gate_label(canary_gates.get('no_invalid_outputs'))}"
                ),
                (
                    "- No fallback outputs: "
                    f"{_gate_label(canary_gates.get('no_fallback_outputs'))}"
                ),
                (
                    "- No budget violations: "
                    f"{_gate_label(canary_gates.get('no_budget_violations'))}"
                ),
                (
                    "- No disabled-source violations: "
                    f"{_gate_label(canary_gates.get('no_disabled_source_violations'))}"
                ),
                (
                    "- No reserved-source violations: "
                    f"{_gate_label(canary_gates.get('no_reserved_source_violations'))}"
                ),
                (
                    "- No context-only source violations: "
                    f"{_gate_label(canary_gates.get('no_context_only_source_violations'))}"
                ),
                (
                    "- No grounding-source violations: "
                    f"{_gate_label(canary_gates.get('no_grounding_source_violations'))}"
                ),
                (
                    "- Qualitative rationale present everywhere: "
                    f"{_gate_label(canary_gates.get('qualitative_rationale_present_everywhere'))}"
                ),
                (
                    "- Profile authority exercised everywhere: "
                    f"{_gate_label(canary_gates.get('profile_authority_exercised_everywhere'))}"
                ),
                (
                    "- At least one source-selection intervention: "
                    f"{_gate_label(canary_gates.get('at_least_one_source_selection_intervention'))}"
                ),
                (
                    "- At least one chase-or-stop intervention: "
                    f"{_gate_label(canary_gates.get('at_least_one_chase_or_stop_intervention'))}"
                ),
                (
                    "- Source-policy violations: disabled="
                    f"{source_policy_violation_counts.get('disabled', 0)}, "
                    "reserved="
                    f"{source_policy_violation_counts.get('reserved', 0)}, "
                    "context_only="
                    f"{source_policy_violation_counts.get('context_only', 0)}, "
                    "grounding="
                    f"{source_policy_violation_counts.get('grounding', 0)}"
                ),
                (
                    "- Canary notes: "
                    f"{'; '.join(_string_list(canary_gate.get('notes'))) or 'none'}"
                ),
            ],
        )
    lines.extend(
        [
            "",
            "## Fixtures",
            "",
            "| Fixture | Status | Selected | Target | Compare | Verdict | Applied | Verified | Proof Gate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ],
    )
    for fixture in fixtures:
        guarded = _dict_value(fixture.get("guarded_evaluation"))
        review_summary = _dict_value(fixture.get("review_summary"))
        graduation_review = _dict_value(fixture.get("guarded_graduation_review"))
        lines.append(
            "| "
            f"{fixture.get('fixture_name', 'unknown')} | "
            f"{guarded.get('status', 'unknown')} | "
            f"{_selected_action_display(review_summary, target=False)} | "
            f"{_selected_action_display(review_summary, target=True)} | "
            f"{review_summary.get('comparison_status', 'n/a')} | "
            f"{review_summary.get('review_verdict', 'n/a')} | "
            f"{guarded.get('applied_count', 0)} | "
            f"{guarded.get('verified_count', 0)} | "
            f"{'PASS' if graduation_review.get('gate_passed') else 'FAIL'} | "
        )
    lines.extend(("", "## Fixture Notes", ""))
    for fixture in fixtures:
        fixture_error = _dict_value(fixture.get("fixture_error"))
        review_summary = _dict_value(fixture.get("review_summary"))
        graduation_review = _dict_value(fixture.get("guarded_graduation_review"))
        lines.extend(
            [
                f"### {fixture.get('fixture_name', 'unknown')}",
                (
                    f"- Selected: {_selected_action_display(review_summary, target=False)}"
                    f" | Target: "
                    f"{_selected_action_display(review_summary, target=True)}"
                    f" | Compare: {review_summary.get('comparison_status', 'n/a')}"
                    f" | Verdict: {review_summary.get('review_verdict', 'n/a')}"
                ),
                (
                    f"- Proposals: baseline={review_summary.get('baseline_proposal_count', 'n/a')}"
                    f" | orchestrator={review_summary.get('orchestrator_proposal_count', 'n/a')}"
                    f" | delta={review_summary.get('proposal_count_delta', 'n/a')}"
                ),
                (
                    "- Runtime (s): "
                    f"{_display_float(fixture.get('fixture_runtime_seconds'))}"
                ),
                (
                    "- Proof gate: "
                    f"{'PASS' if graduation_review.get('gate_passed') else 'FAIL'}"
                    f" | proofs={graduation_review.get('proof_count', 0)}"
                    f" | allowed={graduation_review.get('allowed_count', 0)}"
                    f" | blocked_or_ignored="
                    f"{graduation_review.get('blocked_or_ignored_count', 0)}"
                ),
            ],
        )
        if fixture_error:
            lines.append(
                "- Fixture error: "
                f"{fixture_error.get('error_type', 'unknown')}: "
                f"{fixture_error.get('error_message', '')}"
            )
        proof_notes = _string_list(graduation_review.get("notes"))
        if proof_notes:
            lines.append(f"- Proof notes: {'; '.join(proof_notes)}")
        verdict_note = _review_note_for_display(
            fixture_name=str(fixture.get("fixture_name", "unknown")),
            review_summary=review_summary,
        )
        if verdict_note is not None:
            lines.append(f"- Verdict note: {verdict_note}")
        rationale_excerpt = _maybe_string(
            review_summary.get("qualitative_rationale_excerpt"),
        )
        if rationale_excerpt is not None:
            lines.append(f"- Rationale: {rationale_excerpt}")
        terminal_control_summary = _render_terminal_control_summary(review_summary)
        if terminal_control_summary is not None:
            lines.append(f"- Terminal control: {terminal_control_summary}")
        chase_summary = _render_chase_selection_summary(review_summary)
        if chase_summary is not None:
            lines.append(f"- Chase selection: {chase_summary}")
        filtered_chase_summary = _render_filtered_chase_summary(review_summary)
        if filtered_chase_summary is not None:
            lines.append(f"- Filtered chase candidates: {filtered_chase_summary}")
        drift_label = _drift_label(review_summary.get("drift_class"))
        top_mismatch = _maybe_string(review_summary.get("top_mismatch"))
        if drift_label is not None and top_mismatch is not None:
            lines.append(f"- {drift_label}: {top_mismatch}")
        drift_note = _maybe_string(review_summary.get("drift_note"))
        if drift_note is not None:
            lines.append(f"- Drift note: {drift_note}")
        if drift_label is None and top_mismatch is not None:
            lines.append(f"- Top mismatch: {top_mismatch}")
        lines.append("")
    return "\n".join(lines)


def write_phase1_guarded_evaluation_report(
    report: JSONObject,
    *,
    output_dir: str | Path,
) -> JSONObject:
    """Write the aggregate report and per-fixture JSON payloads."""

    _validate_guarded_report_payload(report)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    summary_json_path = output_dir_path / "summary.json"
    summary_markdown_path = output_dir_path / "summary.md"
    summary_json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_markdown_path.write_text(
        render_phase1_guarded_evaluation_markdown(report) + "\n",
        encoding="utf-8",
    )

    fixture_report_paths: JSONObject = {}
    for fixture_report in _list_of_dicts(report.get("fixtures")):
        fixture_name = str(fixture_report.get("fixture_name", "unknown"))
        fixture_path = output_dir_path / f"{fixture_name.casefold()}_guarded.json"
        fixture_path.write_text(
            json.dumps(fixture_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        fixture_report_paths[fixture_name] = str(fixture_path)

    manifest = {
        "output_dir": str(output_dir_path),
        "summary_json": str(summary_json_path),
        "summary_markdown": str(summary_markdown_path),
        "fixture_reports": fixture_report_paths,
    }
    (output_dir_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _validate_guarded_report_payload(report: JSONObject) -> None:
    if not isinstance(report, dict):
        msg = (
            "Phase 1 guarded evaluation report must be a JSON object, got "
            f"{type(report).__name__}."
        )
        raise TypeError(msg)
    missing_sections = [
        section
        for section in ("summary", "automated_gates", "guarded_graduation_gate")
        if not isinstance(report.get(section), dict)
    ]
    if missing_sections:
        msg = (
            "Phase 1 guarded evaluation report is malformed: missing object "
            f"section(s): {', '.join(missing_sections)}."
        )
        raise ValueError(msg)
    fixtures = report.get("fixtures")
    if not isinstance(fixtures, list):
        msg = "Phase 1 guarded evaluation report is malformed: fixtures must be a list."
        raise TypeError(msg)
    for index, fixture in enumerate(fixtures):
        if isinstance(fixture, dict):
            continue
        msg = (
            "Phase 1 guarded evaluation report is malformed: fixture entry "
            f"{index} must be an object, got {type(fixture).__name__}."
        )
        raise TypeError(msg)
    if report.get("report_mode") == "canary":
        canary_gate = report.get("canary_gate")
        if not isinstance(canary_gate, dict):
            msg = (
                "Phase 1 guarded evaluation report is malformed: canary mode "
                "requires an object `canary_gate` section."
            )
            raise ValueError(msg)
        missing_canary_sections = [
            section
            for section in ("summary", "automated_gates")
            if not isinstance(canary_gate.get(section), dict)
        ]
        if missing_canary_sections:
            msg = (
                "Phase 1 guarded evaluation report is malformed: canary mode "
                "requires object `canary_gate` subsection(s): "
                f"{', '.join(missing_canary_sections)}."
            )
            raise ValueError(msg)
        if _maybe_string(canary_gate.get("verdict")) is None:
            msg = (
                "Phase 1 guarded evaluation report is malformed: canary mode "
                "requires a non-empty `canary_gate.verdict` value."
            )
            raise ValueError(msg)


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _dict_of_ints(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: count
        for key, count in value.items()
        if isinstance(key, str) and isinstance(count, int)
    }


def _latest_chase_context(summary: JSONObject) -> JSONObject:
    for key in ("pending_chase_round", "chase_round_2", "chase_round_1"):
        value = _dict_value(summary.get(key))
        if value:
            return value
    return {}


def _build_fixture_review_summary(
    *,
    fixture_name: str,
    compare_payload: JSONObject,
    guarded_evaluation: JSONObject,
    compare_mode: Phase1GuardedCompareMode,
) -> JSONObject:
    baseline_summary = _dict_value(
        _dict_value(compare_payload.get("baseline")).get("workspace"),
    )
    orchestrator_summary = _dict_value(
        _dict_value(compare_payload.get("orchestrator")).get("workspace"),
    )
    applied_actions = _list_of_dicts(guarded_evaluation.get("applied_actions"))
    candidate_actions = _list_of_dicts(guarded_evaluation.get("candidate_actions"))
    primary_action = _select_primary_review_action(
        applied_actions + candidate_actions,
    )
    baseline_chase_context = _latest_chase_context(baseline_summary)
    orchestrator_chase_context = _latest_chase_context(orchestrator_summary)
    baseline_proposal_count = _int_or_none(baseline_summary.get("proposal_count"))
    orchestrator_proposal_count = _int_or_none(
        orchestrator_summary.get("proposal_count"),
    )
    proposal_count_delta: int | None = None
    if baseline_proposal_count is not None and orchestrator_proposal_count is not None:
        proposal_count_delta = orchestrator_proposal_count - baseline_proposal_count
    rationale = _maybe_string(primary_action.get("qualitative_rationale"))
    mismatches = _string_list(compare_payload.get("mismatches"))
    comparison_status = _maybe_string(primary_action.get("comparison_status"))
    selected_source_key = _maybe_string(primary_action.get("source_key"))
    deterministic_target_source_key = _maybe_string(
        primary_action.get("target_source_key"),
    )
    action_type = _maybe_string(primary_action.get("action_type"))
    selected_entity_ids = _string_list(primary_action.get("selected_entity_ids"))
    selected_labels = _string_list(primary_action.get("selected_labels"))
    deterministic_selected_entity_ids = _string_list(
        primary_action.get("deterministic_selected_entity_ids"),
    )
    deterministic_selected_labels = _string_list(
        primary_action.get("deterministic_selected_labels"),
    )
    exact_chase_selection_match = _bool_or_none(
        primary_action.get("exact_selection_match"),
    )
    stop_reason = _maybe_string(primary_action.get("stop_reason"))
    deterministic_stop_expected = _bool_or_none(
        primary_action.get("deterministic_stop_expected"),
    )
    review_verdict, review_note = _classify_fixture_review_verdict(
        fixture_name=fixture_name,
        review_summary={
            "comparison_status": comparison_status,
            "action_type": action_type,
            "guarded_strategy": _maybe_string(primary_action.get("guarded_strategy")),
            "selected_source_key": selected_source_key,
            "deterministic_target_source_key": deterministic_target_source_key,
            "selected_entity_ids": selected_entity_ids,
            "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
            "exact_chase_selection_match": exact_chase_selection_match,
            "qualitative_rationale_present": rationale is not None,
            "stop_reason": stop_reason,
            "deterministic_stop_expected": deterministic_stop_expected,
        },
    )
    orchestrator_guarded_mode = _extract_enrichment_execution_mode(
        orchestrator_summary,
    )
    deferred_guarded_source_count = _count_deferred_guarded_sources(
        orchestrator_summary,
    )
    filtered_chase_context_drift = _filtered_chase_context_differs(
        baseline_summary=baseline_summary,
        orchestrator_summary=orchestrator_summary,
    )
    drift_class, drift_note = _classify_downstream_drift(
        review_verdict=review_verdict,
        mismatches=mismatches,
        proposal_count_delta=proposal_count_delta,
        comparison_status=comparison_status,
        orchestrator_guarded_mode=orchestrator_guarded_mode,
        deferred_guarded_source_count=deferred_guarded_source_count,
        filtered_chase_context_drift=filtered_chase_context_drift,
        compare_mode=compare_mode,
    )
    top_mismatch = _select_top_mismatch(
        mismatches=mismatches,
        drift_class=drift_class,
    )
    return {
        "selected_source_key": selected_source_key,
        "deterministic_target_source_key": deterministic_target_source_key,
        "comparison_status": comparison_status,
        "action_type": action_type,
        "guarded_strategy": _maybe_string(primary_action.get("guarded_strategy")),
        "round_number": _int_or_none(primary_action.get("round_number")),
        "target_action_type": _maybe_string(primary_action.get("target_action_type")),
        "planner_status": _maybe_string(primary_action.get("planner_status")),
        "stop_reason": stop_reason,
        "deterministic_stop_expected": deterministic_stop_expected,
        "selected_entity_ids": selected_entity_ids,
        "selected_labels": selected_labels,
        "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
        "deterministic_selected_labels": deterministic_selected_labels,
        "selected_entity_overlap_count": _int_or_none(
            primary_action.get("selected_entity_overlap_count"),
        ),
        "exact_chase_selection_match": exact_chase_selection_match,
        "selection_basis": _maybe_string(primary_action.get("selection_basis")),
        "baseline_proposal_count": baseline_proposal_count,
        "orchestrator_proposal_count": orchestrator_proposal_count,
        "proposal_count_delta": proposal_count_delta,
        "orchestrator_guarded_mode": orchestrator_guarded_mode,
        "deferred_guarded_source_count": deferred_guarded_source_count,
        "baseline_pending_questions_count": _list_count(
            baseline_summary.get("pending_questions"),
        ),
        "orchestrator_pending_questions_count": _list_count(
            orchestrator_summary.get("pending_questions"),
        ),
        "baseline_filtered_chase_candidate_count": _int_or_none(
            baseline_chase_context.get("filtered_chase_candidate_count"),
        ),
        "baseline_filtered_chase_filter_reason_counts": _dict_of_ints(
            baseline_chase_context.get("filtered_chase_filter_reason_counts"),
        ),
        "baseline_filtered_chase_labels": _string_list(
            baseline_chase_context.get("filtered_chase_labels"),
        ),
        "orchestrator_filtered_chase_candidate_count": _int_or_none(
            orchestrator_chase_context.get("filtered_chase_candidate_count"),
        ),
        "orchestrator_filtered_chase_filter_reason_counts": _dict_of_ints(
            orchestrator_chase_context.get("filtered_chase_filter_reason_counts"),
        ),
        "orchestrator_filtered_chase_labels": _string_list(
            orchestrator_chase_context.get("filtered_chase_labels"),
        ),
        "qualitative_rationale_present": rationale is not None,
        "qualitative_rationale_excerpt": _excerpt_text(rationale, max_chars=220),
        "review_verdict": review_verdict,
        "review_note": review_note,
        "mismatch_count": len(mismatches),
        "drift_class": drift_class,
        "drift_note": drift_note,
        "top_mismatch": top_mismatch,
    }


def _select_primary_review_action(candidate_actions: list[JSONObject]) -> JSONObject:
    """Pick the action that should drive the human review summary.

    Guarded source narrowing often appears first, but chase-selection divergence is the
    sharper manual-review signal once the planner is actually steering chase rounds.
    Prefer a mismatched chase selection when present so the summary reflects the
    highest-signal remaining review question.
    """

    for action in candidate_actions:
        if _maybe_string(action.get("guarded_strategy")) != "chase_selection":
            continue
        if _bool_or_none(action.get("exact_selection_match")) is False:
            return action
    for action in candidate_actions:
        if _maybe_string(action.get("guarded_strategy")) == "chase_selection":
            return action
    for action in candidate_actions:
        if _maybe_string(action.get("guarded_strategy")) != "terminal_control_flow":
            continue
        if _maybe_string(action.get("checkpoint_key")) not in {
            "after_bootstrap",
            "after_chase_round_1",
        }:
            continue
        return action
    return candidate_actions[0] if candidate_actions else {}


def _classify_fixture_review_verdict(
    *,
    fixture_name: str,
    review_summary: JSONObject,
) -> tuple[str, str]:
    normalized_fixture = fixture_name.strip().casefold()
    comparison_status = _maybe_string(review_summary.get("comparison_status"))
    action_type = _maybe_string(review_summary.get("action_type"))
    guarded_strategy = _maybe_string(review_summary.get("guarded_strategy"))
    selected_source_key = _maybe_string(review_summary.get("selected_source_key"))
    deterministic_target_source_key = _maybe_string(
        review_summary.get("deterministic_target_source_key"),
    )
    exact_chase_selection_match = _bool_or_none(
        review_summary.get("exact_chase_selection_match"),
    )
    selected_entity_ids = _string_list(review_summary.get("selected_entity_ids"))
    deterministic_selected_entity_ids = _string_list(
        review_summary.get("deterministic_selected_entity_ids"),
    )
    qualitative_rationale_present = bool(
        review_summary.get("qualitative_rationale_present"),
    )
    stop_reason = _maybe_string(review_summary.get("stop_reason"))
    deterministic_stop_expected = _bool_or_none(
        review_summary.get("deterministic_stop_expected"),
    )
    if comparison_status == "matched":
        if action_type == "STOP" and guarded_strategy == "terminal_control_flow":
            if deterministic_stop_expected is True:
                reason_suffix = (
                    f" ({stop_reason.replace('_', ' ')})"
                    if stop_reason is not None
                    else ""
                )
                return (
                    "expected_match",
                    "Planner correctly stopped at the chase checkpoint because the "
                    f"deterministic threshold was not met{reason_suffix}.",
                )
            reason_suffix = (
                f" ({stop_reason.replace('_', ' ')})" if stop_reason is not None else ""
            )
            return (
                "expected_match",
                "Planner correctly used guarded terminal control at the chase "
                f"checkpoint{reason_suffix}.",
            )
        if action_type == "RUN_CHASE_ROUND":
            return (
                "expected_match",
                "Planner matched the deterministic chase selection for this fixture.",
            )
        return (
            "expected_match",
            "Planner matched the deterministic next source for this fixture.",
        )
    if not qualitative_rationale_present:
        if action_type == "RUN_CHASE_ROUND":
            return (
                "needs_review",
                "Planner did not provide qualitative rationale for the chase selection.",
            )
        return (
            "needs_review",
            "Planner did not provide qualitative rationale for the source choice.",
        )
    if (
        normalized_fixture == "brca1"
        and comparison_status in {"diverged", "mismatch"}
        and action_type == "RUN_STRUCTURED_ENRICHMENT"
        and selected_source_key == "drugbank"
        and deterministic_target_source_key == "clinvar"
    ):
        return (
            "acceptable_divergence",
            "Objective is therapy-shaped, so preferring DrugBank over ClinVar is acceptable for BRCA1.",
        )
    if (
        normalized_fixture == "med13"
        and comparison_status in {"diverged", "mismatch"}
        and action_type == "RUN_STRUCTURED_ENRICHMENT"
        and selected_source_key in {"marrvel", "mgi"}
        and deterministic_target_source_key == "clinvar"
    ):
        return (
            "acceptable_divergence",
            "Objective is developmental/model-organism shaped, so preferring a model-organism source over ClinVar is acceptable for MED13.",
        )
    if (
        action_type == "RUN_CHASE_ROUND"
        and comparison_status in {"diverged", "mismatch"}
        and selected_entity_ids
        and set(selected_entity_ids).issubset(set(deterministic_selected_entity_ids))
        and exact_chase_selection_match is False
    ):
        return (
            "acceptable_divergence",
            "Planner narrowed the deterministic chase set to a bounded subset with qualitative rationale, so this guarded divergence is acceptable.",
        )
    if (
        action_type == "STOP"
        and guarded_strategy == "terminal_control_flow"
        and comparison_status in {"diverged", "mismatch"}
        and stop_reason is not None
    ):
        return (
            "accepted_conservative_stop",
            "Planner made a conservative guarded STOP with qualitative rationale; treat this as an accepted safety-first divergence when the proof gate is clean.",
        )
    if comparison_status in {"diverged", "mismatch"}:
        return (
            "needs_review",
            "Planner diverged from the deterministic source without a fixture-specific acceptance rule.",
        )
    return (
        "needs_review",
        "Planner did not expose enough comparison detail to classify this fixture automatically.",
    )


def _classify_downstream_drift(  # noqa: PLR0913
    *,
    review_verdict: str,
    mismatches: list[str],
    proposal_count_delta: int,
    comparison_status: str | None,
    orchestrator_guarded_mode: str | None,
    deferred_guarded_source_count: int,
    filtered_chase_context_drift: bool,
    compare_mode: Phase1GuardedCompareMode,
) -> tuple[str | None, str | None]:
    if not mismatches:
        return (None, None)
    if (
        review_verdict == "expected_match"
        and comparison_status == "matched"
        and (
            orchestrator_guarded_mode == "guarded_single_source"
            or deferred_guarded_source_count > 0
        )
    ):
        return (
            "guarded_narrowing_drift",
            "Guarded mode intentionally narrowed structured enrichment to one source, so downstream workspace drift is expected.",
        )
    if review_verdict in {"acceptable_divergence", "accepted_conservative_stop"}:
        return (
            "expected_follow_on_drift",
            "Planner intentionally chose a different accepted path, so downstream workspace drift is expected.",
        )
    if (
        review_verdict == "expected_match"
        and comparison_status == "matched"
        and compare_mode == "dual_live_guarded"
        and proposal_count_delta == 0
        and filtered_chase_context_drift
        and all(
            mismatch
            == "source_results differ between baseline and orchestrator summaries"
            for mismatch in mismatches
        )
    ):
        return (
            "live_source_jitter",
            "Planner matched the deterministic next step, and the remaining drift is limited to chase-candidate pool differences across the two live spaces.",
        )
    if (
        review_verdict == "expected_match"
        and comparison_status == "matched"
        and compare_mode == "dual_live_guarded"
    ):
        if proposal_count_delta == 0 and _mismatches_are_downstream_state_only(
            mismatches,
        ):
            return (
                "downstream_state_drift",
                "Planner matched the deterministic next step and evidence counts aligned; the remaining drift is limited to generated follow-up state such as pending-question wording or summary fields.",
            )
        return (
            "live_source_jitter",
            "Planner matched the deterministic next step, and the remaining drift is likely coming from rerunning live sources in a separate space.",
        )
    if review_verdict == "expected_match":
        return (
            "execution_drift",
            "Planner matched the deterministic next step, but the final workspace still drifted and should be investigated.",
        )
    return (
        "needs_review",
        "Workspace drift is present and this fixture still needs manual review.",
    )


def _select_top_mismatch(
    *,
    mismatches: list[str],
    drift_class: str | None,
) -> str | None:
    if not mismatches:
        return None
    if drift_class == "live_source_jitter":
        for mismatch in mismatches:
            if not mismatch.startswith("proposal_count: "):
                return mismatch
    return mismatches[0]


def _filtered_chase_context_differs(
    *,
    baseline_summary: JSONObject,
    orchestrator_summary: JSONObject,
) -> bool:
    baseline_context = _latest_chase_context(baseline_summary)
    orchestrator_context = _latest_chase_context(orchestrator_summary)
    if not baseline_context and not orchestrator_context:
        return False
    return (
        _int_or_none(baseline_context.get("filtered_chase_candidate_count"))
        != _int_or_none(orchestrator_context.get("filtered_chase_candidate_count"))
        or _dict_of_ints(baseline_context.get("filtered_chase_filter_reason_counts"))
        != _dict_of_ints(
            orchestrator_context.get("filtered_chase_filter_reason_counts"),
        )
        or _string_list(baseline_context.get("filtered_chase_labels"))
        != _string_list(orchestrator_context.get("filtered_chase_labels"))
    )


def _drift_label(value: object) -> str | None:
    drift_class = _maybe_string(value)
    if drift_class == "execution_drift":
        return "Execution drift"
    if drift_class == "live_source_jitter":
        return "Live-source jitter"
    if drift_class == "downstream_state_drift":
        return "Downstream state drift"
    if drift_class == "guarded_narrowing_drift":
        return "Expected guarded narrowing"
    if drift_class == "expected_follow_on_drift":
        return "Expected downstream drift"
    if drift_class == "needs_review":
        return "Review-needed drift"
    return None


def _extract_enrichment_execution_mode(workspace_summary: JSONObject) -> str | None:
    source_results = _dict_value(workspace_summary.get("source_results"))
    orchestration = _dict_value(source_results.get("enrichment_orchestration"))
    return _maybe_string(orchestration.get("execution_mode"))


def _count_deferred_guarded_sources(workspace_summary: JSONObject) -> int:
    source_results = _dict_value(workspace_summary.get("source_results"))
    deferred_count = 0
    for source_key, source_summary in source_results.items():
        if source_key == "enrichment_orchestration":
            continue
        normalized_summary = _dict_value(source_summary)
        if normalized_summary.get("deferred_reason") == "guarded_source_selection":
            deferred_count += 1
    return deferred_count


def _maybe_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped != "" else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _mismatches_are_downstream_state_only(mismatches: list[str]) -> bool:
    allowed_prefixes = (
        "pending_questions:",
        "source_results differ between baseline and orchestrator summaries",
    )
    return bool(mismatches) and all(
        any(mismatch.startswith(prefix) for prefix in allowed_prefixes)
        for mismatch in mismatches
    )


def _int_value(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _list_count(value: object) -> int | None:
    if isinstance(value, list):
        return len(value)
    return None


def _excerpt_text(value: str | None, *, max_chars: int) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _selected_action_display(
    review_summary: JSONObject,
    *,
    target: bool,
) -> str:
    if target:
        if _bool_or_none(review_summary.get("deterministic_stop_expected")) is True:
            return "STOP"
        if (
            _maybe_string(review_summary.get("action_type")) == "STOP"
            and _maybe_string(review_summary.get("guarded_strategy"))
            == "terminal_control_flow"
            and _maybe_string(review_summary.get("comparison_status")) == "matched"
        ):
            return "STOP"
    elif _maybe_string(review_summary.get("action_type")) == "STOP":
        return "STOP"
    source_key = (
        _maybe_string(review_summary.get("deterministic_target_source_key"))
        if target
        else _maybe_string(review_summary.get("selected_source_key"))
    )
    if source_key is not None:
        return source_key
    labels = (
        _string_list(review_summary.get("deterministic_selected_labels"))
        if target
        else _string_list(review_summary.get("selected_labels"))
    )
    if labels:
        return _compact_label_display(labels)
    return "n/a"


def _compact_label_display(labels: list[str], *, limit: int = 3) -> str:
    if len(labels) <= limit:
        return ", ".join(labels)
    head = ", ".join(labels[:limit])
    return f"{head} (+{len(labels) - limit})"


def _format_reason_counts(reason_counts: dict[str, int]) -> str:
    if not reason_counts:
        return "none"
    ordered_items = sorted(reason_counts.items())
    return ", ".join(f"{reason}={count}" for reason, count in ordered_items)


def _render_filtered_chase_summary(review_summary: JSONObject) -> str | None:
    baseline_count = _int_or_none(
        review_summary.get("baseline_filtered_chase_candidate_count"),
    )
    orchestrator_count = _int_or_none(
        review_summary.get("orchestrator_filtered_chase_candidate_count"),
    )
    baseline_labels = _string_list(review_summary.get("baseline_filtered_chase_labels"))
    orchestrator_labels = _string_list(
        review_summary.get("orchestrator_filtered_chase_labels"),
    )
    baseline_reasons = _dict_of_ints(
        review_summary.get("baseline_filtered_chase_filter_reason_counts"),
    )
    orchestrator_reasons = _dict_of_ints(
        review_summary.get("orchestrator_filtered_chase_filter_reason_counts"),
    )
    if (
        (baseline_count in {None, 0})
        and (orchestrator_count in {None, 0})
        and not baseline_labels
        and not orchestrator_labels
    ):
        return None
    if (
        baseline_count == orchestrator_count
        and baseline_labels == orchestrator_labels
        and baseline_reasons == orchestrator_reasons
    ):
        return (
            f"shared count={baseline_count or 0}"
            f" | reasons={_format_reason_counts(baseline_reasons)}"
            f" | examples={_compact_label_display(baseline_labels) if baseline_labels else 'n/a'}"
        )
    return (
        f"baseline count={baseline_count or 0}"
        f" | reasons={_format_reason_counts(baseline_reasons)}"
        f" | examples={_compact_label_display(baseline_labels) if baseline_labels else 'n/a'}"
        f" || orchestrator count={orchestrator_count or 0}"
        f" | reasons={_format_reason_counts(orchestrator_reasons)}"
        f" | examples={_compact_label_display(orchestrator_labels) if orchestrator_labels else 'n/a'}"
    )


def _render_chase_selection_summary(review_summary: JSONObject) -> str | None:
    selected_labels = _string_list(review_summary.get("selected_labels"))
    deterministic_labels = _string_list(
        review_summary.get("deterministic_selected_labels"),
    )
    if not selected_labels and not deterministic_labels:
        return None
    overlap_count = _int_or_none(review_summary.get("selected_entity_overlap_count"))
    exact_match = _bool_or_none(review_summary.get("exact_chase_selection_match"))
    exact_label = (
        "yes" if exact_match is True else "no" if exact_match is False else "n/a"
    )
    overlap_label = overlap_count if overlap_count is not None else "n/a"
    return (
        f"planner={', '.join(selected_labels) or 'n/a'}"
        f" | deterministic={', '.join(deterministic_labels) or 'n/a'}"
        f" | overlap={overlap_label}"
        f" | exact match={exact_label}"
    )


def _render_terminal_control_summary(review_summary: JSONObject) -> str | None:
    if _maybe_string(review_summary.get("action_type")) != "STOP":
        return None
    stop_reason = _maybe_string(review_summary.get("stop_reason")) or "unspecified"
    deterministic_stop_expected = _bool_or_none(
        review_summary.get("deterministic_stop_expected"),
    )
    if deterministic_stop_expected is True:
        expected_label = "yes"
    elif deterministic_stop_expected is False:
        expected_label = "no"
    elif _maybe_string(review_summary.get("comparison_status")) == "matched":
        expected_label = "matched terminal control"
    else:
        expected_label = "n/a"
    return (
        f"planner=STOP | deterministic_stop_expected={expected_label}"
        f" | stop_reason={stop_reason}"
    )


def _review_note_for_display(
    *,
    fixture_name: str,
    review_summary: JSONObject,
) -> str | None:
    _review_verdict, review_note = _classify_fixture_review_verdict(
        fixture_name=fixture_name,
        review_summary=review_summary,
    )
    return review_note


def _fixture_list_text(value: object) -> str:
    if not isinstance(value, list):
        return "none"
    fixture_names = [item for item in value if isinstance(item, str) and item != ""]
    if not fixture_names:
        return "none"
    return ", ".join(fixture_names)


def _gate_label(value: object) -> str:
    return "PASS" if value is True else "FAIL"


def _optional_gate_label(value: object) -> str:
    if value is None:
        return "n/a"
    return _gate_label(value)


def _proof_recommended_source_key(proof: JSONObject) -> str | None:
    for key in ("recommended_source_key", "applied_source_key"):
        source_key = _maybe_string(proof.get(key))
        if source_key is not None:
            return source_key
    for key in ("recommended_action_type", "applied_action_type"):
        action_type = _maybe_string(proof.get(key))
        if action_type is None:
            continue
        default_source_key = _ACTION_DEFAULT_SOURCE_KEYS.get(action_type)
        if default_source_key is not None:
            return default_source_key
    return None


def _proof_source_policy_violation_category(
    proof: JSONObject,
) -> Literal["disabled", "reserved", "context_only", "grounding"] | None:
    if proof.get("disabled_source_violation") is True:
        return "disabled"
    source_key = _proof_recommended_source_key(proof)
    if source_key in _RESERVED_SOURCE_KEYS:
        return "reserved"
    if source_key in _CONTEXT_ONLY_SOURCE_KEYS:
        return "context_only"
    if source_key in _GROUNDING_SOURCE_KEYS:
        return "grounding"
    if source_key in _LIVE_EVIDENCE_SOURCE_KEYS:
        return None
    validation_error = _maybe_string(proof.get("validation_error")) or ""
    lowered_error = validation_error.casefold()
    if "reserved" in lowered_error:
        return "reserved"
    if "context_only" in lowered_error or "context-only" in lowered_error:
        return "context_only"
    if "grounding" in lowered_error:
        return "grounding"
    return None


def _round_runtime_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)


def _display_float(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "n/a"
    return f"{number:.3f}"


def _base_fixture_name(value: str) -> str:
    head, _separator, _tail = value.partition("__repeat_")
    return head


def _canary_verdict_label(value: object) -> str:
    verdict = _maybe_string(value)
    if verdict is None:
        return "n/a"
    if verdict == "rollback_required":
        return "ROLLBACK REQUIRED"
    if verdict == "hold":
        return "HOLD"
    if verdict == "pass":
        return "PASS"
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
