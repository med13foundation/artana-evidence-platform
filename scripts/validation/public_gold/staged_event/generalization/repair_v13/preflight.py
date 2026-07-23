"""Build and verify the forward-only V13 exposed-gate preregistration."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    agent_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    load_contract as load_v12_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    REPO,
    REQUEST_TIMEOUT_SECONDS,
    V13Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    load_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.dependency_manifest import (
    build_dependency_manifest,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    V12_GRADING_SOURCE_SHA256,
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.offline_replay import (
    OfflineReplayPaths,
    build_offline_replay,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.prompt_audit import (
    EXPECTED_RULE_SHA256,
    verify_prompt_audit,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider import (
    provider_format,
)

PASS_TERMINAL = "V13_EXPOSED_GATE_PASS_PENDING_INDEPENDENT_REVIEW"
ROOT_FAIL_TERMINAL = "V13_EXPOSED_GATE_FAIL_COMPOSITIONAL_ROOT"
SOURCE_FAIL_TERMINAL = "V13_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS"
UNRELATED_FAIL_TERMINAL = "V13_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V13_EXECUTION"
OPERATIONAL_BUDGET_TERMINAL = "V13_OPERATIONAL_BUDGET_STOP_INCOMPLETE"
NO_AUTHORIZATION_TERMINAL = "NO_V13_AUTHORIZED_AFTER_ADJUDICATION"
EXPECTED_BRANCH = "alvaro/tg04-source-general-claim-verification-v13"
SCIENTIFIC_HYPOTHESIS = (
    "Within a highlighted finding whose already-inventoried focus-internal event "
    "graph has exactly one event that is not the target of another focus-internal "
    "event, selecting that event as root after link construction, without changing "
    "the event, participant, or link inventory, will correct compositional root "
    "selection while preserving every previously repaired source-semantic behavior."
)

_V12_SEALED_SHA256 = {
    "preregistration": (
        "12a0b0baf6e3a7134ef340091012805e343f799f148a8f3c104cc75da17831c4"
    ),
    "result": "c110ff6eadfa41c90c19b1ff039b007b20926b2efa7ccf53ae596cc351895561",
    "report": "0aa03822d0d0211eeae793d10897d30375027781477476642e3b195961abbe55",
}
_QUALIFIED_TRANSPORT_SHA256 = (
    "241eb7db30148ccdb48640da356ad2abcd82159363594b00c01d2b3a410353fb"
)
_V12_PROVIDER_CALLS = 3
_NESTED_REVIEW_PATHS = (
    REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v13-nested-source-reviewer-a-v1.json",
    REPO / "docs/validation/reviews/"
    "2026-07-23-staged-generalization-v13-nested-source-reviewer-b-v1.json",
)
_NESTED_ADJUDICATION_REPORT = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.md"
)
_EVALUATOR_FILES = (
    "scripts/validation/public_gold/staged_event/generalization/grading/artifacts.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/grading/policy.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v12/evaluation.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v13/contracts.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v13/cg_projection.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v13/evaluation.py",
)
_FOREGROUND_RECEIPT_FILES = (
    "scripts/validation/provider_receipt_boundary/canonical_payload.py",
    "scripts/validation/provider_receipt_boundary/contracts.py",
    "scripts/validation/provider_receipt_boundary/identity.py",
    "scripts/validation/provider_receipt_boundary/operational_accounting_v2.py",
    "scripts/validation/provider_receipt_boundary/validation.py",
    "scripts/validation/provider_receipt_boundary/foreground/contracts.py",
    "scripts/validation/provider_receipt_boundary/foreground/execution.py",
    "scripts/validation/provider_receipt_boundary/foreground/validation.py",
)
_TEST_FILES = (
    "tests/unit/test_staged_generalization_v13_evaluation.py",
    "tests/unit/test_staged_generalization_v13_runtime.py",
    "tests/unit/test_staged_generalization_v13_preflight.py",
    "tests/unit/test_staged_generalization_v13_provider_custody.py",
    "tests/unit/test_staged_generalization_v13_frozen_panel.py",
    "tests/unit/test_staged_generalization_v13_dependency_manifest.py",
    "tests/unit/test_staged_generalization_v8.py",
    "tests/unit/test_staged_generalization_v10_exposed.py",
    "tests/unit/test_staged_generalization_v11_exposed.py",
    "tests/unit/test_staged_generalization_v11_run2.py",
    "tests/unit/test_staged_generalization_v12.py",
    "tests/unit/test_occurrence_evaluator_v2.py",
)
_TRANSITIVE_EXECUTION_FILES = (
    "scripts/validation/public_gold/staged_event/context_experiment/"
    "source_first/attempts.py",
    "scripts/validation/public_gold/staged_event/context_experiment/"
    "source_first/custody.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
    "execution_config.py",
    "scripts/validation/public_gold/staged_event/generalization/repair_v9/contracts.py",
)
_PANEL_TRACKED_CORPUS_FILES = (
    "scripts/validation/source_general_claim_verification/fixtures/"
    "exposed_31_scope_corpus.json",
)
_PANEL_CUSTODY_SCHEMA = "artana.staged_generalization.v13_panel_source_custody.v1"
_SERVICE_MODULE_PREFIX = "artana_evidence_api"
_SERVICE_SOURCE_ROOT = REPO / "services/artana_evidence_api"
_REQUIRED_SERVICE_IMPORT_MODULES = (
    "artana_evidence_api",
    "artana_evidence_api.document_extraction_support",
    "artana_evidence_api.document_extraction_support.claim_frames",
    "artana_evidence_api.document_extraction_support.claim_frames.event_types",
    "artana_evidence_api.document_extraction_support.scientific_events",
    "artana_evidence_api.document_extraction_support.scientific_events.contracts",
    "artana_evidence_api.document_extraction_support.scientific_events.validation",
)
_PANEL_CG_RECOVERY_BASE = (
    "https://raw.githubusercontent.com/openbiocorpora/"
    "bionlp-st-2013-cg/master/original-data/devel/"
)
_PANEL_EXTERNAL_SHA256 = {
    "PMID-21965773.txt": (
        "0bba2db9971b512abac2bf0a0c40627432b9f63fc8f090cc4d3590b08df52880"
    ),
    "PMID-21965773.a1": (
        "d6f0d526567bfc689d7d4c6ea63e9ba0345ee29b83126edf58f9e317fb624ebe"
    ),
    "PMID-21965773.a2": (
        "e554de689b08b2b4db29cae32893459eef6ffe0b11860cfa8f7313584537b0e8"
    ),
    "PMID-7966592.txt": (
        "cef4eed850665c8e55e5e8deccdef2fa92a05377ffb9bf5666a85b6320192f02"
    ),
    "PMID-7966592.a1": (
        "2e47b1725178510245a711cb28749271730df2502e84035d2364e6b663230864"
    ),
    "PMID-7966592.a2": (
        "8921ae260cb96c14867089bd02e12cf614416aacd442d9bed7145db089ec445c"
    ),
}
_RUNTIME_DEPENDENCY_ROOTS = ("scripts/run_staged_generalization_v13_exposed.py",)
_FORBIDDEN_AGENT_INPUT_TERMS = (
    '"reference"',
    "acceptable_texts",
    "expected participant",
    "direct CG",
    "Fresh-CG V2",
    "V3 corrected reference",
    "grader policy",
    "osteonectin",
)
_REMOTE_REF_FIELD_COUNT = 2


class V13PreflightError(RuntimeError):
    """V13 differs from its independently reviewed preregistration."""


def ordered_cases(
    paths: V13Paths = DEFAULT_PATHS,
) -> tuple[GeneralizationCase, ...]:
    """Return the frozen exposed panel in fail-fast execution order."""

    cases = load_frozen_panel(paths.panel)
    by_id = {case.case_id: case for case in cases}
    if set(by_id) != set(CASE_ORDER):
        raise V13PreflightError("V13 panel membership changed")
    return tuple(by_id[case_id] for case_id in CASE_ORDER)


def provider_input(
    case_id: str,
    paths: V13Paths = DEFAULT_PATHS,
) -> str:
    """Compose V11 + V12 + the sole V13 rule + one frozen exposed case."""

    case = next(
        (item for item in ordered_cases(paths) if item.case_id == case_id),
        None,
    )
    if case is None:
        raise V13PreflightError(f"unknown exposed case: {case_id}")
    verify_prompt_audit(
        rule_path=paths.root_rule,
        audit_path=paths.root_rule_audit,
        adjudication_path=paths.nested_adjudication,
        panel_path=paths.panel,
    )
    value = (
        paths.v11_prompt.read_text(encoding="utf-8")
        + "\n\n--- V12 PRESERVED SCIENTIFIC CHANGE ---\n"
        + paths.v12_focus_rule.read_text(encoding="utf-8")
        + "--- END V12 PRESERVED SCIENTIFIC CHANGE ---\n"
        + "\n--- V13 SINGLE SCIENTIFIC CHANGE ---\n"
        + paths.root_rule.read_text(encoding="utf-8")
        + "--- END V13 SINGLE SCIENTIFIC CHANGE ---\n"
        + "\n--- FROZEN EXPOSED CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN EXPOSED CASE ---\n"
    )
    present = [term for term in _FORBIDDEN_AGENT_INPUT_TERMS if term in value]
    if present:
        raise V13PreflightError(
            f"V13 provider input exposes forbidden material: {present}"
        )
    return value


def build_preregistration(
    paths: V13Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Recompute every V13 scientific, execution, and custody binding."""

    _verify_inputs(paths)
    cases = ordered_cases(paths)
    policy = verify_v13_frozen_policy(paths.grading, cases=cases)
    qualification = _object(
        json.loads(paths.qualified_transport_result.read_text(encoding="utf-8"))
    )
    if qualification.get("decision") != "FOREGROUND_TRANSPORT_QUALIFIED":
        raise V13PreflightError("direct foreground transport is not qualified")

    adjudication = _object(
        json.loads(paths.nested_adjudication.read_text(encoding="utf-8"))
    )
    frozen_adjudication_inputs = _object(adjudication.get("frozen_inputs"))
    nested_contract = load_contract(
        paths.nested_two_lane_contract,
        adjudication_path=paths.nested_adjudication,
        v12_contract_path=paths.v12_drug_two_lane_contract,
    )
    full_focus = nested_contract.cg_full_focus_projection
    panel_custody = _verify_panel_source_custody(paths)
    provider_format_value = provider_format()
    runtime_dependencies = _runtime_dependency_hashes()
    _verify_service_import_origins(runtime_dependencies)
    return {
        "schema_version": "artana.staged_generalization.v13_exposed_gate.v1",
        "experiment_id": EXPERIMENT_ID,
        "authorization": "PREREGISTERED_V13_EXPOSED_CASES_ONLY",
        "qualification_credit": False,
        "root_cause_classification": ("COMPOSITIONAL_FOCUS_ROOT_AMBIGUITY"),
        "single_scientific_change": ("COMPOSITIONAL_FOCUS_ROOT_SELECTION"),
        "scientific_hypothesis": SCIENTIFIC_HYPOTHESIS,
        "frozen_state": {
            "case_order": list(CASE_ORDER),
            "panel_sha256": _sha256(paths.panel),
            "panel_canonical_sha256": _canonical_sha256(
                json.loads(paths.panel.read_text(encoding="utf-8"))
            ),
            "panel_runtime_source": panel_custody["runtime_source"],
            "panel_source_custody_sha256": _sha256(paths.panel_source_custody),
            "panel_generator_attestation": panel_custody["generator_attestation"],
            "panel_external_source_sha256": _panel_external_hashes(panel_custody),
            "panel_tracked_corpus_sha256": _hash_files(_PANEL_TRACKED_CORPUS_FILES),
            "v11_prompt_sha256": _sha256(paths.v11_prompt),
            "v12_focus_rule_sha256": _sha256(paths.v12_focus_rule),
            "v13_root_rule_sha256": _sha256(paths.root_rule),
            "v13_root_rule_expected_sha256": EXPECTED_RULE_SHA256,
            "root_rule_audit_sha256": _sha256(paths.root_rule_audit),
            "wording_review_sha256": {
                "reviewer_a": _sha256(paths.wording_review_a),
                "reviewer_b": _sha256(paths.wording_review_b),
            },
            "nested_source_review_sha256": {
                "reviewer_a": _sha256(_NESTED_REVIEW_PATHS[0]),
                "reviewer_b": _sha256(_NESTED_REVIEW_PATHS[1]),
            },
            "nested_source_review_adjudicated_sha256": {
                "reviewer_a": frozen_adjudication_inputs.get("reviewer_a_sha256"),
                "reviewer_b": frozen_adjudication_inputs.get("reviewer_b_sha256"),
            },
            "nested_adjudication_sha256": _sha256(paths.nested_adjudication),
            "nested_adjudication_report_sha256": _sha256(_NESTED_ADJUDICATION_REPORT),
            "nested_two_lane_contract_sha256": _sha256(paths.nested_two_lane_contract),
            "v12_drug_adjudication_sha256": _sha256(paths.v12_drug_adjudication),
            "v12_drug_two_lane_contract_sha256": _sha256(
                paths.v12_drug_two_lane_contract
            ),
            "offline_replay_sha256": _sha256(paths.offline_replay),
            "sealed_v12_nested_raw_sha256": _sha256(paths.v12_nested_raw),
            "sealed_v12_drug_raw_sha256": _sha256(paths.v12_drug_raw),
            "source_sha256_by_case": {
                case.case_id: case.source_sha256 for case in cases
            },
            "provider_input_sha256_by_case": {
                case.case_id: hashlib.sha256(
                    provider_input(case.case_id, paths).encode()
                ).hexdigest()
                for case in cases
            },
            "schema_sha256": _canonical_sha256(
                V9StagedGeneralizationOutput.model_json_schema()
            ),
            "schema_basis": "UNCHANGED_V9_V11_V12",
            "root_schema_resolution": (
                "EXPOSED_NON_COMPLETE_TRANSPORT_ANCHOR_EARLIEST_"
                "SOURCE_SUPPORTED_FOCUS_EVENT"
            ),
            "upstream_provider_eligibility_by_case": _eligibility_proof(cases),
            "provider_format_sha256": _canonical_sha256(provider_format_value),
            "grading_policy_sha256": policy_sha256(policy),
            "shared_frozen_grader_source_sha256": V12_GRADING_SOURCE_SHA256,
            "grader_relaxed": False,
            "frozen_grader_changed": False,
            "evaluation_contract": {
                "qualification_lane": "SOURCE_SEMANTIC",
                "exact_cg_root_dependency_chain_lane": (
                    "REVIEW_ONLY_NONBLOCKING_ARTANA_OUTPUT_ONLY"
                ),
                "cg_root_dependency_chain_qualification_credit": False,
                "source_pass_implies_exact_cg_root_dependency_chain_pass": False,
                "gold_projection_completion_allowed": False,
                "full_focus_cg_projection_status": full_focus.measurement_status,
                "full_focus_unrepresentable_schema_types": list(
                    full_focus.schema_missing_categories
                ),
                "full_focus_official_additional_event_sha256": (
                    _canonical_sha256(
                        full_focus.additional_official_focus_event.model_dump(
                            mode="json"
                        )
                    )
                ),
                "full_focus_unrepresentable_reason": full_focus.reason,
                "full_focus_cg_projection_qualification_blocking": False,
                "unchanged_frozen_grader_cases": [
                    "generalization-comparison-canary",
                    "generalization-uncertainty",
                    "generalization-negated-association",
                    "generalization-null-statistics",
                ],
                "drug_policy": nested_contract.drug_case_policy,
                "implementation_sha256": _hash_files(_EVALUATOR_FILES),
            },
            "execution_implementation_sha256": _hash_files(
                (*_implementation_files(), *_TRANSITIVE_EXECUTION_FILES)
            ),
            "runtime_dependency_root_files": list(_RUNTIME_DEPENDENCY_ROOTS),
            "runtime_dependency_manifest_sha256": runtime_dependencies,
            "service_import_origin_policy": (
                "CURRENT_REPOSITORY_HASHED_SERVICE_MODULES_ONLY"
            ),
            "service_import_required_modules": list(_REQUIRED_SERVICE_IMPORT_MODULES),
            "loaded_service_modules_must_be_manifest_subset": True,
            "transitive_execution_dependency_sha256": _hash_files(
                _TRANSITIVE_EXECUTION_FILES
            ),
            "receipt_implementation_sha256": _hash_files(_FOREGROUND_RECEIPT_FILES),
            "frozen_test_sha256": _hash_files(_TEST_FILES),
        },
        "sealed_history": {
            "v12_terminal": "V12_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION",
            "v12_sha256": _V12_SEALED_SHA256,
            "historical_replay_diagnostic_only": True,
            "historical_replay_credit": False,
            "historical_results_rescored": False,
            "v12_result_changed": False,
        },
        "provider": {
            "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
            "transport_qualification_sha256": _sha256(paths.qualified_transport_result),
            "transport_qualification_reused": True,
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "background": False,
            "store": True,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "application_max_output_tokens": None,
            "application_max_total_tokens": None,
            "provider_retries": 0,
            "fallback": False,
            "exactly_one_creation_per_case": True,
            "stable_response_id_custody": True,
            "confirmation_retrieval_required": True,
            "input_item_retrieval_required": True,
            "rejected_attempt_custody_required": True,
            "rejected_attempt_available_evidence_retained": [
                "response_ids",
                "creation_response",
                "confirmation_response",
                "input_items",
                "canonical_payload",
                "usage",
                "latency_seconds",
            ],
            "rejected_attempt_exclusive_persistence": True,
            "rejected_attempt_unknown_usage_recorded_as_unknown": True,
            "cross_case_response_id_reuse_invalid": True,
            "packet_blinding": {
                "blind": False,
                "descriptive_exposed_case_ids_visible": True,
                "scope": "EXPOSED_DEVELOPMENT_ONLY",
                "carry_packets_into_fresh_validation": False,
            },
        },
        "schema_scope": {
            "all_exposed_focuses_require_upstream_eligibility": True,
            "minimum_explicit_source_supported_focus_events": 1,
            "non_complete_root_event_id_semantics": (
                "TRANSPORT_ANCHOR_ONLY_NOT_ASSERTED_SCIENTIFIC_ROOT"
            ),
            "non_complete_transport_anchor_selection": (
                "EARLIEST_SOURCE_SUPPORTED_FOCUS_INTERNAL_EVENT_IN_SOURCE_ORDER"
            ),
            "inventory_or_links_may_change_to_create_anchor": False,
            "eventless_abstention_supported": False,
            "residual_limitation": (
                "UNIVERSAL_V9_SCHEMA_CANNOT_REPRESENT_TRULY_EVENTLESS_ABSTENTION"
            ),
            "v13_claims_to_resolve_eventless_abstention": False,
        },
        "operational_budget": {
            "cumulative_max_cost_usd": GLOBAL_MAX_COST_USD,
            "maximum_creation_calls": GLOBAL_MAX_CALLS,
            "v13_starting_cost_usd": 0.0,
            "prior_transport_qualification_cost_included": False,
            "check_before_each_creation": True,
            "record_actual_usage_latency_and_cost_after_each_call": True,
            "rejected_calls_count_toward_creation_budget": True,
            "rejected_call_cost_recorded_when_available": True,
            "unaccounted_rejected_call_stops_before_next_creation": True,
            "stop_before_next_call_when_exhausted": True,
            "telemetry_affects_scientific_scoring": False,
            "valid_case_results_preserved_after_budget_stop": True,
        },
        "acceptance": {
            "all_six_source_semantic_cases_pass": True,
            "exposed_source_semantic_gate_complete_on_pass": True,
            "fresh_qualification_status_on_pass": "PENDING_INDEPENDENT_REVIEW",
            "fresh_qualification_complete_on_pass": False,
            "all_previously_repaired_behaviors_stable": True,
            "compositional_focus_root_pass": True,
            "nested_dependency_closure_pass": True,
            "drug_source_semantic_lane_pass": True,
            "drug_exact_cg_projection_measured_separately": True,
            "nested_exact_cg_root_dependency_chain_measured_separately": True,
            "nested_full_focus_cg_projection_measured": False,
            "nested_full_focus_cg_projection_status": ("NOT_MEASURED_UNREPRESENTABLE"),
            "cg_root_dependency_chain_is_qualification_blocking": False,
            "nested_cg_root_dependency_chain_pass_required": False,
            "source_lane_pass_can_coexist_with_cg_root_dependency_chain_fail": True,
            "gold_projection_completion_allowed": False,
            "root_or_abstain_schema_fallback_added": False,
            "non_complete_transport_anchor_is_scientific_root": False,
            "eventless_abstention_limitation_disclosed": True,
            "comparison_uncertainty_negated_null_use_unchanged_frozen_grader": True,
            "drug_v12_metrics_reused_with_source_lane_authoritative": True,
            "drug_cg_projection_is_qualification_blocking": False,
            "all_receipts_valid": True,
            "provider_retries": 0,
            "duplicate_creation_calls": 0,
        },
        "stopping_rules": {
            "sequential_fail_fast": True,
            "first_real_source_scientific_failure": True,
            "invalid_schema_custody_or_exactly_once": True,
            "operational_budget_exhaustion": True,
            "provider_outage_or_missing_secret": True,
        },
        "terminal_decisions": [
            PASS_TERMINAL,
            ROOT_FAIL_TERMINAL,
            SOURCE_FAIL_TERMINAL,
            UNRELATED_FAIL_TERMINAL,
            OPERATIONAL_BUDGET_TERMINAL,
            INVALID_TERMINAL,
            NO_AUTHORIZATION_TERMINAL,
        ],
        "rules": {
            "exposed_cases_only": True,
            "fresh_case_calls_allowed": False,
            "fresh_cases_consumed": 0,
            "automatic_fresh_draft_after_pass": False,
            "fresh_draft_requires_separate_explicit_action": True,
            "exposed_packets_may_be_reused_for_fresh": False,
            "remote_head_must_match_pushed_branch_before_first_call": True,
            "expected_execution_branch": EXPECTED_BRANCH,
            "tracked_worktree_must_be_clean_before_first_call": True,
            "required_frozen_paths_must_be_tracked": True,
            "execution_output_paths_must_be_absent": True,
            "unrelated_untracked_paths_preserved_and_reported": True,
            "graph_writes": False,
            "trusted_graph_promotion": False,
        },
    }


def write_candidate(paths: V13Paths = DEFAULT_PATHS) -> None:
    """Write the replay first, then the preregistration that binds it."""

    verify_output_path_custody(paths)
    present = [
        _repo_relative(path) for path in _all_output_paths(paths) if path.exists()
    ]
    if present:
        raise V13PreflightError(
            f"V13 candidate or execution output already exists: {present}"
        )
    replay = build_offline_replay(_replay_paths(paths))
    write_json_atomic(paths.offline_replay, replay)
    write_json_atomic(paths.preregistration, build_preregistration(paths))


def verify(
    paths: V13Paths = DEFAULT_PATHS,
    *,
    remote_gate: bool = False,
) -> dict[str, object]:
    """Rebuild the preregistration and optionally prove the pushed HEAD."""

    loaded = _object(json.loads(paths.preregistration.read_text(encoding="utf-8")))
    if loaded != build_preregistration(paths):
        raise V13PreflightError("V13 preregistration differs from frozen state")
    if remote_gate:
        observation = verify_remote_execution_state(paths)
        return {**loaded, "remote_gate_observation": observation}
    return loaded


def _verify_inputs(paths: V13Paths) -> None:
    verify_output_path_custody(paths)
    _verify_panel_source_custody(paths)
    verify_prompt_audit(
        rule_path=paths.root_rule,
        audit_path=paths.root_rule_audit,
        adjudication_path=paths.nested_adjudication,
        panel_path=paths.panel,
    )
    _verify_wording_review(
        paths.wording_review_a,
        paths,
        expected_reviewer="v13_rule_reviewer_a",
    )
    _verify_wording_review(
        paths.wording_review_b,
        paths,
        expected_reviewer="v13_rule_reviewer_b",
    )
    contract = load_contract(
        paths.nested_two_lane_contract,
        adjudication_path=paths.nested_adjudication,
        v12_contract_path=paths.v12_drug_two_lane_contract,
    )
    load_v12_contract(
        paths.v12_drug_two_lane_contract,
        adjudication_path=paths.v12_drug_adjudication,
    )
    if contract.cg_root_dependency_chain.qualification_blocking:
        raise V13PreflightError(
            "nested CG root dependency chain became qualification-blocking"
        )
    if contract.cg_root_dependency_chain.qualification_credit:
        raise V13PreflightError(
            "nested CG root dependency chain gained qualification credit"
        )
    if (
        contract.cg_full_focus_projection.measurement_status
        != "NOT_MEASURED_UNREPRESENTABLE"
        or contract.cg_full_focus_projection.qualification_blocking
        or contract.cg_full_focus_projection.qualification_credit
    ):
        raise V13PreflightError("nested full-focus CG scope changed")
    if contract.drug_case_policy != (
        "V12_DRUG_METRICS_REUSED_SOURCE_LANE_AUTHORITATIVE_CG_NONBLOCKING"
    ):
        raise V13PreflightError("V13 drug evaluation policy changed")
    if contract.other_exposed_cases_policy != "UNCHANGED_FROZEN_GRADER":
        raise V13PreflightError("V13 non-drug exposed grader policy changed")
    if contract.graph_promotion_allowed:
        raise V13PreflightError("V13 contract permits graph promotion")

    expected_replay = build_offline_replay(_replay_paths(paths))
    observed_replay = _object(
        json.loads(paths.offline_replay.read_text(encoding="utf-8"))
    )
    if observed_replay != _json_value(expected_replay):
        raise V13PreflightError("sealed V12 diagnostic replay changed")
    _verify_nested_review_custody(paths)

    historical = {
        "preregistration": _sha256(paths.v12_preregistration),
        "result": _sha256(paths.v12_result),
        "report": _sha256(paths.v12_report),
    }
    if historical != _V12_SEALED_SHA256:
        raise V13PreflightError("sealed V12 artifacts changed")
    sealed_result = _object(json.loads(paths.v12_result.read_text(encoding="utf-8")))
    if (
        sealed_result.get("decision") != "V12_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
        or sealed_result.get("provider_calls") != _V12_PROVIDER_CALLS
        or sealed_result.get("provider_retries") != 0
        or sealed_result.get("duplicate_creation_calls") != 0
        or sealed_result.get("graph_writes") != 0
    ):
        raise V13PreflightError("sealed V12 disposition changed")
    if _sha256(paths.qualified_transport_result) != _QUALIFIED_TRANSPORT_SHA256:
        raise V13PreflightError("qualified foreground transport artifact changed")


def _verify_wording_review(
    path: Path,
    paths: V13Paths,
    *,
    expected_reviewer: str,
) -> None:
    review = _object(json.loads(path.read_text(encoding="utf-8")))
    required_pass_fields = (
        "single_change_scope",
        "source_generality",
        "leakage",
        "focus_internal_scope",
        "nested_correctness",
        "schema_compatibility",
        "projection_separation",
        "transport_clarification",
        "exposed_event_eligibility",
        "residual_limitation_disclosure",
    )
    if (
        review.get("verdict") != "PASS"
        or review.get("reviewer_id") != expected_reviewer
        or review.get("rule_sha256") != _sha256(paths.root_rule)
        or review.get("audit_sha256") != _sha256(paths.root_rule_audit)
        or review.get("non_complete_root_credit") != "NOT_APPLICABLE"
        or any(review.get(field) != "PASS" for field in required_pass_fields)
    ):
        raise V13PreflightError(f"wording review failed: {path.name}")
    safety = review.get("case_safety")
    if not isinstance(safety, dict) or set(safety) != set(CASE_ORDER):
        raise V13PreflightError("wording review case coverage changed")
    if set(safety.values()) != {"PASS"}:
        raise V13PreflightError("wording review has a case safety failure")


def _verify_panel_source_custody(
    paths: V13Paths,
) -> dict[str, object]:
    custody = _object(
        json.loads(paths.panel_source_custody.read_text(encoding="utf-8"))
    )
    expected_tracked = [
        {
            "path": _PANEL_TRACKED_CORPUS_FILES[0],
            "sha256": _sha256(REPO / _PANEL_TRACKED_CORPUS_FILES[0]),
            "used_by_build_panel": True,
        }
    ]
    expected_external = [
        _expected_external_panel_input(filename)
        for filename in (
            "PMID-21965773.txt",
            "PMID-21965773.a1",
            "PMID-21965773.a2",
            "PMID-7966592.txt",
            "PMID-7966592.a1",
            "PMID-7966592.a2",
        )
    ]
    expected: dict[str, object] = {
        "schema_version": _PANEL_CUSTODY_SCHEMA,
        "runtime_source": "TRACKED_FROZEN_PANEL",
        "untracked_validation_tree_runtime_dependency": False,
        "frozen_panel_path": _repo_relative(paths.panel),
        "generator_attestation": {
            "canonical_json_normalization": True,
            "generated_panel_matches_frozen": True,
            "generator_path": (
                "scripts/validation/public_gold/staged_event/generalization/panel.py"
            ),
            "verified_at": "2026-07-23",
        },
        "tracked_inputs": expected_tracked,
        "external_inputs": expected_external,
    }
    if custody != expected:
        raise V13PreflightError("V13 panel source custody manifest changed")
    return custody


def _expected_external_panel_input(filename: str) -> dict[str, object]:
    document_id, suffix = filename.rsplit(".", maxsplit=1)
    artifact_kind = {
        "txt": "SOURCE_TEXT",
        "a1": "ENTITY_ANNOTATIONS",
        "a2": "EVENT_ANNOTATIONS",
    }[suffix]
    return {
        "artifact_kind": artifact_kind,
        "document_id": document_id,
        "historical_local_path": (
            "validation/public_gold/bionlp_cg/raw/"
            "bionlp-st-2013-cg-master/original-data/devel/"
            f"{filename}"
        ),
        "recovery_url": f"{_PANEL_CG_RECOVERY_BASE}{filename}",
        "sha256": _PANEL_EXTERNAL_SHA256[filename],
        "used_by_build_panel": suffix == "txt",
    }


def _panel_external_hashes(
    custody: dict[str, object],
) -> dict[str, object]:
    external = custody.get("external_inputs")
    if not isinstance(external, list):
        raise V13PreflightError("panel source custody external inputs are absent")
    result: dict[str, object] = {}
    for value in external:
        item = _object(value)
        path = item.get("historical_local_path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise V13PreflightError("panel source custody input is malformed")
        result[path] = digest
    return result


def _verify_nested_review_custody(paths: V13Paths) -> None:
    adjudication = _object(
        json.loads(paths.nested_adjudication.read_text(encoding="utf-8"))
    )
    frozen = _object(adjudication.get("frozen_inputs"))
    expected = (
        frozen.get("reviewer_a_sha256"),
        frozen.get("reviewer_b_sha256"),
    )
    observed = tuple(_sha256(path) for path in _NESTED_REVIEW_PATHS)
    if expected != observed:
        raise V13PreflightError("nested source reviewer custody changed")
    for path in _NESTED_REVIEW_PATHS:
        review = _object(json.loads(path.read_text(encoding="utf-8")))
        if (
            review.get("verdict") != "V13_SOURCE_GENERAL_REPAIR_SUPPORTED"
            or review.get("case_id") != "generalization-explicit-nested-cause"
        ):
            raise V13PreflightError(
                f"nested source review no longer supports V13: {path.name}"
            )


def _replay_paths(paths: V13Paths) -> OfflineReplayPaths:
    return OfflineReplayPaths(
        panel=paths.panel,
        contract=paths.nested_two_lane_contract,
        adjudication=paths.nested_adjudication,
        v12_contract=paths.v12_drug_two_lane_contract,
        v12_adjudication=paths.v12_drug_adjudication,
        v12_raw=paths.v12_nested_raw,
        v12_result=paths.v12_result,
        grading=paths.grading,
    )


def _eligibility_proof(
    cases: tuple[GeneralizationCase, ...],
) -> dict[str, dict[str, object]]:
    proof: dict[str, dict[str, object]] = {}
    for case in cases:
        has_literal_event = any(
            trigger in case.focus_passage
            for event in case.reference.events
            for trigger in event.acceptable_triggers
        )
        if not case.focus_passage or not has_literal_event:
            raise V13PreflightError(
                f"exposed focus lacks an explicit supported event: {case.case_id}"
            )
        proof[case.case_id] = {
            "upstream_eligible": True,
            "explicit_source_supported_focus_event_minimum_met": True,
            "focus_passage_sha256": hashlib.sha256(
                case.focus_passage.encode()
            ).hexdigest(),
            "proof_basis": "FROZEN_EXPOSED_FOCUS_LITERAL_EVENT_TRIGGER",
        }
    return proof


def verify_output_path_custody(paths: V13Paths = DEFAULT_PATHS) -> None:
    """Prove every V13 output is repo-local, unique, and not historical."""

    outputs = _all_output_paths(paths)
    relatives = tuple(_repo_relative(path) for path in outputs)
    if len(set(relatives)) != len(relatives):
        raise V13PreflightError("V13 output paths are not unique")
    historical = {_repo_relative(path) for path in _historical_input_paths(paths)}
    overlap = sorted(set(relatives) & historical)
    if overlap:
        raise V13PreflightError(
            f"V13 output path overlaps frozen historical input: {overlap}"
        )


def verify_remote_execution_state(
    paths: V13Paths = DEFAULT_PATHS,
) -> dict[str, object]:
    """Verify the pushed branch while preserving unrelated untracked files."""

    verify_output_path_custody(paths)
    branch = _git("branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise V13PreflightError(
            f"V13 execution requires branch {EXPECTED_BRANCH}, got {branch}"
        )
    local = _git("rev-parse", "HEAD")
    remote = _git("ls-remote", "--heads", "origin", branch).split()
    if len(remote) != _REMOTE_REF_FIELD_COUNT or remote[0] != local:
        raise V13PreflightError("local and remote heads differ before V13 execution")
    tracked = _git("status", "--porcelain=v1", "--untracked-files=no")
    if tracked:
        raise V13PreflightError("tracked worktree changes exist before V13 execution")
    present = [
        _repo_relative(path) for path in _execution_output_paths(paths) if path.exists()
    ]
    if present:
        raise V13PreflightError(f"V13 execution output already exists: {present}")
    for path in _required_tracked_paths(paths):
        relative = _repo_relative(path)
        tracked_path = _git(
            "ls-files",
            "--error-unmatch",
            "--",
            relative,
        )
        if tracked_path != relative:
            raise V13PreflightError(
                f"V13 frozen path is not tracked at pushed HEAD: {relative}"
            )
    status = _git("status", "--porcelain=v1", "--untracked-files=all")
    unexpected = [
        line for line in status.splitlines() if line and not line.startswith("?? ")
    ]
    if unexpected:
        raise V13PreflightError("tracked worktree changed during V13 remote gate")
    untracked = [line[3:] for line in status.splitlines() if line.startswith("?? ")]
    return {
        "branch": branch,
        "local_head": local,
        "remote_head": remote[0],
        "tracked_modification_count": 0,
        "execution_outputs_absent": True,
        "untracked_paths_preserved": untracked,
        "untracked_path_count": len(untracked),
    }


def _all_output_paths(paths: V13Paths) -> tuple[Path, ...]:
    return (
        paths.preregistration,
        paths.offline_replay,
        *_execution_output_paths(paths),
    )


def _execution_output_paths(paths: V13Paths) -> tuple[Path, ...]:
    case_outputs: list[Path] = []
    for case_id in CASE_ORDER:
        item = paths.case(case_id)
        case_outputs.extend(
            (
                item.attempt,
                item.bundle,
                item.receipt,
                item.raw_output,
                item.evaluation,
            )
        )
    return (
        paths.result,
        paths.report,
        paths.next_fresh_preregistration,
        *case_outputs,
    )


def _historical_input_paths(paths: V13Paths) -> tuple[Path, ...]:
    grading = paths.grading
    return (
        paths.panel,
        paths.panel_source_custody,
        paths.v11_prompt,
        paths.v12_focus_rule,
        paths.root_rule,
        paths.root_rule_audit,
        paths.wording_review_a,
        paths.wording_review_b,
        paths.nested_adjudication,
        _NESTED_ADJUDICATION_REPORT,
        paths.nested_two_lane_contract,
        paths.v12_drug_adjudication,
        paths.v12_drug_two_lane_contract,
        paths.v12_preregistration,
        paths.v12_result,
        paths.v12_report,
        paths.v12_nested_raw,
        paths.v12_drug_raw,
        paths.qualified_transport_result,
        *_NESTED_REVIEW_PATHS,
        grading.packet,
        grading.evidence,
        grading.schema,
        grading.first_review,
        grading.second_review,
        grading.tiebreaker_review,
        grading.policy,
    )


def _required_tracked_paths(paths: V13Paths) -> tuple[Path, ...]:
    names = {
        *_implementation_files(),
        *_TRANSITIVE_EXECUTION_FILES,
        *_EVALUATOR_FILES,
        *_FOREGROUND_RECEIPT_FILES,
        *_TEST_FILES,
        *_PANEL_TRACKED_CORPUS_FILES,
        *_runtime_dependency_hashes(),
    }
    path_values = {
        *_historical_input_paths(paths),
        paths.preregistration,
        paths.offline_replay,
        *(REPO / name for name in names),
    }
    return tuple(sorted(path_values))


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError as exc:
        raise V13PreflightError(f"V13 path escapes repository custody: {path}") from exc


def _git(*arguments: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local Git executable.
        ["git", *arguments],  # noqa: S607
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise V13PreflightError(completed.stderr.strip())
    return completed.stdout.strip()


def _implementation_files() -> tuple[str, ...]:
    package = (
        REPO / "scripts/validation/public_gold/staged_event/generalization/repair_v13"
    )
    files = tuple(
        sorted(path.relative_to(REPO).as_posix() for path in package.glob("*.py"))
    )
    run_script = "scripts/run_staged_generalization_v13_exposed.py"
    if not (REPO / run_script).is_file():
        raise V13PreflightError("V13 run script is absent")
    return (run_script, *files)


def _hash_files(names: tuple[str, ...]) -> dict[str, str]:
    return {name: _sha256(REPO / name) for name in names}


def _runtime_dependency_hashes() -> dict[str, str]:
    return {
        entry.path: entry.sha256
        for entry in build_dependency_manifest(REPO, _RUNTIME_DEPENDENCY_ROOTS)
    }


def _verify_service_import_origins(
    runtime_dependencies: dict[str, str],
) -> None:
    """Bind loaded Evidence API modules to this repository and frozen bytes."""

    missing = [
        name for name in _REQUIRED_SERVICE_IMPORT_MODULES if name not in sys.modules
    ]
    if missing:
        raise V13PreflightError(
            f"required Evidence API service modules are not loaded: {missing}"
        )

    repository_root = REPO.resolve(strict=True)
    service_root = _SERVICE_SOURCE_ROOT.resolve(strict=True)
    loaded_count = 0
    for name, module in sorted(sys.modules.items()):
        if name != _SERVICE_MODULE_PREFIX and not name.startswith(
            f"{_SERVICE_MODULE_PREFIX}."
        ):
            continue
        origin = getattr(module, "__file__", None)
        if not isinstance(origin, str):
            raise V13PreflightError(
                f"loaded Evidence API service module has no source origin: {name}"
            )
        try:
            source = Path(origin).resolve(strict=True)
            source.relative_to(service_root)
            relative = source.relative_to(repository_root).as_posix()
        except (OSError, ValueError) as exc:
            raise V13PreflightError(
                "loaded Evidence API service module is outside the current "
                f"repository services tree: {name} ({origin})"
            ) from exc
        expected_sha256 = runtime_dependencies.get(relative)
        if expected_sha256 is None:
            raise V13PreflightError(
                "loaded Evidence API service module is absent from the frozen "
                f"runtime dependency manifest: {relative}"
            )
        if _sha256(source) != expected_sha256:
            raise V13PreflightError(
                "loaded Evidence API service module differs from the frozen "
                f"runtime dependency manifest: {relative}"
            )
        loaded_count += 1
    if loaded_count < len(_REQUIRED_SERVICE_IMPORT_MODULES):
        raise V13PreflightError(
            "loaded Evidence API service module set is unexpectedly incomplete"
        )


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _json_value(value: object) -> object:
    return json.loads(json.dumps(value))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise V13PreflightError("expected JSON object")
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "EXPECTED_BRANCH",
    "INVALID_TERMINAL",
    "NO_AUTHORIZATION_TERMINAL",
    "OPERATIONAL_BUDGET_TERMINAL",
    "PASS_TERMINAL",
    "ROOT_FAIL_TERMINAL",
    "SCIENTIFIC_HYPOTHESIS",
    "SOURCE_FAIL_TERMINAL",
    "UNRELATED_FAIL_TERMINAL",
    "V13PreflightError",
    "build_preregistration",
    "ordered_cases",
    "provider_input",
    "verify",
    "verify_output_path_custody",
    "verify_remote_execution_state",
    "write_candidate",
]
