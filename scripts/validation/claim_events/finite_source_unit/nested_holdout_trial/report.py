"""Create the non-lossy scientific report for one nested holdout repeat."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    audit_identity_mismatch_count,
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.gate import (
    NestedHoldoutGateInputs,
    nested_holdout_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    receipt_expectations_for_finite_source_records,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    ProjectionEligibilityDecision,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    model_json,
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
    from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
        SingleUnitAgentRunEvidence,
    )

def build_nested_holdout_report(  # noqa: PLR0913
    *,
    selection: NestedHoldoutSelection,
    run_id: str,
    repeat_index: int,
    configured_model_id: str,
    execution_model_id: str,
    repository_evidence: dict[str, object],
    agent_run: SingleUnitAgentRunEvidence,
) -> dict[str, object]:
    """Combine raw agent evidence and deterministic qualification findings."""

    expectations, invalid_count, unidentified_count = (
        receipt_expectations_for_finite_source_records(list(agent_run.records))
    )
    receipts = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    primary_records = tuple(
        record for record in agent_run.records if record.attempt_role == "primary"
    )
    repair_records = tuple(
        record for record in agent_run.records if record.attempt_role == "schema_retry"
    )
    verification_records = tuple(
        record for record in agent_run.records if record.attempt_role == "weak_review"
    )
    extraction_ids = {
        record.provider_response_id
        for record in (*primary_records, *repair_records)
        if record.provider_response_id is not None
    }
    verification_ids = {
        record.provider_response_id
        for record in verification_records
        if record.provider_response_id is not None
    }
    agent_outputs = {
        "extraction": model_json(agent_run.extraction),
        "verification": model_json(agent_run.verification),
        "error_type": agent_run.error_type,
    }
    projection_match = match_projection_set(
        projection_set=selection.projection_set,
        trusted=agent_run.trusted,
        links=agent_run.controlled_event_links,
    )
    gate_inputs = NestedHoldoutGateInputs(
        repeat_index=repeat_index,
        hidden_expert_event_count=len(selection.expert_graph.events),
        hidden_expert_link_count=len(selection.expert_graph.links),
        expected_eligibility_category=selection.expected_eligibility_category,
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
        review_only_candidate_count=sum(
            candidate.verification.projection_eligibility
            is ProjectionEligibilityDecision.REVIEW_ONLY
            for candidate in agent_run.verified
        ),
        rejected_candidate_count=sum(
            candidate.verification.projection_eligibility
            is ProjectionEligibilityDecision.REJECT
            for candidate in agent_run.verified
        ),
        acceptable_projection_count=len(selection.projection_set.projections),
        fully_recovered_projection_count=len(
            projection_match.fully_recovered_projection_ids
        ),
        minimum_acceptable_projection_link_count=min(
            len(projection.graph.links)
            for projection in selection.projection_set.projections
        ),
        observed_binding_rejection_count=len(agent_run.observed_binding_rejections),
        binding_rejection_count=agent_run.binding_rejection_count,
        schema_retry_count=len(repair_records),
        reported_schema_retry_count=agent_run.schema_retry_count,
        primary_extraction_attempt_count=len(primary_records),
        schema_retry_attempt_count=len(repair_records),
        weak_review_attempt_count=len(verification_records),
        controlled_event_link_count=len(agent_run.controlled_event_links),
        controlled_event_link_ambiguity_count=len(
            agent_run.controlled_event_link_ambiguities
        ),
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
        attempt_model_id_mismatch_count=sum(
            record.model_id != execution_model_id for record in agent_run.records
        ),
    )
    requirements = nested_holdout_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    report: dict[str, object] = {
        "schema_version": f"tg04_nested_event_holdout.v{selection.trial_generation}",
        "run_id": run_id,
        "repeat_index": repeat_index,
        "pre_registered_repeat_indices": [1, 2, 3],
        "generated_at": datetime.now(UTC).isoformat(),
        "configured_model_id": configured_model_id,
        "execution_model_id": execution_model_id,
        "task_id": f"fresh_nested_event_identity_holdout_v{selection.trial_generation}",
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
            "fresh_at_repeat_1_execution": repeat_index == 1,
        },
        "source_corpus": {
            "archive_sha256": selection.archive_sha256,
            "expert_graph_sha256": selection.expert_graph_sha256,
            "projection_set_sha256": selection.projection_set_sha256,
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
        "verified_candidates": [
            {
                "inventory_id": candidate.claim.inventory_id,
                "item": candidate.claim.item.model_dump(mode="json"),
                "verification": candidate.verification.model_dump(mode="json"),
            }
            for candidate in agent_run.verified
        ],
        "observed_binding_rejections": [
            rejection.as_json() for rejection in agent_run.observed_binding_rejections
        ],
        "unresolved_binding_rejections": [
            rejection.as_json() for rejection in agent_run.unresolved_binding_rejections
        ],
        "controlled_event_links": [
            link.as_json() for link in agent_run.controlled_event_links
        ],
        "controlled_event_link_ambiguities": [
            ambiguity.as_json()
            for ambiguity in agent_run.controlled_event_link_ambiguities
        ],
        "sealed_expert_graph": selection.expert_graph.as_json(),
        "sealed_projection_set": selection.projection_set.as_json(),
        "deterministic_projection_match": asdict(projection_match),
        "attempts": [record.as_json() for record in agent_run.records],
        "provider_receipts": receipts.as_json(),
        "gate_inputs": asdict(gate_inputs),
        "gate": {
            "passed": passed,
            "decision": (
                "PROCEED_TO_NEXT_PRE_REGISTERED_REPEAT"
                if passed
                else "STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION"
            ),
            "requirements": requirements,
        },
        "conclusion_scope": {
            "single_fresh_unit_convenience_sample": True,
            "sealed_expert_graph_was_hidden_from_agents": True,
            "sealed_projection_set_was_hidden_from_agents": True,
            "additional_source_valid_claims_are_allowed": True,
            "all_additional_claims_must_be_entailed": True,
            "entailed_unresolved_claims_may_remain_review_only": True,
            "rejected_additional_claims_are_allowed": False,
            "benchmark_credit_awarded": False,
            "scientific_readiness_proven": False,
            "persistence_authorized": False,
            "execution_path": "agent_only_source_unit",
            "deterministic_extraction_fallback_available": False,
        },
    }
    report["report_sha256"] = sha256_json(report)
    return report


__all__ = ["build_nested_holdout_report"]
