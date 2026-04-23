"""Shared helpers for graph workflow service."""


from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.decision_confidence import (
    DecisionConfidenceAssessment,
    DecisionConfidenceResult,
    decision_confidence_assessment_payload,
)
from artana_evidence_db.relation_claim_models import (
    RelationClaimStatus,
    RelationClaimValidationState,
)
from artana_evidence_db.workflow_models import (
    GraphOperatingMode,
    GraphWorkflow,
    GraphWorkflowAction,
    GraphWorkflowKind,
    GraphWorkflowPolicyOutcome,
    GraphWorkflowStatus,
)
from artana_evidence_db.workflow_persistence_models import (
    GraphWorkflowModel,
)

_AI_GRAPH_MODES: frozenset[str] = frozenset(
    {"human_evidence_ai_graph", "ai_full_graph", "ai_full_evidence", "continuous_learning"},
)
_AI_EVIDENCE_MODES: frozenset[str] = frozenset(
    {"ai_full_evidence", "continuous_learning"},
)
_AUTO_CLAIM_MODES: frozenset[str] = frozenset(
    {"human_evidence_ai_graph", "ai_full_graph", "ai_full_evidence", "continuous_learning"},
)
_SUPPORTED_WORKFLOW_KINDS: tuple[GraphWorkflowKind, ...] = (
    "evidence_approval",
    "batch_review",
    "ai_evidence_decision",
    "conflict_resolution",
    "continuous_learning_review",
    "bootstrap_review",
)
_SUPPORTED_WORKFLOW_ACTIONS: tuple[GraphWorkflowAction, ...] = (
    "apply_plan",
    "approve",
    "reject",
    "request_changes",
    "split",
    "defer_to_human",
    "mark_resolved",
)
_CLAIM_VALIDATION_STATE_MAP: dict[str, RelationClaimValidationState] = {
    "ALLOWED": "ALLOWED",
    "FORBIDDEN": "FORBIDDEN",
    "UNDEFINED": "UNDEFINED",
    "INVALID_COMPONENTS": "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED": "ENDPOINT_UNRESOLVED",
    "SELF_LOOP": "SELF_LOOP",
}
_BATCH_RESOURCE_ACTIONS: dict[str, frozenset[str]] = {
    "concept_proposal": frozenset(
        {"approve", "merge", "reject", "request_changes"},
    ),
    "dictionary_proposal": frozenset({"approve", "reject", "request_changes"}),
    "graph_change_proposal": frozenset({"apply", "reject", "request_changes"}),
    "connector_proposal": frozenset({"approve", "reject", "request_changes"}),
    "claim": frozenset({"resolve", "reject", "needs_mapping"}),
    "workflow": frozenset(
        {"approve", "reject", "request_changes", "defer_to_human"},
    ),
}
_CLAIM_BATCH_STATUS_BY_ACTION: dict[str, RelationClaimStatus] = {
    "resolve": "RESOLVED",
    "reject": "REJECTED",
    "needs_mapping": "NEEDS_MAPPING",
}
_WORKFLOW_BATCH_ACTION_BY_ITEM_ACTION: dict[str, GraphWorkflowAction] = {
    "approve": "approve",
    "reject": "reject",
    "request_changes": "request_changes",
    "defer_to_human": "defer_to_human",
}


@dataclass(frozen=True)
class _WorkflowPlan:
    status: GraphWorkflowStatus
    plan_payload: JSONObject
    generated_resources_payload: JSONObject
    decision_payload: JSONObject
    policy_payload: JSONObject
    explanation_payload: JSONObject


@dataclass(frozen=True)
class _GeneratedResourcesApplication:
    status: GraphWorkflowStatus | None
    generated_updates: JSONObject


class WorkflowActionRejected(ValueError):  # noqa: N818
    """Raised after a rejected workflow action has been recorded in the ledger."""


def _to_json_value(value: object) -> JSONValue:  # noqa: PLR0911
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.astimezone(UTC).isoformat() if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_value(item) for item in value]
    return str(value)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _claim_triage_actor(actor: str) -> str:
    if actor.startswith("manual:"):
        return actor.removeprefix("manual:")
    try:
        return str(_as_uuid(actor))
    except ValueError:
        msg = "Claim triage requires a UUID-backed authenticated actor"
        raise ValueError(msg) from None


def _json_object(value: JSONValue | None) -> JSONObject | None:
    if isinstance(value, dict):
        return dict(value)
    return None


def _json_object_list(value: JSONValue | None) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _json_str(value: JSONValue | None, *, field_name: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    msg = f"{field_name} must be a non-empty string"
    raise ValueError(msg)


def _json_optional_str(value: JSONValue | None) -> str | None:
    if isinstance(value, str):
        return _normalize_optional_text(value)
    return None


def _json_bool(value: JSONValue | None, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _json_float(value: JSONValue | None, *, default: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return default


def _model_payload(model: object) -> JSONObject:
    table = getattr(model, "__table__", None)
    if table is None:
        msg = "SQLAlchemy model is missing __table__ metadata"
        raise TypeError(msg)
    payload: JSONObject = {}
    for column in table.columns:
        payload[column.name] = _to_json_value(getattr(model, column.name))
    return payload


def _workflow_hash_payload(payload: JSONObject) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _workflow_hash(model: GraphWorkflowModel) -> str:
    payload = _model_payload(model)
    payload.pop("workflow_hash", None)
    payload.pop("created_at", None)
    payload.pop("updated_at", None)
    return _workflow_hash_payload(payload)


def stable_workflow_input_hash(
    *,
    kind: GraphWorkflowKind,
    operating_mode: GraphOperatingMode,
    input_payload: JSONObject,
    source_ref: str | None,
) -> str:
    """Return the deterministic hash used for initial workflow snapshots."""
    return _workflow_hash_payload(
        {
            "kind": kind,
            "operating_mode": operating_mode,
            "input_payload": input_payload,
            "source_ref": source_ref,
        },
    )


def _workflow_from_model(model: GraphWorkflowModel) -> GraphWorkflow:
    return GraphWorkflow.model_validate(_model_payload(model))


def _policy_payload(
    outcome: GraphWorkflowPolicyOutcome,
    confidence_result: DecisionConfidenceResult | None = None,
) -> JSONObject:
    payload = cast("JSONObject", outcome.model_dump(mode="json"))
    if confidence_result is not None:
        payload["confidence_result"] = confidence_result.to_payload()
    return payload


def _confidence_assessment_payload(
    assessment: DecisionConfidenceAssessment | None,
) -> JSONObject:
    if assessment is None:
        return {}
    return decision_confidence_assessment_payload(assessment)


def _confidence_assessment_from_payload(
    payload: JSONValue | None,
) -> DecisionConfidenceAssessment | None:
    if not isinstance(payload, Mapping):
        return None
    return DecisionConfidenceAssessment.model_validate(payload)


def _normalize_sentence_source(
    value: str | None,
) -> Literal["verbatim_span", "artana_generated"] | None:
    if value == "verbatim_span":
        return "verbatim_span"
    if value == "artana_generated":
        return "artana_generated"
    return None


def _normalize_sentence_confidence(
    value: str | None,
) -> Literal["low", "medium", "high"] | None:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return None
