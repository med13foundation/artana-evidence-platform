"""Non-lossy report and deterministic metrics for one V12 execution."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
)
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    audit_identity_mismatch_count,
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    best_projection_event_coverage,
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.context import (
    v12_context_dimensions_json,
    v12_context_dimensions_match,
    v12_context_dimensions_sha256,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.gate import (
    V12GateDecision,
    V12GateInputs,
    v12_gate_decision,
    v12_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    NormalizationFamily,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    receipt_expectations_for_finite_source_records,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
        NestedHoldoutSelection,
    )
    from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
        ThreeCallAgentRunEvidence,
    )


class TransientProviderReceiptVerificationError(RuntimeError):
    """Provider evidence is temporarily unavailable; no report may be sealed."""


def build_v12_report(  # noqa: PLR0913
    *,
    selection: NestedHoldoutSelection,
    run_id: str,
    repeat_index: int,
    configured_model_id: str,
    execution_model_id: str,
    repository_evidence: dict[str, object],
    agent_run: ThreeCallAgentRunEvidence,
) -> dict[str, object]:
    """Combine raw agent evidence with deterministic scientific qualification."""

    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(list(agent_run.records))
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    receipt_payload = receipts.as_json()
    if _receipt_verification_is_transient(receipt_payload):
        raise TransientProviderReceiptVerificationError(
            "V12 provider receipts are temporarily unavailable"
        )
    role_records = {
        role: tuple(
            record for record in agent_run.records if record.attempt_role == role
        )
        for role in ("primary", "structure_normalization", "normalized_review")
    }
    response_ids = {
        record.provider_response_id
        for record in agent_run.records
        if record.provider_response_id is not None
    }
    normalized = (
        ()
        if agent_run.normalized_result is None
        else agent_run.normalized_result.accepted
    )
    review_decisions = (
        ()
        if agent_run.normalized_review is None
        else agent_run.normalized_review.candidate_reviews
    )
    entailed = tuple(
        candidate
        for candidate, review in zip(normalized, review_decisions, strict=False)
        if review.source_entailment is EntailmentDecision.ENTAILED
    )
    links = (
        ()
        if agent_run.normalized_result is None
        else agent_run.normalized_result.controlled_event_links
    )
    projection_match = match_projection_set(
        projection_set=selection.projection_set,
        trusted=entailed,
        links=links,
    )
    recovered_ids = set(projection_match.fully_recovered_inventory_ids)
    best_matched_count, best_expected_count = best_projection_event_coverage(
        projection_match
    )
    unmatched_count = len(
        {candidate.inventory_id for candidate in entailed} - recovered_ids
    )
    mapping_complete = _normalization_mapping_complete(agent_run)
    original_raw_preserved = _raw_matches_model(
        agent_run.original_raw_output,
        agent_run.original_extraction,
    )
    normalized_raw_preserved = _raw_matches_model(
        agent_run.normalized_raw_output,
        agent_run.normalized_extraction,
    )
    review_raw_preserved = _raw_matches_model(
        agent_run.review_raw_output,
        agent_run.normalized_review,
    )
    review_result = agent_run.review_result
    review_output = agent_run.normalized_review
    original_output = agent_run.original_extraction
    normalized_output = agent_run.normalized_extraction
    agent_outputs = {
        "original_extraction": _model_json(original_output),
        "normalized_extraction": _model_json(normalized_output),
        "normalized_review": _model_json(review_output),
        "error_type": agent_run.error_type,
        "failed_stage": agent_run.failed_stage,
    }
    gate_inputs = V12GateInputs(
        repeat_index=repeat_index,
        agent_execution_complete=(
            original_output is not None
            and normalized_output is not None
            and review_output is not None
            and agent_run.error_type is None
        ),
        expected_category=selection.expected_eligibility_category,
        extraction_category=(
            None if original_output is None else original_output.eligibility_category
        ),
        normalization_category=(
            None
            if normalized_output is None
            else normalized_output.eligibility_category
        ),
        review_category=(
            None if review_output is None else review_output.eligibility_category
        ),
        normalization_family=(
            None if normalized_output is None else normalized_output.family
        ),
        normalization_mapping_complete=mapping_complete,
        context_dimensions_match=(
            normalized_output is not None
            and v12_context_dimensions_match(normalized_output)
        ),
        original_raw_payload_preserved=original_raw_preserved,
        normalized_raw_payload_preserved=normalized_raw_preserved,
        review_raw_payload_preserved=review_raw_preserved,
        original_event_count=(
            0 if original_output is None else len(original_output.events)
        ),
        normalized_candidate_count=len(normalized),
        candidate_review_count=len(review_decisions),
        entailed_normalized_candidate_count=len(entailed),
        inventory_coverage=(
            None if review_output is None else review_output.inventory_coverage
        ),
        unsupported_additions=(
            None if review_output is None else review_output.unsupported_additions
        ),
        family_validity=(
            None if review_output is None else review_output.family_validity
        ),
        cue_alignment=(None if review_output is None else review_output.cue_alignment),
        scientific_loss_count=(
            0 if review_result is None else review_result.scientific_loss_count
        ),
        unsupported_addition_count=(
            0 if review_result is None else review_result.unsupported_addition_count
        ),
        unresolved_axis_count=(
            0 if review_result is None else review_result.unresolved_axis_count
        ),
        fully_recovered_projection_count=len(
            projection_match.fully_recovered_projection_ids
        ),
        best_projection_matched_event_count=best_matched_count,
        best_projection_expected_event_count=best_expected_count,
        unmatched_normalized_candidate_count=unmatched_count,
        primary_attempt_count=len(role_records["primary"]),
        normalization_attempt_count=len(role_records["structure_normalization"]),
        normalized_review_attempt_count=len(role_records["normalized_review"]),
        invalid_agent_output_count=invalid_count,
        unidentified_provider_attempt_count=unidentified_count,
        distinct_provider_response_id_count=len(response_ids),
        verified_provider_receipt_count=receipts.verified_count,
        provider_receipt_gate_passed=receipts.gate_passed,
        model_transport_identity_field_count=count_model_identity_fields(agent_outputs),
        audit_identity_mismatch_count=audit_identity_mismatch_count(
            agent_run.records,
            unit=selection.unit,
        ),
        attempt_model_id_mismatch_count=sum(
            record.model_id != execution_model_id for record in agent_run.records
        ),
    )
    requirements = v12_gate_requirements(gate_inputs)
    decision = v12_gate_decision(gate_inputs, requirements)
    passed = decision is V12GateDecision.GO_TO_SMALL_REPLICATION
    report: dict[str, object] = {
        "schema_version": "tg04_nested_event_holdout.v12",
        "run_id": run_id,
        "repeat_index": repeat_index,
        "pre_registered_repeat_indices": [1],
        "generated_at": datetime.now(UTC).isoformat(),
        "configured_model_id": configured_model_id,
        "execution_model_id": execution_model_id,
        "task_id": "fresh_three_agent_representation_diagnostic_v12",
        "expected_eligibility_category": selection.expected_eligibility_category.value,
        "repository_evidence": repository_evidence,
        "freshness": {
            "selection_seed": selection.selection_seed,
            "selection_rule": selection.selection_rule,
            "selection_rank": selection.selection_rank,
            "excluded_document_ids": selection.excluded_document_ids,
            "development_document_count": 40,
            "non_development_document_count": selection.holdout_document_count,
            "eligible_unit_count": selection.candidate_unit_count,
            "incompatible_document_ids": selection.incompatible_document_ids,
            "convenience_sample": True,
            "fresh_at_execution": True,
        },
        "source_corpus": {
            "archive_sha256": selection.archive_sha256,
            "expert_graph_sha256": selection.expert_graph_sha256,
            "projection_set_sha256": selection.projection_set_sha256,
            "context_dimensions_sha256": v12_context_dimensions_sha256(),
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
            "authoritative_article_url": selection.authoritative_article_url,
        },
        "agent_outputs": agent_outputs,
        "raw_agent_outputs": {
            "original_extraction": agent_run.original_raw_output,
            "normalized_extraction": agent_run.normalized_raw_output,
            "normalized_review": agent_run.review_raw_output,
        },
        "original_binding_rejections": (
            []
            if agent_run.original_result is None
            else [item.as_json() for item in agent_run.original_result.rejected]
        ),
        "normalized_candidates": normalized_candidate_rows(
            normalized,
            review_decisions,
        ),
        "controlled_event_links": [link.as_json() for link in links],
        "sealed_expert_graph": selection.expert_graph.as_json(),
        "sealed_projection_set": selection.projection_set.as_json(),
        "sealed_context_dimensions": v12_context_dimensions_json(),
        "deterministic_projection_match": asdict(projection_match),
        "deterministic_metrics": deterministic_metrics(gate_inputs),
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipt_payload,
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": decision.value,
            "requirements": requirements,
        },
        "conclusion_scope": {
            "single_fresh_unit_convenience_sample": True,
            "scientific_qualification_proven": False,
            "small_replication_authorized": passed,
            "benchmark_gold_hidden_from_all_agents": True,
            "original_agent_output_preserved": True,
            "deterministic_scientific_repair_available": False,
            "deterministic_extraction_fallback_available": False,
            "persistence_authorized": False,
            "execution_path": "three_agent_source_normalization_review",
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


def _normalization_mapping_complete(agent_run: ThreeCallAgentRunEvidence) -> bool:
    original = agent_run.original_extraction
    normalized = agent_run.normalized_extraction
    if original is None or normalized is None:
        return False
    if normalized.family is NormalizationFamily.ABSTAIN:
        return False
    mapped = {
        position
        for mapping in normalized.mappings
        for position in mapping.source_event_positions
    }
    return mapped == set(range(len(original.events)))


def _raw_matches_model(raw: dict[str, object] | None, model: BaseModel | None) -> bool:
    if raw is None or model is None:
        return False
    payload = model.model_dump(mode="json")
    return canonical_json_sha256(raw) == canonical_json_sha256(payload)


def _receipt_verification_is_transient(payload: dict[str, object]) -> bool:
    receipts = payload.get("receipts")
    if payload.get("status") not in {"not_verified", "unavailable"}:
        return False
    return isinstance(receipts, list) and bool(receipts) and all(
        isinstance(receipt, dict)
        and (receipt.get("status"), receipt.get("failure"))
        in {
            ("not_verified", "verifier_absent"),
            ("unavailable", "retrieve_failed"),
        }
        for receipt in receipts
    )


def _model_json(model: BaseModel | None) -> dict[str, object] | None:
    if model is None:
        return None
    value = model.model_dump(mode="json")
    if not isinstance(value, dict):
        raise TypeError("agent model output must serialize to an object")
    return value


def normalized_candidate_rows(
    candidates: tuple[object, ...],
    reviews: tuple[object, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for position, candidate in enumerate(candidates):
        inventory_id = getattr(candidate, "inventory_id", None)
        item = getattr(candidate, "item", None)
        if not isinstance(inventory_id, str) or not isinstance(item, BaseModel):
            raise TypeError("normalized candidate is not source bound")
        review = reviews[position] if position < len(reviews) else None
        if review is not None and not isinstance(review, BaseModel):
            raise TypeError("normalized candidate review is invalid")
        rows.append(
            {
                "inventory_id": inventory_id,
                "item": item.model_dump(mode="json"),
                "review": None if review is None else review.model_dump(mode="json"),
            }
        )
    return rows


def deterministic_metrics(inputs: V12GateInputs) -> dict[str, object]:
    source_denominator = inputs.original_event_count
    normalized_denominator = inputs.normalized_candidate_count
    resolved_axes = 10 - inputs.unresolved_axis_count
    return {
        "normalization_mapping_coverage": _ratio(
            source_denominator if inputs.normalization_mapping_complete else 0,
            source_denominator,
        ),
        "frozen_projection_event_recall": _ratio(
            inputs.best_projection_matched_event_count,
            inputs.best_projection_expected_event_count,
        ),
        "normalized_event_precision": _ratio(
            inputs.entailed_normalized_candidate_count,
            normalized_denominator,
        ),
        "scientific_loss_count": inputs.scientific_loss_count,
        "unsupported_addition_count": inputs.unsupported_addition_count,
        "unresolved_axis_count": inputs.unresolved_axis_count,
        "resolved_material_axis_count": resolved_axes,
        "fully_recovered_projection_count": inputs.fully_recovered_projection_count,
        "unmatched_normalized_candidate_count": (
            inputs.unmatched_normalized_candidate_count
        ),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


__all__ = [
    "TransientProviderReceiptVerificationError",
    "build_v12_report",
    "deterministic_metrics",
    "normalized_candidate_rows",
]
