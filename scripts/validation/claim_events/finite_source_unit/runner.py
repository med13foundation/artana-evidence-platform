"""Sealed four-case runner for the finite source-unit TG-04 diagnostic."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast
from uuid import uuid4

from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    VerifiedEventCandidate,
    as_model_client,
    extract_source_unit,
    verify_source_unit_candidates,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)
from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.runner import (
    build_tg04_runtime,
    nary_events_from_bound_inventory,
    receipt_expectation_from_attempt,
)
from scripts.validation.claim_events.scoring import score_fixture
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    ProviderReceiptExpectation,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.claim_frames import (
        BoundClaimInventoryItem,
    )
    from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
        ModelAttemptAuditRecord,
    )

    from scripts.validation.claim_events.contracts import (
        NaryClaimCase,
        NaryClaimFixture,
    )
    from scripts.validation.claim_events.scoring import BenchmarkFixtureContract

_REPO_ROOT: Final = Path(__file__).resolve().parents[4]
_MODEL_ID: Final = "openai:gpt-5.6-luna"
_PANEL_CASE_IDS: Final = (
    "bionlp-ge-2011:PMID-9361029",
    "bionlp-ge-2011:PMC-2222968-03-Results-02",
    "bionlp-ge-2011:PMC-2222968-05-Results-04",
    "bionlp-ge-2011:PMC-2222968-15-Materials_and_Methods-07",
)


@dataclass(frozen=True, slots=True)
class _DiagnosticPanel:
    cases: tuple[NaryClaimCase, ...]


@dataclass(frozen=True, slots=True)
class _CaseResult:
    prediction: dict[str, object]
    evidence: dict[str, object]
    records: tuple[ModelAttemptAuditRecord, ...]
    executable: bool
    coverage_confirmed: bool
    entailed_count: int
    binding_rejection_count: int
    review_only_count: int


@dataclass(frozen=True, slots=True)
class RestartGateInputs:
    case_count: int
    executable_case_count: int
    coverage_confirmed_case_count: int
    exact_whole_event_match_count: int
    empty_control_false_positive_count: int
    negative_or_null_leakage_count: int
    epistemic_escalation_count: int
    binding_rejection_count: int
    invalid_agent_output_count: int
    unidentified_provider_attempt_count: int
    provider_receipts_verified: bool


def run_finite_source_unit_pilot(
    *,
    fixture: NaryClaimFixture,
    run_id: str,
) -> dict[str, object]:
    """Run the one-shot diagnostic against the frozen four-case panel."""

    require_frozen_development_fixture(fixture)
    repository_evidence = collect_repository_evidence(_REPO_ROOT)
    if repository_evidence["clean"] is not True:
        raise RuntimeError("finite source-unit runs require a clean tracked worktree")
    panel = _select_panel(fixture)
    return asyncio.run(
        _run_panel(
            fixture=fixture,
            panel=panel,
            run_id=run_id,
            repository_evidence=repository_evidence,
        ),
    )


async def _run_panel(
    *,
    fixture: NaryClaimFixture,
    panel: _DiagnosticPanel,
    run_id: str,
    repository_evidence: dict[str, object],
) -> dict[str, object]:
    client, tenant, execution_model_id, kernel, store = build_tg04_runtime(_MODEL_ID)
    model_client = as_model_client(client)
    predictions: list[dict[str, object]] = []
    case_evidence: list[dict[str, object]] = []
    all_records: list[ModelAttemptAuditRecord] = []
    executable_cases = coverage_confirmed_cases = 0
    entailed_count = binding_rejections = review_only_count = 0
    try:
        for case in panel.cases:
            result = await _execute_case(
                case=case,
                client=model_client,
                tenant=tenant,
                model_id=execution_model_id,
                run_id=run_id,
            )
            predictions.append(result.prediction)
            case_evidence.append(result.evidence)
            all_records.extend(result.records)
            executable_cases += int(result.executable)
            coverage_confirmed_cases += int(result.coverage_confirmed)
            entailed_count += result.entailed_count
            binding_rejections += result.binding_rejection_count
            review_only_count += result.review_only_count
    finally:
        with suppress(Exception):
            await kernel.close()
        with suppress(Exception):
            await store.close()

    if collect_repository_evidence(_REPO_ROOT) != repository_evidence:
        raise RuntimeError("repository state changed during the finite source-unit run")

    score = score_fixture(cast("BenchmarkFixtureContract", panel), predictions)
    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(all_records)
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    metrics = asdict(score.metrics)
    whole_matches = score.metrics.whole_event_recall.count
    source_supported_unmatched = source_supported_unmatched_count(
        entailed_count=entailed_count,
        exact_match_count=whole_matches,
    )
    requirements = restart_gate_requirements(
        RestartGateInputs(
            case_count=len(panel.cases),
            executable_case_count=executable_cases,
            coverage_confirmed_case_count=coverage_confirmed_cases,
            exact_whole_event_match_count=whole_matches,
            empty_control_false_positive_count=(
                score.metrics.empty_control_false_positive.count
            ),
            negative_or_null_leakage_count=(score.metrics.negative_null_leakage.count),
            epistemic_escalation_count=score.metrics.epistemic_escalation.count,
            binding_rejection_count=binding_rejections,
            invalid_agent_output_count=invalid_count,
            unidentified_provider_attempt_count=unidentified_count,
            provider_receipts_verified=receipts.gate_passed,
        ),
    )
    gate = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": "tg04_finite_source_unit_pilot.v1",
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "model_id": _MODEL_ID,
        "task_id": "finite_source_unit_event_audit",
        "conclusion_scope": {
            "qualifies_experimental_task_only": True,
            "production_document_extraction_exercised": False,
            "production_path_confirmation_required": True,
        },
        "fixture_sha256": fixture.sha256,
        "panel_case_ids": list(_PANEL_CASE_IDS),
        "panel_sha256": _panel_sha256(fixture.sha256),
        "repository_evidence": repository_evidence,
        "predictions": predictions,
        "metrics": metrics,
        "case_scores": [asdict(case) for case in score.cases],
        "diagnostic_measurements": {
            "executable_case_count": executable_cases,
            "case_count": len(panel.cases),
            "coverage_confirmed_case_count": coverage_confirmed_cases,
            "exact_whole_event_match_count": whole_matches,
            "source_entailed_event_count": entailed_count,
            "source_supported_unmatched_count": source_supported_unmatched,
            "review_only_candidate_count": review_only_count,
            "binding_rejection_count": binding_rejections,
        },
        "safety": {
            "fallback_count": 0,
            "invalid_agent_output_count": invalid_count,
            "unidentified_provider_attempt_count": unidentified_count,
            "provider_receipt_status": receipts.status,
            "verified_provider_receipt_count": receipts.verified_count,
            "provider_response_id_count": len(expectations),
        },
        "provider_receipts": receipts.as_json(),
        "case_evidence": case_evidence,
        "restart_gate": {
            "passed": gate,
            "decision": "PROCEED_TO_LARGER_PANEL" if gate else "STOP_AND_RECALIBRATE",
            "requirements": requirements,
        },
    }
    report["report_sha256"] = _sha256_json(report)
    return report


async def _execute_case(
    *,
    case: NaryClaimCase,
    client: object,
    tenant: object,
    model_id: str,
    run_id: str,
) -> _CaseResult:
    from artana_evidence_api.document_extraction import normalize_text_document

    from scripts.validation.claim_events.finite_source_unit.service import (
        FiniteSourceUnitModelClient,
    )

    normalized_text = normalize_text_document(case.source_text)
    units = enumerate_source_units(case_id=case.case_id, source_text=normalized_text)
    audit = start_model_attempt_audit(evidence_unit_id=case.case_id)
    unit_evidence: list[dict[str, object]] = []
    entailed_claims: list[BoundClaimInventoryItem] = []
    review_only: list[dict[str, object]] = []
    binding_rejection_count = 0
    executable = True
    coverage_confirmed = True
    namespace = f"{run_id}:{case.case_id}:{uuid4().hex}"
    try:
        for unit in units:
            try:
                extraction = await extract_source_unit(
                    client=cast("FiniteSourceUnitModelClient", client),
                    tenant=tenant,
                    model_id=model_id,
                    execution_namespace=namespace,
                    unit=unit,
                )
            except Exception as exc:  # noqa: BLE001 - preserve failed run evidence
                executable = False
                coverage_confirmed = False
                unit_evidence.append(
                    _failed_unit_evidence(unit.unit_id, "extraction", exc)
                )
                continue

            extracted = extraction.value
            binding_rejection_count += len(extracted.rejected)
            unit_record: dict[str, object] = {
                "unit_id": unit.unit_id,
                "source_start": unit.source_start,
                "source_end": unit.source_end,
                "eligibility_category": (extracted.output.eligibility_category.value),
                "decision": extracted.output.decision.value,
                "accepted_candidate_ids": [
                    candidate.inventory_id for candidate in extracted.accepted
                ],
                "binding_rejections": [
                    rejection.as_json() for rejection in extracted.rejected
                ],
            }
            try:
                verification = await verify_source_unit_candidates(
                    client=cast("FiniteSourceUnitModelClient", client),
                    tenant=tenant,
                    model_id=model_id,
                    execution_namespace=namespace,
                    unit=unit,
                    candidates=extracted.accepted,
                )
            except Exception as exc:  # noqa: BLE001 - preserve failed run evidence
                executable = False
                coverage_confirmed = False
                unit_record["verification_error"] = type(exc).__name__
                unit_evidence.append(unit_record)
                continue

            categories_agree, unit_coverage_confirmed = _record_eligibility_review(
                unit_record,
                extracted.output.eligibility_category,
                verification.parsed,
            )
            if not categories_agree:
                executable = False
                coverage_confirmed = False
                unit_evidence.append(unit_record)
                continue
            coverage_confirmed = coverage_confirmed and unit_coverage_confirmed
            decisions, accepted, rejected = _partition_verified_candidates(
                verification.value,
            )
            entailed_claims.extend(accepted)
            review_only.extend(rejected)
            unit_record["verification_decisions"] = decisions
            unit_evidence.append(unit_record)
    finally:
        stop_model_attempt_audit(audit)

    events = nary_events_from_bound_inventory(tuple(entailed_claims))
    return _CaseResult(
        prediction={
            "case_id": case.case_id,
            "events": events,
            "review_only_events": review_only,
            "abstained": not events,
            "execution_outcome": "COMPLETE" if executable else "INVALID",
        },
        evidence={
            "case_id": case.case_id,
            "source_unit_count": len(units),
            "units": unit_evidence,
            "attempts": [record.as_json() for record in audit.records],
        },
        records=tuple(audit.records),
        executable=executable,
        coverage_confirmed=coverage_confirmed,
        entailed_count=len(entailed_claims),
        binding_rejection_count=binding_rejection_count,
        review_only_count=len(review_only),
    )


def receipt_expectations_for_finite_source_records(
    records: list[ModelAttemptAuditRecord],
) -> tuple[list[ProviderReceiptExpectation], int, int]:
    expectations: list[ProviderReceiptExpectation] = []
    seen: set[str] = set()
    invalid_count = unidentified_count = 0
    schema_hashes = {
        "primary": output_schema_json_sha256(SourceUnitExtractionOutput),
        "weak_review": output_schema_json_sha256(SourceUnitVerificationOutput),
        "structure_normalization": output_schema_json_sha256(
            SourceUnitNormalizationOutput
        ),
        "normalized_review": output_schema_json_sha256(
            SourceUnitNormalizedReviewOutput
        ),
    }
    for record in records:
        invalid_count += int(record.validation_outcome != "accepted")
        if record.provider_response_id is None:
            unidentified_count += 1
            continue
        if record.provider_response_id in seen:
            raise RuntimeError(
                "finite source-unit provider response IDs must be unique"
            )
        seen.add(record.provider_response_id)
        expectations.append(
            receipt_expectation_from_attempt(
                case_id=record.semantic_unit_id or "unknown-source-unit",
                report_model_id=_MODEL_ID,
                record=record.as_json(),
                expected_output_schema_sha256=schema_hashes[record.pass_role],
            ),
        )
    return expectations, invalid_count, unidentified_count


def _select_panel(fixture: NaryClaimFixture) -> _DiagnosticPanel:
    by_id = {case.case_id: case for case in fixture.cases}
    if set(_PANEL_CASE_IDS) - set(by_id):
        raise RuntimeError("frozen finite source-unit panel is missing cases")
    return _DiagnosticPanel(cases=tuple(by_id[case_id] for case_id in _PANEL_CASE_IDS))


def _panel_sha256(fixture_sha256: str) -> str:
    return _sha256_json(
        {"fixture_sha256": fixture_sha256, "case_ids": _PANEL_CASE_IDS},
    )


def _failed_unit_evidence(
    unit_id: str,
    phase: str,
    error: BaseException,
) -> dict[str, object]:
    return {
        "unit_id": unit_id,
        "phase": phase,
        "error_type": type(error).__name__,
    }


def source_supported_unmatched_count(
    *,
    entailed_count: int,
    exact_match_count: int,
) -> int:
    """Count verified events outside exact gold, including stress-case output."""

    if not 0 <= exact_match_count <= entailed_count:
        raise ValueError("exact matches must be bounded by entailed events")
    return entailed_count - exact_match_count


def _record_eligibility_review(
    unit_record: dict[str, object],
    extraction_category: SourceUnitEligibilityCategory,
    verification: SourceUnitVerificationOutput,
) -> tuple[bool, bool]:
    verification_category = verification.eligibility_category
    categories_agree = eligibility_categories_agree(
        extraction_category,
        verification_category,
    )
    unit_record["verification_eligibility_category"] = verification_category.value
    unit_record["eligibility_categories_agree"] = categories_agree
    unit_record["coverage_decision"] = verification.coverage_decision.value
    unit_record["coverage_reasoning"] = verification.coverage_reasoning
    coverage_confirmed = verification.coverage_decision in {
        SourceUnitCoverageDecision.CANDIDATES_COMPLETE,
        SourceUnitCoverageDecision.NO_EVENT_CONFIRMED,
    }
    return categories_agree, coverage_confirmed


def _partition_verified_candidates(
    candidates: tuple[VerifiedEventCandidate, ...],
) -> tuple[
    list[dict[str, object]],
    tuple[BoundClaimInventoryItem, ...],
    list[dict[str, object]],
]:
    decisions: list[dict[str, object]] = []
    accepted: list[BoundClaimInventoryItem] = []
    rejected: list[dict[str, object]] = []
    for candidate in candidates:
        serialized = {
            "candidate_id": candidate.claim.inventory_id,
            **candidate.verification.model_dump(mode="json"),
        }
        decisions.append(serialized)
        if candidate.verification.trusted_projection_eligible:
            accepted.append(candidate.claim)
        else:
            rejected.append(serialized)
    return decisions, tuple(accepted), rejected


def eligibility_categories_agree(
    extraction: SourceUnitEligibilityCategory,
    verification: SourceUnitEligibilityCategory,
) -> bool:
    """Require independent agents to return the same eligibility category."""

    return extraction is verification


def restart_gate_requirements(inputs: RestartGateInputs) -> dict[str, bool]:
    """Derive every pre-registered stop/go requirement deterministically."""

    return {
        "all_four_cases_executable": (
            inputs.executable_case_count == inputs.case_count
        ),
        "all_source_units_coverage_confirmed": (
            inputs.coverage_confirmed_case_count == inputs.case_count
        ),
        "at_least_one_exact_whole_event": (inputs.exact_whole_event_match_count >= 1),
        "methods_control_empty": inputs.empty_control_false_positive_count == 0,
        "negative_or_null_leakage_zero": (inputs.negative_or_null_leakage_count == 0),
        "epistemic_escalation_zero": inputs.epistemic_escalation_count == 0,
        "binding_rejection_zero": inputs.binding_rejection_count == 0,
        "invalid_agent_output_zero": inputs.invalid_agent_output_count == 0,
        "provider_lineage_complete": (inputs.unidentified_provider_attempt_count == 0),
        "provider_receipts_verified": inputs.provider_receipts_verified,
    }


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


__all__ = [
    "RestartGateInputs",
    "eligibility_categories_agree",
    "receipt_expectations_for_finite_source_records",
    "restart_gate_requirements",
    "run_finite_source_unit_pilot",
    "source_supported_unmatched_count",
]
