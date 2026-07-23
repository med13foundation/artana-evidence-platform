"""V13 prompt custody, sealed replay, and preregistration regressions."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from scripts.validation.public_gold.staged_event.generalization import (
    panel as generated_panel,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13 import (
    preflight as v13_preflight,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    CASE_ORDER,
    DEFAULT_PATHS,
    REPO,
    V13Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    build_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    V12_GRADING_POLICY_SHA256,
    V12_GRADING_SOURCE_SHA256,
    verify_shared_grader_sources,
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.offline_replay import (
    OfflineReplayPaths,
    build_offline_replay,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.preflight import (
    EXPECTED_BRANCH,
    OPERATIONAL_BUDGET_TERMINAL,
    PASS_TERMINAL,
    SCIENTIFIC_HYPOTHESIS,
    V13PreflightError,
    build_preregistration,
    provider_input,
    verify_output_path_custody,
    verify_remote_execution_state,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.prompt_audit import (
    EXPECTED_RULE,
    EXPECTED_RULE_SHA256,
    verify_prompt_audit,
)

_OBJECT = TypeAdapter(dict[str, object])
_OBJECT_LIST = TypeAdapter(list[dict[str, object]])
_STRING_LIST = TypeAdapter(list[str])


def test_v13_rule_is_exact_source_general_and_audited_for_all_cases() -> None:
    audit = verify_prompt_audit(
        rule_path=DEFAULT_PATHS.root_rule,
        audit_path=DEFAULT_PATHS.root_rule_audit,
        adjudication_path=DEFAULT_PATHS.nested_adjudication,
    )
    rule = DEFAULT_PATHS.root_rule.read_text(encoding="utf-8")

    assert rule == EXPECTED_RULE
    assert _sha256(DEFAULT_PATHS.root_rule) == EXPECTED_RULE_SHA256
    assert audit["case_count"] == 6
    cases = _OBJECT_LIST.validate_python(audit["cases"])
    assert tuple(case["case_id"] for case in cases) == CASE_ORDER
    assert audit["unresolved_safety_findings"] == []
    assert audit["leakage_findings"] == []
    transport = _object(audit["non_scientific_transport_clarification"])
    assert transport["panel_focus_event_eligibility_required"] is True
    assert transport["non_complete_root_event_id_semantics"] == (
        "TRANSPORT_ANCHOR_ONLY"
    )
    assert transport["eventless_abstention_supported"] is False
    assert "eventless abstention" in str(audit["residual_capability_limitation"])
    for source_specific in (
        "PMID",
        "7966592",
        "HCMV",
        "p53",
        "fibroblast",
        "responsible",
        "elevating",
        "REGULATION",
    ):
        assert source_specific not in rule


def test_provider_prompt_is_exact_v11_plus_v12_plus_v13_then_case() -> None:
    value = provider_input(
        "generalization-explicit-nested-cause",
        DEFAULT_PATHS,
    )
    prompt_only, frozen_case = value.split(
        "\n--- FROZEN EXPOSED CASE ---\n",
        maxsplit=1,
    )

    assert value.startswith(DEFAULT_PATHS.v11_prompt.read_text(encoding="utf-8"))
    assert DEFAULT_PATHS.v12_focus_rule.read_text(encoding="utf-8") in prompt_only
    assert DEFAULT_PATHS.root_rule.read_text(encoding="utf-8") in prompt_only
    assert prompt_only.count("--- V13 SINGLE SCIENTIFIC CHANGE ---") == 1
    assert "PMID" not in prompt_only
    assert "7966592" not in prompt_only
    assert '"reference"' not in value
    assert "acceptable_texts" not in value
    assert "generalization-explicit-nested-cause" in frozen_case


def test_independent_wording_reviews_bind_the_exact_rule_and_audit() -> None:
    expected = {
        "rule_sha256": _sha256(DEFAULT_PATHS.root_rule),
        "audit_sha256": _sha256(DEFAULT_PATHS.root_rule_audit),
        "verdict": "PASS",
    }
    reviewer_ids = set()
    for path in (
        DEFAULT_PATHS.wording_review_a,
        DEFAULT_PATHS.wording_review_b,
    ):
        review = _OBJECT.validate_json(path.read_text(encoding="utf-8"))
        reviewer_ids.add(review["reviewer_id"])
        for key, value in expected.items():
            assert review[key] == value
        assert review["transport_clarification"] == "PASS"
        assert review["exposed_event_eligibility"] == "PASS"
        assert review["residual_limitation_disclosure"] == "PASS"
        assert review["non_complete_root_credit"] == "NOT_APPLICABLE"
        safety = _object(review["case_safety"])
        assert set(safety) == set(CASE_ORDER)
        assert set(safety.values()) == {"PASS"}

    assert reviewer_ids == {
        "v13_rule_reviewer_a",
        "v13_rule_reviewer_b",
    }


def test_sealed_v12_artifacts_and_inputs_remain_byte_identical() -> None:
    expected = {
        DEFAULT_PATHS.v12_preregistration: (
            "12a0b0baf6e3a7134ef340091012805e343f799f148a8f3c104cc75da17831c4"
        ),
        DEFAULT_PATHS.v12_result: (
            "c110ff6eadfa41c90c19b1ff039b007b20926b2efa7ccf53ae596cc351895561"
        ),
        DEFAULT_PATHS.v12_report: (
            "0aa03822d0d0211eeae793d10897d30375027781477476642e3b195961abbe55"
        ),
        DEFAULT_PATHS.v12_nested_raw: (
            "c982fdc5282cef320cf2436f3ab70b380547553b6efb091f26fe5c4e6624304d"
        ),
        DEFAULT_PATHS.v12_drug_raw: (
            "a2787a3eb453f7637d412dccec2781b1d196dbf30c0b4a2f0eda94fbdc18ba54"
        ),
    }

    for path, digest in expected.items():
        assert _sha256(path) == digest


def test_v13_local_policy_adapter_reproduces_unchanged_v12_grader() -> None:
    cases = load_frozen_panel()
    historical = verify_frozen_policy(DEFAULT_PATHS.grading)
    adapted = verify_v13_frozen_policy(DEFAULT_PATHS.grading, cases=cases)

    verify_shared_grader_sources()
    assert adapted == historical
    assert policy_sha256(adapted) == V12_GRADING_POLICY_SHA256
    assert {
        name: _sha256(REPO / name) for name in V12_GRADING_SOURCE_SHA256
    } == V12_GRADING_SOURCE_SHA256


def test_preregistration_does_not_read_untracked_panel_corpus(
    monkeypatch: pytest.MonkeyPatch,
    repo_tmp_path: Path,
) -> None:
    paths = _paths_with_frozen_replay(repo_tmp_path)
    unavailable = REPO / "must-not-read-untracked-panel-corpus"
    monkeypatch.setattr(generated_panel, "EXPOSED_CORPUS", unavailable)
    monkeypatch.setattr(generated_panel, "CG_DEVELOPMENT", unavailable)

    preregistration = build_preregistration(paths)

    frozen = _object(preregistration["frozen_state"])
    assert frozen["panel_runtime_source"] == "TRACKED_FROZEN_PANEL"
    assert frozen["panel_generator_attestation"] == {
        "canonical_json_normalization": True,
        "generated_panel_matches_frozen": True,
        "generator_path": (
            "scripts/validation/public_gold/staged_event/generalization/panel.py"
        ),
        "verified_at": "2026-07-23",
    }


def test_panel_source_custody_mutation_fails_preregistration(
    repo_tmp_path: Path,
) -> None:
    paths = _paths_with_frozen_replay(repo_tmp_path)
    custody: object = json.loads(
        DEFAULT_PATHS.panel_source_custody.read_text(encoding="utf-8")
    )
    custody_object = _object(custody)
    external = _OBJECT_LIST.validate_python(custody_object["external_inputs"])
    external[0]["sha256"] = "0" * 64
    custody_object["external_inputs"] = external
    mutated = repo_tmp_path / "mutated-panel-source-custody.json"
    _write_json(mutated, custody_object)

    with pytest.raises(V13PreflightError, match="source custody manifest changed"):
        build_preregistration(replace(paths, panel_source_custody=mutated))


def test_v12_nested_replay_is_root_only_and_grants_zero_credit(
    repo_tmp_path: Path,
) -> None:
    paths = _paths_with_frozen_replay(repo_tmp_path)
    replay = build_offline_replay(_replay_paths(paths))
    observed = _object(replay["sealed_v12"])
    observed_metrics = _object(observed["v13_diagnostic"])
    synthetic = _object(replay["synthetic_forward_diagnostic"])
    synthetic_metrics = _object(synthetic["v13_diagnostic"])

    assert observed["source_lane_fails_only_wrong_root"] is True
    assert (
        observed["exact_cg_root_dependency_chain_failure_is_independent_of_root"]
        is True
    )
    assert observed["source_semantic_historical_credit"] is False
    assert observed["exact_cg_root_dependency_chain_credit"] is False
    assert observed["retroactive_credit"] is False
    assert observed["sealed_result_changed"] is False
    assert observed_metrics["passed"] is False
    assert observed_metrics["focus_event_passed"] is False
    assert observed_metrics["source_semantic_status"] == "FAIL"
    assert observed_metrics["benchmark_projection_status"] == "FAIL"
    assert observed_metrics["benchmark_projection_scope"] == (
        "EXACT_CG_ROOT_DEPENDENCY_CHAIN"
    )
    assert observed_metrics["root_selection_status"] == "FAIL"
    assert observed_metrics["source_dimensions_except_root_passed"] is True
    assert observed_metrics["root_only_failure"] is True
    assert observed_metrics["failure_reasons"] == [
        "source root is not the outer responsible event"
    ]
    assert synthetic["mutation"] == "ROOT_EVENT_ID_ONLY"
    assert synthetic["counterfactual_only"] is True
    assert synthetic["root_event_id_before"] == "E2"
    assert synthetic["root_event_id_after"] == "E1"
    assert synthetic_metrics["passed"] is True
    assert synthetic_metrics["source_semantic_status"] == "PASS"
    assert synthetic_metrics["benchmark_projection_status"] == "FAIL"
    assert synthetic_metrics["benchmark_projection"] is None
    assert synthetic_metrics["root_selection_status"] == "PASS"
    assert synthetic_metrics["source_dimensions_except_root_passed"] is True
    assert synthetic_metrics["root_only_failure"] is False
    assert synthetic_metrics["full_focus_cg_status"] == ("NOT_MEASURED_UNREPRESENTABLE")
    assert synthetic["source_semantic_historical_credit"] is False
    assert synthetic["exact_cg_root_dependency_chain_pass"] is False
    assert synthetic["exact_cg_root_dependency_chain_credit"] is False
    assert synthetic["gold_projection_synthesized"] is False
    assert synthetic["qualification_credit"] is False
    lane_separation = _object(replay["lane_separation"])
    assert (
        lane_separation[
            "source_semantic_pass_implies_exact_cg_root_dependency_chain_pass"
        ]
        is False
    )
    assert (
        lane_separation["exact_cg_root_dependency_chain_uses_artana_output_only"]
        is True
    )
    assert lane_separation["gold_reference_completion_allowed"] is False
    assert lane_separation["full_focus_cg_projection_status"] == (
        "NOT_MEASURED_UNREPRESENTABLE"
    )
    assert lane_separation["full_focus_unrepresentable_schema_types"] == [
        "INFECTION",
        "CELL",
        "ORGANISM",
    ]
    additional = _object(lane_separation["full_focus_official_additional_event"])
    assert additional["event_id"] == "E28"
    assert additional["event_type"] == "INFECTION"
    assert replay["historical_replay_credit"] is False
    assert replay["historical_result_rescored"] is False
    assert replay["graph_writes"] == 0
    assert replay["trusted_promotion"] is False


def test_preregistration_is_deterministic_and_separates_projection(
    repo_tmp_path: Path,
) -> None:
    paths = _paths_with_frozen_replay(repo_tmp_path)
    first = build_preregistration(paths)
    second = build_preregistration(paths)

    assert first == second
    assert first["single_scientific_change"] == ("COMPOSITIONAL_FOCUS_ROOT_SELECTION")
    assert first["scientific_hypothesis"] == SCIENTIFIC_HYPOTHESIS
    assert "already-inventoried focus-internal event graph" in SCIENTIFIC_HYPOTHESIS
    assert "without changing the event, participant, or link inventory" in (
        SCIENTIFIC_HYPOTHESIS
    )
    provider = _object(first["provider"])
    assert provider["application_max_output_tokens"] is None
    assert provider["application_max_total_tokens"] is None
    assert provider["provider_retries"] == 0
    assert provider["fallback"] is False
    assert provider["rejected_attempt_custody_required"] is True
    assert provider["rejected_attempt_exclusive_persistence"] is True
    assert provider["rejected_attempt_unknown_usage_recorded_as_unknown"] is True
    assert provider["cross_case_response_id_reuse_invalid"] is True
    assert provider["rejected_attempt_available_evidence_retained"] == [
        "response_ids",
        "creation_response",
        "confirmation_response",
        "input_items",
        "canonical_payload",
        "usage",
        "latency_seconds",
    ]
    frozen = _object(first["frozen_state"])
    assert frozen["panel_runtime_source"] == "TRACKED_FROZEN_PANEL"
    assert frozen["panel_source_custody_sha256"] == _sha256(
        DEFAULT_PATHS.panel_source_custody
    )
    assert len(str(frozen["panel_canonical_sha256"])) == 64
    tracked_corpus = _object(frozen["panel_tracked_corpus_sha256"])
    assert tracked_corpus == {
        "scripts/validation/source_general_claim_verification/fixtures/"
        "exposed_31_scope_corpus.json": (
            "35377c6a263a21a47851e70ea935da27f7d83a34c3f11646a71c9c115b93ccb3"
        )
    }
    external_sources = _object(frozen["panel_external_source_sha256"])
    assert len(external_sources) == 6
    assert (
        external_sources[
            "validation/public_gold/bionlp_cg/raw/"
            "bionlp-st-2013-cg-master/original-data/devel/PMID-7966592.txt"
        ]
        == "cef4eed850665c8e55e5e8deccdef2fa92a05377ffb9bf5666a85b6320192f02"
    )
    runtime_dependencies = _object(frozen["runtime_dependency_manifest_sha256"])
    assert set(runtime_dependencies) >= {
        "scripts/validation/public_gold/lossless_event_provider.py",
        "scripts/validation/public_gold/staged_event/contracts.py",
        "scripts/validation/public_gold/staged_event/generalization/anchors.py",
        "scripts/validation/public_gold/staged_event/generalization/contracts.py",
        "scripts/validation/public_gold/staged_event/generalization/panel.py",
        "scripts/validation/public_gold/staged_event/generalization/span_identity.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/frozen_panel.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/frozen_policy.py",
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/request_contract.py",
    }
    assert (
        "scripts/validation/provider_receipt_boundary/background/contracts.py"
        in runtime_dependencies
    )
    assert frozen["service_import_origin_policy"] == (
        "CURRENT_REPOSITORY_HASHED_SERVICE_MODULES_ONLY"
    )
    assert frozen["loaded_service_modules_must_be_manifest_subset"] is True
    assert frozen["service_import_required_modules"] == [
        "artana_evidence_api",
        "artana_evidence_api.document_extraction_support",
        "artana_evidence_api.document_extraction_support.claim_frames",
        ("artana_evidence_api.document_extraction_support.claim_frames.event_types"),
        "artana_evidence_api.document_extraction_support.scientific_events",
        ("artana_evidence_api.document_extraction_support.scientific_events.contracts"),
        (
            "artana_evidence_api.document_extraction_support.scientific_events."
            "validation"
        ),
    ]
    assert frozen["shared_frozen_grader_source_sha256"] == (V12_GRADING_SOURCE_SHA256)
    assert frozen["root_schema_resolution"] == (
        "EXPOSED_NON_COMPLETE_TRANSPORT_ANCHOR_EARLIEST_SOURCE_SUPPORTED_FOCUS_EVENT"
    )
    assert frozen["nested_adjudication_report_sha256"] == _sha256(
        REPO / "docs/validation/adjudications/"
        "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.md"
    )
    eligibility = _object(frozen["upstream_provider_eligibility_by_case"])
    assert set(eligibility) == set(CASE_ORDER)
    assert all(
        _object(value)["upstream_eligible"] is True for value in eligibility.values()
    )
    frozen_tests = _object(frozen["frozen_test_sha256"])
    assert set(frozen_tests) == {
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
    }
    contract = _object(frozen["evaluation_contract"])
    assert contract["qualification_lane"] == "SOURCE_SEMANTIC"
    assert contract["exact_cg_root_dependency_chain_lane"] == (
        "REVIEW_ONLY_NONBLOCKING_ARTANA_OUTPUT_ONLY"
    )
    assert contract["cg_root_dependency_chain_qualification_credit"] is False
    assert contract["source_pass_implies_exact_cg_root_dependency_chain_pass"] is False
    assert contract["gold_projection_completion_allowed"] is False
    assert contract["full_focus_cg_projection_status"] == (
        "NOT_MEASURED_UNREPRESENTABLE"
    )
    assert contract["full_focus_unrepresentable_schema_types"] == [
        "INFECTION",
        "CELL",
        "ORGANISM",
    ]
    assert len(str(contract["full_focus_official_additional_event_sha256"])) == 64
    assert "has no INFECTION" in str(contract["full_focus_unrepresentable_reason"])
    assert contract["unchanged_frozen_grader_cases"] == [
        "generalization-comparison-canary",
        "generalization-uncertainty",
        "generalization-negated-association",
        "generalization-null-statistics",
    ]
    assert contract["drug_policy"] == (
        "V12_DRUG_METRICS_REUSED_SOURCE_LANE_AUTHORITATIVE_CG_NONBLOCKING"
    )
    evaluator_hashes = _object(contract["implementation_sha256"])
    assert (
        "scripts/validation/public_gold/staged_event/generalization/"
        "repair_v13/cg_projection.py"
    ) in evaluator_hashes
    transitive = _object(frozen["transitive_execution_dependency_sha256"])
    assert set(transitive) == {
        "scripts/validation/public_gold/staged_event/context_experiment/"
        "source_first/attempts.py",
        "scripts/validation/public_gold/staged_event/context_experiment/"
        "source_first/custody.py",
        "scripts/validation/public_gold/staged_event/generalization/repair_v10/"
        "execution_config.py",
        "scripts/validation/public_gold/staged_event/generalization/repair_v9/"
        "contracts.py",
    }
    acceptance = _object(first["acceptance"])
    assert PASS_TERMINAL == "V13_EXPOSED_GATE_PASS_PENDING_INDEPENDENT_REVIEW"
    assert acceptance["exposed_source_semantic_gate_complete_on_pass"] is True
    assert acceptance["fresh_qualification_status_on_pass"] == (
        "PENDING_INDEPENDENT_REVIEW"
    )
    assert acceptance["fresh_qualification_complete_on_pass"] is False
    assert acceptance["all_six_source_semantic_cases_pass"] is True
    assert acceptance["cg_root_dependency_chain_is_qualification_blocking"] is False
    assert acceptance["nested_cg_root_dependency_chain_pass_required"] is False
    assert (
        acceptance["source_lane_pass_can_coexist_with_cg_root_dependency_chain_fail"]
        is True
    )
    assert acceptance["nested_full_focus_cg_projection_measured"] is False
    assert acceptance["nested_full_focus_cg_projection_status"] == (
        "NOT_MEASURED_UNREPRESENTABLE"
    )
    assert acceptance["gold_projection_completion_allowed"] is False
    assert acceptance["root_or_abstain_schema_fallback_added"] is False
    assert acceptance["non_complete_transport_anchor_is_scientific_root"] is False
    assert acceptance["eventless_abstention_limitation_disclosed"] is True
    assert (
        acceptance["comparison_uncertainty_negated_null_use_unchanged_frozen_grader"]
        is True
    )
    assert acceptance["drug_v12_metrics_reused_with_source_lane_authoritative"] is True
    assert acceptance["drug_cg_projection_is_qualification_blocking"] is False
    provider_packets = _object(provider["packet_blinding"])
    assert provider_packets["blind"] is False
    assert provider_packets["descriptive_exposed_case_ids_visible"] is True
    assert provider_packets["carry_packets_into_fresh_validation"] is False
    schema_scope = _object(first["schema_scope"])
    assert schema_scope["non_complete_root_event_id_semantics"] == (
        "TRANSPORT_ANCHOR_ONLY_NOT_ASSERTED_SCIENTIFIC_ROOT"
    )
    assert schema_scope["eventless_abstention_supported"] is False
    assert schema_scope["v13_claims_to_resolve_eventless_abstention"] is False
    budget = _object(first["operational_budget"])
    rules = _object(first["rules"])
    sealed_history = _object(first["sealed_history"])
    terminals = _STRING_LIST.validate_python(first["terminal_decisions"])
    assert budget["cumulative_max_cost_usd"] == 5.0
    assert budget["rejected_calls_count_toward_creation_budget"] is True
    assert budget["rejected_call_cost_recorded_when_available"] is True
    assert budget["unaccounted_rejected_call_stops_before_next_creation"] is True
    assert rules["remote_head_must_match_pushed_branch_before_first_call"] is True
    assert rules["fresh_case_calls_allowed"] is False
    assert rules["automatic_fresh_draft_after_pass"] is False
    assert rules["fresh_draft_requires_separate_explicit_action"] is True
    assert rules["exposed_packets_may_be_reused_for_fresh"] is False
    assert rules["expected_execution_branch"] == EXPECTED_BRANCH
    assert rules["tracked_worktree_must_be_clean_before_first_call"] is True
    assert rules["required_frozen_paths_must_be_tracked"] is True
    assert rules["execution_output_paths_must_be_absent"] is True
    assert rules["unrelated_untracked_paths_preserved_and_reported"] is True
    assert rules["graph_writes"] is False
    assert rules["trusted_graph_promotion"] is False
    assert sealed_history["historical_results_rescored"] is False
    assert OPERATIONAL_BUDGET_TERMINAL == "V13_OPERATIONAL_BUDGET_STOP_INCOMPLETE"
    assert OPERATIONAL_BUDGET_TERMINAL in terminals


def test_preregistration_rejects_foreign_service_import_origin(
    monkeypatch: pytest.MonkeyPatch,
    repo_tmp_path: Path,
) -> None:
    paths = _paths_with_frozen_replay(repo_tmp_path)
    foreign_source = repo_tmp_path / "foreign-event-types.py"
    foreign_source.write_text("# foreign service dependency\n", encoding="utf-8")
    event_types = sys.modules[
        "artana_evidence_api.document_extraction_support.claim_frames.event_types"
    ]
    monkeypatch.setattr(event_types, "__file__", str(foreign_source))

    with pytest.raises(
        V13PreflightError,
        match="outside the current repository services tree",
    ):
        build_preregistration(paths)


def test_output_paths_are_repo_local_and_cannot_overlap_history(
    tmp_path: Path,
) -> None:
    verify_output_path_custody(DEFAULT_PATHS)

    with pytest.raises(V13PreflightError, match="escapes repository custody"):
        verify_output_path_custody(
            replace(DEFAULT_PATHS, result=tmp_path / "outside-result.json")
        )
    with pytest.raises(V13PreflightError, match="overlaps frozen historical"):
        verify_output_path_custody(
            replace(DEFAULT_PATHS, result=DEFAULT_PATHS.v12_result)
        )


def test_remote_gate_requires_exact_branch_and_reports_untracked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "a" * 40

    def fake_git(*arguments: str) -> str:
        if arguments == ("branch", "--show-current"):
            return EXPECTED_BRANCH
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments[:3] == ("ls-remote", "--heads", "origin"):
            return f"{head}\trefs/heads/{EXPECTED_BRANCH}"
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return ""
        if arguments == ("status", "--porcelain=v1", "--untracked-files=all"):
            return "?? user-notes.txt\n?? validation/public_gold/bionlp_cg/raw"
        if arguments[:3] == ("ls-files", "--error-unmatch", "--"):
            return arguments[-1]
        raise AssertionError(arguments)

    monkeypatch.setattr(v13_preflight, "_git", fake_git)

    observed = verify_remote_execution_state(DEFAULT_PATHS)

    assert observed["branch"] == EXPECTED_BRANCH
    assert observed["local_head"] == head
    assert observed["remote_head"] == head
    assert observed["tracked_modification_count"] == 0
    assert observed["untracked_paths_preserved"] == [
        "user-notes.txt",
        "validation/public_gold/bionlp_cg/raw",
    ]


def test_remote_gate_rejects_any_other_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        v13_preflight,
        "_git",
        lambda *_arguments: "alvaro/wrong-branch",
    )

    with pytest.raises(V13PreflightError, match="requires branch"):
        verify_remote_execution_state(DEFAULT_PATHS)


def test_remote_gate_rejects_tracked_changes_and_existing_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = "b" * 40

    def tracked_git(*arguments: str) -> str:
        if arguments == ("branch", "--show-current"):
            return EXPECTED_BRANCH
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments[:3] == ("ls-remote", "--heads", "origin"):
            return f"{head}\trefs/heads/{EXPECTED_BRANCH}"
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return " M tracked-file.py"
        raise AssertionError(arguments)

    monkeypatch.setattr(v13_preflight, "_git", tracked_git)
    with pytest.raises(V13PreflightError, match="tracked worktree changes"):
        verify_remote_execution_state(DEFAULT_PATHS)

    def clean_git(*arguments: str) -> str:
        if arguments == ("branch", "--show-current"):
            return EXPECTED_BRANCH
        if arguments == ("rev-parse", "HEAD"):
            return head
        if arguments[:3] == ("ls-remote", "--heads", "origin"):
            return f"{head}\trefs/heads/{EXPECTED_BRANCH}"
        if arguments == ("status", "--porcelain=v1", "--untracked-files=no"):
            return ""
        raise AssertionError(arguments)

    monkeypatch.setattr(v13_preflight, "_git", clean_git)
    with pytest.raises(V13PreflightError, match="execution output already exists"):
        verify_remote_execution_state(replace(DEFAULT_PATHS, result=REPO / "README.md"))


def _paths_with_frozen_replay(tmp_path: Path) -> V13Paths:
    contract_path = tmp_path / "nested-contract.json"
    contract = build_contract(
        DEFAULT_PATHS.nested_adjudication,
        v12_contract_path=DEFAULT_PATHS.v12_drug_two_lane_contract,
    )
    _write_json(contract_path, contract.model_dump(mode="json"))
    paths = replace(
        DEFAULT_PATHS,
        nested_two_lane_contract=contract_path,
        offline_replay=tmp_path / "offline-replay.json",
        preregistration=tmp_path / "preregistration.json",
    )
    _write_json(
        paths.offline_replay,
        build_offline_replay(_replay_paths(paths)),
    )
    return paths


@pytest.fixture
def repo_tmp_path(tmp_path: Path) -> Iterator[Path]:
    path = REPO / f".pytest-v13-preflight-{tmp_path.name}"
    path.mkdir()
    try:
        yield path
    finally:
        for child in path.iterdir():
            child.unlink()
        path.rmdir()


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


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _object(value: object) -> dict[str, object]:
    return _OBJECT.validate_python(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
