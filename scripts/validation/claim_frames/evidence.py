"""Fail-closed execution evidence for TG-03 benchmark artifacts.

Offline JSON reports carry structural evidence but cannot authenticate their
own execution claims. Provider response IDs, canonical output hashes, kernel
events, replay flags, and repository evidence are therefore required here;
the three-run gate separately verifies each provider receipt live.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    CLAIM_FRAME_PIPELINE_PROMPT_VERSION,
    canonical_openai_response_id,
)

from scripts.validation.claim_frames.evidence_contract import (
    AGENT_NUMERIC_ASSESSMENT_RES as _AGENT_NUMERIC_ASSESSMENT_RES,
)
from scripts.validation.claim_frames.evidence_contract import (
    ATTEMPT_OUTCOMES,
    ATTEMPT_ROLES,
    DIAGNOSTIC_STATUSES,
    FALLBACK_STATUSES,
    PASS_ROLES,
    ROUTING_STATUSES,
)
from scripts.validation.claim_frames.evidence_contract import (
    COMMIT_RE as _COMMIT_RE,
)
from scripts.validation.claim_frames.evidence_contract import (
    FALLBACK_MARKER_KEYS as _FALLBACK_MARKER_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    FALLBACK_PROVENANCE_KEYS as _FALLBACK_PROVENANCE_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    FALLBACK_PROVENANCE_RE as _FALLBACK_PROVENANCE_RE,
)
from scripts.validation.claim_frames.evidence_contract import (
    INVENTORY_REQUIRED_KEYS as _INVENTORY_REQUIRED_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    INVENTORY_SOURCE_FIELD_KEYS as _INVENTORY_SOURCE_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    MIN_MULTI_FRAME_RELATIONS as _MIN_MULTI_FRAME_RELATIONS,
)
from scripts.validation.claim_frames.evidence_contract import (
    MIN_TYPED_ARGUMENTS as _MIN_TYPED_ARGUMENTS,
)
from scripts.validation.claim_frames.evidence_contract import (
    NUMERIC_LEXEM_RE as _NUMERIC_LEXEM_RE,
)
from scripts.validation.claim_frames.evidence_contract import (
    QUALIFIER_FIELD_KEYS as _QUALIFIER_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    QUALIFIER_SOURCE_FIELD_KEYS as _QUALIFIER_SOURCE_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    RELATION_REQUIRED_KEYS as _RELATION_REQUIRED_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    ROLE_QUALIFIER_FIELDS as _ROLE_QUALIFIER_FIELDS,
)
from scripts.validation.claim_frames.evidence_contract import (
    SHA256_RE as _SHA256_RE,
)
from scripts.validation.claim_frames.evidence_contract import (
    SOURCE_CITATION_FIELD_KEYS as _SOURCE_CITATION_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    SOURCE_EVIDENCE_CONTAINER_KEYS as _SOURCE_EVIDENCE_CONTAINER_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    SOURCE_EVIDENCE_FIELD_KEYS as _SOURCE_EVIDENCE_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    SOURCE_MEASUREMENT_CONTAINER_KEYS as _SOURCE_MEASUREMENT_CONTAINER_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    SOURCE_MEASUREMENT_FIELD_KEYS as _SOURCE_MEASUREMENT_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    SOURCE_MEASUREMENT_NUMERIC_FIELD_KEYS as _SOURCE_MEASUREMENT_NUMERIC_FIELD_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    TYPED_ARGUMENT_REQUIRED_KEYS as _TYPED_ARGUMENT_REQUIRED_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    TYPED_ARGUMENT_ROLES as _TYPED_ARGUMENT_ROLES,
)
from scripts.validation.claim_frames.evidence_contract import (
    TYPED_INVENTORY_REQUIRED_KEYS as _TYPED_INVENTORY_REQUIRED_KEYS,
)
from scripts.validation.claim_frames.evidence_contract import (
    AgentPayloadContext as _AgentPayloadContext,
)
from scripts.validation.claim_frames.provider_receipts import (
    REPORT_MODEL_ID,
    canonical_provider_model_id,
)

JsonObject = dict[str, object]

REQUIRED_MODEL_ID: Final = REPORT_MODEL_ID
REQUIRED_PROMPT_VERSION: Final = CLAIM_FRAME_PIPELINE_PROMPT_VERSION
OFFLINE_JSON_AUTHENTICATION: Final = "not_cryptographically_authenticated"

def collect_repository_evidence(repo_root: Path) -> JsonObject:
    """Capture the clean tracked-tree evidence required for live TG-03 runs."""

    commit = _git_text(repo_root, "rev-parse", "HEAD")
    tracked_tree_oid = _git_text(repo_root, "rev-parse", "HEAD^{tree}")
    status = _git_text(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    tracked_index = _git_text(repo_root, "ls-files", "--stage")
    return {
        "commit": commit,
        "clean": status == "",
        "tracked_tree_oid": tracked_tree_oid,
        "tracked_tree_sha256": hashlib.sha256(
            tracked_index.encode("utf-8"),
        ).hexdigest(),
    }


def validate_repository_evidence(value: object) -> JsonObject:
    """Validate repository evidence without claiming it authenticates JSON."""

    evidence = _object(value, "repository_evidence")
    commit = _required_string(evidence, "commit")
    if _COMMIT_RE.fullmatch(commit) is None:
        raise ValueError("repository commit must be a 40-character SHA-1")
    if evidence.get("clean") is not True:
        raise ValueError("TG-03 reports require a clean tracked worktree")
    tree_oid = _required_string(evidence, "tracked_tree_oid")
    if _COMMIT_RE.fullmatch(tree_oid) is None:
        raise ValueError("tracked_tree_oid must be a 40-character SHA-1")
    tree_sha256 = _required_string(evidence, "tracked_tree_sha256")
    if _SHA256_RE.fullmatch(tree_sha256) is None:
        raise ValueError("tracked_tree_sha256 must be a SHA-256 digest")
    return {
        "commit": commit,
        "clean": True,
        "tracked_tree_oid": tree_oid,
        "tracked_tree_sha256": tree_sha256,
    }


def validate_diagnostics(value: object) -> JsonObject:
    """Validate the complete diagnostic envelope used for derived state."""

    diagnostics = _object(value, "diagnostics")
    status = _required_string(diagnostics, "llm_candidate_status")
    if status not in DIAGNOSTIC_STATUSES:
        raise ValueError(f"unknown TG-03 candidate status: {status}")
    validated: JsonObject = {"llm_candidate_status": status}
    for key in (
        "llm_candidate_count",
        "fallback_candidate_count",
        "pruned_generic_relation_count",
        "quality_filtered_candidate_count",
        "llm_extraction_chunk_count",
        "llm_extraction_text_char_count",
        "candidate_overflow_count",
    ):
        validated[key] = _nonnegative_int(diagnostics, key)
    routing_status = _required_string(
        diagnostics,
        "claim_extraction_routing_status",
    )
    if routing_status not in ROUTING_STATUSES:
        raise ValueError(f"unknown TG-03 claim routing status: {routing_status}")
    overflow_count = cast("int", validated["candidate_overflow_count"])
    if routing_status == "candidate_overflow":
        if overflow_count == 0:
            raise ValueError("candidate_overflow routing requires overflow evidence")
        if status != "completed":
            raise ValueError("candidate_overflow routing requires completed extraction")
    elif overflow_count != 0:
        raise ValueError(
            "candidate_overflow_count requires candidate_overflow routing",
        )
    if (status == "semantic_incomplete") != (routing_status == "semantic_incomplete"):
        raise ValueError(
            "semantic_incomplete candidate and routing statuses must agree",
        )
    validated["claim_extraction_routing_status"] = routing_status
    return validated


def validate_model_attempt_records(
    raw_output: object,
    *,
    expected_model_id: str,
) -> tuple[JsonObject, ...]:
    """Validate every serialized model-boundary attempt and its evidence."""

    output = _object(raw_output, "raw_agent_output")
    raw_attempts = output.get("attempts")
    if not isinstance(raw_attempts, list) or not raw_attempts:
        raise ValueError(
            "model-attempt evidence must contain a non-empty attempts list"
        )
    accepted_pass_payloads = output.get("accepted_pass_payloads")
    if not isinstance(accepted_pass_payloads, list):
        raise TypeError("model-attempt evidence requires accepted_pass_payloads")

    validated: list[JsonObject] = []
    executed: list[JsonObject] = []
    response_ids: set[str] = set()
    kernel_events: set[tuple[str, int]] = set()
    for raw_attempt in raw_attempts:
        evidence = _validated_attempt_evidence(
            raw_attempt,
            expected_model_id=expected_model_id,
        )
        if evidence.response_id is not None:
            if evidence.response_id in response_ids:
                raise ValueError("provider response IDs must be unique")
            response_ids.add(evidence.response_id)
        if evidence.kernel_event is not None:
            if evidence.kernel_event in kernel_events:
                raise ValueError("kernel run/event identities must be unique")
            kernel_events.add(evidence.kernel_event)
        if evidence.executed:
            executed.append(evidence.attempt)
        validated.append(evidence.attempt)

    if not executed:
        raise ValueError("model-attempt evidence contains no executed model attempt")
    for payload in accepted_pass_payloads:
        if not isinstance(payload, dict):
            raise TypeError("accepted_pass_payloads entries must be objects")
        validate_agent_payload(payload)
    _validate_accepted_payload_inventory(
        attempts=validated,
        accepted_pass_payloads=accepted_pass_payloads,
    )
    return tuple(validated)


@dataclass(frozen=True, slots=True)
class _ValidatedAttemptEvidence:
    attempt: JsonObject
    executed: bool
    response_id: str | None
    kernel_event: tuple[str, int] | None


def _validated_attempt_evidence(
    raw_attempt: object,
    *,
    expected_model_id: str,
) -> _ValidatedAttemptEvidence:
    attempt = _object(raw_attempt, "model-attempt record")
    outcome = _required_string(attempt, "validation_outcome")
    if outcome not in ATTEMPT_OUTCOMES:
        raise ValueError(f"unknown model-attempt validation outcome: {outcome}")
    _validate_attempt_contract(attempt, expected_model_id=expected_model_id)
    raw_payload = _validate_attempt_payload(attempt, outcome=outcome)
    if outcome == "intentionally_skipped":
        _validate_skipped_attempt(attempt, raw_payload=raw_payload)
        return _ValidatedAttemptEvidence(
            attempt=attempt,
            executed=False,
            response_id=None,
            kernel_event=None,
        )
    if outcome == "invocation_failed" and attempt.get("provider_response_id") is None:
        _validate_failed_attempt_without_response(attempt)
        return _ValidatedAttemptEvidence(
            attempt=attempt,
            executed=True,
            response_id=None,
            kernel_event=None,
        )
    _validate_provider_evidence(attempt)
    return _ValidatedAttemptEvidence(
        attempt=attempt,
        executed=True,
        response_id=_required_string(attempt, "provider_response_id"),
        kernel_event=(
            _required_string(attempt, "kernel_run_id"),
            _positive_int(attempt, "kernel_event_seq"),
        ),
    )


def _validate_attempt_contract(
    attempt: Mapping[str, object],
    *,
    expected_model_id: str,
) -> None:
    _validate_attempt_strings(attempt)
    expected_provider_model = canonical_provider_model_id(expected_model_id)
    attempt_provider_model = canonical_provider_model_id(
        _required_string(attempt, "model_id"),
    )
    if attempt_provider_model != expected_provider_model:
        raise ValueError("model-attempt model_id does not match the report model")
    for key in (
        "prompt_sha256",
        "source_sha256",
        "input_sha256",
        "evidence_unit_sha256",
    ):
        _validate_hash(attempt, key)
    _required_string(attempt, "output_schema_identity")
    _validate_payload_hash(attempt)


def _validate_attempt_payload(
    attempt: Mapping[str, object],
    *,
    outcome: str,
) -> JsonObject | None:
    raw_payload = attempt.get("raw_model_payload")
    if raw_payload is not None and not isinstance(raw_payload, dict):
        raise TypeError("raw_model_payload must be an object or null")
    if outcome == "accepted" and not isinstance(raw_payload, dict):
        raise ValueError("accepted model attempts require raw_model_payload")
    validate_agent_payload(raw_payload)
    return cast("JsonObject | None", raw_payload)


def _validate_skipped_attempt(
    attempt: Mapping[str, object],
    *,
    raw_payload: JsonObject | None,
) -> None:
    if raw_payload is not None or attempt.get("payload_sha256") is not None:
        raise ValueError("intentionally skipped attempts cannot contain payloads")
    for key in (
        "provider_execution_response_id",
        "provider_response_id",
        "provider_output_sha256",
        "kernel_run_id",
        "kernel_event_seq",
    ):
        if attempt.get(key) is not None:
            raise ValueError(f"intentionally skipped attempts cannot contain {key}")
    if attempt.get("replayed") not in {None, False}:
        raise ValueError("intentionally skipped attempts cannot be replayed")


def _validate_failed_attempt_without_response(
    attempt: Mapping[str, object],
) -> None:
    for key in (
        "provider_execution_response_id",
        "provider_response_id",
        "provider_output_sha256",
        "kernel_run_id",
        "kernel_event_seq",
    ):
        if attempt.get(key) is not None:
            raise ValueError(
                f"provider-less invocation failure cannot contain {key}",
            )
    if attempt.get("replayed") not in {None, False}:
        raise ValueError("provider-less invocation failure cannot be replayed")


def derive_execution_state(
    raw_output: object,
    diagnostics: object,
    *,
    expected_model_id: str,
) -> JsonObject:
    """Derive completion and fallback only from validated evidence."""

    attempts = validate_model_attempt_records(
        raw_output,
        expected_model_id=expected_model_id,
    )
    validated_diagnostics = validate_diagnostics(diagnostics)
    status = cast("str", validated_diagnostics["llm_candidate_status"])
    routing_status = cast(
        "str",
        validated_diagnostics["claim_extraction_routing_status"],
    )
    overflow_count = cast("int", validated_diagnostics["candidate_overflow_count"])
    accepted = any(
        attempt.get("validation_outcome") == "accepted" for attempt in attempts
    )
    invocation_failure_count = sum(
        attempt.get("validation_outcome") == "invocation_failed" for attempt in attempts
    )
    if status in {"completed", "llm_empty"} and not accepted:
        raise ValueError(f"{status} diagnostics require an accepted model attempt")
    if _contains_truthy_fallback_marker(raw_output):
        raise ValueError("fallback markers must be represented by diagnostics")
    agent_authored_numeric_value_count = sum(
        validate_agent_payload(attempt.get("raw_model_payload")) for attempt in attempts
    )
    return {
        "agent_invocation_completed": status in {"completed", "llm_empty"} and accepted,
        "strict_usable_extraction_completed": (
            status == "completed"
            and accepted
            and routing_status == "complete"
            and overflow_count == 0
        ),
        "fallback_output_count": int(
            cast("int", validated_diagnostics["fallback_candidate_count"]) > 0
            or status in FALLBACK_STATUSES
        ),
        "agent_authored_numeric_value_count": agent_authored_numeric_value_count,
        "model_invocation_failure_count": invocation_failure_count,
    }


def derive_composed_pipeline_state(
    raw_output: object,
    *,
    expected_model_id: str,
) -> JsonObject:
    """Derive whether one case executed the inventory-to-framing topology."""

    attempts = validate_model_attempt_records(
        raw_output,
        expected_model_id=expected_model_id,
    )
    accepted_inventory_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
        and attempt.get("pass_role") == "claim_inventory"
    )
    accepted_completeness_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
        and attempt.get("pass_role") == "claim_inventory_completeness"
    )
    accepted_recovery_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
        and attempt.get("pass_role") == "claim_inventory_recovery"
    )
    accepted_framing_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
        and attempt.get("pass_role") == "claim_framing"
    )
    legacy_attempt_count = sum(
        attempt.get("validation_outcome") != "intentionally_skipped"
        and attempt.get("pass_role") in {"primary", "weak_review"}
        for attempt in attempts
    )

    inventory_items = _unique_inventory_items(
        (*accepted_inventory_attempts, *accepted_recovery_attempts),
    )
    completeness_decisions = tuple(
        _inventory_completeness_decision(attempt)
        for attempt in accepted_completeness_attempts
    )
    recovery_required = "INCOMPLETE" in completeness_decisions
    completeness_closed = bool(completeness_decisions) and (
        completeness_decisions[-1] == "COMPLETE"
    )
    framing_units_bound = _framing_units_match_inventory(
        inventory_items=inventory_items,
        framing_attempts=accepted_framing_attempts,
    )
    inventory_count = len(inventory_items)
    framing_count = len(accepted_framing_attempts)
    topology_completed = (
        bool(accepted_inventory_attempts)
        and completeness_closed
        and (not recovery_required or bool(accepted_recovery_attempts))
        and legacy_attempt_count == 0
        and framing_count == inventory_count
        and framing_units_bound
    )
    return {
        "composed_pipeline_completed": topology_completed,
        "accepted_claim_inventory_attempt_count": len(
            accepted_inventory_attempts,
        ),
        "accepted_claim_inventory_completeness_attempt_count": len(
            accepted_completeness_attempts,
        ),
        "accepted_claim_inventory_recovery_attempt_count": len(
            accepted_recovery_attempts,
        ),
        "unique_inventoried_item_count": inventory_count,
        "terminal_claim_framing_attempt_count": framing_count,
        "legacy_extraction_attempt_count": legacy_attempt_count,
    }


@dataclass(frozen=True, slots=True)
class _InventoriedItemEvidence:
    identity: str
    item: JsonObject


def _inventory_completeness_decision(
    attempt: Mapping[str, object],
) -> str:
    payload = _object(
        attempt.get("raw_model_payload"),
        "claim inventory completeness payload",
    )
    decision = _required_string(payload, "decision")
    if decision not in {"COMPLETE", "INCOMPLETE"}:
        raise ValueError(
            "claim inventory completeness decision must be COMPLETE or INCOMPLETE",
        )
    return decision


def _unique_inventory_items(
    attempts: Sequence[Mapping[str, object]],
) -> tuple[_InventoriedItemEvidence, ...]:
    items_by_identity: dict[str, _InventoriedItemEvidence] = {}
    for attempt in attempts:
        payload = _object(attempt.get("raw_model_payload"), "claim inventory payload")
        raw_claims = payload.get("claims")
        if not isinstance(raw_claims, list):
            raise TypeError("accepted claim_inventory payload requires a claims list")
        chunk_sha256 = _required_string(attempt, "input_sha256")
        for raw_claim in raw_claims:
            item = _object(raw_claim, "inventoried claim item")
            identity = _sha256_json(
                {
                    "chunk_sha256": chunk_sha256,
                    "item": item,
                },
            )
            items_by_identity.setdefault(
                identity,
                _InventoriedItemEvidence(identity=identity, item=item),
            )
    return tuple(items_by_identity.values())


def _framing_units_match_inventory(
    *,
    inventory_items: Sequence[_InventoriedItemEvidence],
    framing_attempts: Sequence[Mapping[str, object]],
) -> bool:
    matched_inventory_ids: set[str] = set()
    semantic_unit_ids: set[str] = set()
    for attempt in framing_attempts:
        semantic_unit_id = _required_string(attempt, "semantic_unit_id")
        if semantic_unit_id in semantic_unit_ids:
            return False
        semantic_unit_ids.add(semantic_unit_id)
        framing_input_sha256 = _required_string(attempt, "input_sha256")
        matching_inventory = tuple(
            inventory_item
            for inventory_item in inventory_items
            if _claim_framing_input_sha256(
                semantic_unit_id=semantic_unit_id,
                item=inventory_item.item,
            )
            == framing_input_sha256
        )
        if len(matching_inventory) != 1:
            return False
        matched_inventory = matching_inventory[0]
        if matched_inventory.identity in matched_inventory_ids:
            return False
        matched_inventory_ids.add(matched_inventory.identity)

        payload = _object(attempt.get("raw_model_payload"), "claim framing payload")
        decision = _required_string(payload, "decision")
        relations = _framing_payload_relations(payload, decision=decision)
        if decision == "ABSTAIN":
            continue
        if not _framed_relations_match_inventory(
            item=matched_inventory.item,
            relations=relations,
        ):
            return False
    return len(matched_inventory_ids) == len(inventory_items)


def _claim_framing_input_sha256(
    *,
    semantic_unit_id: str,
    item: Mapping[str, object],
) -> str:
    return _sha256_json(
        {
            "inventory_id": semantic_unit_id,
            "item": item,
        },
    )


def _inventory_semantic_signature(item: Mapping[str, object]) -> str:
    endpoint_a = _required_string(item, "endpoint_a_span")
    endpoint_b = _required_string(item, "endpoint_b_span")
    role_order = _required_string(item, "endpoint_role_order")
    if role_order == "A_SUBJECT_B_OBJECT":
        subject, object_ = endpoint_a, endpoint_b
    elif role_order == "B_SUBJECT_A_OBJECT":
        subject, object_ = endpoint_b, endpoint_a
    elif role_order == "UNRESOLVED":
        subject, object_ = None, None
    else:
        raise ValueError("inventory endpoint_role_order is not registered")
    return _sha256_json(
        {
            "exact_span": _required_string(item, "exact_span"),
            "subject": subject,
            "object": object_,
            "polarity": _required_string(item, "polarity"),
            "epistemic_status": _required_string(item, "epistemic_status"),
        },
    )


def _framing_payload_relations(
    payload: Mapping[str, object],
    *,
    decision: str,
) -> tuple[JsonObject, ...]:
    if decision == "FRAMED":
        return (_object(payload.get("relation"), "framed relation"),)
    if decision == "ABSTAIN" and "relations" not in payload:
        if payload.get("relation") is not None:
            raise ValueError("legacy ABSTAIN cannot include a framed relation")
        return ()
    raw_relations = payload.get("relations")
    if not isinstance(raw_relations, list):
        raise TypeError("typed claim_framing payload requires a relations list")
    relations = tuple(_object(item, "framed relation") for item in raw_relations)
    expected_cardinality = {
        "SINGLE_FRAME": lambda count: count == 1,
        "MULTIPLE_VALID_FRAMES": lambda count: count >= _MIN_MULTI_FRAME_RELATIONS,
        "AMBIGUOUS": lambda count: count >= _MIN_MULTI_FRAME_RELATIONS,
        "ABSTAIN": lambda count: count == 0,
    }
    cardinality_check = expected_cardinality.get(decision)
    if cardinality_check is None:
        raise ValueError(
            "claim_framing decision is not a registered categorical outcome",
        )
    if not cardinality_check(len(relations)):
        raise ValueError(f"claim_framing {decision} relation cardinality is invalid")
    return relations


def _framed_relations_match_inventory(
    *,
    item: Mapping[str, object],
    relations: Sequence[Mapping[str, object]],
) -> bool:
    if "arguments" not in item:
        expected = _inventory_semantic_signature(item)
        return all(
            _framed_relation_semantic_signature(relation) == expected
            for relation in relations
        )
    return all(
        _typed_framed_relation_matches_inventory(item=item, relation=relation)
        for relation in relations
    )


def _typed_framed_relation_matches_inventory(
    *,
    item: Mapping[str, object],
    relation: Mapping[str, object],
) -> bool:
    raw_arguments = item.get("arguments")
    if (
        not isinstance(raw_arguments, list)
        or len(raw_arguments) < _MIN_TYPED_ARGUMENTS
    ):
        raise TypeError("typed inventory item requires at least two arguments")
    arguments = tuple(
        _object(argument, "typed inventory argument") for argument in raw_arguments
    )
    argument_spans = {_required_string(argument, "exact_span") for argument in arguments}
    subject = _required_string(relation, "subject")
    object_ = _required_string(relation, "object")
    if subject not in argument_spans or object_ not in argument_spans:
        return False
    if _required_string(relation, "sentence") != _required_string(item, "exact_span"):
        return False
    if _required_string(relation, "polarity") != _required_string(item, "polarity"):
        return False
    if _required_string(relation, "epistemic_status") != _required_string(
        item,
        "epistemic_status",
    ):
        return False
    endpoint_spans = {subject, object_}
    for argument in arguments:
        span = _required_string(argument, "exact_span")
        if span in endpoint_spans:
            continue
        role = _required_string(argument, "role")
        if role not in _TYPED_ARGUMENT_ROLES:
            raise ValueError(f"typed inventory role is not registered: {role}")
        qualifier_field = _ROLE_QUALIFIER_FIELDS.get(role)
        if qualifier_field is None:
            continue
        qualifier = _object(relation.get(qualifier_field), qualifier_field)
        if qualifier.get("state") != "PRESENT" or qualifier.get("exact_span") != span:
            return False
    return True


def _framed_relation_semantic_signature(relation: Mapping[str, object]) -> str:
    return _sha256_json(
        {
            "exact_span": _required_string(relation, "sentence"),
            "subject": _required_string(relation, "subject"),
            "object": _required_string(relation, "object"),
            "polarity": _required_string(relation, "polarity"),
            "epistemic_status": _required_string(relation, "epistemic_status"),
        },
    )


def _validate_provider_evidence(attempt: Mapping[str, object]) -> None:
    """Require provider/kernel provenance on every real model attempt."""

    execution_response_id = _required_string(
        attempt,
        "provider_execution_response_id",
    )
    provider_response_id = _required_string(attempt, "provider_response_id")
    if canonical_openai_response_id(execution_response_id) != provider_response_id:
        raise ValueError(
            "provider_response_id must be the canonical OpenAI execution response ID",
        )
    _validate_hash(attempt, "provider_output_sha256")
    _required_string(attempt, "kernel_run_id")
    _positive_int(attempt, "kernel_event_seq")
    if attempt.get("replayed") is not False:
        raise ValueError("model attempts must explicitly record replayed=false")


def _validate_attempt_strings(attempt: Mapping[str, object]) -> None:
    for key in (
        "invocation_id",
        "attempt_role",
        "pass_role",
        "model_id",
        "step_key",
    ):
        _required_string(attempt, key)
    if attempt.get("attempt_role") not in ATTEMPT_ROLES:
        raise ValueError("model-attempt attempt_role is not a registered role")
    if attempt.get("pass_role") not in PASS_ROLES:
        raise ValueError("model-attempt pass_role is not a registered role")
    semantic_unit_id = attempt.get("semantic_unit_id")
    if attempt.get("pass_role") in {
        "claim_framing",
        "claim_inventory_recovery",
    }:
        _required_string(attempt, "semantic_unit_id")
    elif semantic_unit_id is not None:
        raise ValueError(
            "semantic_unit_id must be null outside claim_framing and "
            "claim_inventory_recovery attempts",
        )
    retry_context = attempt.get("retry_context")
    if retry_context not in {None, "zero_candidate_retry"}:
        raise ValueError("retry_context must be null or zero_candidate_retry")
    error_type = attempt.get("error_type")
    if error_type is not None and not isinstance(error_type, str):
        raise TypeError("error_type must be a string or null")


def _validate_payload_hash(attempt: Mapping[str, object]) -> None:
    payload = attempt.get("raw_model_payload")
    payload_hash = attempt.get("payload_sha256")
    if payload is None:
        if payload_hash is not None:
            raise ValueError("payload_sha256 requires raw_model_payload")
        return
    if not isinstance(payload_hash, str) or _SHA256_RE.fullmatch(payload_hash) is None:
        raise ValueError("payload_sha256 must be a SHA-256 digest")
    if payload_hash != _sha256_json(payload):
        raise ValueError("payload_sha256 does not match raw_model_payload")


def validate_agent_payload(value: object) -> int:
    """Enforce categorical agent output and source-bound numeric exceptions."""

    return _validate_agent_payload(
        value,
        parent_key=None,
        context="agent_text",
    )


def _validate_agent_payload(
    value: object,
    *,
    parent_key: str | None,
    context: _AgentPayloadContext,
) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        raise TypeError("agent-authored numeric value is forbidden")
    if isinstance(value, str):
        source_numeric_allowed = _source_numeric_text_allowed(
            context=context,
            parent_key=parent_key,
        )
        if (
            _NUMERIC_LEXEM_RE.fullmatch(value.strip()) is not None
            and not source_numeric_allowed
        ):
            raise ValueError(
                "numeric lexical value is only allowed in explicit source evidence, "
                f"qualifier, or source_measurement fields: {parent_key}",
            )
        if not _source_assessment_text_allowed(
            context=context,
            parent_key=parent_key,
        ) and _contains_numeric_assessment(value):
            raise ValueError(
                f"agent-authored numeric score language is forbidden at {parent_key}",
            )
        if (
            parent_key in _FALLBACK_PROVENANCE_KEYS
            and _FALLBACK_PROVENANCE_RE.search(value) is not None
        ):
            raise ValueError(f"fallback provenance is forbidden at {parent_key}")
        return 0
    if isinstance(value, dict):
        numeric_count = 0
        for key, item in value.items():
            numeric_count += _validate_agent_payload(
                item,
                parent_key=key,
                context=_child_payload_context(
                    value,
                    parent_context=context,
                    key=key,
                ),
            )
        return numeric_count
    if isinstance(value, list):
        return sum(
            _validate_agent_payload(
                item,
                parent_key=parent_key,
                context=context,
            )
            for item in value
        )
    return 0


def _contains_numeric_assessment(value: str) -> bool:
    return any(
        pattern.search(value) is not None for pattern in _AGENT_NUMERIC_ASSESSMENT_RES
    )


def _source_numeric_text_allowed(
    *,
    context: _AgentPayloadContext,
    parent_key: str | None,
) -> bool:
    if parent_key is None:
        return False
    if context == "source_evidence":
        return parent_key in _SOURCE_EVIDENCE_FIELD_KEYS | _SOURCE_CITATION_FIELD_KEYS
    if context == "qualifier":
        return parent_key in _QUALIFIER_SOURCE_FIELD_KEYS
    if context == "source_measurement":
        return parent_key in (
            _SOURCE_MEASUREMENT_NUMERIC_FIELD_KEYS | _SOURCE_CITATION_FIELD_KEYS
        )
    return False


def _source_assessment_text_allowed(
    *,
    context: _AgentPayloadContext,
    parent_key: str | None,
) -> bool:
    if parent_key is None:
        return False
    if context == "source_evidence":
        return parent_key in _SOURCE_EVIDENCE_FIELD_KEYS
    if context == "qualifier":
        return parent_key in _QUALIFIER_SOURCE_FIELD_KEYS
    return context == "source_measurement" and parent_key == "literal_span"


def _child_payload_context(
    parent: Mapping[str, object],
    *,
    parent_context: _AgentPayloadContext,
    key: str,
) -> _AgentPayloadContext:
    source_object_context = _source_object_child_context(
        parent_context=parent_context,
        key=key,
    )
    if source_object_context is not None:
        return source_object_context
    collection_context = _source_collection_child_context(
        parent,
        parent_context=parent_context,
        key=key,
    )
    if collection_context is not None:
        return collection_context
    return _root_child_payload_context(parent, key=key)


def _source_object_child_context(
    *,
    parent_context: _AgentPayloadContext,
    key: str,
) -> _AgentPayloadContext | None:
    if parent_context == "source_evidence":
        if key in _SOURCE_EVIDENCE_FIELD_KEYS | _SOURCE_CITATION_FIELD_KEYS:
            return "source_evidence"
        return "agent_text"
    if parent_context == "qualifier":
        if key in _QUALIFIER_SOURCE_FIELD_KEYS:
            return "qualifier"
        return "agent_text"
    if parent_context == "source_measurement":
        if key in _SOURCE_MEASUREMENT_FIELD_KEYS:
            return "source_measurement"
        return "agent_text"
    return None


def _source_collection_child_context(
    parent: Mapping[str, object],
    *,
    parent_context: _AgentPayloadContext,
    key: str,
) -> _AgentPayloadContext | None:
    if parent_context == "qualifier_collection":
        if key in _QUALIFIER_FIELD_KEYS:
            return "qualifier"
        return "agent_text"
    if parent_context == "source_measurement_collection":
        if (
            parent.get("origin") == "source_measurement"
            and key in _SOURCE_MEASUREMENT_FIELD_KEYS
        ):
            return "source_measurement"
        return "agent_text"
    return None


def _root_child_payload_context(
    parent: Mapping[str, object],
    *,
    key: str,
) -> _AgentPayloadContext:
    if key in _SOURCE_EVIDENCE_CONTAINER_KEYS:
        return "source_evidence"
    if key == "qualifiers":
        return "qualifier_collection"
    if key in _QUALIFIER_FIELD_KEYS:
        return "qualifier"
    if key in _SOURCE_MEASUREMENT_CONTAINER_KEYS:
        return "source_measurement_collection"
    if key in _SOURCE_CITATION_FIELD_KEYS:
        return "source_evidence"
    if (
        parent.keys() >= _INVENTORY_REQUIRED_KEYS
        and key in _INVENTORY_SOURCE_FIELD_KEYS
    ):
        return "source_evidence"
    if (
        parent.keys() >= _TYPED_INVENTORY_REQUIRED_KEYS
        and key in _INVENTORY_SOURCE_FIELD_KEYS
    ):
        return "source_evidence"
    if parent.keys() >= _TYPED_ARGUMENT_REQUIRED_KEYS and key == "exact_span":
        return "source_evidence"
    if parent.keys() >= _RELATION_REQUIRED_KEYS and key == "sentence":
        return "source_evidence"
    return "agent_text"


def accepted_raw_relations(
    attempts: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    """Return every relation directly present in an accepted model payload."""

    relations: list[JsonObject] = []
    for attempt in attempts:
        if attempt.get("validation_outcome") != "accepted":
            continue
        payload = _object(attempt.get("raw_model_payload"), "accepted raw payload")
        relation = payload.get("relation")
        if payload.get("decision") == "FRAMED" and isinstance(relation, dict):
            relations.append(cast("JsonObject", relation))
        raw_relations = payload.get("relations")
        if isinstance(raw_relations, list):
            relations.extend(
                _object(item, "accepted raw relation") for item in raw_relations
            )
    return tuple(relations)


def _validate_accepted_payload_inventory(
    *,
    attempts: Sequence[Mapping[str, object]],
    accepted_pass_payloads: Sequence[object],
) -> None:
    attempt_payloads = [
        _object(attempt.get("raw_model_payload"), "accepted raw payload")
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
    ]
    listed_payloads = [
        _object(payload, "accepted_pass_payloads entry")
        for payload in accepted_pass_payloads
    ]
    if Counter(map(_sha256_json, attempt_payloads)) != Counter(
        map(_sha256_json, listed_payloads)
    ):
        raise ValueError(
            "accepted_pass_payloads must exactly match accepted model attempts",
        )


def _contains_truthy_fallback_marker(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            (key in _FALLBACK_MARKER_KEYS and item is True)
            or _contains_truthy_fallback_marker(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_truthy_fallback_marker(item) for item in value)
    return False


def _validate_hash(payload: Mapping[str, object], key: str) -> None:
    value = _required_string(payload, key)
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{key} must be a SHA-256 digest")


def _nonnegative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{key} must be a non-negative integer")
    return value


def _positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TypeError(f"{key} must be a positive integer")
    return value


def _git_text(repo_root: Path, *args: str) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git executable is required for repository evidence")
    result = subprocess.run(
        [git_executable, *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


def _object(value: object, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return cast("JsonObject", value)


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


__all__ = [
    "DIAGNOSTIC_STATUSES",
    "FALLBACK_STATUSES",
    "OFFLINE_JSON_AUTHENTICATION",
    "REQUIRED_MODEL_ID",
    "REQUIRED_PROMPT_VERSION",
    "ROUTING_STATUSES",
    "accepted_raw_relations",
    "collect_repository_evidence",
    "derive_composed_pipeline_state",
    "derive_execution_state",
    "validate_agent_payload",
    "validate_diagnostics",
    "validate_model_attempt_records",
    "validate_repository_evidence",
]
