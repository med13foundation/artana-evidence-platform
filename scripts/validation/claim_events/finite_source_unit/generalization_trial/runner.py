"""Execute one pre-registered fresh causal-event generalization repeat."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast
from uuid import uuid4

from scripts.validation.claim_events.finite_source_unit.controlled_event_trial.matching import (
    expert_core_event_match_count,
)
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    audit_identity_mismatch_count,
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.adaptive_replay_authorization import (
    verify_failed_adaptive_replay_authorization,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.authorization import (
    verify_reassessment_authorization,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.gate import (
    GeneralizationGateInputs,
    generalization_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.replay_authorization import (
    verify_failed_generalization_authorization,
)
from scripts.validation.claim_events.finite_source_unit.generalization_trial.selection import (
    GeneralizationTrialSelection,
    select_generalization_trial,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    receipt_expectations_for_finite_source_records,
)
from scripts.validation.claim_events.finite_source_unit.service import as_model_client
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    SingleUnitAgentRunEvidence,
    execute_source_unit_agents,
    model_json,
    provider_response_ids,
    sha256_json,
)
from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.runner import (
    build_tg04_runtime,
    nary_events_from_bound_inventory,
)
from scripts.validation.claim_events.scoring import (
    BenchmarkFixtureContract,
    score_fixture,
)
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import (
        NaryClaimEvent,
        NaryClaimFixture,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_MODEL_ID: Final = "openai:gpt-5.6-luna"
TrialMode = Literal["fresh", "adaptive_replay"]


@dataclass(slots=True)
class _TrialCase:
    case_id: str
    events: tuple[NaryClaimEvent, ...]


@dataclass(slots=True)
class _TrialFixture:
    cases: tuple[_TrialCase, ...]


def run_generalization_trial(
    *,
    fixture: NaryClaimFixture,
    authorization_artifact: Path,
    run_id: str,
    repeat_index: int,
) -> dict[str, object]:
    """Run extractor and blinded verifier once against the untouched unit."""

    require_frozen_development_fixture(fixture)
    authorization_sha256 = verify_reassessment_authorization(
        authorization_artifact,
    )
    selection = select_generalization_trial(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("generalization trial requires a clean tracked worktree")
    return asyncio.run(
        _run_trial(
            selection=selection,
            authorization_sha256=authorization_sha256,
            authorization_source="successful_zero_call_reassessment",
            mode="fresh",
            run_id=run_id,
            repeat_index=repeat_index,
            repository_evidence=repository_evidence,
        ),
    )


def run_generalization_replay(
    *,
    fixture: NaryClaimFixture,
    failed_trial_artifact: Path,
    run_id: str,
) -> dict[str, object]:
    """Replay the exposed failed unit without awarding qualification credit."""

    require_frozen_development_fixture(fixture)
    authorization_sha256 = verify_failed_generalization_authorization(
        failed_trial_artifact,
    )
    selection = select_generalization_trial(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("generalization replay requires a clean tracked worktree")
    return asyncio.run(
        _run_trial(
            selection=selection,
            authorization_sha256=authorization_sha256,
            authorization_source="failed_fresh_generalization_repeat_1",
            mode="adaptive_replay",
            run_id=run_id,
            repeat_index=1,
            repository_evidence=repository_evidence,
        ),
    )


def run_generalization_second_replay(
    *,
    fixture: NaryClaimFixture,
    failed_replay_artifact: Path,
    run_id: str,
) -> dict[str, object]:
    """Run one final exposed replay after the first adaptive contract failure."""

    require_frozen_development_fixture(fixture)
    authorization_sha256 = verify_failed_adaptive_replay_authorization(
        failed_replay_artifact,
    )
    selection = select_generalization_trial(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("second generalization replay requires a clean worktree")
    return asyncio.run(
        _run_trial(
            selection=selection,
            authorization_sha256=authorization_sha256,
            authorization_source="failed_first_adaptive_generalization_replay",
            mode="adaptive_replay",
            run_id=run_id,
            repeat_index=1,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_trial(  # noqa: PLR0913
    *,
    selection: GeneralizationTrialSelection,
    authorization_sha256: str,
    authorization_source: str,
    mode: TrialMode,
    run_id: str,
    repeat_index: int,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    unit = selection.unit
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    try:
        agent_run = await execute_source_unit_agents(
            client=as_model_client(client),
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=f"{run_id}:{unit.unit_id}:{uuid4().hex}",
            unit=unit,
        )
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()
    if collect_repository_evidence(_REPO_ROOT) != repository_evidence:
        raise RuntimeError("repository changed during generalization trial")
    return _build_report(
        selection=selection,
        authorization_sha256=authorization_sha256,
        authorization_source=authorization_source,
        mode=mode,
        run_id=run_id,
        repeat_index=repeat_index,
        repository_evidence=repository_evidence,
        agent_run=agent_run,
    )


def _build_report(  # noqa: PLR0913
    *,
    selection: GeneralizationTrialSelection,
    authorization_sha256: str,
    authorization_source: str,
    mode: TrialMode,
    run_id: str,
    repeat_index: int,
    repository_evidence: dict[str, object],
    agent_run: SingleUnitAgentRunEvidence,
) -> dict[str, object]:
    trusted_events = nary_events_from_bound_inventory(agent_run.trusted)
    score = score_fixture(
        cast(
            "BenchmarkFixtureContract",
            _TrialFixture(
                cases=(
                    _TrialCase(
                        case_id=selection.case_id,
                        events=selection.expert_events,
                    ),
                ),
            ),
        ),
        [
            {
                "case_id": selection.case_id,
                "events": trusted_events,
                "abstained": not trusted_events,
            },
        ],
    )
    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(list(agent_run.records))
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    extraction_ids = provider_response_ids(agent_run.records, "primary")
    verification_ids = provider_response_ids(agent_run.records, "weak_review")
    agent_outputs = {
        "extraction": model_json(agent_run.extraction),
        "verification": model_json(agent_run.verification),
        "error_type": agent_run.error_type,
    }
    gate_inputs = GeneralizationGateInputs(
        authorization_verified=True,
        selection_verified=True,
        fresh_unit_declared=mode == "fresh",
        adaptive_replay_declared=mode == "adaptive_replay",
        repeat_index=repeat_index,
        hidden_expert_event_count=len(selection.expert_events),
        agent_execution_complete=(
            agent_run.extraction is not None
            and agent_run.verification is not None
            and agent_run.error_type is None
        ),
        extraction_category=(
            None
            if agent_run.extraction is None
            else agent_run.extraction.eligibility_category
        ),
        verification_category=(
            None
            if agent_run.verification is None
            else agent_run.verification.eligibility_category
        ),
        extraction_decision=(
            None if agent_run.extraction is None else agent_run.extraction.decision
        ),
        verification_coverage=(
            None
            if agent_run.verification is None
            else agent_run.verification.coverage_decision
        ),
        extracted_candidate_count=agent_run.extracted_candidate_count,
        verification_decision_count=len(agent_run.verified),
        entailed_candidate_count=len(agent_run.entailed),
        trusted_candidate_count=len(agent_run.trusted),
        expert_core_event_match_count=expert_core_event_match_count(
            selection.expert_events,
            trusted_events,
        ),
        binding_rejection_count=agent_run.binding_rejection_count,
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        extraction_provider_response_id_count=len(extraction_ids),
        verification_provider_response_id_count=len(verification_ids),
        distinct_provider_response_id_count=len(extraction_ids | verification_ids),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        model_transport_identity_field_count=count_model_identity_fields(agent_outputs),
        audit_identity_mismatch_count=audit_identity_mismatch_count(
            agent_run.records,
            unit=selection.unit,
        ),
        fallback_count=0,
    )
    requirements = generalization_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": (
            "tg04_generalization_trial.v1"
            if mode == "fresh"
            else "tg04_generalization_replay.v1"
        ),
        "run_id": run_id,
        "repeat_index": repeat_index,
        "pre_registered_repeat_indices": [1, 2, 3],
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": (
            "fresh_causal_event_generalization_trial"
            if mode == "fresh"
            else "adaptive_causal_event_generalization_replay"
        ),
        "experiment_mode": mode,
        "repository_evidence": repository_evidence,
        "authorization": {
            "source": authorization_source,
            "artifact_sha256": authorization_sha256,
        },
        "freshness": {
            "scope": "TG-04 live work through the successful zero-call reassessment",
            "selection_rule": "lowest reassessment-seeded untouched causal unit",
            "selection_rank": selection.selection_rank,
            "exposure_registry_sha256": selection.exposure_registry_sha256,
            "convenience_sample": True,
            "fresh_at_execution": mode == "fresh",
        },
        "unit": {
            "case_id": selection.case_id,
            "unit_id": selection.unit.unit_id,
            "unit_index": selection.unit.index,
            "source_start": selection.unit.source_start,
            "source_end": selection.unit.source_end,
            "source_sha256": selection.unit.source_sha256,
            "input_sha256": selection.unit.input_sha256,
            "text": selection.unit.text,
            "hidden_minimum_expert_event_count": len(selection.expert_events),
            "authoritative_article_url": selection.authoritative_article_url,
        },
        "agent_outputs": agent_outputs,
        "verified_candidates": [
            {
                "item": candidate.claim.item.model_dump(mode="json"),
                "verification": candidate.verification.model_dump(mode="json"),
            }
            for candidate in agent_run.verified
        ],
        "trusted_events": trusted_events,
        "sealed_minimum_expert_events": [
            {
                "event_id": event.event_id,
                "trigger": event.trigger_span,
                "event_type": event.event_type.value,
                "polarity": event.polarity.value,
                "epistemic_status": event.epistemic_status.value,
                "arguments": [
                    {
                        "event_role": argument.event_role.value,
                        "role": argument.participant_role.value,
                        "exact_span": argument.exact_span,
                    }
                    for argument in sorted(
                        event.arguments,
                        key=lambda item: (item.source_start, item.argument_id),
                    )
                ],
            }
            for event in selection.expert_events
        ],
        "deterministic_metrics": {
            "expert_core_event_match_count": gate_inputs.expert_core_event_match_count,
            "strict_exact_benchmark_metrics": asdict(score.metrics),
        },
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                (
                    "PROCEED_TO_NEXT_PRE_REGISTERED_REPEAT_OR_SOURCE_REVIEW"
                    if mode == "fresh"
                    else "PROCEED_TO_NEW_FRESH_UNIT"
                )
                if passed
                else "STOP_AND_RECALIBRATE_GENERALIZATION"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "single_fresh_unit_convenience_sample": mode == "fresh",
            "adaptive_replay": mode == "adaptive_replay",
            "qualification_eligible": mode == "fresh",
            "sealed_expert_event_was_hidden_from_agents": True,
            "expert_event_is_minimum_expected_source_structure": True,
            "strict_exact_benchmark_match_is_reported_but_not_a_gate": True,
            "additional_source_valid_claims_are_allowed": True,
            "all_additional_claims_must_be_entailed_and_structure_trusted": True,
            "benchmark_credit_awarded": False,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


__all__ = [
    "run_generalization_replay",
    "run_generalization_second_replay",
    "run_generalization_trial",
]
