"""Independent deterministic replay of the V9 scientific qualification gate."""

from __future__ import annotations

import hashlib
from dataclasses import asdict

from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    link_controlled_events,
    unlinked_controlled_target_ids,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    ProjectionEligibilityDecision,
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.gate import (
    NestedHoldoutGateInputs,
    nested_holdout_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.selection import (
    ninth_projection_set,
    ninth_unit_identity,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_verification,
    canonical_source_unit_binding_repair_prompt,
    canonical_source_unit_extraction_prompt,
    canonical_source_unit_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)
from scripts.validation.claim_events.finite_source_unit.source_validation.replay import (
    ReplayedSourceBinding,
    replay_source_binding,
)


def require_replayed_ninth_qualification(report: dict[str, object]) -> None:
    """Rebuild every scientific derived field from receipt-bound agent payloads."""

    unit = _required_dict(report, "unit")
    expected_identity = ninth_unit_identity()
    if any(unit.get(key) != value for key, value in expected_identity.items()):
        raise RuntimeError("ninth holdout unit identity changed")
    frozen_unit = FrozenSourceUnit(
        unit_id=_required_string(unit, "unit_id"),
        index=_required_int(unit, "unit_index"),
        source_start=_required_int(unit, "source_start"),
        source_end=_required_int(unit, "source_end"),
        text=_required_string(unit, "text"),
        source_sha256=_required_string(unit, "source_sha256"),
    )
    if frozen_unit.input_sha256 != unit.get("input_sha256"):
        raise RuntimeError("ninth holdout source input identity changed")

    agent_outputs = _required_dict(report, "agent_outputs")
    attempts = _required_list(report, "attempts")
    if (
        report.get("expected_eligibility_category")
        != SourceUnitEligibilityCategory.MIXED_SCIENTIFIC.value
    ):
        raise RuntimeError("ninth holdout expected category changed")
    replayed_binding = replay_source_binding(
        unit=frozen_unit,
        agent_extraction=_required_dict(agent_outputs, "extraction"),
        attempts=attempts,
    )
    extraction = replayed_binding.extraction
    verification = SourceUnitVerificationOutput.model_validate(
        _required_dict(agent_outputs, "verification")
    )
    bound = replayed_binding.bound
    verified = bind_source_unit_verification(
        verification,
        unit=frozen_unit,
        candidates=bound.accepted,
    )
    entailed = tuple(
        candidate.claim
        for candidate in verified
        if candidate.verification.decision is EntailmentDecision.ENTAILED
    )
    trusted = tuple(
        candidate.claim
        for candidate in verified
        if candidate.verification.trusted_projection_eligible
    )
    link_result = link_controlled_events(bound.accepted)
    projection_set = ninth_projection_set()
    projection_match = match_projection_set(
        projection_set=projection_set,
        trusted=trusted,
        links=link_result.links,
    )
    _require_equal(
        report,
        "verified_candidates",
        [
            {
                "inventory_id": candidate.claim.inventory_id,
                "item": candidate.claim.item.model_dump(mode="json"),
                "verification": candidate.verification.model_dump(mode="json"),
            }
            for candidate in verified
        ],
    )
    _require_equal(
        report,
        "observed_binding_rejections",
        [rejection.as_json() for rejection in replayed_binding.observed_rejections],
    )
    _require_equal(
        report,
        "unresolved_binding_rejections",
        [rejection.as_json() for rejection in replayed_binding.unresolved_rejections],
    )
    _require_equal(
        report,
        "controlled_event_links",
        [link.as_json() for link in link_result.links],
    )
    _require_equal(
        report,
        "controlled_event_link_ambiguities",
        [ambiguity.as_json() for ambiguity in link_result.ambiguities],
    )
    _require_equal(
        report,
        "unlinked_controlled_event_references",
        [reference.as_json() for reference in link_result.unlinked_references],
    )
    orphan_target_ids = unlinked_controlled_target_ids(
        bound.accepted,
        link_result.links,
    )
    _require_equal(
        report,
        "unlinked_controlled_target_ids",
        list(orphan_target_ids),
    )
    _require_equal(
        report, "sealed_expert_graph", projection_set.canonical_projection.graph.as_json()
    )
    _require_equal(report, "sealed_projection_set", projection_set.as_json())
    _require_equal(report, "deterministic_projection_match", asdict(projection_match))

    receipts = _required_dict(report, "provider_receipts")
    _require_canonical_provider_prompts(
        unit=frozen_unit,
        candidates=bound.accepted,
        replayed_binding=replayed_binding,
        attempts=attempts,
        receipts=receipts,
    )
    primary_count = _attempt_count(attempts, "primary")
    repair_count = _attempt_count(attempts, "schema_retry")
    review_count = _attempt_count(attempts, "weak_review")
    extraction_ids = _response_ids(attempts, {"primary", "schema_retry"})
    verification_ids = _response_ids(attempts, {"weak_review"})
    gate_inputs = NestedHoldoutGateInputs(
        repeat_index=_required_int(report, "repeat_index"),
        hidden_expert_event_count=len(projection_set.canonical_projection.graph.events),
        hidden_expert_link_count=len(projection_set.canonical_projection.graph.links),
        expected_eligibility_category=SourceUnitEligibilityCategory.MIXED_SCIENTIFIC,
        agent_execution_complete=agent_outputs.get("error_type") is None,
        extraction_category=extraction.eligibility_category,
        verification_category=verification.eligibility_category,
        extraction_decision=extraction.decision,
        verification_coverage=verification.coverage_decision,
        extracted_candidate_count=len(bound.accepted),
        verification_decision_count=len(verified),
        entailed_candidate_count=len(entailed),
        trusted_candidate_count=len(trusted),
        unmatched_trusted_candidate_count=len(
            {candidate.inventory_id for candidate in trusted}
            - set(projection_match.fully_recovered_inventory_ids)
        ),
        review_only_candidate_count=sum(
            item.verification.projection_eligibility
            is ProjectionEligibilityDecision.REVIEW_ONLY
            for item in verified
        ),
        rejected_candidate_count=sum(
            item.verification.projection_eligibility
            is ProjectionEligibilityDecision.REJECT
            for item in verified
        ),
        acceptable_projection_count=len(projection_set.projections),
        fully_recovered_projection_count=len(
            projection_match.fully_recovered_projection_ids
        ),
        minimum_acceptable_projection_link_count=min(
            len(projection.graph.links) for projection in projection_set.projections
        ),
        observed_binding_rejection_count=len(replayed_binding.observed_rejections),
        binding_rejection_count=len(replayed_binding.unresolved_rejections),
        schema_retry_count=repair_count,
        reported_schema_retry_count=repair_count,
        primary_extraction_attempt_count=primary_count,
        schema_retry_attempt_count=repair_count,
        weak_review_attempt_count=review_count,
        controlled_event_link_count=len(link_result.links),
        controlled_event_link_ambiguity_count=len(link_result.ambiguities),
        unlinked_controlled_event_reference_count=len(link_result.unlinked_references),
        unlinked_controlled_target_count=len(orphan_target_ids),
        invalid_agent_output_count=sum(
            isinstance(item, dict) and item.get("validation_outcome") != "accepted"
            for item in attempts
        ),
        unidentified_provider_attempt_count=sum(
            not isinstance(item, dict)
            or not isinstance(item.get("provider_response_id"), str)
            for item in attempts
        ),
        extraction_provider_response_id_count=len(extraction_ids),
        verification_provider_response_id_count=len(verification_ids),
        distinct_provider_response_id_count=len(extraction_ids | verification_ids),
        verified_provider_receipt_count=_required_int(receipts, "verified_count"),
        provider_receipt_gate_passed=(
            receipts.get("status") == "verified_live"
            and receipts.get("expected_count") == receipts.get("verified_count")
        ),
        model_transport_identity_field_count=count_model_identity_fields(agent_outputs),
        audit_identity_mismatch_count=sum(
            not isinstance(item, dict)
            or item.get("semantic_unit_id") != frozen_unit.unit_id
            or item.get("source_sha256") != frozen_unit.source_sha256
            or item.get("input_sha256") != frozen_unit.input_sha256
            for item in attempts
        ),
        attempt_model_id_mismatch_count=sum(
            not isinstance(item, dict)
            or item.get("model_id") != report.get("execution_model_id")
            for item in attempts
        ),
    )
    _require_equal(report, "gate_inputs", asdict(gate_inputs))
    requirements = nested_holdout_gate_requirements(gate_inputs)
    passed = all(requirements.values())
    _require_equal(
        report,
        "gate",
        {
            "passed": passed,
            "decision": (
                "PROCEED_TO_NEXT_PRE_REGISTERED_REPEAT"
                if passed
                else "STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION"
            ),
            "requirements": requirements,
        },
    )


def _require_canonical_provider_prompts(
    *,
    unit: FrozenSourceUnit,
    candidates: tuple[BoundClaimInventoryItem, ...],
    replayed_binding: ReplayedSourceBinding | None = None,
    attempts: list[object],
    receipts: dict[str, object],
) -> None:
    receipt_items = receipts.get("receipts")
    if not isinstance(receipt_items, list):
        raise TypeError("ninth holdout provider receipts must be a list")
    receipts_by_id = {
        item.get("response_id"): item
        for item in receipt_items
        if isinstance(item, dict) and isinstance(item.get("response_id"), str)
    }
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise TypeError("ninth holdout attempt must be an object")
        role = attempt.get("attempt_role")
        output_schema: type[SourceUnitExtractionOutput | SourceUnitVerificationOutput]
        if role == "primary":
            output_schema = SourceUnitExtractionOutput
            prompt = canonical_source_unit_extraction_prompt(unit)
        elif role == "schema_retry":
            if replayed_binding is None:
                raise RuntimeError("ninth holdout repair replay is unavailable")
            output_schema = SourceUnitExtractionOutput
            prompt = canonical_source_unit_binding_repair_prompt(
                unit=unit,
                rejected_output=replayed_binding.primary_extraction,
                binding_errors=replayed_binding.primary_rejections,
            )
        elif role == "weak_review":
            output_schema = SourceUnitVerificationOutput
            prompt = canonical_source_unit_verification_prompt(
                unit=unit,
                candidates=candidates,
            )
        else:
            raise RuntimeError("ninth holdout attempt role is not canonical")
        response_id = _required_string(attempt, "provider_response_id")
        receipt = receipts_by_id.get(response_id)
        if not isinstance(receipt, dict):
            raise TypeError("ninth holdout attempt lacks its provider receipt")
        schema_sha256 = output_schema_json_sha256(output_schema)
        provider_prompt = bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=_required_string(attempt, "invocation_id"),
            source_sha256=unit.source_sha256,
            input_sha256=unit.input_sha256,
            evidence_unit_sha256=_required_string(
                attempt,
                "evidence_unit_sha256",
            ),
            output_schema_sha256=schema_sha256,
        )
        prompt_sha256 = hashlib.sha256(provider_prompt.encode("utf-8")).hexdigest()
        expected_schema_identity = (
            f"{output_schema.__module__}.{output_schema.__qualname__}"
        )
        if (
            attempt.get("prompt_sha256") != prompt_sha256
            or attempt.get("output_schema_identity") != expected_schema_identity
            or receipt.get("expected_prompt_sha256") != prompt_sha256
            or receipt.get("expected_output_schema_sha256") != schema_sha256
        ):
            raise RuntimeError("ninth holdout provider prompt is not canonical")


def _attempt_count(attempts: list[object], role: str) -> int:
    return sum(
        isinstance(item, dict) and item.get("attempt_role") == role for item in attempts
    )


def _response_ids(attempts: list[object], roles: set[str]) -> set[str]:
    return {
        response_id
        for item in attempts
        if isinstance(item, dict)
        and item.get("attempt_role") in roles
        and isinstance((response_id := item.get("provider_response_id")), str)
    }


def _require_equal(report: dict[str, object], key: str, expected: object) -> None:
    if sha256_json(report.get(key)) != sha256_json(expected):
        raise RuntimeError(f"ninth holdout {key} differs from deterministic replay")


def _required_dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"ninth holdout {key} must be an object")
    return item


def _required_list(value: dict[str, object], key: str) -> list[object]:
    item = value.get(key)
    if not isinstance(item, list):
        raise TypeError(f"ninth holdout {key} must be a list")
    return item


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"ninth holdout {key} must be text")
    return item


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TypeError(f"ninth holdout {key} must be an integer")
    return item


__all__ = ["require_replayed_ninth_qualification"]
