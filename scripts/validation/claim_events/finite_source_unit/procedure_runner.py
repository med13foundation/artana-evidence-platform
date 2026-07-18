"""One-unit TG-04 procedure-recognition experiment."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from artana_evidence_api.document_extraction import normalize_text_document
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.procedure_gate import (
    ProcedureUnitGateInputs,
    procedure_unit_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    receipt_expectations_for_finite_source_records,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    as_model_client,
    extract_source_unit,
    verify_source_unit_candidates,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
)
from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.runner import build_tg04_runtime
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.contracts import NaryClaimFixture
    from scripts.validation.claim_events.finite_source_unit.contracts import (
        SourceUnitExtractionOutput,
        SourceUnitVerificationOutput,
    )
    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[4]
_MODEL_ID: Final = "openai:gpt-5.6-luna"
_CASE_ID: Final = "bionlp-ge-2011:PMC-2222968-15-Materials_and_Methods-07"
_UNIT_INDEX: Final = 2
_EXPECTED_UNIT_ID: Final = (
    "source-unit-063ab2e2ce044fe71c9f700805f4ed61be4a66879bd9aa3d50e7a683c2ee3af1"
)
_EXPECTED_INPUT_SHA256: Final = (
    "19f72827611fa17d2b45c457ed6b632a1f549a9e44c3bb58387dc8d86dbdf47d"
)


@dataclass(frozen=True, slots=True)
class _AgentRunEvidence:
    extraction: SourceUnitExtractionOutput | None
    verification: SourceUnitVerificationOutput | None
    extracted_candidate_count: int
    verification_decision_count: int
    binding_rejection_count: int
    records: tuple[ModelAttemptAuditRecord, ...]
    error_type: str | None


def run_procedure_source_unit_pilot(
    *,
    fixture: NaryClaimFixture,
    run_id: str,
) -> dict[str, object]:
    """Run exactly one extractor and one verifier on the frozen procedure unit."""

    require_frozen_development_fixture(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("procedure source-unit runs require a clean tracked worktree")
    unit = select_procedure_unit(fixture)
    return asyncio.run(
        _run_procedure_source_unit(
            unit=unit,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


def select_procedure_unit(fixture: NaryClaimFixture) -> FrozenSourceUnit:
    """Select the pre-registered disputed electroporation sentence by identity."""

    case = next((case for case in fixture.cases if case.case_id == _CASE_ID), None)
    if case is None:
        raise RuntimeError("frozen procedure-control case is missing")
    units = enumerate_source_units(
        case_id=case.case_id,
        source_text=normalize_text_document(case.source_text),
    )
    if len(units) <= _UNIT_INDEX:
        raise RuntimeError("frozen procedure source unit is missing")
    unit = units[_UNIT_INDEX]
    if (
        unit.unit_id != _EXPECTED_UNIT_ID
        or unit.input_sha256 != _EXPECTED_INPUT_SHA256
    ):
        raise RuntimeError("frozen procedure source-unit identity changed")
    return unit


async def _run_procedure_source_unit(
    *,
    unit: FrozenSourceUnit,
    run_id: str,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    try:
        agent_run = await _execute_agents(
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
        raise RuntimeError("repository state changed during procedure source-unit run")

    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(list(agent_run.records))
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    extraction_ids = _provider_response_ids(agent_run.records, "primary")
    verification_ids = _provider_response_ids(agent_run.records, "weak_review")
    distinct_ids = extraction_ids | verification_ids
    gate_inputs = ProcedureUnitGateInputs(
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
        verification_decision_count=agent_run.verification_decision_count,
        binding_rejection_count=agent_run.binding_rejection_count,
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        extraction_provider_response_id_count=len(extraction_ids),
        verification_provider_response_id_count=len(verification_ids),
        distinct_provider_response_id_count=len(distinct_ids),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        fallback_count=0,
    )
    requirements = procedure_unit_gate_requirements(gate_inputs)
    gate_passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_procedure_source_unit.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "procedure_source_unit_recognition",
        "repository_evidence": repository_evidence,
        "unit": {
            "case_id": _CASE_ID,
            "unit_id": unit.unit_id,
            "unit_index": unit.index,
            "source_start": unit.source_start,
            "source_end": unit.source_end,
            "source_sha256": unit.source_sha256,
            "input_sha256": unit.input_sha256,
            "text": unit.text,
        },
        "agent_outputs": {
            "extraction": _model_json(agent_run.extraction),
            "verification": _model_json(agent_run.verification),
            "error_type": agent_run.error_type,
        },
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": gate_passed,
            "decision": (
                "PROCEED_TO_ONE_EXPERT_EVENT"
                if gate_passed
                else "STOP_AND_RECALIBRATE"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "procedure_recognition_only": True,
            "scientific_accuracy_measured": False,
            "new_discovery_measured": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = _sha256_json(report)
    return report


async def _execute_agents(
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
) -> _AgentRunEvidence:
    audit = start_model_attempt_audit(evidence_unit_id=unit.unit_id)
    extraction_output: SourceUnitExtractionOutput | None = None
    verification_output: SourceUnitVerificationOutput | None = None
    extracted_candidate_count = verification_decision_count = 0
    binding_rejection_count = 0
    error_type: str | None = None
    try:
        extraction = await extract_source_unit(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=execution_namespace,
            unit=unit,
        )
        extraction_output = extraction.value.output
        extracted_candidate_count = len(extraction.value.accepted)
        binding_rejection_count = len(extraction.value.rejected)
        verification = await verify_source_unit_candidates(
            client=client,
            tenant=tenant,
            model_id=model_id,
            execution_namespace=execution_namespace,
            unit=unit,
            candidates=extraction.value.accepted,
        )
        verification_output = verification.parsed
        verification_decision_count = len(verification.parsed.decisions)
    except Exception as exc:  # noqa: BLE001 - preserve categorical failure evidence
        error_type = type(exc).__name__
    finally:
        stop_model_attempt_audit(audit)
    return _AgentRunEvidence(
        extraction=extraction_output,
        verification=verification_output,
        extracted_candidate_count=extracted_candidate_count,
        verification_decision_count=verification_decision_count,
        binding_rejection_count=binding_rejection_count,
        records=tuple(audit.records),
        error_type=error_type,
    )


def _provider_response_ids(
    records: tuple[ModelAttemptAuditRecord, ...],
    pass_role: str,
) -> set[str]:
    return {
        record.provider_response_id
        for record in records
        if record.pass_role == pass_role and record.provider_response_id is not None
    }


def _model_json(
    model: SourceUnitExtractionOutput | SourceUnitVerificationOutput | None,
) -> dict[str, object] | None:
    return None if model is None else model.model_dump(mode="json")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = ["run_procedure_source_unit_pilot", "select_procedure_unit"]
