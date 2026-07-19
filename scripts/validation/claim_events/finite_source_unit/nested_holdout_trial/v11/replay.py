"""Deterministic replay of the complete V11 scientific result."""

from __future__ import annotations

from dataclasses import asdict
from enum import StrEnum
from typing import Final, TypeVar

from scripts.validation.claim_events.finite_source_unit.contracts import (
    EntailmentDecision,
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.discovery.identity_evidence import (
    count_model_identity_fields,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    best_projection_event_coverage,
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.sequence_support.terminal_failure import (
    TerminalFailureContract,
    require_terminal_workflow_failure_evidence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.context import (
    V11_CONTEXT_DIMENSIONS,
    v11_context_dimensions_match,
    v11_context_dimensions_sha256,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.custody import (
    validate_v11_attempt_chain,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.gate import (
    V11GateInputs,
    v11_gate_decision,
    v11_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.report import (
    deterministic_metrics,
    normalized_candidate_rows,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.selection import (
    eleventh_projection_set,
    eleventh_unit_identity,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    CueAlignmentDecision,
    FamilyValidityDecision,
    InventoryCoverageDecision,
    NormalizationFamily,
    PresenceDecision,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    bind_source_unit_normalized_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    SourceUnitNormalizationResult,
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)

V11_ARCHIVE_SHA256: Final = (
    "f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f"
)
V11_EXPERT_GRAPH_SHA256: Final = (
    "a77aa47edb35008c9149e9ab92bc0f01dce32510c92e1adb4b2bbca8df310a15"
)
V11_PROJECTION_SET_SHA256: Final = (
    "e74d4cce878d1e6894bbd82345f438df437bddfbe8663bb26f91b161ce687f1a"
)
_EXPECTED_ATTEMPT_COUNT: Final = 3
_V11_ATTEMPT_ROLES: Final = (
    ("primary", "primary", "original_extraction"),
    (
        "structure_normalization",
        "structure_normalization",
        "normalized_extraction",
    ),
    ("normalized_review", "normalized_review", "normalized_review"),
)
EnumT = TypeVar("EnumT", bound=StrEnum)


def require_replayed_v11_qualification(report: dict[str, object]) -> None:
    """Rebuild source meaning and the V11 gate from immutable report payloads."""

    _require_report_hash(report)
    _require_frozen_identity(report)
    unit_payload = _dict(report, "unit")
    unit = FrozenSourceUnit(
        unit_id=_string(unit_payload, "unit_id"),
        index=_integer(unit_payload, "unit_index"),
        source_start=_integer(unit_payload, "source_start"),
        source_end=_integer(unit_payload, "source_end"),
        text=_string(unit_payload, "text"),
        source_sha256=_string(unit_payload, "source_sha256"),
    )
    if unit.input_sha256 != _string(unit_payload, "input_sha256"):
        raise RuntimeError("V11 source-unit input identity changed")

    outputs = _dict(report, "agent_outputs")
    raw_outputs = _dict(report, "raw_agent_outputs")
    if isinstance(outputs.get("error_type"), str):
        _require_terminal_failure_replay(
            report=report,
            unit=unit,
            outputs=outputs,
            raw_outputs=raw_outputs,
        )
        return
    original_payload = _dict(outputs, "original_extraction")
    normalized_payload = _dict(outputs, "normalized_extraction")
    review_payload = _dict(outputs, "normalized_review")
    if outputs.get("error_type") is not None or outputs.get("failed_stage") is not None:
        raise RuntimeError("V11 completed qualification cannot contain agent error")
    _require_raw_output(raw_outputs, "original_extraction", original_payload)
    _require_raw_output(raw_outputs, "normalized_extraction", normalized_payload)
    _require_raw_output(raw_outputs, "normalized_review", review_payload)
    _require_attempt_topology(report, outputs)
    _require_chain_custody(report)

    original_output = SourceUnitExtractionOutput.model_validate(original_payload)
    original = bind_source_unit_extraction(original_output, unit=unit)
    normalized_output = SourceUnitNormalizationOutput.model_validate(normalized_payload)
    normalized = bind_source_unit_normalization(
        normalized_output,
        unit=unit,
        original=original,
    )
    review_output = SourceUnitNormalizedReviewOutput.model_validate(review_payload)
    reviewed = bind_source_unit_normalized_review(
        review_output,
        unit=unit,
        original=original,
        normalized=normalized,
    )
    entailed = tuple(
        candidate
        for candidate, review in zip(
            normalized.accepted,
            review_output.candidate_reviews,
            strict=True,
        )
        if review.source_entailment is EntailmentDecision.ENTAILED
    )
    projection_match = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=entailed,
        links=normalized.controlled_event_links,
    )
    best_matched_count, best_expected_count = best_projection_event_coverage(
        projection_match
    )
    if canonical_json_sha256(report.get("deterministic_projection_match")) != (
        canonical_json_sha256(asdict(projection_match))
    ):
        raise RuntimeError("V11 deterministic projection match changed")

    gate_payload = _dict(report, "gate_inputs")
    expected_derived = {
        "extraction_category": original_output.eligibility_category.value,
        "normalization_category": normalized_output.eligibility_category.value,
        "review_category": review_output.eligibility_category.value,
        "normalization_family": normalized_output.family.value,
        "normalization_mapping_complete": _mapping_complete(
            original_output,
            normalized_output,
        ),
        "context_dimensions_match": v11_context_dimensions_match(normalized_output),
        "original_raw_payload_preserved": True,
        "normalized_raw_payload_preserved": True,
        "original_event_count": len(original_output.events),
        "normalized_candidate_count": len(normalized.accepted),
        "candidate_review_count": len(review_output.candidate_reviews),
        "entailed_normalized_candidate_count": len(entailed),
        "inventory_coverage": review_output.inventory_coverage.value,
        "unsupported_additions": review_output.unsupported_additions.value,
        "family_validity": review_output.family_validity.value,
        "cue_alignment": review_output.cue_alignment.value,
        "scientific_loss_count": reviewed.scientific_loss_count,
        "unsupported_addition_count": reviewed.unsupported_addition_count,
        "unresolved_axis_count": reviewed.unresolved_axis_count,
        "fully_recovered_projection_count": len(
            projection_match.fully_recovered_projection_ids
        ),
        "best_projection_matched_event_count": best_matched_count,
        "best_projection_expected_event_count": best_expected_count,
        "unmatched_normalized_candidate_count": len(
            {candidate.inventory_id for candidate in entailed}
            - set(projection_match.fully_recovered_inventory_ids)
        ),
        "model_transport_identity_field_count": count_model_identity_fields(outputs),
    }
    if any(gate_payload.get(key) != value for key, value in expected_derived.items()):
        raise RuntimeError("V11 gate inputs do not replay from agent outputs")
    inputs = _gate_inputs(gate_payload)
    _require_derived_artifacts(
        report=report,
        original_rejections=[item.as_json() for item in original.rejected],
        normalized=normalized,
        review=review_output,
        inputs=inputs,
    )
    requirements = v11_gate_requirements(inputs)
    gate = _dict(report, "gate")
    if gate.get("requirements") != requirements:
        raise RuntimeError("V11 gate requirements changed during replay")
    decision = v11_gate_decision(inputs, requirements)
    if gate.get("decision") != decision.value or gate.get("passed") is not all(
        requirements.values()
    ):
        raise RuntimeError("V11 terminal gate decision changed during replay")


def _require_chain_custody(report: dict[str, object]) -> None:
    attempts = report.get("attempts")
    if (
        not isinstance(attempts, list)
        or not attempts
        or not isinstance(attempts[0], dict)
    ):
        raise TypeError("V11 replay requires chained attempt evidence")
    validate_v11_attempt_chain(
        report,
        _string(attempts[0], "evidence_unit_sha256"),
    )


def _require_derived_artifacts(
    *,
    report: dict[str, object],
    original_rejections: list[dict[str, object]],
    normalized: SourceUnitNormalizationResult,
    review: SourceUnitNormalizedReviewOutput,
    inputs: V11GateInputs,
) -> None:
    if report.get("original_binding_rejections") != original_rejections:
        raise RuntimeError("V11 original binding rejection artifact changed")
    if report.get("normalized_candidates") != normalized_candidate_rows(
        normalized.accepted,
        review.candidate_reviews,
    ):
        raise RuntimeError("V11 normalized candidate artifact changed")
    if report.get("controlled_event_links") != [
        link.as_json() for link in normalized.controlled_event_links
    ]:
        raise RuntimeError("V11 controlled-event link artifact changed")
    if canonical_json_sha256(
        report.get("sealed_expert_graph")
    ) != canonical_json_sha256(
        eleventh_projection_set().canonical_projection.graph.as_json()
    ):
        raise RuntimeError("V11 sealed expert graph changed")
    if report.get("deterministic_metrics") != deterministic_metrics(inputs):
        raise RuntimeError("V11 deterministic metrics changed")
    if canonical_json_sha256(
        report.get("sealed_context_dimensions")
    ) != canonical_json_sha256(
        [dimension.as_json() for dimension in V11_CONTEXT_DIMENSIONS]
    ):
        raise RuntimeError("V11 sealed context dimensions changed")


def _require_terminal_failure_replay(
    *,
    report: dict[str, object],
    unit: FrozenSourceUnit,
    outputs: dict[str, object],
    raw_outputs: dict[str, object],
) -> None:
    attempts = report.get("attempts")
    if (
        not isinstance(attempts, list)
        or not attempts
        or not isinstance(attempts[0], dict)
    ):
        raise RuntimeError("V11 terminal failure lacks attempt evidence")
    validate_v11_attempt_chain(
        report,
        _string(attempts[0], "evidence_unit_sha256"),
    )
    receipts_payload = _dict(report, "provider_receipts")
    require_terminal_workflow_failure_evidence(
        contract=TerminalFailureContract(
            label="eleventh holdout",
            execution_model_id="openai/gpt-5.6-luna",
            receipt_model_id="gpt-5.6-luna",
            execution_path="three_agent_source_normalization_review",
            roles=_V11_ATTEMPT_ROLES,
            evidence_unit_sha256=_string(attempts[0], "evidence_unit_sha256"),
        ),
        unit=_dict(report, "unit"),
        agent_outputs=outputs,
        attempts=attempts,
        receipts=receipts_payload,
        repository=report.get("repository_evidence"),
        scope=report.get("conclusion_scope"),
        report_execution_model_id=report.get("execution_model_id"),
    )
    original_payload = _optional_dict(outputs, "original_extraction")
    normalized_payload = _optional_dict(outputs, "normalized_extraction")
    review_payload = _optional_dict(outputs, "normalized_review")
    if review_payload is not None:
        raise RuntimeError("V11 terminal failure cannot contain accepted review")
    original_output = (
        None
        if original_payload is None
        else SourceUnitExtractionOutput.model_validate(original_payload)
    )
    original = (
        None
        if original_output is None
        else bind_source_unit_extraction(original_output, unit=unit)
    )
    normalized_output = (
        None
        if normalized_payload is None
        else SourceUnitNormalizationOutput.model_validate(normalized_payload)
    )
    if normalized_output is not None and original is None:
        raise RuntimeError("V11 normalization cannot precede extraction")
    normalized = (
        None
        if normalized_output is None or original is None
        else bind_source_unit_normalization(
            normalized_output,
            unit=unit,
            original=original,
        )
    )
    _require_optional_raw_output(raw_outputs, "original_extraction", original_payload)
    _require_optional_raw_output(
        raw_outputs, "normalized_extraction", normalized_payload
    )
    _require_optional_raw_output(raw_outputs, "normalized_review", None)
    projection_match = match_projection_set(
        projection_set=eleventh_projection_set(),
        trusted=(),
        links=() if normalized is None else normalized.controlled_event_links,
    )
    best_matched_count, best_expected_count = best_projection_event_coverage(
        projection_match
    )
    receipts = receipts_payload
    receipt_items = receipts.get("receipts")
    if not isinstance(receipt_items, list):
        raise TypeError("V11 provider receipts must be a list")
    response_ids = {
        attempt.get("provider_response_id")
        for attempt in attempts
        if isinstance(attempt, dict)
        and isinstance(attempt.get("provider_response_id"), str)
    }
    verified_receipt_count = sum(
        isinstance(receipt, dict) and receipt.get("status") == "verified_live"
        for receipt in receipt_items
    )
    expected_receipt_count = receipts.get("expected_count")
    receipt_gate_passed = (
        receipts.get("status") == "verified_live"
        and isinstance(expected_receipt_count, int)
        and expected_receipt_count > 0
        and receipts.get("verified_count") == expected_receipt_count
    )
    inputs = V11GateInputs(
        repeat_index=_integer(report, "repeat_index"),
        agent_execution_complete=False,
        expected_category=SourceUnitEligibilityCategory.NULL_RESULT,
        extraction_category=(
            None if original_output is None else original_output.eligibility_category
        ),
        normalization_category=(
            None
            if normalized_output is None
            else normalized_output.eligibility_category
        ),
        review_category=None,
        normalization_family=(
            None if normalized_output is None else normalized_output.family
        ),
        normalization_mapping_complete=(
            False
            if original_output is None or normalized_output is None
            else _mapping_complete(original_output, normalized_output)
        ),
        context_dimensions_match=(
            normalized_output is not None
            and v11_context_dimensions_match(normalized_output)
        ),
        original_raw_payload_preserved=original_payload is not None,
        normalized_raw_payload_preserved=normalized_payload is not None,
        original_event_count=(
            0 if original_output is None else len(original_output.events)
        ),
        normalized_candidate_count=(
            0 if normalized is None else len(normalized.accepted)
        ),
        candidate_review_count=0,
        entailed_normalized_candidate_count=0,
        inventory_coverage=None,
        unsupported_additions=None,
        family_validity=None,
        cue_alignment=None,
        scientific_loss_count=0,
        unsupported_addition_count=0,
        unresolved_axis_count=0,
        fully_recovered_projection_count=0,
        best_projection_matched_event_count=best_matched_count,
        best_projection_expected_event_count=best_expected_count,
        unmatched_normalized_candidate_count=0,
        primary_attempt_count=_attempt_count(attempts, "primary"),
        normalization_attempt_count=_attempt_count(attempts, "structure_normalization"),
        normalized_review_attempt_count=_attempt_count(attempts, "normalized_review"),
        invalid_agent_output_count=sum(
            isinstance(attempt, dict)
            and attempt.get("validation_outcome") != "accepted"
            for attempt in attempts
        ),
        unidentified_provider_attempt_count=sum(
            isinstance(attempt, dict) and attempt.get("provider_response_id") is None
            for attempt in attempts
        ),
        distinct_provider_response_id_count=len(response_ids),
        verified_provider_receipt_count=verified_receipt_count,
        provider_receipt_gate_passed=receipt_gate_passed,
        model_transport_identity_field_count=count_model_identity_fields(outputs),
        audit_identity_mismatch_count=0,
        attempt_model_id_mismatch_count=sum(
            isinstance(attempt, dict)
            and attempt.get("model_id") != report.get("execution_model_id")
            for attempt in attempts
        ),
    )
    gate_payload = _dict(report, "gate_inputs")
    if canonical_json_sha256(gate_payload) != canonical_json_sha256(asdict(inputs)):
        raise RuntimeError("V11 terminal gate inputs changed during replay")
    requirements = v11_gate_requirements(inputs)
    decision = v11_gate_decision(inputs, requirements)
    gate = _dict(report, "gate")
    if (
        inputs.agent_execution_complete
        or gate.get("requirements") != requirements
        or decision.value != "STOP_WORKFLOW_INVALID"
        or gate.get("decision") != decision.value
        or gate.get("passed") is not False
        or report.get("deterministic_metrics") != deterministic_metrics(inputs)
    ):
        raise RuntimeError("V11 terminal workflow failure changed during replay")
    expected_rows = (
        [] if normalized is None else normalized_candidate_rows(normalized.accepted, ())
    )
    expected_links = (
        []
        if normalized is None
        else [link.as_json() for link in normalized.controlled_event_links]
    )
    if (
        report.get("original_binding_rejections")
        != ([] if original is None else [item.as_json() for item in original.rejected])
        or report.get("normalized_candidates") != expected_rows
        or report.get("controlled_event_links") != expected_links
        or canonical_json_sha256(report.get("sealed_expert_graph"))
        != canonical_json_sha256(
            eleventh_projection_set().canonical_projection.graph.as_json()
        )
        or canonical_json_sha256(report.get("sealed_context_dimensions"))
        != canonical_json_sha256(
            [dimension.as_json() for dimension in V11_CONTEXT_DIMENSIONS]
        )
        or canonical_json_sha256(report.get("deterministic_projection_match"))
        != canonical_json_sha256(asdict(projection_match))
    ):
        raise RuntimeError("V11 terminal scientific artifacts changed during replay")
    scope = _dict(report, "conclusion_scope")
    if (
        scope.get("persistence_authorized") is not False
        or scope.get("small_replication_authorized") is not False
        or not isinstance(outputs.get("error_type"), str)
        or not isinstance(outputs.get("failed_stage"), str)
    ):
        raise RuntimeError("V11 terminal failure scope is invalid")


def _attempt_count(attempts: list[object], role: str) -> int:
    return sum(
        isinstance(attempt, dict) and attempt.get("attempt_role") == role
        for attempt in attempts
    )


def _optional_dict(
    value: dict[str, object],
    key: str,
) -> dict[str, object] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, dict):
        raise TypeError(f"V11 {key} must be an object or null")
    return item


def _require_optional_raw_output(
    raw_outputs: dict[str, object],
    key: str,
    parsed: dict[str, object] | None,
) -> None:
    raw = raw_outputs.get(key)
    if parsed is None:
        if raw is not None:
            raise RuntimeError(f"V11 raw {key} exists without accepted output")
        return
    if not isinstance(raw, dict) or canonical_json_sha256(raw) != (
        canonical_json_sha256(parsed)
    ):
        raise RuntimeError(f"V11 raw {key} output changed")


def _require_attempt_topology(
    report: dict[str, object],
    outputs: dict[str, object],
) -> None:
    attempts = report.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != _EXPECTED_ATTEMPT_COUNT:
        raise RuntimeError("V11 replay requires exactly three attempts")
    expected = (
        ("primary", "original_extraction"),
        ("structure_normalization", "normalized_extraction"),
        ("normalized_review", "normalized_review"),
    )
    response_ids: set[str] = set()
    for attempt, (role, output_key) in zip(attempts, expected, strict=True):
        if not isinstance(attempt, dict):
            raise TypeError("V11 attempt must be an object")
        response_id = attempt.get("provider_response_id")
        if (
            attempt.get("attempt_role") != role
            or attempt.get("pass_role") != role
            or attempt.get("validation_outcome") != "accepted"
            or attempt.get("replayed") is not False
            or not isinstance(response_id, str)
            or attempt.get("raw_model_payload") != outputs.get(output_key)
        ):
            raise RuntimeError("V11 attempt topology or raw payload changed")
        response_ids.add(response_id)
    if len(response_ids) != _EXPECTED_ATTEMPT_COUNT:
        raise RuntimeError("V11 provider response identities must be distinct")


def _require_frozen_identity(report: dict[str, object]) -> None:
    if report.get("schema_version") != "tg04_nested_event_holdout.v11":
        raise RuntimeError("V11 report schema changed")
    source = _dict(report, "source_corpus")
    if source != {
        "archive_sha256": V11_ARCHIVE_SHA256,
        "expert_graph_sha256": V11_EXPERT_GRAPH_SHA256,
        "projection_set_sha256": V11_PROJECTION_SET_SHA256,
        "context_dimensions_sha256": v11_context_dimensions_sha256(),
    }:
        raise RuntimeError("V11 corpus or projection identity changed")
    unit = _dict(report, "unit")
    identity = eleventh_unit_identity()
    if any(unit.get(key) != value for key, value in identity.items()):
        raise RuntimeError("V11 frozen source identity changed")
    if canonical_json_sha256(report.get("sealed_projection_set")) != (
        canonical_json_sha256(eleventh_projection_set().as_json())
    ):
        raise RuntimeError("V11 sealed projection set changed")


def _require_report_hash(report: dict[str, object]) -> None:
    unsigned = dict(report)
    observed = unsigned.pop("report_sha256", None)
    if not isinstance(observed, str) or observed != sha256_json(unsigned):
        raise RuntimeError("V11 report hash changed")


def _require_raw_output(
    raw_outputs: dict[str, object],
    key: str,
    parsed: dict[str, object],
) -> None:
    raw = _dict(raw_outputs, key)
    if canonical_json_sha256(raw) != canonical_json_sha256(parsed):
        raise RuntimeError(f"V11 raw {key} output changed")


def _mapping_complete(
    original: SourceUnitExtractionOutput,
    normalized: SourceUnitNormalizationOutput,
) -> bool:
    if normalized.family is NormalizationFamily.ABSTAIN:
        return False
    return {
        position
        for mapping in normalized.mappings
        for position in mapping.source_event_positions
    } == set(range(len(original.events)))


def _gate_inputs(value: dict[str, object]) -> V11GateInputs:
    return V11GateInputs(
        repeat_index=_integer(value, "repeat_index"),
        agent_execution_complete=_boolean(value, "agent_execution_complete"),
        expected_category=SourceUnitEligibilityCategory(
            _string(value, "expected_category")
        ),
        extraction_category=_eligibility(value.get("extraction_category")),
        normalization_category=_eligibility(value.get("normalization_category")),
        review_category=_eligibility(value.get("review_category")),
        normalization_family=_optional_enum(
            NormalizationFamily, value.get("normalization_family")
        ),
        normalization_mapping_complete=_boolean(
            value, "normalization_mapping_complete"
        ),
        context_dimensions_match=_boolean(value, "context_dimensions_match"),
        original_raw_payload_preserved=_boolean(
            value, "original_raw_payload_preserved"
        ),
        normalized_raw_payload_preserved=_boolean(
            value, "normalized_raw_payload_preserved"
        ),
        original_event_count=_integer(value, "original_event_count"),
        normalized_candidate_count=_integer(value, "normalized_candidate_count"),
        candidate_review_count=_integer(value, "candidate_review_count"),
        entailed_normalized_candidate_count=_integer(
            value, "entailed_normalized_candidate_count"
        ),
        inventory_coverage=_optional_enum(
            InventoryCoverageDecision, value.get("inventory_coverage")
        ),
        unsupported_additions=_optional_enum(
            PresenceDecision, value.get("unsupported_additions")
        ),
        family_validity=_optional_enum(
            FamilyValidityDecision, value.get("family_validity")
        ),
        cue_alignment=_optional_enum(CueAlignmentDecision, value.get("cue_alignment")),
        scientific_loss_count=_integer(value, "scientific_loss_count"),
        unsupported_addition_count=_integer(value, "unsupported_addition_count"),
        unresolved_axis_count=_integer(value, "unresolved_axis_count"),
        fully_recovered_projection_count=_integer(
            value, "fully_recovered_projection_count"
        ),
        best_projection_matched_event_count=_integer(
            value, "best_projection_matched_event_count"
        ),
        best_projection_expected_event_count=_integer(
            value, "best_projection_expected_event_count"
        ),
        unmatched_normalized_candidate_count=_integer(
            value, "unmatched_normalized_candidate_count"
        ),
        primary_attempt_count=_integer(value, "primary_attempt_count"),
        normalization_attempt_count=_integer(value, "normalization_attempt_count"),
        normalized_review_attempt_count=_integer(
            value, "normalized_review_attempt_count"
        ),
        invalid_agent_output_count=_integer(value, "invalid_agent_output_count"),
        unidentified_provider_attempt_count=_integer(
            value, "unidentified_provider_attempt_count"
        ),
        distinct_provider_response_id_count=_integer(
            value, "distinct_provider_response_id_count"
        ),
        verified_provider_receipt_count=_integer(
            value, "verified_provider_receipt_count"
        ),
        provider_receipt_gate_passed=_boolean(value, "provider_receipt_gate_passed"),
        model_transport_identity_field_count=_integer(
            value, "model_transport_identity_field_count"
        ),
        audit_identity_mismatch_count=_integer(value, "audit_identity_mismatch_count"),
        attempt_model_id_mismatch_count=_integer(
            value, "attempt_model_id_mismatch_count"
        ),
    )


def _eligibility(value: object) -> SourceUnitEligibilityCategory | None:
    return _optional_enum(SourceUnitEligibilityCategory, value)


def _optional_enum(enum_type: type[EnumT], value: object) -> EnumT | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("V11 enum gate input must be text or null")
    return enum_type(value)


def _dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"V11 {key} must be an object")
    return item


def _string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"V11 {key} must be text")
    return item


def _integer(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TypeError(f"V11 {key} must be an integer")
    return item


def _boolean(value: dict[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise TypeError(f"V11 {key} must be boolean")
    return item


__all__ = [
    "V11_ARCHIVE_SHA256",
    "V11_EXPERT_GRAPH_SHA256",
    "V11_PROJECTION_SET_SHA256",
    "require_replayed_v11_qualification",
]
