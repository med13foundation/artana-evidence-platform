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
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as V5_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    build_panel,
    panel_json,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v6 import runner
from scripts.validation.public_gold.staged_event.generalization.repair_v6.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v6.preflight import (
    V6PreflightError,
    provider_input,
    verify,
    write_candidate,
)

REPO = Path(__file__).resolve().parents[2]
V5_CANARY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v5-generalization-comparison-canary-raw.json"
)
CASE_SPECIFIC_TERMS = (
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
    output: StagedGeneralizationOutput,
    response_id: str,
) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
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


def test_v6_prompt_is_source_general_and_contains_both_repairs() -> None:
    prompt = DEFAULT_PATHS.prompt.read_text(encoding="utf-8")
    normalized = " ".join(prompt.split())

    assert not any(term in normalized for term in CASE_SPECIFIC_TERMS)
    assert (
        "ground the participant to the antecedent's exact contiguous source text"
        in normalized
    )
    assert "Do not use the referring grammar itself as `exact_text`" in normalized
    assert (
        "independent of whether the sentence grammatically asserts that proposition"
        in normalized
    )
    assert "Use `UNCERTAIN`" in normalized
    assert "Use `ASSERTED` for an unqualified event" in normalized


def test_v6_reuses_panel_schema_model_and_frozen_grader() -> None:
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


def test_v6_preregistration_is_reproducible_and_provider_input_remains_blind() -> (
    None
):
    preregistration = verify(DEFAULT_PATHS)
    change = cast("dict[str, object]", preregistration["change_control"])
    rules = cast("dict[str, object]", preregistration["rules"])

    assert preregistration["experiment_id"] == "staged-generalization-v6"
    assert preregistration["supersedes_terminal"] == "PIVOT_WITH_EVIDENCE"
    assert change["single_scientific_change"] == (
        "SOURCE_GENERAL_REFERENTIAL_GROUNDING"
    )
    assert change["historical_v5_rescored"] is False
    assert change["grader_changed"] is False
    assert change["panel_changed"] is False
    assert change["schema_changed"] is False
    assert change["model_changed"] is False
    assert rules["silent_retries"] == 0
    assert rules["fallback"] is False
    assert rules["graph_writes"] is False
    assert rules["promotion"] is False
    for case in build_panel():
        value = provider_input(DEFAULT_PATHS, case.case_id)
        assert "dual_lane_policy" not in value
        assert "acceptable_triggers" not in value
        assert "reference_basis" not in value
        assert "PERMITTED_CONTEXT" not in value
        assert "V5 output" not in value


def test_v6_preflight_rejects_prompt_drift_and_case_specific_terms(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    verify(paths)
    paths.prompt.write_text(
        paths.prompt.read_text(encoding="utf-8") + "\n947 variants\n",
        encoding="utf-8",
    )

    with pytest.raises(V6PreflightError, match="case-specific"):
        verify(paths)


def test_v6_runner_stops_on_scientific_canary_with_separate_custody(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    canary = StagedGeneralizationOutput.model_validate_json(
        V5_CANARY_RAW.read_text(encoding="utf-8")
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
    ) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(failing, "response-v6-failed-canary")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(runner.V6Runtime(call), paths=paths)
    result = json.loads(paths.result.read_text(encoding="utf-8"))

    assert decision == "PIVOT_WITH_EVIDENCE"
    assert calls == ["generalization-comparison-canary"]
    assert result["experiment_id"] == "staged-generalization-v6"
    assert result["scientific_change"] == "SOURCE_GENERAL_REFERENTIAL_GROUNDING"
    assert result["direction_fidelity"] == "0/1"
    assert result["provider_calls"] == 1
    assert result["qualification_credit"] is False
    assert result["graph_writes"] == 0
    assert paths.case(calls[0]).raw_output.exists()
    assert not V5_PATHS.case(calls[0]).attempt.samefile(paths.case(calls[0]).attempt)
