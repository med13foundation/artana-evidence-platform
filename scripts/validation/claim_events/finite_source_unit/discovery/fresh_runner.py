"""One-unit fresh scientific-discovery experiment after transport repair."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from scripts.validation.claim_events.finite_source_unit.discovery.fresh_authorization import (
    verify_fresh_discovery_authorization,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_gate import (
    FreshDiscoveryGateInputs,
    fresh_discovery_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.discovery.fresh_unit import (
    FreshUnitSelection,
    select_fresh_hidden_unit,
)
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    audit_identity_mismatch_count,
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    receipt_expectations_for_finite_source_records,
)
from scripts.validation.claim_events.finite_source_unit.service import as_model_client
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
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
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import NaryClaimFixture

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_MODEL_ID: Final = "openai:gpt-5.6-luna"
_TARGET_TRIGGER: Final = "enhanced"
_TARGET_EVENT_TYPES: Final = frozenset({"INCREASE", "POSITIVE_REGULATION"})
_GENERIC_EVENT_ROLES: Final = frozenset(
    {"ARGUMENT", "ENTITY", "GENERIC", "OTHER", "PARTICIPANT"},
)


def run_fresh_hidden_discovery(
    *,
    fixture: NaryClaimFixture,
    run_id: str,
) -> dict[str, object]:
    """Run one extractor and one verifier on a pre-registered fresh unit."""

    require_frozen_development_fixture(fixture)
    authorization_sha256 = verify_fresh_discovery_authorization()
    selection = select_fresh_hidden_unit(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("fresh discovery requires a clean tracked worktree")
    return asyncio.run(
        _run_fresh_hidden_discovery(
            selection=selection,
            authorization_sha256=authorization_sha256,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_fresh_hidden_discovery(
    *,
    selection: FreshUnitSelection,
    authorization_sha256: str,
    run_id: str,
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
        raise RuntimeError("repository changed during fresh discovery")

    events = nary_events_from_bound_inventory(agent_run.accepted)
    target_events = tuple(
        event
        for event in events
        if _optional_text(event, "relation_cue_span") == _TARGET_TRIGGER
    )
    target_event = target_events[0] if len(target_events) == 1 else None
    target_arguments = _event_arguments(target_event)
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
    gate_inputs = FreshDiscoveryGateInputs(
        authorization_verified=True,
        exposure_registry_verified=True,
        hidden_expert_event_count=selection.hidden_expert_event_count,
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
        verification_decision_count=(
            0
            if agent_run.verification is None
            else len(agent_run.verification.decisions)
        ),
        entailed_candidate_count=len(agent_run.accepted),
        target_event_count=len(target_events),
        target_direction_preserved=(
            _optional_text(target_event, "event_type") in _TARGET_EVENT_TYPES
        ),
        target_polarity_asserted=(
            _optional_text(target_event, "polarity") == "SUPPORT"
            and _optional_text(target_event, "epistemic_status") == "ASSERTED"
        ),
        target_arguments_preserved=_target_arguments_preserved(target_arguments),
        generic_event_role_count=sum(
            _optional_text(argument, "event_role") in _GENERIC_EVENT_ROLES
            for event in events
            for argument in _event_arguments(event)
        ),
        binding_rejection_count=agent_run.binding_rejection_count,
        model_transport_identity_field_count=count_model_identity_fields(
            agent_outputs,
        ),
        audit_identity_mismatch_count=audit_identity_mismatch_count(
            agent_run.records,
            unit=unit,
        ),
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        extraction_provider_response_id_count=len(extraction_ids),
        verification_provider_response_id_count=len(verification_ids),
        distinct_provider_response_id_count=len(extraction_ids | verification_ids),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        fallback_count=0,
    )
    requirements = fresh_discovery_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_fresh_hidden_discovery.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "fresh_hidden_source_unit_discovery",
        "repository_evidence": repository_evidence,
        "authorization": {
            "merged_pr": 176,
            "transport_report_sha256": authorization_sha256,
        },
        "freshness": {
            "scope": "tracked TG-04 live reports through merged PR #176",
            "exposure_registry_sha256": selection.exposure_registry_sha256,
            "convenience_sample": True,
        },
        "unit": {
            "unit_id": unit.unit_id,
            "unit_index": unit.index,
            "source_start": unit.source_start,
            "source_end": unit.source_end,
            "source_sha256": unit.source_sha256,
            "input_sha256": unit.input_sha256,
            "text": unit.text,
            "hidden_expert_event_count": selection.hidden_expert_event_count,
            "authoritative_article_url": selection.authoritative_article_url,
        },
        "agent_outputs": agent_outputs,
        "predicted_events": events,
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "PROCEED_TO_INDEPENDENT_SOURCE_AND_LITERATURE_REVIEW"
                if passed
                else "STOP_AND_RECALIBRATE_FRESH_DISCOVERY"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "single_fresh_unit_convenience_sample": True,
            "literature_review_completed": False,
            "benchmark_credit_awarded": False,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


def _event_arguments(
    event: Mapping[str, object] | None,
) -> tuple[Mapping[str, object], ...]:
    if event is None:
        return ()
    arguments = event.get("arguments")
    if not isinstance(arguments, list):
        return ()
    return tuple(argument for argument in arguments if isinstance(argument, dict))


def _target_arguments_preserved(
    arguments: tuple[Mapping[str, object], ...],
) -> bool:
    surfaces = {
        text.casefold()
        for argument in arguments
        if (text := _optional_text(argument, "exact_span")) is not None
    }
    return "p-selectin" in surfaces and any(
        "nuclear factor-kappa b" in surface or surface == "nf-kappa b"
        for surface in surfaces
    )


def _optional_text(
    value: Mapping[str, object] | None,
    field: str,
) -> str | None:
    if value is None:
        return None
    item = value.get(field)
    return item if isinstance(item, str) else None


__all__ = ["run_fresh_hidden_discovery"]
