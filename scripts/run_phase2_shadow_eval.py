#!/usr/bin/env python3
"""Run the manual Phase 2 shadow-planner evaluation workflow."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.phase1_compare import run_phase1_comparison_sync
from artana_evidence_api.phase2_shadow_compare import (
    DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
    evaluate_phase2_shadow_fixture_directory_sync,
    render_phase2_shadow_evaluation_markdown,
    write_phase2_shadow_evaluation_report,
)
from artana_evidence_api.phase2_shadow_fixture_refresh import (
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

_LOCAL_DEV_ENV_DEFAULTS: dict[str, str] = {
    "AUTH_JWT_SECRET": "artana-platform-backend-jwt-secret-for-development-2026-01",
    "GRAPH_JWT_SECRET": "artana-platform-backend-jwt-secret-for-development-2026-01",
    "GRAPH_JWT_ISSUER": "artana-platform",
    "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY": (
        "artana-evidence-api-bootstrap-key-for-development-2026-03"
    ),
}
_PUBMED_BACKEND_ENV = "ARTANA_PUBMED_SEARCH_BACKEND"
_PARTIAL_COVERAGE_GATE_KEYS = frozenset(
    {"minimum_fixture_coverage_met", "minimum_run_coverage_met"},
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the manual Phase 2 shadow-planner evaluation against the "
            "documented BRCA1, MED13, CFTR, and PCSK9 fixtures plus the "
            "supplemental chase fixtures and label-filtering fixture."
        ),
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
        help="Directory containing the Phase 2 shadow-planner fixture bundles.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for generated reports. Defaults to "
            "reports/full_ai_orchestrator_phase2_shadow/<timestamp>/."
        ),
    )
    parser.add_argument(
        "--skip-baseline-telemetry",
        action="store_true",
        help=(
            "Skip live deterministic baseline telemetry collection and rely only "
            "on telemetry stored in the fixture bundles."
        ),
    )
    parser.add_argument(
        "--allow-partial-coverage",
        action="store_true",
        help=(
            "Allow subset or diagnostic runs to exit successfully when the only "
            "failing automated gates are minimum fixture/run coverage."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""

    args = parse_args(argv)
    fixture_dir = _resolve_path(args.fixture_dir)
    output_dir = (
        _resolve_path(args.output_dir)
        if args.output_dir is not None
        else (
            _REPO_ROOT
            / "reports"
            / "full_ai_orchestrator_phase2_shadow"
            / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        )
    )
    preflight = _phase2_shadow_planner_preflight()
    if preflight["status"] != "ready":
        model_id = preflight["model_id"]
        model_text = f" ({model_id})" if model_id is not None else ""
        raise SystemExit(
            "Phase 2 shadow evaluation requires live planner access before running. "
            f"Planner capability `{preflight['capability']}`{model_text}: "
            f"{preflight['detail']}",
        )

    deterministic_baseline_payloads = None
    deterministic_baseline_expected_run_count = None
    if not args.skip_baseline_telemetry:
        (
            deterministic_baseline_payloads,
            deterministic_baseline_expected_run_count,
        ) = _collect_live_deterministic_baseline_telemetry(fixture_dir)

    report = evaluate_phase2_shadow_fixture_directory_sync(
        fixture_dir,
        deterministic_baseline_telemetry_payloads=deterministic_baseline_payloads,
        deterministic_baseline_expected_run_count=(
            deterministic_baseline_expected_run_count
        ),
    )
    manifest = write_phase2_shadow_evaluation_report(report, output_dir=output_dir)
    print(render_phase2_shadow_evaluation_markdown(report))
    print()
    print(f"Summary JSON: {manifest['summary_json']}")
    print(f"Summary Markdown: {manifest['summary_markdown']}")

    automated_gates = report.get("automated_gates")
    if not isinstance(automated_gates, dict):
        raise SystemExit("Phase 2 shadow evaluation did not produce automated gates.")
    if bool(automated_gates.get("all_passed")):
        return 0
    if args.allow_partial_coverage and _only_partial_coverage_gates_failed(
        automated_gates,
    ):
        print()
        print(
            "Phase 2 shadow evaluation passed in diagnostic mode: only the "
            "minimum coverage gates failed for this subset run.",
        )
        return 0

    unavailable_recommendations = int(
        report.get("summary", {}).get("unavailable_recommendations", 0)
        if isinstance(report.get("summary"), dict)
        else 0
    )
    if unavailable_recommendations > 0:
        msg = (
            "Phase 2 shadow evaluation failed automated gates because live planner "
            "recommendations were unavailable. Confirm model access and rerun. "
            f"See {manifest['summary_json']}."
        )
        raise SystemExit(msg)
    msg = (
        "Phase 2 shadow evaluation failed automated gates. "
        f"See {manifest['summary_json']}."
    )
    raise SystemExit(msg)


def _resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else _REPO_ROOT / path


def _only_partial_coverage_gates_failed(automated_gates: dict[str, object]) -> bool:
    failed_gates = {
        key
        for key, value in automated_gates.items()
        if key != "all_passed" and not bool(value)
    }
    return bool(failed_gates) and failed_gates <= _PARTIAL_COVERAGE_GATE_KEYS


def _phase2_shadow_planner_preflight() -> dict[str, str | None]:
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


def _collect_live_deterministic_baseline_telemetry(
    fixture_dir: Path,
) -> tuple[list[dict[str, object]], int]:
    selected_specs = _phase2_shadow_specs_for_fixture_dir(fixture_dir)
    if not selected_specs:
        return ([], 0)

    _apply_local_dev_env_defaults()
    previous_pubmed_backend = os.getenv(_PUBMED_BACKEND_ENV)
    os.environ[_PUBMED_BACKEND_ENV] = "deterministic"
    try:
        payloads: list[dict[str, object]] = []
        expected_run_count = 0
        for spec in selected_specs:
            for _run_spec in spec.runs:
                try:
                    compare_payload = run_phase1_comparison_sync(
                        fixture_request_from_spec(spec),
                    )
                except GraphServiceClientError as exc:
                    raise SystemExit(
                        _format_shadow_graph_error(spec, exc),
                    ) from exc
                baseline_payload = compare_payload.get("baseline")
                if not isinstance(baseline_payload, dict):
                    msg = (
                        "Phase 2 shadow evaluation could not read the baseline "
                        f"payload for fixture {spec.fixture_name}."
                    )
                    raise SystemExit(msg)
                telemetry = baseline_payload.get("telemetry")
                if not isinstance(telemetry, dict):
                    msg = (
                        "Phase 2 shadow evaluation did not receive deterministic "
                        f"baseline telemetry for fixture {spec.fixture_name}."
                    )
                    raise SystemExit(msg)
                payloads.append(dict(telemetry))
                expected_run_count += 1
        return (payloads, expected_run_count)
    finally:
        if previous_pubmed_backend is None:
            os.environ.pop(_PUBMED_BACKEND_ENV, None)
        else:
            os.environ[_PUBMED_BACKEND_ENV] = previous_pubmed_backend


def _phase2_shadow_specs_for_fixture_dir(
    fixture_dir: Path,
) -> tuple[Phase2ShadowFixtureSpec, ...]:
    fixture_names = {
        path.stem.casefold() for path in fixture_dir.glob("*.json") if path.is_file()
    }
    return tuple(
        spec
        for spec in phase2_shadow_fixture_specs_for_set("all")
        if spec.fixture_filename.removesuffix(".json").casefold() in fixture_names
    )


def _apply_local_dev_env_defaults() -> None:
    for key, value in _LOCAL_DEV_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def _format_shadow_graph_error(
    spec: Phase2ShadowFixtureSpec,
    exc: GraphServiceClientError,
) -> str:
    detail = exc.detail or str(exc)
    if "Signature verification failed" in detail:
        return (
            "Phase 2 shadow evaluation could not sync the temporary research "
            f"space for fixture `{spec.fixture_name}` because the backend and "
            "graph service JWT secrets are out of sync "
            "(signature verification failed). Restart both services with the "
            "same AUTH_JWT_SECRET and GRAPH_JWT_SECRET, then rerun the "
            "shadow evaluation."
        )
    return (
        "Phase 2 shadow evaluation failed while syncing the temporary "
        f"research space for fixture `{spec.fixture_name}`: {exc}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
