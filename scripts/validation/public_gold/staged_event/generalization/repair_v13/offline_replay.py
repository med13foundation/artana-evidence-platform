"""Zero-credit sealed V12 nested replay through the V13 source contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    V13CaseMetrics,
    evaluate_v13_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.config import (
        GradingArtifactPaths,
    )

_CASE_ID = "generalization-explicit-nested-cause"
_ONLY_OBSERVED_FAILURE = ("source root is not the outer responsible event",)


@dataclass(frozen=True, slots=True)
class OfflineReplayPaths:
    panel: Path
    contract: Path
    adjudication: Path
    v12_contract: Path
    v12_adjudication: Path
    v12_raw: Path
    v12_result: Path
    grading: GradingArtifactPaths


class OfflineReplayInvariantError(RuntimeError):
    """The sealed diagnostic no longer isolates the V13 owning boundary."""


def build_offline_replay(
    paths: OfflineReplayPaths,
) -> dict[str, object]:
    """Prove the root-only repair without modifying or rescoring V12."""

    cases = load_frozen_panel(paths.panel)
    case = next(item for item in cases if item.case_id == _CASE_ID)
    contract = load_contract(
        paths.contract,
        adjudication_path=paths.adjudication,
        v12_contract_path=paths.v12_contract,
    )
    full_focus = contract.cg_full_focus_projection
    policy = verify_v13_frozen_policy(paths.grading, cases=cases)
    frozen_case_policy = case_policy(policy, case.case_id)
    observed_output = V9StagedGeneralizationOutput.model_validate_json(
        paths.v12_raw.read_text(encoding="utf-8")
    )
    observed = evaluate_v13_case(
        case,
        observed_output,
        frozen_case_policy,
        contract,
    )
    _verify_observed_frontier(observed)

    responsible_rule = next(
        item
        for item in contract.source_lane.events
        if item.event_key == contract.source_lane.root_event_key
    )
    root_candidates = tuple(
        item.event_id
        for item in observed_output.inventory
        if item.event_type in responsible_rule.acceptable_event_types
        and item.trigger_text in responsible_rule.acceptable_triggers
    )
    if len(root_candidates) != 1:
        raise OfflineReplayInvariantError(
            "sealed V12 output lacks one adjudicated responsible event"
        )
    corrected_output = observed_output.model_copy(
        update={"root_event_id": root_candidates[0]}
    )
    corrected = evaluate_v13_case(
        case,
        corrected_output,
        frozen_case_policy,
        contract,
    )
    _verify_synthetic_correction(corrected)

    return {
        "schema_version": (
            "artana.staged_generalization.v13_v12_nested_offline_replay.v1"
        ),
        "case_id": case.case_id,
        "contract_sha256": _sha256(paths.contract),
        "adjudication_sha256": _sha256(paths.adjudication),
        "unchanged_v12_contract_sha256": _sha256(paths.v12_contract),
        "sealed_v12": {
            "terminal": "V12_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION",
            "raw_output_sha256": _sha256(paths.v12_raw),
            "result_sha256": _sha256(paths.v12_result),
            "v13_diagnostic": _json_metrics(observed),
            "source_lane_fails_only_wrong_root": True,
            "exact_cg_root_dependency_chain_failure_is_independent_of_root": True,
            "source_semantic_historical_credit": False,
            "exact_cg_root_dependency_chain_credit": False,
            "retroactive_credit": False,
            "sealed_result_changed": False,
        },
        "synthetic_forward_diagnostic": {
            "mutation": "ROOT_EVENT_ID_ONLY",
            "counterfactual_only": True,
            "root_event_id_before": observed_output.root_event_id,
            "root_event_id_after": corrected_output.root_event_id,
            "synthetic_output_sha256": _canonical_sha256(
                corrected_output.model_dump(mode="json")
            ),
            "v13_diagnostic": _json_metrics(corrected),
            "source_semantic_pass": True,
            "source_semantic_historical_credit": False,
            "exact_cg_root_dependency_chain_pass": False,
            "exact_cg_root_dependency_chain_credit": False,
            "gold_projection_synthesized": False,
            "qualification_credit": False,
        },
        "lane_separation": {
            "source_semantic_pass_implies_exact_cg_root_dependency_chain_pass": False,
            "exact_cg_root_dependency_chain_uses_artana_output_only": True,
            "gold_reference_completion_allowed": False,
            "full_focus_cg_projection_status": full_focus.measurement_status,
            "full_focus_unrepresentable_schema_types": list(
                full_focus.schema_missing_categories
            ),
            "full_focus_official_additional_event": (
                full_focus.additional_official_focus_event.model_dump(mode="json")
            ),
            "full_focus_unrepresentable_reason": full_focus.reason,
            "full_focus_cg_projection_qualification_blocking": False,
        },
        "diagnostic_only": True,
        "historical_replay_credit": False,
        "historical_result_rescored": False,
        "graph_writes": 0,
        "trusted_promotion": False,
    }


def _verify_observed_frontier(metrics: V13CaseMetrics) -> None:
    if (
        metrics.passed
        or metrics.focus_event_passed
        or metrics.source_semantic_status != "FAIL"
        or metrics.benchmark_projection_status != "FAIL"
        or metrics.benchmark_projection_scope != "EXACT_CG_ROOT_DEPENDENCY_CHAIN"
        or metrics.benchmark_projection is not None
        or metrics.full_focus_cg_status != "NOT_MEASURED_UNREPRESENTABLE"
        or metrics.root_selection_status != "FAIL"
        or not metrics.source_dimensions_except_root_passed
        or not metrics.root_only_failure
        or not metrics.mandatory_participants_passed
        or not metrics.participant_roles_passed
        or not metrics.semantic_axes_passed
        or not metrics.exact_evidence_grounding
        or metrics.unsupported_extraction_count != 0
        or metrics.failure_reasons != _ONLY_OBSERVED_FAILURE
    ):
        raise OfflineReplayInvariantError(
            "sealed V12 nested replay no longer fails only the wrong root"
        )


def _verify_synthetic_correction(metrics: V13CaseMetrics) -> None:
    if (
        not metrics.passed
        or not metrics.focus_event_passed
        or metrics.source_semantic_status != "PASS"
        or metrics.benchmark_projection_status != "FAIL"
        or metrics.benchmark_projection_scope != "EXACT_CG_ROOT_DEPENDENCY_CHAIN"
        or metrics.benchmark_projection is not None
        or metrics.full_focus_cg_status != "NOT_MEASURED_UNREPRESENTABLE"
        or metrics.root_selection_status != "PASS"
        or not metrics.source_dimensions_except_root_passed
        or metrics.root_only_failure
        or not metrics.mandatory_participants_passed
        or not metrics.participant_roles_passed
        or not metrics.semantic_axes_passed
        or not metrics.exact_evidence_grounding
        or metrics.unsupported_extraction_count != 0
        or metrics.failure_reasons
    ):
        raise OfflineReplayInvariantError(
            "root-only synthetic correction does not pass the V13 source lane"
        )


def _json_metrics(metrics: V13CaseMetrics) -> dict[str, object]:
    value: object = json.loads(json.dumps(metrics.as_json()))
    if not isinstance(value, dict):
        raise OfflineReplayInvariantError("metrics did not serialize as an object")
    return value


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "OfflineReplayInvariantError",
    "OfflineReplayPaths",
    "build_offline_replay",
]
