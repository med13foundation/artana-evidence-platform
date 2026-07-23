"""Fail-closed static verification for V10 without a provider call."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.validation.public_gold.staged_event.generalization.repair_v10.config import (
    DEFAULT_PATHS,
    V10Paths,
)

_BOUNDARY_START = "\nNamed biomedical occurrence boundary:\n"
_BOUNDARY_END = "\nFocus-gated referential grounding:"


def verify(paths: V10Paths = DEFAULT_PATHS) -> dict[str, object]:
    preregistration = _object(
        json.loads(paths.preregistration.read_text(encoding="utf-8"))
    )
    frozen = _object(preregistration["frozen_state"])
    evidence = _object(preregistration["evidence"])
    execution = _object(preregistration["execution"])
    change = _object(preregistration["change_control"])
    if _sha256(paths.v9_prompt) != frozen["v9_prompt_sha256"]:
        raise ValueError("V9 prompt pin changed")
    if _sha256(paths.prompt) != frozen["prompt_sha256"]:
        raise ValueError("V10 prompt pin changed")
    if _sha256(paths.consensus) != evidence["root_cause_consensus_sha256"]:
        raise ValueError("V10 consensus evidence changed")
    if _sha256(paths.v3_reference) != frozen["v3_exposed_reference_sha256"]:
        raise ValueError("V10 exposed reference changed")
    if _sha256(paths.v3_replay) != frozen["v3_exposed_replay_sha256"]:
        raise ValueError("V10 exposed replay changed")
    _verify_single_prompt_change(paths)
    if change["single_scientific_change"] != "NAMED_BIOMEDICAL_OCCURRENCE_BOUNDARY":
        raise ValueError("V10 contains an unregistered scientific change")
    if execution != {
        "fresh_case_calls_allowed": False,
        "graph_writes": False,
        "provider_calls_during_this_task": 0,
        "remaining_fresh_cases_preserved": 7,
        "status": "NOT_EXECUTED",
        "trusted_graph_promotion": False,
    }:
        raise ValueError("V10 execution boundary changed")
    return {
        "status": "PASS",
        "experiment_id": preregistration["experiment_id"],
        "single_scientific_change": change["single_scientific_change"],
        "prompt_sha256": frozen["prompt_sha256"],
        "provider_calls": 0,
        "remaining_fresh_cases_preserved": 7,
        "graph_writes": 0,
        "qualification_credit": False,
    }


def _verify_single_prompt_change(paths: V10Paths) -> None:
    v9 = paths.v9_prompt.read_text(encoding="utf-8")
    v10 = paths.prompt.read_text(encoding="utf-8")
    if v10.count(_BOUNDARY_START) != 1 or v10.count(_BOUNDARY_END) != 1:
        raise ValueError("V10 occurrence-boundary section is absent or duplicated")
    start = v10.index(_BOUNDARY_START)
    end = v10.index(_BOUNDARY_END)
    without_boundary = v10[:start] + v10[end:]
    normalized = without_boundary.replace(
        "# Staged Scientific Event Generalization V10",
        "# Staged Scientific Event Generalization V9",
        1,
    )
    if normalized != v9:
        raise ValueError("V10 changed content outside the registered boundary rule")


def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["verify"]
