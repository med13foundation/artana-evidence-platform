"""One-call TG-04 adjudication of a frozen representation mismatch."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.known_expert_runner import (
    select_known_expert_unit,
)
from scripts.validation.claim_events.finite_source_unit.representation_artifact import (
    load_frozen_known_expert_artifact,
)
from scripts.validation.claim_events.finite_source_unit.representation_contracts import (
    RepresentationAdjudicationOutput,
)
from scripts.validation.claim_events.finite_source_unit.representation_gate import (
    RepresentationGateInputs,
    representation_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.representation_service import (
    RepresentationAdjudicationRequest,
    adjudicate_representation,
)
from scripts.validation.claim_events.finite_source_unit.service import as_model_client
from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.runner import (
    build_tg04_runtime,
    receipt_expectation_from_attempt,
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
    from scripts.validation.claim_events.finite_source_unit.representation_artifact import (
        FrozenKnownExpertArtifact,
    )

_REPO_ROOT: Final = Path(__file__).resolve().parents[4]
_MODEL_ID: Final = "openai:gpt-5.6-luna"


def run_representation_adjudication_pilot(
    *,
    fixture: NaryClaimFixture,
    prior_artifact_path: Path,
    run_id: str,
) -> dict[str, object]:
    """Run one independent adjudicator against immutable prior evidence."""

    require_frozen_development_fixture(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError(
            "representation adjudication requires a clean tracked worktree"
        )
    artifact = load_frozen_known_expert_artifact(prior_artifact_path)
    unit, expert_event = select_known_expert_unit(fixture)
    if (
        artifact.unit_id != unit.unit_id
        or artifact.source_text != unit.text
        or artifact.source_sha256 != unit.source_sha256
        or artifact.input_sha256 != unit.input_sha256
    ):
        raise RuntimeError("representation artifact differs from frozen fixture unit")
    return asyncio.run(
        _run_representation_adjudication(
            artifact=artifact,
            expert_event=expert_event,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_representation_adjudication(
    *,
    artifact: FrozenKnownExpertArtifact,
    expert_event: NaryClaimEvent,
    run_id: str,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    audit = start_model_attempt_audit(evidence_unit_id=artifact.unit_id)
    output: RepresentationAdjudicationOutput | None = None
    error_type: str | None = None
    try:
        try:
            result = await adjudicate_representation(
                client=as_model_client(client),
                tenant=tenant,
                model_id=execution_model_id,
                request=RepresentationAdjudicationRequest(
                    execution_namespace=(f"{run_id}:{artifact.unit_id}:{uuid4().hex}"),
                    unit_id=artifact.unit_id,
                    source_sha256=artifact.source_sha256,
                    source_text=artifact.source_text,
                    expert_event=expert_event,
                    candidate_event=artifact.predicted_event,
                ),
            )
            output = result.value
        except Exception as exc:  # noqa: BLE001 - preserve categorical failure
            error_type = type(exc).__name__
    finally:
        stop_model_attempt_audit(audit)
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()

    if collect_repository_evidence(_REPO_ROOT) != repository_evidence:
        raise RuntimeError("repository changed during representation adjudication")
    records = tuple(audit.records)
    invalid_count = sum(record.validation_outcome != "accepted" for record in records)
    unidentified_count = sum(record.provider_response_id is None for record in records)
    expectations = [
        receipt_expectation_from_attempt(
            case_id=artifact.unit_id,
            report_model_id=_MODEL_ID,
            record=record.as_json(),
            expected_output_schema_sha256=output_schema_json_sha256(
                RepresentationAdjudicationOutput,
            ),
        )
        for record in records
        if record.provider_response_id is not None
    ]
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    gate_inputs = RepresentationGateInputs(
        prior_artifact_verified=True,
        prior_exact_match_count=artifact.prior_exact_match_count,
        prior_predicted_event_count=artifact.prior_predicted_event_count,
        prior_non_exact_requirements_passed=(
            artifact.prior_non_exact_requirements_passed
        ),
        adjudication_execution_complete=(
            output is not None and error_type is None and len(records) == 1
        ),
        decision=None if output is None else output.decision,
        expert_source_support=None if output is None else output.expert_source_support,
        candidate_source_support=(
            None if output is None else output.candidate_source_support
        ),
        axes=() if output is None else output.axes,
        evidence_coverage_complete=output is not None,
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        provider_response_id_count=len(expectations),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        fallback_count=0,
    )
    requirements = representation_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_representation_adjudication.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "known_expert_representation_adjudication",
        "repository_evidence": repository_evidence,
        "prior_artifact": {
            "artifact_sha256": artifact.artifact_sha256,
            "report_sha256": artifact.report_sha256,
            "unit_id": artifact.unit_id,
            "exact_whole_event_match_count": artifact.prior_exact_match_count,
            "predicted_event_count": artifact.prior_predicted_event_count,
        },
        "adjudication": None if output is None else output.model_dump(mode="json"),
        "error_type": error_type,
        "attempts": [record.as_json() for record in records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "PROCEED_TO_ONE_UNANNOTATED_DISCOVERY_UNIT"
                if passed
                else "STOP_AND_RECALIBRATE"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "exact_benchmark_score_changed": False,
            "exact_whole_event_match_count": artifact.prior_exact_match_count,
            "agent_adjudicated_diagnostic_only": True,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
        },
    }
    report["report_sha256"] = _sha256_json(report)
    return report


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = ["run_representation_adjudication_pilot"]
