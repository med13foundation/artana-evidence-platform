"""Fail-closed preregistration tests for the fresh-CG experiment."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1 import (
    preflight,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    BRANCH,
    DEFAULT_PATHS,
)


def test_preregistration_recomputes_all_frozen_science_and_governance() -> None:
    value = preflight.build_preregistration(DEFAULT_PATHS)
    frozen = value["frozen_state"]
    governance = value["review_governance"]
    rules = value["execution_rules"]

    assert isinstance(frozen, dict)
    assert isinstance(governance, dict)
    assert isinstance(rules, dict)
    assert frozen["unresolved_reference_fields"] == []
    assert frozen["case_order"] == [
        "fresh-cg-pmid-21963494-e3",
        "fresh-cg-pmid-2681013-e5",
        "fresh-cg-pmid-16098727-e5",
        "fresh-cg-pmid-7904970-e11",
        "fresh-cg-pmid-19648108-e11",
        "fresh-cg-pmid-11306510-e1",
        "fresh-cg-pmid-18841154-e12",
        "fresh-cg-pmid-20448329-e6",
    ]
    assert governance["internet_enabled"] is True
    assert governance["model_output_blinded"] is True
    assert governance["other_reviewer_output_blinded"] is True
    assert governance["review_only_scoring"] == "NO_AUTOMATIC_CREDIT_OR_PENALTY"
    assert rules["one_creation_call_per_case"] is True
    assert rules["stop_before_next_on_first_failure"] is True
    assert rules["fallback"] is False
    assert rules["graph_writes"] is False
    assert rules["qualification"] is False


def test_preregistration_rejects_mutated_reviewer_schema(tmp_path: Path) -> None:
    schema = json.loads(DEFAULT_PATHS.review_schema.read_text(encoding="utf-8"))
    schema["description"] = "mutated"
    candidate = tmp_path / "review.schema.json"
    candidate.write_text(json.dumps(schema), encoding="utf-8")

    with pytest.raises(preflight.FreshCGPreflightError, match="strict contract"):
        preflight.build_preregistration(
            replace(DEFAULT_PATHS, review_schema=candidate)
        )


def test_preregistration_rejects_tiebreak_request_not_derived_from_disputes(
    tmp_path: Path,
) -> None:
    request = json.loads(
        DEFAULT_PATHS.tiebreak_request.read_text(encoding="utf-8")
    )
    request["disputed_field_ids"] = request["disputed_field_ids"][:-1]
    candidate = tmp_path / "tiebreak.json"
    candidate.write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(preflight.FreshCGPreflightError, match="primary disagreements"):
        preflight.build_preregistration(
            replace(DEFAULT_PATHS, tiebreak_request=candidate)
        )


def test_remote_gate_rejects_local_remote_head_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_git(*arguments: str) -> str:
        if arguments == ("rev-parse", "--abbrev-ref", "HEAD"):
            return BRANCH
        if arguments == ("rev-parse", "HEAD"):
            return "local-head"
        if arguments[0] == "ls-remote":
            return f"remote-head\trefs/heads/{BRANCH}"
        raise AssertionError(arguments)

    monkeypatch.setattr(preflight, "_git", fake_git)

    with pytest.raises(preflight.FreshCGPreflightError, match="live remote"):
        preflight._verify_remote_gate(DEFAULT_PATHS)
