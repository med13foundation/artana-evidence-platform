"""One-unit TG-04 hidden scientific-discovery experiment."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from artana_evidence_api.document_extraction import normalize_text_document

from scripts.validation.claim_events.finite_source_unit.discovery.authorization import (
    load_discovery_authorization,
)
from scripts.validation.claim_events.finite_source_unit.discovery.gate import (
    HiddenDiscoveryGateInputs,
    hidden_discovery_gate_requirements,
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
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
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
_CASE_ID: Final = "bionlp-ge-2011:PMC-2222968-05-Results-04"
_UNIT_INDEX: Final = 6
_EXPECTED_UNIT_ID: Final = (
    "source-unit-a1e6d72064289601fc6e82446a14036433e1b1bf32cd014de2c817bf7b4cfde9"
)
_EXPECTED_INPUT_SHA256: Final = (
    "5461f6bf2aa1e22bd9d6e292ca3e6e21e896d898c4b194229aebe6ace6c3ad0a"
)
_ARTICLE_URL: Final = "https://pmc.ncbi.nlm.nih.gov/articles/PMC2222968/"
_GENERIC_EVENT_ROLES: Final = frozenset(
    {"ARGUMENT", "ENTITY", "GENERIC", "OTHER", "PARTICIPANT"},
)


def run_hidden_discovery_pilot(
    *,
    fixture: NaryClaimFixture,
    authorization_artifact_path: Path,
    run_id: str,
) -> dict[str, object]:
    """Run two blinded agent roles on one source unit without local gold."""

    require_frozen_development_fixture(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("hidden discovery requires a clean tracked worktree")
    authorization = load_discovery_authorization(authorization_artifact_path)
    unit, hidden_event_count = select_hidden_discovery_unit(fixture)
    return asyncio.run(
        _run_hidden_discovery(
            unit=unit,
            hidden_event_count=hidden_event_count,
            authorization_artifact_sha256=authorization.artifact_sha256,
            authorization_report_sha256=authorization.report_sha256,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


def select_hidden_discovery_unit(
    fixture: NaryClaimFixture,
) -> tuple[FrozenSourceUnit, int]:
    """Select the pre-registered sentence and prove no event label is local."""

    case = next((case for case in fixture.cases if case.case_id == _CASE_ID), None)
    if case is None:
        raise RuntimeError("frozen hidden-discovery case is missing")
    units = enumerate_source_units(
        case_id=case.case_id,
        source_text=normalize_text_document(case.source_text),
    )
    if len(units) <= _UNIT_INDEX:
        raise RuntimeError("frozen hidden-discovery source unit is missing")
    unit = units[_UNIT_INDEX]
    if unit.unit_id != _EXPECTED_UNIT_ID or unit.input_sha256 != _EXPECTED_INPUT_SHA256:
        raise RuntimeError("frozen hidden-discovery source-unit identity changed")
    local_events = tuple(
        event
        for event in case.events
        if unit.source_start <= event.trigger_source_start < unit.source_end
    )
    if local_events:
        raise RuntimeError("hidden-discovery unit unexpectedly contains benchmark gold")
    return unit, len(local_events)


async def _run_hidden_discovery(  # noqa: PLR0913
    *,
    unit: FrozenSourceUnit,
    hidden_event_count: int,
    authorization_artifact_sha256: str,
    authorization_report_sha256: str,
    run_id: str,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
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
        raise RuntimeError("repository changed during hidden discovery")

    events = nary_events_from_bound_inventory(agent_run.accepted)
    event = events[0] if len(events) == 1 else None
    event_arguments = _event_arguments(event)
    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(list(agent_run.records))
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    extraction_ids = provider_response_ids(agent_run.records, "primary")
    verification_ids = provider_response_ids(agent_run.records, "weak_review")
    gate_inputs = HiddenDiscoveryGateInputs(
        authorization_verified=True,
        hidden_expert_event_count=hidden_event_count,
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
        entailed_candidate_count=len(agent_run.accepted),
        predicted_event_count=len(events),
        predicted_event_type=_optional_text(event, "event_type"),
        predicted_polarity=_optional_text(event, "polarity"),
        predicted_epistemic_status=_optional_text(event, "epistemic_status"),
        material_argument_count=len(event_arguments),
        generic_event_role_count=sum(
            _optional_text(argument, "event_role") in _GENERIC_EVENT_ROLES
            for argument in event_arguments
        ),
        binding_rejection_count=agent_run.binding_rejection_count,
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        extraction_provider_response_id_count=len(extraction_ids),
        verification_provider_response_id_count=len(verification_ids),
        distinct_provider_response_id_count=len(extraction_ids | verification_ids),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        fallback_count=0,
    )
    requirements = hidden_discovery_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_hidden_discovery_unit.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "hidden_source_unit_discovery",
        "repository_evidence": repository_evidence,
        "authorization": {
            "artifact_sha256": authorization_artifact_sha256,
            "report_sha256": authorization_report_sha256,
        },
        "unit": {
            "case_id": _CASE_ID,
            "unit_id": unit.unit_id,
            "unit_index": unit.index,
            "source_start": unit.source_start,
            "source_end": unit.source_end,
            "source_sha256": unit.source_sha256,
            "input_sha256": unit.input_sha256,
            "text": unit.text,
            "hidden_expert_event_count": hidden_event_count,
            "authoritative_article_url": _ARTICLE_URL,
        },
        "agent_outputs": {
            "extraction": model_json(agent_run.extraction),
            "verification": model_json(agent_run.verification),
            "error_type": agent_run.error_type,
        },
        "predicted_events": events,
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "PROCEED_TO_SOURCE_AND_LITERATURE_REVIEW"
                if passed
                else "STOP_AND_RECALIBRATE"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "single_hidden_unit_only": True,
            "literature_review_completed": False,
            "benchmark_credit_awarded": False,
            "review_only": True,
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


def _optional_text(
    value: Mapping[str, object] | None,
    field: str,
) -> str | None:
    if value is None:
        return None
    item = value.get(field)
    return item if isinstance(item, str) else None


__all__ = ["run_hidden_discovery_pilot", "select_hidden_discovery_unit"]
