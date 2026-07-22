from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.contracts import (
    DiscoveryCandidate,
    EventDiscoveryOutput,
    EventModifierFinding,
    EventParticipantInventory,
    EventRoleAssignment,
    EventVerification,
    ModifierDecision,
    ModifierOutput,
    ParticipantCandidate,
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    RoleAssignment,
    RoleAssignmentOutput,
    SourceArgumentRole,
    SourceEntityType,
    StatementKind,
    VerificationAxes,
    VerificationAxisDecision,
    VerificationAxisFinding,
    VerificationOutput,
    VerificationVerdict,
)
from scripts.validation.public_gold.staged_event.live_execution import (
    ArtifactPaths,
    StageCallContext,
    run_comparison,
)
from scripts.validation.public_gold.staged_event.preflight import (
    build_preregistration,
)
from scripts.validation.public_gold.staged_event.registry import StageSpec

ROOT = Path(__file__).parents[2]
PASSAGE = "Decrease in c-Myc activity enhances cancer cell sensitivity to vinblastine."


def test_five_stage_orchestration_writes_auditable_terminal_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    preregistration_payload = build_preregistration(ROOT)
    preregistration_payload["execution_authorized"] = True
    preregistration_payload["status"] = "FROZEN_AUTHORIZED_FOR_ONE_EXECUTION"
    preregistration = tmp_path / "preregistration.json"
    preregistration.write_text(json.dumps(preregistration_payload), encoding="utf-8")
    stage_names: list[str] = []

    def fake_verify(*_args, **_kwargs) -> dict[str, object]:
        return {"status": "PREFLIGHT_PASSED"}

    def fake_stage(*, spec: StageSpec, context: StageCallContext, **kwargs):
        stage_names.append(spec.name)
        context.ledger.record(
            spec.name,
            {
                "response_id": f"resp-{spec.name}",
                "usage": {
                    "total_tokens": 10,
                    "output_tokens": 5,
                    "cost_usd": 0.001,
                    "latency_seconds": 0.1,
                },
            },
        )
        if spec.name == "discovery":
            return EventDiscoveryOutput(
                decision="DISCOVERED",
                candidates=(
                    DiscoveryCandidate(
                        trigger_text="enhances",
                        event_passage=PASSAGE,
                        source_event_type=SourceEventType.POSITIVE_REGULATION,
                        statement_kind=StatementKind.EXPLICIT_RESULT,
                        explanation="The supplied sentence states the event.",
                    ),
                ),
                abstention_reason=None,
            )
        payload = kwargs["payload"]
        events = (
            payload["assembled_event_claims"]
            if spec.name == "verification"
            else payload["events"]
        )
        event_id = events[0]["event_id"]
        if spec.name == "participants":
            return ParticipantInventoryOutput(
                inventories=(
                    EventParticipantInventory(
                        event_id=event_id,
                        decision="INVENTORIED",
                        participants=(
                            ParticipantCandidate(
                                participant_key="myc",
                                exact_text="c-Myc",
                                occurrence_id="occurrence-0",
                                occurrence_index=0,
                                candidate_target_kind=(
                                    ParticipantTargetKind.PARTICIPANT
                                ),
                                source_entity_type=(
                                    SourceEntityType.GENE_OR_GENE_PRODUCT
                                ),
                                explanation="The participant is explicit.",
                            ),
                            ParticipantCandidate(
                                participant_key="vinblastine",
                                exact_text="vinblastine",
                                occurrence_id="occurrence-0",
                                occurrence_index=0,
                                candidate_target_kind=(
                                    ParticipantTargetKind.PARTICIPANT
                                ),
                                source_entity_type=SourceEntityType.SIMPLE_CHEMICAL,
                                explanation="The participant is explicit.",
                            ),
                        ),
                        abstention_reason=None,
                    ),
                )
            )
        if spec.name == "roles":
            return RoleAssignmentOutput(
                events=(
                    EventRoleAssignment(
                        event_id=event_id,
                        decision="ASSIGNED",
                        assignments=(
                            RoleAssignment(
                                participant_key="myc",
                                source_role=SourceArgumentRole.CAUSE,
                                target_kind=ParticipantTargetKind.PARTICIPANT,
                                target_event_id=None,
                                explanation="The source supports this role.",
                            ),
                            RoleAssignment(
                                participant_key="vinblastine",
                                source_role=SourceArgumentRole.THEME,
                                target_kind=ParticipantTargetKind.PARTICIPANT,
                                target_event_id=None,
                                explanation="The source supports this role.",
                            ),
                        ),
                        abstention_reason=None,
                    ),
                )
            )
        if spec.name == "modifiers":
            return ModifierOutput(
                events=(
                    EventModifierFinding(
                        event_id=event_id,
                        decision=ModifierDecision.NEITHER,
                        exact_evidence=None,
                        explanation="No local negation or speculation is present.",
                    ),
                )
            )
        if spec.name == "verification":
            return VerificationOutput(
                events=(
                    EventVerification(
                        event_id=event_id,
                        verdict=VerificationVerdict.ENTAILED,
                        exact_evidence=PASSAGE,
                        axes=_passing_axes(),
                        explanation="The complete event is explicit.",
                        falsification_explanation=(
                            "Removing the event wording would remove support."
                        ),
                    ),
                ),
                missing_supported_events=(),
            )
        raise AssertionError(f"unexpected stage: {spec.name}")

    monkeypatch.setattr(
        "scripts.validation.public_gold.staged_event.live_execution.verify_preregistration",
        fake_verify,
    )
    monkeypatch.setattr(
        "scripts.validation.public_gold.staged_event.live_execution._run_stage",
        fake_stage,
    )
    artifacts = ArtifactPaths(
        receipt=tmp_path / "receipt.json",
        result=tmp_path / "result.json",
        report=tmp_path / "report.md",
        raw_output_directory=tmp_path / "raw",
    )

    decision = run_comparison(
        repository_root=ROOT,
        preregistration_path=preregistration,
        artifacts=artifacts,
    )
    result = json.loads(artifacts.result.read_text(encoding="utf-8"))
    report = artifacts.report.read_text(encoding="utf-8")

    assert decision == "STAGED_NO_MEANINGFUL_IMPROVEMENT"
    assert stage_names == [
        "discovery",
        "participants",
        "roles",
        "modifiers",
        "verification",
    ]
    assert result["accounting"]["provider_creation_calls"] == 5
    assert result["completion_used"] is False
    assert set(result["stage_outputs"]) == set(stage_names)
    assert "Stage Outputs And Abstentions" in report


def _passing_axes() -> VerificationAxes:
    finding = VerificationAxisFinding(
        decision=VerificationAxisDecision.PASS,
        explanation="The complete typed-event axis passes.",
    )
    return VerificationAxes(
        event_type=finding,
        trigger=finding,
        participants=finding,
        roles=finding,
        nesting=finding,
        modifier=finding,
        evidence=finding,
    )
