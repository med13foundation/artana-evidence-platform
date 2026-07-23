"""Prepare a draft next Fresh-CG preregistration after a V12 pass."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.config import (
    DEFAULT_PATHS,
    V12Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.preflight import (
    PASS_TERMINAL,
)

_FRESH_V2_PREREGISTRATION = (
    DEFAULT_PATHS.preregistration.parent
    / "2026-07-22-fresh-cg-occurrence-v2-v2.json"
)
_FRESH_V2_RESULT = (
    DEFAULT_PATHS.result.parent / "2026-07-22-fresh-cg-occurrence-v2-v2.json"
)
_V2_CONSUMED_CASE = "fresh-cg-pmid-2681013-e5"
_UNTOUCHED_CASES = (
    "fresh-cg-pmid-16098727-e5",
    "fresh-cg-pmid-7904970-e11",
    "fresh-cg-pmid-19648108-e11",
    "fresh-cg-pmid-11306510-e1",
    "fresh-cg-pmid-18841154-e12",
    "fresh-cg-pmid-20448329-e6",
    "fresh-cg-pmid-8895545-e6",
)


class FreshDraftError(RuntimeError):
    """The next fresh draft cannot be derived from changed case history."""


def build_fresh_draft(paths: V12Paths = DEFAULT_PATHS) -> dict[str, object]:
    v12 = _object(json.loads(paths.result.read_text(encoding="utf-8")))
    if v12.get("decision") != PASS_TERMINAL:
        raise FreshDraftError("V12 did not pass")
    fresh_v2 = _object(
        json.loads(_FRESH_V2_PREREGISTRATION.read_text(encoding="utf-8"))
    )
    frozen = _object(fresh_v2["frozen_state"])
    old_order = tuple(cast("list[str]", frozen["case_order"]))
    if old_order != (_V2_CONSUMED_CASE, *_UNTOUCHED_CASES):
        raise FreshDraftError("fresh-case history changed")
    source_hashes = _object(frozen["source_sha256_by_case"])
    reference_hashes = _object(
        frozen["direct_cg_reference_sha256_by_case"]
    )
    return {
        "schema_version": "artana.fresh_cg.after_v12_draft.v1",
        "experiment_id": "fresh-cg-after-v12-draft-v1",
        "authorization": "DRAFT_ONLY_NO_PROVIDER_CALL_AUTHORIZED",
        "scientific_basis": {
            "v12_result_sha256": _sha256(paths.result),
            "v12_terminal": PASS_TERMINAL,
            "v12_focus_rule_sha256": _sha256(paths.focus_rule),
            "v12_two_lane_contract_sha256": _sha256(
                paths.two_lane_contract
            ),
            "grader_relaxed": False,
        },
        "case_accounting": {
            "sealed_v1_consumed_case_id": frozen["consumed_v1_case_id"],
            "sealed_v2_consumed_case_id": _V2_CONSUMED_CASE,
            "untouched_case_count": len(_UNTOUCHED_CASES),
            "untouched_case_order": list(_UNTOUCHED_CASES),
            "source_sha256_by_case": {
                case_id: source_hashes[case_id]
                for case_id in _UNTOUCHED_CASES
            },
            "direct_cg_reference_sha256_by_case": {
                case_id: reference_hashes[case_id]
                for case_id in _UNTOUCHED_CASES
            },
        },
        "frozen_history": {
            "fresh_v2_preregistration_sha256": _sha256(
                _FRESH_V2_PREREGISTRATION
            ),
            "fresh_v2_result_sha256": _sha256(_FRESH_V2_RESULT),
            "v12_result_sha256": _sha256(paths.result),
        },
        "required_before_execution": {
            "separate_forward_only_preregistration": True,
            "independent_review": True,
            "implementation_and_transport_hashes_frozen": True,
            "commit_and_push_before_provider_call": True,
        },
        "rules": {
            "provider_calls_authorized_by_this_artifact": 0,
            "fresh_cases_consumed_by_this_artifact": 0,
            "graph_writes": False,
            "trusted_graph_promotion": False,
        },
    }


def write_fresh_draft(paths: V12Paths = DEFAULT_PATHS) -> None:
    if paths.next_fresh_preregistration.exists():
        raise FreshDraftError("next fresh draft already exists")
    write_json_atomic(
        paths.next_fresh_preregistration,
        build_fresh_draft(paths),
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FreshDraftError("expected JSON object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["FreshDraftError", "build_fresh_draft", "write_fresh_draft"]
