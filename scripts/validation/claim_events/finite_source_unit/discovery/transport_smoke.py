"""Non-qualifying live smoke for deterministic source-unit identity binding."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    audit_identity_mismatch_count,
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.discovery.runner import (
    select_hidden_discovery_unit,
)
from scripts.validation.claim_events.finite_source_unit.discovery.transport_gate import (
    TransportIdentityGateInputs,
    transport_identity_gate_requirements,
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
from scripts.validation.claim_events.runner import build_tg04_runtime
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import NaryClaimFixture
    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_MODEL_ID: Final = "openai:gpt-5.6-luna"
_PR175_REPORT_PATH: Final = (
    _REPO_ROOT / "docs/validation/reports/2026-07-18-tg04-hidden-discovery-unit.md"
)
#: Moved once, by the 2026-07-25 redaction, which replaced a quoted source
#: sentence in the report with a locator and a digest and changed no finding,
#: count or verdict in it.  The redaction did not update this pin, so the check
#: raised on every run afterwards.  Superseded digest:
#: `fb77b85369c17adcd98c6d99a927ddcabe10b9e4ef9aa22c33299ea0f8a4a34a` -- which
#: is also the value recorded in the #176 transport-identity report, correctly
#: and permanently, because that report is an account of a run that consumed
#: those exact bytes.  A record of the past does not follow a later redaction;
#: a live pin over the current file does.
_PR175_REPORT_SHA256: Final = (
    "0f9792b8d11ae9a86bc57c8ea8e3c4522f081b7810bab705c5238ce81a8c508b"
)


def run_transport_identity_smoke(
    *,
    fixture: NaryClaimFixture,
    run_id: str,
) -> dict[str, object]:
    """Replay the failed unit only to validate deterministic identity transport."""

    require_frozen_development_fixture(fixture)
    prior_report_sha256 = verify_prior_failure_report()
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("transport smoke requires a clean tracked worktree")
    unit, hidden_event_count = select_hidden_discovery_unit(fixture)
    return asyncio.run(
        _run_transport_identity_smoke(
            unit=unit,
            hidden_event_count=hidden_event_count,
            prior_report_sha256=prior_report_sha256,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


def verify_prior_failure_report(
    path: Path = _PR175_REPORT_PATH,
    *,
    expected_sha256: str = _PR175_REPORT_SHA256,
) -> str:
    """Pin the exact merged #175 stop report that authorized this smoke."""

    report_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if report_sha256 != expected_sha256:
        raise RuntimeError("#175 hidden-discovery stop report changed")
    return report_sha256


async def _run_transport_identity_smoke(  # noqa: PLR0913
    *,
    unit: FrozenSourceUnit,
    hidden_event_count: int,
    prior_report_sha256: str,
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
        raise RuntimeError("repository changed during transport smoke")

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
    gate_inputs = TransportIdentityGateInputs(
        prior_failure_report_verified=True,
        adaptive_replay_declared=True,
        agent_execution_complete=(
            agent_run.extraction is not None
            and agent_run.verification is not None
            and agent_run.error_type is None
        ),
        extracted_candidate_count=agent_run.extracted_candidate_count,
        verification_decision_count=(
            0
            if agent_run.verification is None
            else len(agent_run.verification.decisions)
        ),
        entailed_candidate_count=len(agent_run.entailed),
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
    requirements = transport_identity_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_transport_identity_smoke.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "source_unit_transport_identity_smoke",
        "repository_evidence": repository_evidence,
        "authorization": {
            "merged_pr": 175,
            "prior_failure_report_sha256": prior_report_sha256,
        },
        "unit": {
            "unit_id": unit.unit_id,
            "unit_index": unit.index,
            "source_start": unit.source_start,
            "source_end": unit.source_end,
            "source_sha256": unit.source_sha256,
            "input_sha256": unit.input_sha256,
            "text": unit.text,
            "hidden_expert_event_count": hidden_event_count,
        },
        "agent_outputs": agent_outputs,
        "accepted_claims": [
            {
                "inventory_id": claim.inventory_id,
                "source_sha256": claim.source_sha256,
                "source_start": claim.source_start,
                "source_end": claim.source_end,
                "item": claim.item.model_dump(mode="json"),
            }
            for claim in agent_run.entailed
        ],
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "TRANSPORT_IDENTITY_SMOKE_PASSED"
                if passed
                else "STOP_AND_RECALIBRATE_TRANSPORT"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "adaptive_replay_of_failed_unit": True,
            "qualification_eligible": False,
            "scientific_accuracy_measured": False,
            "benchmark_credit_awarded": False,
            "literature_review_authorized": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


__all__ = [
    "run_transport_identity_smoke",
    "verify_prior_failure_report",
]
