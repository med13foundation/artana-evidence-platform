from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.generalization.anchors import (
    GeneralizationAnchorError,
    resolve_in_context,
)
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    EventArgument,
    EventLinks,
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
from scripts.validation.public_gold.staged_event.generalization.repair_v8.contracts import (
    POLARITY_TAXONOMY,
    V8StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9 import runner
from scripts.validation.public_gold.staged_event.generalization.repair_v9.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    CLASSIFICATION_ARGUMENT_TAXONOMY,
    V9EventArgument,
    V9EventLinks,
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.preflight import (
    PIVOT_BASIS_FILES,
    V9PreflightError,
    provider_input,
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.historical_v9 import (
    verify_provenance,
)

REPO = Path(__file__).resolve().parents[2]
V8_CANARY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v8-generalization-comparison-canary-raw.json"
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
    output: V9StagedGeneralizationOutput,
    response_id: str,
) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
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


def test_v9_versions_classification_arguments_without_changing_output_shape() -> None:
    schema = V9StagedGeneralizationOutput.model_json_schema()
    role = schema["$defs"]["V9EventArgument"]["properties"]["role"]
    polarity = schema["$defs"]["V8SemanticAxes"]["properties"]["polarity"]

    assert role["description"] == CLASSIFICATION_ARGUMENT_TAXONOMY
    assert polarity["description"] == POLARITY_TAXONOMY
    assert set(V9StagedGeneralizationOutput.model_fields) == set(
        V8StagedGeneralizationOutput.model_fields
    )
    assert set(V9EventLinks.model_fields) == set(EventLinks.model_fields)
    assert set(V9EventArgument.model_fields) == set(EventArgument.model_fields)
    assert hashlib.sha256(
        json.dumps(schema, sort_keys=True).encode()
    ).hexdigest() != hashlib.sha256(
        json.dumps(
            V8StagedGeneralizationOutput.model_json_schema(), sort_keys=True
        ).encode()
    ).hexdigest()

    for path in sorted(
        (REPO / "docs/validation/results").glob(
            "2026-07-22-staged-generalization-v8-generalization-*-raw.json"
        )
    ):
        prior = V8StagedGeneralizationOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        versioned = V9StagedGeneralizationOutput.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        assert versioned.model_dump(mode="json") == prior.model_dump(mode="json")


def test_v9_prompt_is_source_general_and_matches_argument_taxonomy() -> None:
    prompt = DEFAULT_PATHS.prompt.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    assert not any(term in normalized for term in CASE_SPECIFIC_TERMS)
    assert (
        "In a `CLASSIFICATION` event, link the classified entity as "
        "`AFFECTED_ENTITY`" in normalized
    )
    assert "link the restricting entity as `CONTEXTUAL_PARTICIPANT`" in normalized
    assert (
        "Do not duplicate it as `OUTCOME` unless it independently participates in "
        "another event" in normalized
    )
    assert "Polarity records scientific result status, not surface grammar" in normalized
    assert (
        "independent of whether the sentence grammatically asserts that proposition"
        in normalized
    )


def test_v9_reuses_panel_model_and_frozen_v5_grader() -> None:
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


def test_v9_preregistration_reproduces_at_pin_and_provider_input_remains_blind() -> (
    None
):
    with pytest.raises(
        V9PreflightError,
        match="independently recomputed frozen state",
    ):
        verify(DEFAULT_PATHS)
    provenance = verify_provenance()
    assert provenance["historical_code_manifest_match"] is True
    assert provenance["current_checkout_code_manifest_match"] is False

    preregistration = cast(
        "dict[str, object]",
        json.loads(DEFAULT_PATHS.preregistration.read_text(encoding="utf-8")),
    )
    frozen = cast("dict[str, object]", preregistration["frozen_state"])
    change = cast("dict[str, object]", preregistration["change_control"])
    rules = cast("dict[str, object]", preregistration["rules"])

    assert preregistration["schema_version"] == "artana.staged_generalization.v9"
    assert preregistration["experiment_id"] == "staged-generalization-v9"
    assert preregistration["supersedes_terminal"] == "PIVOT_WITH_EVIDENCE"
    assert change["single_scientific_change"] == "CLASSIFICATION_ARGUMENT_BOUNDARY"
    assert change["classification_argument_rule"] == CLASSIFICATION_ARGUMENT_TAXONOMY
    assert change["polarity_rule"] == POLARITY_TAXONOMY
    assert change["historical_v8_rescored"] is False
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
        assert "V8 output" not in value


@pytest.mark.parametrize("term", CASE_SPECIFIC_TERMS)
def test_v9_preflight_rejects_case_specific_prompt_terms(
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

    with pytest.raises(V9PreflightError, match="case-specific"):
        verify(paths)


def test_v9_preflight_rejects_removal_of_argument_rule(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    prompt = paths.prompt.read_text(encoding="utf-8").replace(
        "link the classified entity as `AFFECTED_ENTITY`",
        "choose a role for the classified entity",
    )
    paths.prompt.write_text(prompt, encoding="utf-8")

    with pytest.raises(V9PreflightError, match="semantic rules"):
        verify(paths)


def test_v9_runner_stops_on_scientific_canary_with_separate_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    canary = V9StagedGeneralizationOutput.model_validate_json(
        V8_CANARY_RAW.read_text(encoding="utf-8")
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
    ) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(failing, "response-v9-failed-canary")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(runner.V9Runtime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "PIVOT_WITH_EVIDENCE"
    assert calls == ["generalization-comparison-canary"]
    assert result["experiment_id"] == "staged-generalization-v9"
    assert result["scientific_change"] == "CLASSIFICATION_ARGUMENT_BOUNDARY"
    assert result["direction_fidelity"] == "0/1"
    assert result["provider_calls"] == 1
    assert result["qualification_credit"] is False
    assert result["graph_writes"] == 0
    assert paths.case(calls[0]).raw_output.exists()
    assert not V5_PATHS.case(calls[0]).attempt.samefile(paths.case(calls[0]).attempt)


def test_v9_exposes_frozen_drug_span_as_deterministically_ambiguous() -> None:
    case = next(
        item for item in build_panel() if item.case_id == "generalization-drug-sensitivity"
    )
    sentence = case.local_context.strip()

    assert sentence.count("5-FU") == 2
    with pytest.raises(GeneralizationAnchorError, match="child text.*ambiguous"):
        resolve_in_context(
            source=case.source,
            context_start=case.context_start,
            context_end=case.context_end,
            exact_evidence=sentence,
            exact_text="5-FU",
        )


def test_checked_in_v9_result_recomputes_and_preserves_fail_fast_custody() -> None:
    result = json.loads(DEFAULT_PATHS.result.read_text(encoding="utf-8"))
    panel = {case.case_id: case for case in build_panel()}
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    case_ids = [item["case_id"] for item in result["cases"]]
    outputs = [
        V9StagedGeneralizationOutput.model_validate_json(
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
    assert result["stopped_after_case_id"] == "generalization-drug-sensitivity"
    assert result["provider_calls"] == len(case_ids) == 5
    assert result["grading_policy_sha256"] == policy_sha256(policy)
    assert result["passed_case_count"] == 4
    assert result["unsupported_claim_count"] == 5
    assert result["all_receipts_valid"] is True
    assert result["qualification_credit"] is False
    assert result["trusted_promotion"] is False
    assert result["graph_writes"] == 0

    preregistration_sha256 = hashlib.sha256(
        DEFAULT_PATHS.preregistration.read_bytes()
    ).hexdigest()
    schema_sha256 = hashlib.sha256(
        json.dumps(
            V9StagedGeneralizationOutput.model_json_schema(),
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
    uncalled = DEFAULT_PATHS.case("generalization-explicit-nested-cause")
    assert not any(
        path.exists()
        for path in (
            uncalled.attempt,
            uncalled.bundle,
            uncalled.receipt,
            uncalled.raw_output,
        )
    )
