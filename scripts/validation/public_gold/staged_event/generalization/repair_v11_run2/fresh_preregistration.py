"""Prepare, but do not authorize, the next untouched Fresh-CG run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    DEFAULT_PATHS,
    V11Run2Paths,
)

_FRESH_V2_PREREGISTRATION = (
    DEFAULT_PATHS.preregistration.parent
    / "2026-07-22-fresh-cg-occurrence-v2-v2.json"
)
_FRESH_V2_RESULT = (
    DEFAULT_PATHS.result.parent / "2026-07-22-fresh-cg-occurrence-v2-v2.json"
)
_CONSUMED_RUN2_CASE = "fresh-cg-pmid-2681013-e5"
_UNTOUCHED_CASES = (
    "fresh-cg-pmid-16098727-e5",
    "fresh-cg-pmid-7904970-e11",
    "fresh-cg-pmid-19648108-e11",
    "fresh-cg-pmid-11306510-e1",
    "fresh-cg-pmid-18841154-e12",
    "fresh-cg-pmid-20448329-e6",
    "fresh-cg-pmid-8895545-e6",
)


class FreshPreregistrationError(RuntimeError):
    """The next fresh candidate cannot be prepared from changed history."""


def build_fresh_preregistration(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Freeze the seven untouched cases without authorizing a provider call."""

    v11_result = _object(json.loads(paths.result.read_text(encoding="utf-8")))
    if (
        v11_result.get("decision")
        != "V11_EXPOSED_RUN_V2_PASS_READY_FOR_FRESH_PREREGISTRATION"
    ):
        raise FreshPreregistrationError("V11 run 2 did not pass")
    fresh_v2 = _object(json.loads(_FRESH_V2_PREREGISTRATION.read_text(encoding="utf-8")))
    frozen = _object(fresh_v2["frozen_state"])
    old_order = tuple(cast("list[str]", frozen["case_order"]))
    if old_order != (_CONSUMED_RUN2_CASE, *_UNTOUCHED_CASES):
        raise FreshPreregistrationError("fresh-case history changed")
    source_hashes = _object(frozen["source_sha256_by_case"])
    reference_hashes = _object(frozen["direct_cg_reference_sha256_by_case"])
    return {
        "schema_version": (
            "artana.staged_generalization.fresh_after_v11_candidate.v1"
        ),
        "experiment_id": "fresh-cg-after-v11-pass-v1",
        "authorization": (
            "PREPARED_FOR_REVIEW_NO_PROVIDER_EXECUTION_AUTHORIZED_IN_V11_TASK"
        ),
        "scientific_basis": {
            "v11_exposed_run2_result_sha256": _sha256(paths.result),
            "v11_terminal": v11_result["decision"],
            "v11_prompt_sha256": _sha256(paths.prompt),
            "scientific_prompt": (
                "UNCHANGED_V11_PLUS_UNCHANGED_OCCURRENCE_BINDINGS_V2_SIDECAR"
            ),
            "schema_sha256": frozen["combined_provider_schema_sha256"],
            "occurrence_evaluator_package_sha256": frozen[
                "occurrence_evaluator_package_sha256"
            ],
            "grader_or_reference_relaxation": False,
        },
        "case_accounting": {
            "sealed_v1_consumed_case_id": frozen["consumed_v1_case_id"],
            "sealed_v2_consumed_case_id": _CONSUMED_RUN2_CASE,
            "untouched_case_count": len(_UNTOUCHED_CASES),
            "untouched_case_order": list(_UNTOUCHED_CASES),
            "source_sha256_by_case": {
                case_id: source_hashes[case_id] for case_id in _UNTOUCHED_CASES
            },
            "direct_cg_reference_sha256_by_case": {
                case_id: reference_hashes[case_id] for case_id in _UNTOUCHED_CASES
            },
        },
        "frozen_history": {
            "fresh_v2_preregistration_sha256": _sha256(
                _FRESH_V2_PREREGISTRATION
            ),
            "fresh_v2_result_sha256": _sha256(_FRESH_V2_RESULT),
            "v11_exposed_run2_result_sha256": _sha256(paths.result),
        },
        "required_before_execution": {
            "separate_forward_only_execution_version": True,
            "implementation_and_transport_hashes_frozen": True,
            "provider_budget_preregistered": True,
            "commit_and_push_before_provider_call": True,
            "review_approval": True,
        },
        "rules": {
            "provider_calls_authorized_by_this_artifact": 0,
            "fresh_cases_consumed_by_this_artifact": 0,
            "graph_writes": False,
            "trusted_graph_promotion": False,
        },
    }


def write_fresh_preregistration(
    paths: V11Run2Paths = DEFAULT_PATHS,
) -> None:
    """Persist the review-ready next-run preregistration candidate."""

    if paths.fresh_preregistration.exists():
        raise FreshPreregistrationError("fresh preregistration already exists")
    write_json_atomic(
        paths.fresh_preregistration,
        build_fresh_preregistration(paths),
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FreshPreregistrationError("expected JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "FreshPreregistrationError",
    "build_fresh_preregistration",
    "write_fresh_preregistration",
]
