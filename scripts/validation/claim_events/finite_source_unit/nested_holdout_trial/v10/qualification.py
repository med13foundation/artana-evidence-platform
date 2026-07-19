"""Deterministic replay contract for the V10 scientific gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Final

from artana_evidence_api.document_extraction_support.claim_frames import (
    link_controlled_events,
    unlinked_controlled_target_ids,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v9.qualification import (
    QualificationReplayContract,
    _require_canonical_provider_prompts,
    require_replayed_nested_qualification,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    V10_PROMPT_POLICY,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.selection import (
    tenth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_verification,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)
from scripts.validation.claim_events.finite_source_unit.source_validation.replay import (
    replay_source_binding,
)

TENTH_ARCHIVE_SHA256: Final = (
    "f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f"
)
TENTH_EXPERT_GRAPH_SHA256: Final = (
    "ddd564c4fc7a431358df7f193c4b0284ff5dcebc87a4fd6ce6f61d6b29f28cc5"
)
TENTH_PROJECTION_SET_SHA256: Final = (
    "4f6add86982fe4eabb9df893ee71af9b8cce60aa1b280d18edff9598004821cd"
)
TENTH_SOURCE_IDENTITY: Final[tuple[tuple[str, object], ...]] = (
    ("case_id", "bionlp-ge-2011-holdout:PMC-2222968-04-Results-03"),
    (
        "unit_id",
        "source-unit-463bf8e1b37963d7547eb57c6d51545a466050b2c6c9faa9abc76ff8e2330914",
    ),
    ("unit_index", 17),
    ("source_start", 2622),
    ("source_end", 2723),
    (
        "source_sha256",
        "d452cea84a786851d0d5686c5acab618745b4b8ccaf09cc6fa638a48b370a17a",
    ),
    (
        "input_sha256",
        "cc50c7039a85ec0c7512d0f8f9571331f4001a61e88284a040ec701ec619a121",
    ),
)
TENTH_PROMPT_DIGESTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "extraction_prompt_sha256",
        "13f5cb79aaa72d97b11628ed48847a562ca553a010131b47021d87ce8ccac4e7",
    ),
    (
        "verification_prompt_probe_sha256",
        "bbd7aeb9e7365e2744ca843ca4425f4b57d79698b3362f7c8ce146c3ccdc7c0d",
    ),
)
TENTH_AUTHORITATIVE_ARTICLE_URL: Final = (
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC2222968/"
)
TENTH_FRESHNESS_IDENTITY: Final[dict[str, object]] = {
    "selection_seed": (
        "59107ff0d23bf9543b23df2add9885d0bab4c7dd0c38ffbd18e030734cc2c897"
    ),
    "selection_rule": (
        "lowest_sha256_remaining_negated_graph_seeded_by_finalized_v9_report"
    ),
    "selection_rank": (
        "a7b2a256a3eb75f1efcea5bc01e581ca200c5d951043c6193645c4bebbac952d"
    ),
    "excluded_document_ids": [
        "PMC-1134658-05-Results-04",
        "PMC-1920263-15-DISCUSSION",
        "PMC-2222968-00-TIAB",
        "PMC-2222968-08-Discussion",
        "PMC-2806624-04-RESULTS-03",
        "PMC-2806624-07-DISCUSSION",
        "PMID-10455128",
        "PMID-8622948",
        "PMID-8690900",
        "PMID-9233802",
    ],
    "development_document_count": 40,
    "non_development_document_count": 219,
    "eligible_unit_count": 3,
    "incompatible_document_ids": [
        "PMC-1134658-08-Discussion",
        "PMC-1920263-11-RESULTS-03",
        "PMID-7747440",
    ],
    "convenience_sample": True,
}


def require_replayed_tenth_qualification(report: dict[str, object]) -> None:
    """Rebuild V10 from receipt-bound outputs and its frozen scientific gold."""

    _require_tenth_frozen_lineage(report)
    require_replayed_nested_qualification(report, contract=_tenth_replay_contract())


def require_replayed_tenth_terminal_failure(report: dict[str, object]) -> None:
    """Reproduce the receipt-bound verifier rejection for a failed V10 run."""

    _require_tenth_frozen_lineage(report)
    unit = _required_dict(report, "unit")
    frozen_unit = FrozenSourceUnit(
        unit_id=_required_string(unit, "unit_id"),
        index=_required_int(unit, "unit_index"),
        source_start=_required_int(unit, "source_start"),
        source_end=_required_int(unit, "source_end"),
        text=_required_string(unit, "text"),
        source_sha256=_required_string(unit, "source_sha256"),
    )
    agent_outputs = _required_dict(report, "agent_outputs")
    attempts = report.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise TypeError("tenth holdout attempts must be a nonempty list")
    replayed = replay_source_binding(
        unit=frozen_unit,
        agent_extraction=_required_dict(agent_outputs, "extraction"),
        attempts=attempts,
    )
    terminal_attempt = attempts[-1]
    if (
        not isinstance(terminal_attempt, dict)
        or terminal_attempt.get("attempt_role") != "weak_review"
        or terminal_attempt.get("validation_outcome") != "semantic_invalid"
        or terminal_attempt.get("error_type") != "StructuredModelSemanticError"
        or agent_outputs.get("error_type") != "StructuredModelSemanticError"
        or agent_outputs.get("verification") is not None
    ):
        raise RuntimeError("tenth holdout terminal failure category changed")
    raw_verification = _required_dict(terminal_attempt, "raw_model_payload")
    verification = SourceUnitVerificationOutput.model_validate(raw_verification)
    try:
        bind_source_unit_verification(
            verification,
            unit=frozen_unit,
            candidates=replayed.bound.accepted,
        )
    except StructuredModelSemanticError as exc:
        if "complete temporal phrase" not in str(exc):
            raise RuntimeError(
                "tenth holdout terminal semantic failure changed"
            ) from exc
    else:
        raise RuntimeError("tenth holdout terminal semantic failure no longer replays")
    _require_complete_terminal_report_replay(
        report=report,
        unit=frozen_unit,
        replayed=replayed,
        attempts=attempts,
        agent_outputs=agent_outputs,
    )


def _require_complete_terminal_report_replay(
    *,
    report: dict[str, object],
    unit: FrozenSourceUnit,
    replayed: object,
    attempts: list[object],
    agent_outputs: dict[str, object],
) -> None:
    from scripts.validation.claim_events.finite_source_unit.source_validation.replay import (
        ReplayedSourceBinding,
    )

    if not isinstance(replayed, ReplayedSourceBinding):
        raise TypeError("tenth holdout extraction replay is invalid")
    bound = replayed.bound
    projection_set = tenth_projection_set()
    link_result = link_controlled_events(bound.accepted)
    orphan_target_ids = unlinked_controlled_target_ids(
        bound.accepted,
        link_result.links,
    )
    projection_match = match_projection_set(
        projection_set=projection_set,
        trusted=(),
        links=link_result.links,
    )
    expected_fields: dict[str, object] = {
        "verified_candidates": [],
        "observed_binding_rejections": [
            rejection.as_json() for rejection in replayed.observed_rejections
        ],
        "unresolved_binding_rejections": [
            rejection.as_json() for rejection in replayed.unresolved_rejections
        ],
        "controlled_event_links": [link.as_json() for link in link_result.links],
        "controlled_event_link_ambiguities": [
            ambiguity.as_json() for ambiguity in link_result.ambiguities
        ],
        "unlinked_controlled_event_references": [
            reference.as_json() for reference in link_result.unlinked_references
        ],
        "unlinked_controlled_target_ids": list(orphan_target_ids),
        "sealed_expert_graph": projection_set.canonical_projection.graph.as_json(),
        "sealed_projection_set": projection_set.as_json(),
        "deterministic_projection_match": asdict(projection_match),
        "conclusion_scope": _terminal_conclusion_scope(),
    }
    for key, expected in expected_fields.items():
        _require_equal(report, key, expected)
    receipts = _required_dict(report, "provider_receipts")
    _require_canonical_provider_prompts(
        unit=unit,
        candidates=bound.accepted,
        replayed_binding=replayed,
        attempts=attempts,
        receipts=receipts,
        contract=_tenth_replay_contract(),
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
        expected_eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
        agent_execution_complete=False,
        extraction_category=replayed.extraction.eligibility_category,
        verification_category=None,
        extraction_decision=replayed.extraction.decision,
        verification_coverage=None,
        extracted_candidate_count=len(bound.accepted),
        verification_decision_count=0,
        entailed_candidate_count=0,
        trusted_candidate_count=0,
        unmatched_trusted_candidate_count=0,
        review_only_candidate_count=0,
        rejected_candidate_count=0,
        acceptable_projection_count=len(projection_set.projections),
        fully_recovered_projection_count=0,
        minimum_acceptable_projection_link_count=min(
            len(projection.graph.links) for projection in projection_set.projections
        ),
        observed_binding_rejection_count=len(replayed.observed_rejections),
        binding_rejection_count=len(replayed.unresolved_rejections),
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
            not isinstance(item, dict) or item.get("validation_outcome") != "accepted"
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
            or item.get("semantic_unit_id") != unit.unit_id
            or item.get("source_sha256") != unit.source_sha256
            or item.get("input_sha256") != unit.input_sha256
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
    _require_equal(
        report,
        "gate",
        {
            "passed": False,
            "decision": "STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION",
            "requirements": requirements,
        },
    )


def _tenth_replay_contract() -> QualificationReplayContract:
    return QualificationReplayContract(
        ordinal="tenth",
        unit_identity=dict(TENTH_SOURCE_IDENTITY),
        expected_eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
        projection_set=tenth_projection_set(),
        prompt_policy=V10_PROMPT_POLICY,
    )


def _terminal_conclusion_scope() -> dict[str, object]:
    return {
        "single_fresh_unit_convenience_sample": True,
        "sealed_expert_graph_was_hidden_from_agents": True,
        "sealed_projection_set_was_hidden_from_agents": True,
        "additional_source_valid_claims_are_allowed": True,
        "unmatched_source_valid_claims_must_remain_review_only": True,
        "all_additional_claims_must_be_entailed": True,
        "entailed_unresolved_claims_may_remain_review_only": True,
        "rejected_additional_claims_are_allowed": False,
        "benchmark_credit_awarded": False,
        "scientific_readiness_proven": False,
        "persistence_authorized": False,
        "execution_path": "agent_only_source_unit",
        "deterministic_extraction_fallback_available": False,
    }


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
    if _sha256_json(report.get(key)) != _sha256_json(expected):
        raise RuntimeError(f"tenth holdout {key} differs from deterministic replay")


def _require_tenth_frozen_lineage(report: dict[str, object]) -> None:
    projection_set = tenth_projection_set()
    if (
        _sha256_json(projection_set.canonical_projection.graph.as_json())
        != TENTH_EXPERT_GRAPH_SHA256
        or _sha256_json(projection_set.as_json()) != TENTH_PROJECTION_SET_SHA256
    ):
        raise RuntimeError("tenth holdout scientific contract identity changed")
    source_corpus = _required_dict(report, "source_corpus")
    if (
        source_corpus.get("archive_sha256") != TENTH_ARCHIVE_SHA256
        or source_corpus.get("expert_graph_sha256") != TENTH_EXPERT_GRAPH_SHA256
        or source_corpus.get("projection_set_sha256") != TENTH_PROJECTION_SET_SHA256
    ):
        raise RuntimeError("tenth holdout source corpus identity changed")
    unit = _required_dict(report, "unit")
    if (
        any(unit.get(key) != expected for key, expected in TENTH_SOURCE_IDENTITY)
        or unit.get("authoritative_article_url") != TENTH_AUTHORITATIVE_ARTICLE_URL
    ):
        raise RuntimeError("tenth holdout source identity changed")
    repeat_index = _required_int(report, "repeat_index")
    expected_freshness = {
        **TENTH_FRESHNESS_IDENTITY,
        "fresh_at_repeat_1_execution": repeat_index == 1,
    }
    if (
        report.get("expected_eligibility_category") != "NULL_RESULT"
        or report.get("pre_registered_repeat_indices") != [1, 2, 3]
        or report.get("task_id") != "fresh_nested_event_identity_holdout_v10"
        or _sha256_json(report.get("freshness")) != _sha256_json(expected_freshness)
    ):
        raise RuntimeError("tenth holdout scientific provenance changed")
    frozen_unit = FrozenSourceUnit(
        unit_id=_required_string(unit, "unit_id"),
        index=_required_int(unit, "unit_index"),
        source_start=_required_int(unit, "source_start"),
        source_end=_required_int(unit, "source_end"),
        text=_required_string(unit, "text"),
        source_sha256=_required_string(unit, "source_sha256"),
    )
    if frozen_unit.input_sha256 != dict(TENTH_SOURCE_IDENTITY)["input_sha256"]:
        raise RuntimeError("tenth holdout source text identity changed")
    actual_prompt_digests = {
        "extraction_prompt_sha256": _sha256_text(
            V10_PROMPT_POLICY.extraction_prompt(frozen_unit),
        ),
        "verification_prompt_probe_sha256": _sha256_text(
            V10_PROMPT_POLICY.verification_prompt(unit=frozen_unit, candidates=()),
        ),
    }
    if actual_prompt_digests != dict(TENTH_PROMPT_DIGESTS):
        raise RuntimeError("tenth holdout prompt policy identity changed")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def _required_dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"tenth holdout {key} must be an object")
    return item


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"tenth holdout {key} must be text")
    return item


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TypeError(f"tenth holdout {key} must be an integer")
    return item


__all__ = [
    "TENTH_ARCHIVE_SHA256",
    "TENTH_AUTHORITATIVE_ARTICLE_URL",
    "TENTH_EXPERT_GRAPH_SHA256",
    "TENTH_FRESHNESS_IDENTITY",
    "TENTH_PROMPT_DIGESTS",
    "TENTH_PROJECTION_SET_SHA256",
    "TENTH_SOURCE_IDENTITY",
    "require_replayed_tenth_qualification",
    "require_replayed_tenth_terminal_failure",
]
