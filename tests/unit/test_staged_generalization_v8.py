from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    SemanticAxes,
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as V5_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    build_panel,
    panel_json,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8 import runner
from scripts.validation.public_gold.staged_event.generalization.repair_v8.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.contracts import (
    POLARITY_TAXONOMY,
    V8SemanticAxes,
    V8StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.preflight import (
    PIVOT_BASIS_FILES,
    V8PreflightError,
    provider_input,
    verify,
    write_candidate,
)

REPO = Path(__file__).resolve().parents[2]
V7_CANARY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v7-generalization-comparison-canary-raw.json"
)
CASE_SPECIFIC_TERMS = (
    "generalization-null-statistics",
    "Kaplan-Meier",
    "NSCLC",
    "generalization-negated-association",
    "steroid dose before ICI initiation",
    "worse OS",
    "no longer associated",
    "generalization-uncertainty",
    "947 variants",
    "SLC12A3",
    "the majority of which",
)


def _paths(tmp_path: Path) -> ExperimentPaths:
    prompt = tmp_path / "prompt.md"
    prompt.write_bytes(DEFAULT_PATHS.prompt.read_bytes())
    return ExperimentPaths(
        panel=tmp_path / "panel.json",
        prompt=prompt,
        preregistration=tmp_path / "preregistration.json",
        result=tmp_path / "result.json",
        receipts=tmp_path / "receipts",
        raw_outputs=tmp_path / "raw",
        grading=V5_PATHS.grading,
    )


def _execution(
    output: V8StagedGeneralizationOutput,
    response_id: str,
) -> BackgroundProviderExecution[V8StagedGeneralizationOutput]:
    envelope: dict[str, object] = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {"response_id": response_id, "model": "gpt-5.6-luna"},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
                "latency_seconds": 1.0,
                "cost_usd": 0.01,
            },
            "budgets": {
                "requested_max_output_tokens": 20_000,
                "requested_max_total_tokens": 24_000,
                "requested_max_latency_seconds": 900.0,
                "requested_max_cost_usd": 0.15,
                "observed_output_tokens": 200,
                "observed_total_tokens": 300,
                "observed_latency_seconds": 1.0,
                "observed_cost_usd": 0.01,
                "output_tokens": "PASS",
                "total_tokens": "PASS",
                "latency": "PASS",
                "cost": "PASS",
            },
        },
    )


def test_v8_versions_polarity_semantics_without_changing_output_shape() -> None:
    schema = V8StagedGeneralizationOutput.model_json_schema()
    polarity = schema["$defs"]["V8SemanticAxes"]["properties"]["polarity"]

    assert polarity["description"] == POLARITY_TAXONOMY
    assert polarity["enum"] == ["AFFIRMED", "NEGATED", "NULL_RESULT"]
    assert set(V8StagedGeneralizationOutput.model_fields) == set(
        StagedGeneralizationOutput.model_fields
    )
    assert set(V8SemanticAxes.model_fields) == set(SemanticAxes.model_fields)
    assert hashlib.sha256(
        json.dumps(schema, sort_keys=True).encode()
    ).hexdigest() != hashlib.sha256(
        json.dumps(StagedGeneralizationOutput.model_json_schema(), sort_keys=True).encode()
    ).hexdigest()

    for path in sorted(
        (REPO / "docs/validation/results").glob(
            "2026-07-22-staged-generalization-v7-generalization-*-raw.json"
        )
    ):
        shared = StagedGeneralizationOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        versioned = V8StagedGeneralizationOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        assert versioned.model_dump(mode="json") == shared.model_dump(mode="json")


def test_v8_prompt_is_source_general_and_matches_versioned_taxonomy() -> None:
    prompt = DEFAULT_PATHS.prompt.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    assert not any(term in normalized for term in CASE_SPECIFIC_TERMS)
    assert "Polarity records scientific result status, not surface grammar" in normalized
    assert (
        "Use `NULL_RESULT` when a study or analysis reports absence of an "
        "association, difference, or effect" in normalized
    )
    assert (
        "Use `NEGATED` only for direct denial or non-occurrence outside an "
        "analytic null finding" in normalized
    )
    assert (
        "Apply antecedent resolution only when the highlighted finding contains a "
        "referring expression" in normalized
    )
    assert (
        "independent of whether the sentence grammatically asserts that proposition"
        in normalized
    )


def test_v8_reuses_panel_model_and_frozen_v5_grader() -> None:
    assert DEFAULT_PATHS.grading == V5_PATHS.grading
    assert DEFAULT_PATHS.panel != V5_PATHS.panel
    assert DEFAULT_PATHS.result != V5_PATHS.result
    assert DEFAULT_PATHS.preregistration != V5_PATHS.preregistration
    assert json.loads(DEFAULT_PATHS.panel.read_text(encoding="utf-8")) == json.loads(
        json.dumps(panel_json())
    )
    assert hashlib.sha256(DEFAULT_PATHS.panel.read_bytes()).hexdigest() == (
        hashlib.sha256(V5_PATHS.panel.read_bytes()).hexdigest()
    )


def test_v8_preregistration_is_reproducible_and_provider_input_remains_blind() -> (
    None
):
    preregistration = verify(DEFAULT_PATHS)
    frozen = cast("dict[str, object]", preregistration["frozen_state"])
    change = cast("dict[str, object]", preregistration["change_control"])
    rules = cast("dict[str, object]", preregistration["rules"])

    assert preregistration["schema_version"] == "artana.staged_generalization.v8"
    assert preregistration["experiment_id"] == "staged-generalization-v8"
    assert preregistration["supersedes_terminal"] == "PIVOT_WITH_EVIDENCE"
    assert change["single_scientific_change"] == "SOURCE_GENERAL_POLARITY_TAXONOMY"
    assert change["polarity_rule"] == POLARITY_TAXONOMY
    assert change["historical_v7_rescored"] is False
    assert change["grader_changed"] is False
    assert change["panel_changed"] is False
    assert change["prompt_changed"] is True
    assert change["schema_changed"] is True
    assert change["schema_shape_changed"] is False
    assert change["model_changed"] is False
    assert rules["silent_retries"] == 0
    assert rules["fallback"] is False
    assert rules["graph_writes"] is False
    assert rules["promotion"] is False
    assert set(cast("dict[str, str]", frozen["pivot_basis_sha256"])) == set(
        PIVOT_BASIS_FILES
    )
    for case in build_panel():
        value = provider_input(DEFAULT_PATHS, case.case_id)
        assert "dual_lane_policy" not in value
        assert "acceptable_triggers" not in value
        assert "reference_basis" not in value
        assert "PERMITTED_CONTEXT" not in value
        assert "V7 output" not in value


@pytest.mark.parametrize("term", CASE_SPECIFIC_TERMS)
def test_v8_preflight_rejects_case_specific_prompt_terms(
    tmp_path: Path,
    term: str,
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    verify(paths)
    paths.prompt.write_text(
        paths.prompt.read_text(encoding="utf-8") + f"\n{term}\n",
        encoding="utf-8",
    )

    with pytest.raises(V8PreflightError, match="case-specific"):
        verify(paths)


def test_v8_preflight_rejects_removal_of_polarity_rule(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    prompt = paths.prompt.read_text(encoding="utf-8").replace(
        "Polarity records scientific result status, not surface grammar",
        "Polarity records the wording used in the source",
    )
    paths.prompt.write_text(prompt, encoding="utf-8")

    with pytest.raises(V8PreflightError, match="semantic rules"):
        verify(paths)


def test_v8_runner_stops_on_scientific_canary_with_separate_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    canary = V8StagedGeneralizationOutput.model_validate_json(
        V7_CANARY_RAW.read_text(encoding="utf-8")
    )
    wrong_axes = canary.semantic_axes[0].model_copy(update={"direction": "DECREASED"})
    failing = canary.model_copy(update={"semantic_axes": (wrong_axes,)})
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[V8StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(failing, "response-v8-failed-canary")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(runner.V8Runtime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "PIVOT_WITH_EVIDENCE"
    assert calls == ["generalization-comparison-canary"]
    assert result["experiment_id"] == "staged-generalization-v8"
    assert result["scientific_change"] == "SOURCE_GENERAL_POLARITY_TAXONOMY"
    assert result["direction_fidelity"] == "0/1"
    assert result["provider_calls"] == 1
    assert result["qualification_credit"] is False
    assert result["graph_writes"] == 0
    assert paths.case(calls[0]).raw_output.exists()
    assert not V5_PATHS.case(calls[0]).attempt.samefile(paths.case(calls[0]).attempt)


def test_checked_in_v8_result_recomputes_and_preserves_fail_fast_custody() -> None:
    result = json.loads(DEFAULT_PATHS.result.read_text(encoding="utf-8"))
    panel = {case.case_id: case for case in build_panel()}
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    case_ids = [item["case_id"] for item in result["cases"]]
    outputs = [
        V8StagedGeneralizationOutput.model_validate_json(
            DEFAULT_PATHS.case(case_id).raw_output.read_text(encoding="utf-8")
        )
        for case_id in case_ids
    ]
    metrics = tuple(
        evaluate_case(
            panel[output.case_id],
            output,
            case_policy(policy, output.case_id),
        )
        for output in outputs
    )
    recomputed = json.loads(json.dumps(aggregate(metrics)))

    assert all(result[key] == value for key, value in recomputed.items())
    assert result["decision"] == "PIVOT_WITH_EVIDENCE"
    assert result["stopped_after_case_id"] == "generalization-uncertainty"
    assert result["provider_calls"] == len(case_ids) == 4
    assert result["grading_policy_sha256"] == policy_sha256(policy)
    assert result["polarity_fidelity"] == "4/4"
    assert result["uncertainty_fidelity"] == "4/4"
    assert result["unsupported_claim_count"] == 2
    assert result["all_receipts_valid"] is True
    assert result["qualification_credit"] is False
    assert result["trusted_promotion"] is False
    assert result["graph_writes"] == 0

    preregistration_sha256 = hashlib.sha256(
        DEFAULT_PATHS.preregistration.read_bytes()
    ).hexdigest()
    schema_sha256 = hashlib.sha256(
        json.dumps(
            V8StagedGeneralizationOutput.model_json_schema(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    response_ids: list[str] = []
    for case_id in case_ids:
        paths = DEFAULT_PATHS.case(case_id)
        attempt = json.loads(paths.attempt.read_text(encoding="utf-8"))
        bundle = json.loads(paths.bundle.read_text(encoding="utf-8"))
        receipt = json.loads(paths.receipt.read_text(encoding="utf-8"))
        raw = json.loads(paths.raw_output.read_text(encoding="utf-8"))
        response_id = receipt["identity"]["response_id"]
        expected_input_sha256 = hashlib.sha256(
            provider_input(DEFAULT_PATHS, case_id).encode()
        ).hexdigest()

        assert attempt["preregistration_sha256"] == preregistration_sha256
        assert attempt["provider_creation_limit"] == 1
        assert attempt["provider_retries"] == 0
        assert attempt["response_id"] == response_id
        assert bundle["response_id"] == response_id
        assert bundle["provider_input_sha256"] == expected_input_sha256
        assert bundle["schema_sha256"] == schema_sha256
        assert bundle["typed_output"] == raw
        assert bundle["receipt"] == receipt
        assert receipt["status"] == "VERIFIED_LIVE"
        assert receipt["provider_creation_calls"] == 1
        assert receipt["duplicate_creation_calls"] == 0
        assert receipt["provider_retries"] == 0
        assert all(
            receipt["budgets"][key] == "PASS"
            for key in ("output_tokens", "total_tokens", "latency", "cost")
        )
        response_ids.append(response_id)

    assert result["response_ids"] == response_ids
    for case_id in (
        "generalization-drug-sensitivity",
        "generalization-explicit-nested-cause",
    ):
        paths = DEFAULT_PATHS.case(case_id)
        assert not any(
            path.exists()
            for path in (paths.attempt, paths.bundle, paths.receipt, paths.raw_output)
        )
