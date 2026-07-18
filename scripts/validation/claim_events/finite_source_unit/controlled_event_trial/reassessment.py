"""Offline corrected-matcher reassessment over the immutable adaptive replay."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.matching import (
    expert_core_event_match_count,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.reassessment_gate import (
    ReassessmentGateInputs,
    reassessment_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.selection import (
    select_controlled_event_trial,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_frames.evidence import collect_repository_evidence

if TYPE_CHECKING:
    from collections.abc import Mapping

    from scripts.validation.claim_events.contracts import NaryClaimFixture

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_EXPECTED_FILE_SHA256: Final = (
    "bbf3a697d5b1b221d8fcc2e36a52273e280463de9f4b9c1ed8c50f0fb0fed0a3"
)
_EXPECTED_REPORT_SHA256: Final = (
    "e6976e2ba0262a96c9cba5866c7307bc9c5cf89f30e10888e9eb43a8d6f6df5b"
)
_EXPECTED_PROVIDER_RECEIPT_COUNT: Final = 2


def run_controlled_event_reassessment(
    *,
    fixture: NaryClaimFixture,
    replay_artifact: Path,
    run_id: str,
) -> dict[str, object]:
    """Recalculate the gate without changing or re-calling agent output."""

    require_frozen_development_fixture(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("controlled-event reassessment requires a clean worktree")
    payload, artifact_sha256 = _load_replay_artifact(replay_artifact)
    selection = select_controlled_event_trial(fixture)
    unit = payload.get("unit")
    source_identity_verified = isinstance(unit, dict) and all(
        unit.get(field) == value
        for field, value in {
            "unit_id": selection.unit.unit_id,
            "source_sha256": selection.unit.source_sha256,
            "input_sha256": selection.unit.input_sha256,
        }.items()
    )
    trusted_events = _trusted_events(payload)
    core_match_count = expert_core_event_match_count(
        selection.expert_events,
        trusted_events,
    )
    gate = cast("dict[str, object]", payload["gate"])
    requirements = cast("dict[str, object]", gate["requirements"])
    failed_requirements = {
        name for name, passed in requirements.items() if passed is not True
    }
    receipts = payload.get("provider_receipts")
    prior_receipts_verified = (
        isinstance(receipts, dict)
        and receipts.get("status") == "verified_live"
        and receipts.get("verified_count") == _EXPECTED_PROVIDER_RECEIPT_COUNT
    )
    inputs = ReassessmentGateInputs(
        artifact_verified=True,
        adaptive_replay_declared=True,
        offline_reassessment_declared=True,
        model_call_count=0,
        source_identity_verified=source_identity_verified,
        prior_only_failed_requirement_was_matcher=(
            failed_requirements == {"sealed_expert_core_recovered"}
        ),
        prior_provider_receipts_verified=prior_receipts_verified,
        trusted_event_count=len(trusted_events),
        expert_core_event_match_count=core_match_count,
    )
    new_requirements = reassessment_gate_requirements(inputs)
    passed = all(new_requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_controlled_event_reassessment.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "task_id": "offline_controlled_event_reassessment",
        "repository_evidence": repository_evidence,
        "authorization": {
            "adaptive_replay_artifact_sha256": artifact_sha256,
            "adaptive_replay_report_sha256": _EXPECTED_REPORT_SHA256,
        },
        "prior_gate": gate,
        "reassessment_inputs": asdict(inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "PROCEED_TO_NEW_FRESH_UNIT"
                if passed
                else "STOP_AND_RECALIBRATE_EVENT_MATCHING"
            ),
            "requirements": new_requirements,
        },
        "conclusion_scope": {
            "offline_reassessment": True,
            "model_call_count": 0,
            "adaptive_replay": True,
            "qualification_eligible": False,
            "benchmark_credit_awarded": False,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


def _load_replay_artifact(path: Path) -> tuple[dict[str, object], str]:
    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha256 != _EXPECTED_FILE_SHA256:
        raise RuntimeError("adaptive replay artifact changed")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("adaptive replay artifact must be a JSON object")
    if (
        payload.get("schema_version") != "tg04_controlled_event_replay.v1"
        or payload.get("experiment_mode") != "adaptive_replay"
        or payload.get("report_sha256") != _EXPECTED_REPORT_SHA256
    ):
        raise RuntimeError("adaptive replay custody changed")
    gate = payload.get("gate")
    if not isinstance(gate, dict) or not isinstance(gate.get("requirements"), dict):
        raise TypeError("adaptive replay artifact lacks gate requirements")
    return payload, file_sha256


def _trusted_events(payload: dict[str, object]) -> list[Mapping[str, object]]:
    value = payload.get("trusted_events")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError("adaptive replay trusted events are invalid")
    return cast("list[Mapping[str, object]]", value)


__all__ = ["run_controlled_event_reassessment"]
