"""Run one independent structure review over the immutable #177 candidates."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    EventStructureDecision,
    SemanticValidityDecision,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    audit_identity_mismatch_count,
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    receipt_expectations_for_finite_source_records,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    as_model_client,
    verify_source_unit_candidates,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    provider_response_ids,
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.structure_review.gate import (
    StructureReplayGateInputs,
    structure_replay_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.structure_review.source import (
    FrozenStructureReplaySource,
    load_structure_replay_source,
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

_REPO_ROOT: Final = Path(__file__).resolve().parents[5]
_MODEL_ID: Final = "openai:gpt-5.6-luna"


def run_structure_replay(
    *,
    fixture: NaryClaimFixture,
    artifact_path: Path,
    run_id: str,
) -> dict[str, object]:
    """Review frozen candidates without rerunning or crediting extraction."""

    require_frozen_development_fixture(fixture)
    source = load_structure_replay_source(
        fixture=fixture,
        artifact_path=artifact_path,
    )
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("structure replay requires a clean tracked worktree")
    return asyncio.run(
        _run_structure_replay(
            source=source,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_structure_replay(
    *,
    source: FrozenStructureReplaySource,
    run_id: str,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    audit = start_model_attempt_audit(evidence_unit_id=source.unit.unit_id)
    verification: SourceUnitVerificationOutput | None = None
    error_type: str | None = None
    try:
        result = await verify_source_unit_candidates(
            client=as_model_client(client),
            tenant=tenant,
            model_id=execution_model_id,
            execution_namespace=f"{run_id}:{source.unit.unit_id}:{uuid4().hex}",
            unit=source.unit,
            candidates=source.candidates,
        )
        verification = result.parsed
    except Exception as exc:  # noqa: BLE001 - retain categorical failure evidence
        error_type = type(exc).__name__
    finally:
        stop_model_attempt_audit(audit)
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()
    records = tuple(audit.records)
    if collect_repository_evidence(_REPO_ROOT) != repository_evidence:
        raise RuntimeError("repository changed during structure replay")
    return _build_report(
        source=source,
        run_id=run_id,
        repository_evidence=repository_evidence,
        verification=verification,
        error_type=error_type,
        records=records,
    )


def _build_report(  # noqa: PLR0913
    *,
    source: FrozenStructureReplaySource,
    run_id: str,
    repository_evidence: dict[str, object],
    verification: SourceUnitVerificationOutput | None,
    error_type: str | None,
    records: tuple[ModelAttemptAuditRecord, ...],
) -> dict[str, object]:
    decisions = () if verification is None else verification.decisions
    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(list(records))
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    verification_ids = provider_response_ids(records, "weak_review")
    structure_blocker_count = sum(
        decision.structure_decision is not EventStructureDecision.COMPLETE
        for decision in decisions
    )
    invalid_argument_type_count = sum(
        argument.type_decision is SemanticValidityDecision.INVALID
        for decision in decisions
        for argument in decision.argument_semantic_decisions
    )
    gate_inputs = StructureReplayGateInputs(
        authorization_verified=True,
        frozen_artifact_verified=True,
        adaptive_replay_declared=True,
        review_execution_complete=verification is not None and error_type is None,
        verification_category=(
            None if verification is None else verification.eligibility_category
        ),
        verification_coverage=(
            None if verification is None else verification.coverage_decision
        ),
        candidate_count=len(source.candidates),
        verification_decision_count=len(decisions),
        entailed_candidate_count=sum(
            decision.decision is EntailmentDecision.ENTAILED for decision in decisions
        ),
        trusted_projection_count=sum(
            decision.trusted_projection_eligible for decision in decisions
        ),
        structure_blocker_count=structure_blocker_count,
        invalid_argument_type_count=invalid_argument_type_count,
        model_transport_identity_field_count=count_model_identity_fields(
            None if verification is None else verification.model_dump(mode="json"),
        ),
        audit_identity_mismatch_count=audit_identity_mismatch_count(
            records,
            unit=source.unit,
        ),
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        verification_provider_response_id_count=len(verification_ids),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        fallback_count=0,
    )
    requirements = structure_replay_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_structure_replay.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "frozen_candidate_structure_replay",
        "repository_evidence": repository_evidence,
        "authorization": {
            "merged_pr": 177,
            "report_sha256": source.report_sha256,
            "artifact_sha256": source.artifact_sha256,
            "prior_embedded_report_sha256": source.prior_embedded_report_sha256,
        },
        "unit": {
            "unit_id": source.unit.unit_id,
            "source_sha256": source.unit.source_sha256,
            "input_sha256": source.unit.input_sha256,
            "text": source.unit.text,
        },
        "frozen_candidates": [
            candidate.item.model_dump(mode="json") for candidate in source.candidates
        ],
        "agent_output": (
            None if verification is None else verification.model_dump(mode="json")
        ),
        "error_type": error_type,
        "attempts": [record.as_json() for record in records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "PROCEED_TO_ONE_NEW_HIDDEN_UNIT"
                if passed
                else "STOP_AND_RECALIBRATE_STRUCTURE_REVIEW"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "adaptive_replay": True,
            "extraction_rerun": False,
            "discovery_credit_awarded": False,
            "benchmark_credit_awarded": False,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


__all__ = ["run_structure_replay"]
