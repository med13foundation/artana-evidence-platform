#!/usr/bin/env python3
"""Refresh Phase 2 shadow-planner fixtures from real Phase 1 compare runs."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.phase1_compare import run_phase1_comparison_sync
from artana_evidence_api.phase2_shadow_compare import (
    DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
)
from artana_evidence_api.phase2_shadow_fixture_refresh import (
    build_fixture_bundle,
    default_phase2_shadow_fixture_specs,
    fixture_request_from_spec,
    resolve_fixture_output_path,
    write_fixture_bundle,
)

_PUBMED_BACKEND_ENV = "ARTANA_PUBMED_SEARCH_BACKEND"
_LOCAL_DEV_ENV_DEFAULTS: dict[str, str] = {
    "AUTH_JWT_SECRET": "artana-platform-backend-jwt-secret-for-development-2026-01",
    "GRAPH_JWT_SECRET": "artana-platform-backend-jwt-secret-for-development-2026-01",
    "GRAPH_JWT_ISSUER": "artana-platform",
    "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY": (
        "artana-evidence-api-bootstrap-key-for-development-2026-03"
    ),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the BRCA1, CFTR, MED13, and PCSK9 Phase 2 shadow-planner "
            "fixture bundles from real Phase 1 compare runs."
        ),
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_PHASE2_SHADOW_FIXTURE_DIR,
        help="Directory where the fixture JSON files should be written.",
    )
    parser.add_argument(
        "--fixtures",
        type=str,
        default="",
        help=(
            "Optional comma-separated fixture names to refresh "
            "(for example: BRCA1,MED13)."
        ),
    )
    parser.add_argument(
        "--pubmed-backend",
        type=str,
        default="deterministic",
        help=(
            "Value for ARTANA_PUBMED_SEARCH_BACKEND during fixture refresh. "
            "Defaults to deterministic."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and validate bundles without writing the fixture files.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    selected_names = {
        item.strip().casefold()
        for item in args.fixtures.split(",")
        if item.strip() != ""
    }
    fixture_specs = tuple(
        spec
        for spec in default_phase2_shadow_fixture_specs()
        if not selected_names or spec.fixture_name.casefold() in selected_names
    )
    if not fixture_specs:
        raise SystemExit("No Phase 2 shadow fixtures matched the requested names.")

    previous_pubmed_backend = os.getenv(_PUBMED_BACKEND_ENV)
    previous_local_dev_env = {key: os.getenv(key) for key in _LOCAL_DEV_ENV_DEFAULTS}
    os.environ[_PUBMED_BACKEND_ENV] = args.pubmed_backend
    for key, value in _LOCAL_DEV_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
    try:
        for spec in fixture_specs:
            compare_payloads_by_run_id = {}
            print(f"Refreshing {spec.fixture_name}...", flush=True)
            for run_spec in spec.runs:
                request = fixture_request_from_spec(spec)
                compare_payloads_by_run_id[run_spec.run_id] = (
                    run_phase1_comparison_sync(
                        request,
                    )
                )
            bundle = build_fixture_bundle(
                spec=spec,
                compare_payloads_by_run_id=compare_payloads_by_run_id,
            )
            output_path = resolve_fixture_output_path(
                spec=spec,
                fixture_dir=args.fixture_dir,
            )
            if args.dry_run:
                print(f"  validated {spec.fixture_name} -> {output_path}")
                continue
            written_path = write_fixture_bundle(
                fixture_bundle=bundle,
                output_path=output_path,
            )
            print(f"  wrote {written_path}")
    finally:
        if previous_pubmed_backend is None:
            os.environ.pop(_PUBMED_BACKEND_ENV, None)
        else:
            os.environ[_PUBMED_BACKEND_ENV] = previous_pubmed_backend
        for key, previous_value in previous_local_dev_env.items():
            if previous_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous_value
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
