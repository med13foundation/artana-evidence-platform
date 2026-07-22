"""Execute one frozen four-call Luna semantic-context experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    execute_background_provider_call,
)
from scripts.validation.public_gold.bionlp_cg_event_projection import (
    project_development_directory,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
    ProviderRequest,
)
from scripts.validation.public_gold.lossless_event_scoring import (
    LosslessEventScore,
    score_scientific_event_document,
)
from scripts.validation.public_gold.staged_event.assembly import (
    AssemblyInputs,
    StagedAssembly,
    StagedAssemblyError,
    assemble_staged_document,
)
from scripts.validation.public_gold.staged_event.context_experiment.panel import (
    CONTROL_IDS,
    PANEL_IDS,
    ContextPanel,
    build_context_panel,
)
from scripts.validation.public_gold.staged_event.context_experiment.preflight import (
    PROMPTS,
    RESULT_PATH,
    SOURCE_PATH,
    verify_preregistration,
)
from scripts.validation.public_gold.staged_event.contracts import (
    ModifierDecision,
    ModifierOutput,
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    RoleAssignmentOutput,
    VerificationOutput,
    VerificationVerdict,
)
from scripts.validation.public_gold.staged_event.diagnostic_projection import (
    project_dependency_closed_subgraph,
)
from scripts.validation.public_gold.staged_event.live_execution import (
    BudgetLedger,
    StagedComparisonError,
)
from scripts.validation.public_gold.staged_event.paths import repository_root
from scripts.validation.public_gold.staged_event.prompting import (
    build_provider_format,
    build_stage_input,
    load_prompt,
)

_OutputT = TypeVar("_OutputT", bound=BaseModel)
STAGES = ("participants", "roles", "modifiers", "verification")
OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    "participants": ParticipantInventoryOutput,
    "roles": RoleAssignmentOutput,
    "modifiers": ModifierOutput,
    "verification": VerificationOutput,
}


@dataclass(frozen=True, slots=True)
class OutputPaths:
    receipt: Path
    result: Path
    report: Path
    raw_directory: Path


@dataclass(frozen=True, slots=True)
class StageEnvironment:
    root: Path
    preregistration_path: Path
    paths: OutputPaths
    ledger: BudgetLedger
    budgets: dict[str, object]
    model: dict[str, object]
    source_sha256: str


@dataclass(frozen=True, slots=True)
class MechanicalInputs:
    baseline_outputs: tuple[object, ...]
    final_outputs: tuple[object, ...]
    baseline_assembly: StagedAssembly
    final_assembly: StagedAssembly
    baseline_score: LosslessEventScore
    final_score: LosslessEventScore


def execute_context_experiment(
    *, preregistration_path: Path, paths: OutputPaths
) -> str:
    root = repository_root()
    preflight = verify_preregistration(root, preregistration_path)
    preregistration = _load_object(preregistration_path)
    budgets = _object(preregistration, "budgets")
    model = _object(_object(preregistration, "frozen_state"), "model")
    panel = build_context_panel(
        result_path=root / RESULT_PATH,
        source_path=root / SOURCE_PATH,
    )
    source_text = (root / SOURCE_PATH).read_text(encoding="utf-8")
    ledger = BudgetLedger(
        max_calls=_integer(budgets, "max_agent_calls"),
        max_tokens=_integer(budgets, "max_total_tokens"),
        max_output_tokens_per_call=_integer(
            budgets, "max_output_tokens_per_call"
        ),
        max_cost_usd=_number(budgets, "max_total_cost_usd"),
        max_latency_seconds=_number(budgets, "max_total_latency_seconds"),
    )
    v2 = _load_object(root / RESULT_PATH)
    baseline_outputs = _parse_outputs(_object(v2, "stage_outputs"))
    baseline_assembly, baseline_score = _assemble_and_score(
        root=root,
        panel=panel,
        source_text=source_text,
        outputs=baseline_outputs,
        producer="preserved-v2-panel-baseline",
    )
    stage_outputs: dict[str, object] = {}
    environment = StageEnvironment(
        root=root,
        preregistration_path=preregistration_path,
        paths=paths,
        ledger=ledger,
        budgets=budgets,
        model=model,
        source_sha256=panel.source_sha256,
    )
    current_stage = "preflight"
    try:
        participants = _call_stage(
            stage="participants",
            output_model=ParticipantInventoryOutput,
            payload={"context_packets": list(panel.packets)},
            environment=environment,
        )
        current_stage = "participants"
        _require_stage_ids(participants.inventories)
        stage_outputs[current_stage] = participants.model_dump(mode="json")

        roles = _call_stage(
            stage="roles",
            output_model=RoleAssignmentOutput,
            payload={
                "context_packets": list(panel.packets),
                "participant_inventory": participants.model_dump(mode="json"),
            },
            environment=environment,
        )
        current_stage = "roles"
        _require_stage_ids(roles.events)
        _require_permitted_references(roles)
        stage_outputs[current_stage] = roles.model_dump(mode="json")

        modifiers = _call_stage(
            stage="modifiers",
            output_model=ModifierOutput,
            payload={
                "context_packets": list(panel.packets),
                "participant_inventory": participants.model_dump(mode="json"),
                "role_assignments": roles.model_dump(mode="json"),
            },
            environment=environment,
        )
        current_stage = "modifiers"
        _require_stage_ids(modifiers.events)
        stage_outputs[current_stage] = modifiers.model_dump(mode="json")

        verification = _call_stage(
            stage="verification",
            output_model=VerificationOutput,
            payload={
                "context_packets": list(panel.packets),
                "participant_inventory": participants.model_dump(mode="json"),
                "role_assignments": roles.model_dump(mode="json"),
                "modifiers": modifiers.model_dump(mode="json"),
            },
            environment=environment,
        )
        current_stage = "verification"
        _require_stage_ids(verification.events)
        stage_outputs[current_stage] = verification.model_dump(mode="json")

        final_outputs = (participants, roles, modifiers, verification)
        final_assembly, final_score = _assemble_and_score(
            root=root,
            panel=panel,
            source_text=source_text,
            outputs=final_outputs,
            producer="luna-context-experiment-v1",
        )
        mechanical = _mechanical_metrics(
            MechanicalInputs(
                baseline_outputs=baseline_outputs,
                final_outputs=final_outputs,
                baseline_assembly=baseline_assembly,
                final_assembly=final_assembly,
                baseline_score=baseline_score,
                final_score=final_score,
            )
        )
        result = {
            "schema_version": "artana.public_gold.luna_context_result.v1",
            "decision": "PENDING_SCIENTIFIC_ADJUDICATION",
            "qualification_status": "EXPOSED_DEVELOPMENT_NON_QUALIFYING",
            "preflight": preflight,
            "model": model,
            "stage_outputs": stage_outputs,
            "baseline_score": baseline_score.as_json(),
            "final_score": final_score.as_json(),
            "mechanical_metrics": mechanical,
            "accounting": ledger.as_json(),
            "terminal_rules": _object(preregistration, "terminal_rules"),
            "trusted_promotion": False,
        }
        _write_outputs(paths, ledger, result)
        return "PENDING_SCIENTIFIC_ADJUDICATION"  # noqa: TRY300
    except (ProviderExecutionError, StagedAssemblyError, StagedComparisonError) as exc:
        result = {
            "schema_version": "artana.public_gold.luna_context_result.v1",
            "decision": "INVALID_EXPERIMENT",
            "qualification_status": "EXPOSED_DEVELOPMENT_NON_QUALIFYING",
            "preflight": preflight,
            "failure": {
                "stage": current_stage,
                "boundary": getattr(exc, "stage", type(exc).__name__),
                "root_cause": getattr(exc, "root_cause", str(exc)),
                "diagnostics": getattr(exc, "diagnostics", {}),
            },
            "stage_outputs": stage_outputs,
            "accounting": ledger.as_json(),
            "trusted_promotion": False,
        }
        _write_outputs(paths, ledger, result)
        return "INVALID_EXPERIMENT"


def _call_stage(
    *,
    stage: str,
    output_model: type[_OutputT],
    payload: dict[str, object],
    environment: StageEnvironment,
) -> _OutputT:
    environment.ledger.ensure_call_available()
    remaining_tokens, remaining_cost, remaining_latency = environment.ledger.remaining()
    if min(remaining_tokens, remaining_cost, remaining_latency) <= 0:
        raise StagedComparisonError("aggregate budget exhausted before next stage")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise StagedComparisonError("OPENAI_API_KEY is absent")
    provider_input = build_stage_input(
        prompt=load_prompt(environment.root, PROMPTS[stage]),
        document_id="PMID-16428936",
        source_sha256=environment.source_sha256,
        payload=payload,
    )
    execution = execute_background_provider_call(
        api_key=api_key,
        output_model=output_model,
        transport_budgets=BackgroundExecutionBudgets(
            acknowledgement_timeout_seconds=_number(
                environment.budgets, "acknowledgement_timeout_seconds"
            ),
            polling_interval_seconds=_number(
                environment.budgets, "polling_interval_seconds"
            ),
            max_polling_seconds=min(
                _number(
                    environment.budgets, "max_polling_seconds_per_call"
                ),
                remaining_latency,
            ),
        ),
        request=ProviderRequest(
            provider_input=provider_input,
            provider_format=build_provider_format(
                output_model,
                description=f"Focused Luna {stage} output for fixed V2 events.",
            ),
            provider_model_id=_string(environment.model, "provider_model_id"),
            reasoning_effort=_string(environment.model, "reasoning_effort"),
            max_output_tokens=_integer(
                environment.budgets, "max_output_tokens_per_call"
            ),
            max_total_tokens=remaining_tokens,
            max_cost_usd=remaining_cost,
            max_latency_seconds=remaining_latency,
            pricing={
                key: float(value)
                for key, value in _object(
                    environment.budgets, "pricing_usd_per_token"
                ).items()
                if isinstance(value, int | float)
            },
            metadata={
                "artana_experiment": "luna-context-semantic-v1",
                "artana_preregistration_sha256": _sha256(
                    environment.preregistration_path
                ),
                "artana_source_sha256": environment.source_sha256,
                "artana_stage": stage,
            },
        ),
    )
    environment.paths.raw_directory.mkdir(parents=True, exist_ok=True)
    (environment.paths.raw_directory / f"{stage}.json").write_text(
        json.dumps(
            {
                "acknowledgement": execution.acknowledgement_response,
                "terminal": execution.terminal_response,
                "confirmation": execution.confirmation_response,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        **execution.receipt,
        "provider_input_sha256": hashlib.sha256(provider_input.encode()).hexdigest(),
        "stage_output_sha256": _canonical_sha256(
            execution.extraction.model_dump(mode="json")
        ),
    }
    environment.ledger.record(stage, receipt)
    return execution.extraction


def _assemble_and_score(
    *,
    root: Path,
    panel: ContextPanel,
    source_text: str,
    outputs: tuple[object, ...],
    producer: str,
) -> tuple[StagedAssembly, LosslessEventScore]:
    participants, roles, modifiers, verification = outputs
    if not isinstance(participants, ParticipantInventoryOutput):
        raise StagedComparisonError("participant output type changed")
    if not isinstance(roles, RoleAssignmentOutput):
        raise StagedComparisonError("role output type changed")
    if not isinstance(modifiers, ModifierOutput):
        raise StagedComparisonError("modifier output type changed")
    if not isinstance(verification, VerificationOutput):
        raise StagedComparisonError("verification output type changed")
    candidates = panel.candidates
    projection = project_dependency_closed_subgraph(
        candidates=candidates,
        participants=participants,
        roles=roles,
        modifiers=modifiers,
        verifications=verification,
    )
    retained = set(projection.retained_event_ids)
    assembly = assemble_staged_document(
        AssemblyInputs(
            candidates=tuple(item for item in candidates if item.event_id in retained),
            participant_output=ParticipantInventoryOutput(
                inventories=tuple(
                    item for item in participants.inventories if item.event_id in retained
                )
            ),
            role_output=RoleAssignmentOutput(
                events=tuple(item for item in roles.events if item.event_id in retained)
            ),
            modifier_output=ModifierOutput(
                events=tuple(
                    item for item in modifiers.events if item.event_id in retained
                )
            ),
            verification_output=VerificationOutput(
                events=tuple(
                    item for item in verification.events if item.event_id in retained
                ),
                missing_supported_events=verification.missing_supported_events,
            ),
            document_id="PMID-16428936",
            source_text=source_text,
            source_sha256=hashlib.sha256(source_text.encode()).hexdigest(),
            producer_identity=producer,
        )
    )
    gold = next(
        item
        for item in project_development_directory((root / SOURCE_PATH).parent)
        if item.document_id == "PMID-16428936"
    )
    return assembly, score_scientific_event_document(gold=gold, predicted=assembly.document)


def _mechanical_metrics(inputs: MechanicalInputs) -> dict[str, object]:
    baseline_signatures = _control_signatures(inputs.baseline_outputs)
    final_signatures = _control_signatures(inputs.final_outputs)
    control_regressions = sorted(
        event_id
        for event_id in CONTROL_IDS
        if baseline_signatures[event_id] != final_signatures[event_id]
    )
    modifier_output = inputs.final_outputs[2]
    verification_output = inputs.final_outputs[3]
    assert isinstance(modifier_output, ModifierOutput)
    assert isinstance(verification_output, VerificationOutput)
    modifier = {item.event_id: item for item in modifier_output.events}[
        "E-2773996d557442a07d58"
    ]
    verifier = {item.event_id: item for item in verification_output.events}[
        "E-2773996d557442a07d58"
    ]
    return {
        "wrong_to_correct_lower_bound": max(
            0,
            inputs.final_score.complete_events.matched
            - inputs.baseline_score.complete_events.matched,
        ),
        "control_regression_event_ids": control_regressions,
        "known_modifier_scope_correct": (
            modifier.decision is ModifierDecision.NEITHER
            and verifier.verdict is VerificationVerdict.ENTAILED
            and modifier.event_id in inputs.final_assembly.included_event_ids
        ),
        "typed_role_matches_increased": (
            inputs.final_score.typed_arguments.matched
            > inputs.baseline_score.typed_arguments.matched
        ),
        "nested_matches_increased": (
            inputs.final_score.nested_arguments.matched
            > inputs.baseline_score.nested_arguments.matched
        ),
        "baseline_retained_events": len(inputs.baseline_assembly.included_event_ids),
        "final_retained_events": len(inputs.final_assembly.included_event_ids),
        "requires_blinded_false_acceptance_adjudication": True,
    }


def _control_signatures(outputs: tuple[object, ...]) -> dict[str, str]:
    participants, roles, modifiers, verification = outputs
    assert isinstance(participants, ParticipantInventoryOutput)
    assert isinstance(roles, RoleAssignmentOutput)
    assert isinstance(modifiers, ModifierOutput)
    assert isinstance(verification, VerificationOutput)
    inventories = {item.event_id: item for item in participants.inventories}
    role_index = {item.event_id: item for item in roles.events}
    modifier_index = {item.event_id: item for item in modifiers.events}
    verifier_index = {item.event_id: item for item in verification.events}
    result: dict[str, str] = {}
    for event_id in CONTROL_IDS:
        participant_index = {
            item.participant_key: item for item in inventories[event_id].participants
        }
        arguments = []
        for assignment in role_index[event_id].assignments:
            participant = participant_index[assignment.participant_key]
            arguments.append(
                (
                    assignment.source_role.value,
                    assignment.target_kind.value,
                    participant.exact_text,
                    participant.occurrence_index,
                    participant.source_entity_type.value
                    if participant.source_entity_type
                    else None,
                    assignment.target_event_id,
                )
            )
        result[event_id] = _canonical_sha256(
            {
                "arguments": sorted(arguments),
                "modifier": modifier_index[event_id].decision.value,
                "modifier_evidence": modifier_index[event_id].exact_evidence,
                "verdict": verifier_index[event_id].verdict.value,
            }
        )
    return result


def _parse_outputs(stages: dict[str, object]) -> tuple[object, ...]:
    participants = ParticipantInventoryOutput.model_validate_json(
        json.dumps(_object(stages, "participants"))
    )
    roles = RoleAssignmentOutput.model_validate_json(
        json.dumps(_object(stages, "roles"))
    )
    modifiers = ModifierOutput.model_validate_json(
        json.dumps(_object(stages, "modifiers"))
    )
    verification = VerificationOutput.model_validate_json(
        json.dumps(_object(stages, "verification"))
    )
    return (
        ParticipantInventoryOutput(
            inventories=tuple(
                item for item in participants.inventories if item.event_id in PANEL_IDS
            )
        ),
        RoleAssignmentOutput(
            events=tuple(item for item in roles.events if item.event_id in PANEL_IDS)
        ),
        ModifierOutput(
            events=tuple(item for item in modifiers.events if item.event_id in PANEL_IDS)
        ),
        VerificationOutput(
            events=tuple(
                item for item in verification.events if item.event_id in PANEL_IDS
            ),
            missing_supported_events=verification.missing_supported_events,
        ),
    )


def _require_stage_ids(items: tuple[object, ...]) -> None:
    ids = {getattr(item, "event_id", None) for item in items}
    if ids != PANEL_IDS or len(items) != len(PANEL_IDS):
        raise StagedComparisonError("stage event identities differ from frozen panel")


def _require_permitted_references(roles: RoleAssignmentOutput) -> None:
    for event in roles.events:
        for assignment in event.assignments:
            if (
                assignment.target_kind is ParticipantTargetKind.EVENT
                and assignment.target_event_id not in PANEL_IDS
            ):
                raise StagedComparisonError("role references an event outside the panel")


def _write_outputs(
    paths: OutputPaths, ledger: BudgetLedger, result: dict[str, object]
) -> None:
    paths.receipt.parent.mkdir(parents=True, exist_ok=True)
    paths.result.parent.mkdir(parents=True, exist_ok=True)
    paths.receipt.write_text(
        json.dumps(ledger.as_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths.result.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths.report.write_text(
        "# Luna Focused Context Experiment\n\n"
        f"**Decision:** `{result['decision']}`\n\n"
        "This exposed-development result is non-qualifying and review-only.\n\n"
        "```json\n"
        + json.dumps(
            {
                "failure": result.get("failure"),
                "baseline_score": result.get("baseline_score"),
                "final_score": result.get("final_score"),
                "mechanical_metrics": result.get("mechanical_metrics"),
                "accounting": result.get("accounting"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n```\n",
        encoding="utf-8",
    )


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StagedComparisonError(f"{path} must contain an object")
    return value


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise StagedComparisonError(f"{key} must be an object")
    return value


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise StagedComparisonError(f"{key} must be a string")
    return value


def _integer(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise StagedComparisonError(f"{key} must be an integer")
    return value


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise StagedComparisonError(f"{key} must be numeric")
    return float(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--raw-output-directory", type=Path, required=True)
    args = parser.parse_args()
    decision = execute_context_experiment(
        preregistration_path=args.preregistration,
        paths=OutputPaths(
            receipt=args.receipt,
            result=args.result,
            report=args.report,
            raw_directory=args.raw_output_directory,
        ),
    )
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["execute_context_experiment", "OutputPaths"]
