"""Tests for create-once, sequential eighth-holdout authorization."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial import (
    eighth_qualification,
    eighth_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.eighth_sequence import (
    EighthRepeatAuthorization,
    finalize_eighth_repeat,
    reserve_eighth_repeat,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)
from scripts.validation.claim_frames.provider_receipts import (
    ProviderReceiptEvidence,
    ProviderReceiptExpectation,
)

_SELECTION_SEED = "969619fd2b8faf60d81c34ba9b12c3f100d69f3af56dcda431072dd009156916"
_PROJECTION_SET_SHA256 = (
    "5c8e13c4eac5087d151c1b4b391b1215555ce401fdbb1c38a95b61853ed6cde6"
)
_UNIT_ID = (
    "source-unit-def51372591d9c4244a4dac031c801c8781aa4006f6718ddd8bfb77dece566a2"
)
_SOURCE_SHA256 = "09a14c9ddcfd3ef03820e5fe7f3a62164fdf051f3a46335b8523c0681ed5fe35"
_INPUT_SHA256 = "606efd1510850b66276d48b00a042680aa0982e9d233195c3b1906cfb9b513db"
_UNIT_TEXT = (
    "Although there was a trend, the transfection of CD4+ T cells with RUNX3 "
    "did not lead to statistically significant increase in FOXP3 (Fig. S5)."
)
_REAL_QUALIFICATION_REPLAY = eighth_sequence.require_replayed_eighth_qualification


@pytest.fixture(autouse=True)
def _live_provider_reverification(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        eighth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: _LiveVerifier(),
    )
    monkeypatch.setattr(
        eighth_sequence,
        "require_replayed_eighth_qualification",
        lambda report: None,
    )


def test_repeats_are_create_once_and_require_previous_pass(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    run_id = "tg04-v8-test"
    repeat_1_output = tmp_path / "repeat-1.json"
    repeat_1 = reserve_eighth_repeat(
        repository_root=repository,
        run_id=run_id,
        repeat_index=1,
        output=repeat_1_output,
        previous_report=None,
    )
    repeat_1.require_active()
    with pytest.raises(FileExistsError):
        reserve_eighth_repeat(
            repository_root=repository,
            run_id=run_id,
            repeat_index=1,
            output=tmp_path / "selective-rerun.json",
            previous_report=None,
        )

    report_1 = _report(
        authorization=repeat_1,
        passed=True,
    )
    repeat_1_output.write_text(json.dumps(report_1), encoding="utf-8")
    finalize_eighth_repeat(repeat_1, report=report_1)

    repeat_2 = reserve_eighth_repeat(
        repository_root=repository,
        run_id=run_id,
        repeat_index=2,
        output=tmp_path / "repeat-2.json",
        previous_report=repeat_1_output,
    )
    repeat_2.require_active()


def test_failed_previous_repeat_blocks_sequence(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    run_id = "tg04-v8-failed"
    report_path = tmp_path / "failed-repeat-1.json"
    repeat_1 = reserve_eighth_repeat(
        repository_root=repository,
        run_id=run_id,
        repeat_index=1,
        output=report_path,
        previous_report=None,
    )
    report = _report(
        authorization=repeat_1,
        passed=False,
    )
    report_path.write_text(json.dumps(report), encoding="utf-8")
    finalize_eighth_repeat(repeat_1, report=report)

    with pytest.raises(
        RuntimeError, match="previous eighth holdout repeat did not pass"
    ):
        reserve_eighth_repeat(
            repository_root=repository,
            run_id=run_id,
            repeat_index=2,
            output=tmp_path / "repeat-2.json",
            previous_report=report_path,
        )


def test_later_repeat_requires_untampered_previous_report(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    run_id = "tg04-v8-tamper"
    report_path = tmp_path / "repeat-1.json"
    repeat_1 = reserve_eighth_repeat(
        repository_root=repository,
        run_id=run_id,
        repeat_index=1,
        output=report_path,
        previous_report=None,
    )
    report = _report(
        authorization=repeat_1,
        passed=True,
    )
    report_path.write_text(json.dumps(report), encoding="utf-8")
    finalize_eighth_repeat(repeat_1, report=report)
    report["run_id"] = "changed-after-finalization"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RuntimeError, match="report identity is invalid"):
        reserve_eighth_repeat(
            repository_root=repository,
            run_id=run_id,
            repeat_index=2,
            output=tmp_path / "repeat-2.json",
            previous_report=report_path,
        )


def test_later_repeat_requires_the_same_repository_snapshot(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    report_path = tmp_path / "repeat-1.json"
    repeat_1 = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-cross-repeat-drift",
        repeat_index=1,
        output=report_path,
        previous_report=None,
    )
    report = _report(authorization=repeat_1, passed=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")
    finalize_eighth_repeat(repeat_1, report=report)
    (repository / "tracked.txt").write_text("new system\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(repository), "add", "tracked.txt"), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "commit", "-q", "-m", "change system"),
        check=True,
    )

    with pytest.raises(RuntimeError, match="one frozen repository"):
        reserve_eighth_repeat(
            repository_root=repository,
            run_id=repeat_1.run_id,
            repeat_index=2,
            output=tmp_path / "repeat-2.json",
            previous_report=report_path,
        )


def test_repeat_two_cannot_run_directly(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)

    with pytest.raises(
        ValueError,
        match="later repeats require the immediately previous report",
    ):
        reserve_eighth_repeat(
            repository_root=repository,
            run_id="tg04-v8-direct-repeat-2",
            repeat_index=2,
            output=tmp_path / "repeat-2.json",
            previous_report=None,
        )


def test_repository_change_after_reservation_blocks_provider_binding(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    authorization = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-repository-drift",
        repeat_index=1,
        output=tmp_path / "repository-drift.json",
        previous_report=None,
    )
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="repository changed after"):
        authorization.provider_evidence_unit_id()


def test_noncanonical_provider_prompt_hash_is_rejected() -> None:
    unit = FrozenSourceUnit(
        unit_id=_UNIT_ID,
        index=10,
        source_start=1909,
        source_end=2051,
        text=_UNIT_TEXT,
        source_sha256=_SOURCE_SHA256,
    )
    attempts: list[object] = [
        {
            "attempt_role": role,
            "provider_response_id": f"resp_{role}",
            "invocation_id": f"invocation-{role}",
            "evidence_unit_sha256": "a" * 64,
            "prompt_sha256": "tampered-prompt",
            "output_schema_identity": "tampered-schema",
        }
        for role in ("primary", "weak_review")
    ]
    receipts: dict[str, object] = {
        "receipts": [
            {
                "response_id": f"resp_{role}",
                "expected_prompt_sha256": "tampered-prompt",
                "expected_output_schema_sha256": "tampered-schema",
            }
            for role in ("primary", "weak_review")
        ]
    }

    with pytest.raises(RuntimeError, match="provider prompt is not canonical"):
        eighth_qualification._require_canonical_provider_prompts(
            unit=unit,
            candidates=(),
            attempts=attempts,
            receipts=receipts,
        )


def test_minimal_self_signed_report_cannot_finalize(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "minimal.json"
    authorization = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-minimal",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report: dict[str, object] = {
        "schema_version": "tg04_nested_event_holdout.v8",
        "run_id": authorization.run_id,
        "repeat_index": 1,
        "source_corpus": {"projection_set_sha256": _PROJECTION_SET_SHA256},
        "unit": {"unit_id": _UNIT_ID},
        "freshness": {"selection_seed": _SELECTION_SEED},
        "gate": {"passed": True},
        "repeat_authorization": {
            "run_id": authorization.run_id,
            "repeat_index": 1,
            "token_sha256": hashlib.sha256(
                authorization.token.encode(),
            ).hexdigest(),
        },
    }
    report["report_sha256"] = sha256_json(report)
    output.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RuntimeError, match="report repository differs"):
        finalize_eighth_repeat(authorization, report=report)


def test_persisted_json_arrays_equal_in_memory_tuples(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "tuple-roundtrip.json"
    authorization = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-tuple-roundtrip",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report = _report(authorization=authorization, passed=False)
    source_corpus = report["source_corpus"]
    assert isinstance(source_corpus, dict)
    source_corpus["serialization_probe"] = ("one", "two")
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    output.write_text(json.dumps(report), encoding="utf-8")

    finalize_eighth_repeat(authorization, report=report)


def test_receipt_shaped_report_cannot_finalize_without_live_provider_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "forged-receipts.json"
    authorization = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-forged-receipts",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report = _report(
        authorization=authorization,
        passed=True,
    )
    output.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        eighth_sequence.OpenAIProviderReceiptVerifier,
        "from_environment",
        lambda: None,
    )

    with pytest.raises(RuntimeError, match="independent live reverification"):
        finalize_eighth_repeat(authorization, report=report)

    authorization.require_active()


def test_live_old_response_cannot_be_reused_for_the_v8_unit(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "old-response.json"
    authorization = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-old-response",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report = _report(
        authorization=authorization,
        passed=True,
    )
    attempts = report["attempts"]
    receipts = report["provider_receipts"]
    assert isinstance(attempts, list)
    assert isinstance(receipts, dict)
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    old_source_sha256 = "old-source"
    for attempt in attempts:
        assert isinstance(attempt, dict)
        attempt["source_sha256"] = old_source_sha256
    for receipt in receipt_items:
        assert isinstance(receipt, dict)
        receipt["expected_source_sha256"] = old_source_sha256
        receipt["retrieved_source_sha256"] = old_source_sha256
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    output.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(RuntimeError, match="attempt evidence is invalid"):
        finalize_eighth_repeat(authorization, report=report)

    authorization.require_active()


def test_self_attested_empty_scientific_gate_cannot_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "self-attested-gate.json"
    authorization = reserve_eighth_repeat(
        repository_root=repository,
        run_id="tg04-v8-self-attested",
        repeat_index=1,
        output=output,
        previous_report=None,
    )
    report = _report(authorization=authorization, passed=True)
    output.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        eighth_sequence,
        "require_replayed_eighth_qualification",
        _REAL_QUALIFICATION_REPLAY,
    )

    with pytest.raises(ValueError):
        finalize_eighth_repeat(authorization, report=report)

    authorization.require_active()


def _report(
    *,
    authorization: EighthRepeatAuthorization,
    passed: bool,
) -> dict[str, object]:
    run_id = authorization.run_id
    repeat_index = authorization.repeat_index
    token = authorization.token
    requirement_names = {
        "agent_execution_complete",
        "all_candidates_source_entailed",
        "attempt_model_identity_bound",
        "audit_attempt_topology_exact",
        "audit_identity_bound",
        "candidate_inventory_complete",
        "complete_acceptable_projection_recovered",
        "controlled_event_link_ambiguity_zero",
        "invalid_agent_output_zero",
        "provider_lineage_complete",
        "provider_receipts_verified",
        "repeat_index_pre_registered",
        "sealed_graph_shape_verified",
    }
    requirements = dict.fromkeys(requirement_names, True)
    if not passed:
        requirements["complete_acceptable_projection_recovered"] = False
    repository_evidence = authorization.repository_evidence
    evidence_unit_sha256 = hashlib.sha256(
        authorization.provider_evidence_unit_id().encode()
    ).hexdigest()
    expectations = tuple(
        _expectation(index=index, evidence_unit_sha256=evidence_unit_sha256)
        for index in range(2)
    )
    response_ids = tuple(expectation.response_id for expectation in expectations)
    primary_payload = {"decision": "EXPLICIT_EVENT", "events": []}
    verification_payload = {
        "coverage_decision": "CANDIDATES_COMPLETE",
        "decisions": [],
    }
    payloads = (primary_payload, verification_payload)
    report: dict[str, object] = {
        "schema_version": "tg04_nested_event_holdout.v8",
        "run_id": run_id,
        "repeat_index": repeat_index,
        "configured_model_id": "openai:gpt-5.6-luna",
        "execution_model_id": "openai/gpt-5.6-luna",
        "expected_eligibility_category": "MIXED_SCIENTIFIC",
        "source_corpus": {"projection_set_sha256": _PROJECTION_SET_SHA256},
        "unit": {
            "case_id": "bionlp-ge-2011-holdout:PMC-2806624-04-RESULTS-03",
            "unit_id": _UNIT_ID,
            "unit_index": 10,
            "source_start": 1909,
            "source_end": 2051,
            "text": _UNIT_TEXT,
            "source_sha256": _SOURCE_SHA256,
            "input_sha256": _INPUT_SHA256,
        },
        "freshness": {"selection_seed": _SELECTION_SEED},
        "gate": {"passed": passed, "requirements": requirements},
        "agent_outputs": {
            "extraction": primary_payload,
            "verification": verification_payload,
            "error_type": None,
        },
        "attempts": [
            {
                "provider_response_id": response_id,
                "error_type": None,
                "replayed": False,
                "validation_outcome": "accepted",
                "model_id": "openai/gpt-5.6-luna",
                "semantic_unit_id": _UNIT_ID,
                "source_sha256": _SOURCE_SHA256,
                "input_sha256": _INPUT_SHA256,
                "attempt_role": "primary" if index == 0 else "weak_review",
                "pass_role": "primary" if index == 0 else "weak_review",
                "raw_model_payload": payloads[index],
                "payload_sha256": sha256_json(payloads[index]),
                "provider_output_sha256": expectations[index].expected_output_sha256,
                "prompt_sha256": expectations[index].expected_prompt_sha256,
                "invocation_id": expectations[index].expected_invocation_id,
                "kernel_run_id": expectations[index].expected_kernel_run_id,
                "evidence_unit_sha256": expectations[
                    index
                ].expected_evidence_unit_sha256,
            }
            for index, response_id in enumerate(response_ids)
        ],
        "provider_receipts": {
            "status": "verified_live",
            "expected_count": 2,
            "verified_count": 2,
            "receipts": [
                _verified_receipt(expectation).as_json() for expectation in expectations
            ],
        },
        "repository_evidence": repository_evidence,
        "conclusion_scope": {
            "execution_path": "agent_only_source_unit",
            "deterministic_extraction_fallback_available": False,
            "persistence_authorized": False,
        },
        "repeat_authorization": {
            "run_id": run_id,
            "repeat_index": repeat_index,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


def _expectation(
    *,
    index: int,
    evidence_unit_sha256: str,
) -> ProviderReceiptExpectation:
    return ProviderReceiptExpectation(
        response_id=f"resp_test_{index}",
        expected_case_id=_UNIT_ID,
        expected_model_id="gpt-5.6-luna",
        expected_output_sha256=f"output-{index}",
        expected_payload_sha256=sha256_json(
            {"decision": "EXPLICIT_EVENT", "events": []}
            if index == 0
            else {
                "coverage_decision": "CANDIDATES_COMPLETE",
                "decisions": [],
            }
        ),
        expected_prompt_sha256=f"prompt-{index}",
        expected_invocation_id=f"invocation-{index}",
        expected_kernel_run_id=f"kernel-{index}",
        expected_source_sha256=_SOURCE_SHA256,
        expected_input_sha256=_INPUT_SHA256,
        expected_evidence_unit_sha256=evidence_unit_sha256,
        expected_output_schema_sha256=f"schema-{index}",
    )


def _verified_receipt(
    expectation: ProviderReceiptExpectation,
) -> ProviderReceiptEvidence:
    return ProviderReceiptEvidence(
        response_id=expectation.response_id,
        expected_case_id=expectation.expected_case_id,
        status="verified_live",
        failure="none",
        expected_model_id=expectation.expected_model_id,
        retrieved_model_id=expectation.expected_model_id,
        expected_output_sha256=expectation.expected_output_sha256,
        retrieved_output_sha256=expectation.expected_output_sha256,
        provider_output_hash_matched=True,
        provider_output_verification_source="exact_provider_output",
        expected_payload_sha256=expectation.expected_payload_sha256,
        retrieved_payload_sha256=expectation.expected_payload_sha256,
        expected_prompt_sha256=expectation.expected_prompt_sha256,
        retrieved_prompt_sha256=expectation.expected_prompt_sha256,
        expected_invocation_id=expectation.expected_invocation_id,
        retrieved_invocation_id=expectation.expected_invocation_id,
        expected_kernel_run_id=expectation.expected_kernel_run_id,
        retrieved_kernel_run_id=expectation.expected_kernel_run_id,
        expected_source_sha256=expectation.expected_source_sha256,
        retrieved_source_sha256=expectation.expected_source_sha256,
        expected_input_sha256=expectation.expected_input_sha256,
        retrieved_input_sha256=expectation.expected_input_sha256,
        expected_evidence_unit_sha256=expectation.expected_evidence_unit_sha256,
        retrieved_evidence_unit_sha256=expectation.expected_evidence_unit_sha256,
        expected_output_schema_sha256=expectation.expected_output_schema_sha256,
        retrieved_output_schema_sha256=expectation.expected_output_schema_sha256,
        output_schema_verification_source="provider_response_and_input_binding",
        provider_response_schema_supported=True,
        provider_status="completed",
        response_completed_verified=True,
        incomplete_details_absent=True,
        standalone_context_verified=True,
        input_topology_verified=True,
        invocation_topology_supported=True,
        invocation_topology_verified=True,
    )


class _LiveVerifier:
    def verify(
        self,
        expectation: ProviderReceiptExpectation,
    ) -> ProviderReceiptEvidence:
        return _verified_receipt(expectation)


def _git_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(("git", "init", "-q", str(repository)), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "config", "user.email", "test@example.com"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(repository), "config", "user.name", "Artana Test"),
        check=True,
    )
    (repository / "tracked.txt").write_text("sealed\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(repository), "add", "tracked.txt"), check=True)
    subprocess.run(
        ("git", "-C", str(repository), "commit", "-q", "-m", "seal test tree"),
        check=True,
    )
    return repository
