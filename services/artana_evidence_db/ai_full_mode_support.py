"""Shared helpers for DB-owned AI Full Mode governance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from artana_evidence_db.ai_full_mode_models import (
    AIDecision,
    ConceptProposal,
    ConceptProposalDecision,
    ConnectorProposal,
    GraphChangeProposal,
)
from artana_evidence_db.ai_full_mode_persistence_models import (
    AIDecisionModel,
    ConceptProposalModel,
    ConnectorProposalModel,
    GraphChangeProposalModel,
)
from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.kernel_concept_models import (
    ConceptMemberModel,
)
from artana_evidence_db.kernel_domain_models import ConceptMember

_REVIEWABLE_CONCEPT_STATUSES = frozenset(
    {"SUBMITTED", "DUPLICATE_CANDIDATE", "CHANGES_REQUESTED", "APPROVED"},
)
_REVIEWABLE_GRAPH_CHANGE_STATUSES = frozenset(
    {"READY_FOR_REVIEW", "CHANGES_REQUESTED"},
)
_REVIEWABLE_CONNECTOR_STATUSES = frozenset({"SUBMITTED", "CHANGES_REQUESTED"})
_DEFAULT_MIN_AI_CONFIDENCE = 0.9


@dataclass(frozen=True)
class ConceptResolution:
    """Deterministic duplicate-resolution result for a proposed concept."""

    candidate_decision: ConceptProposalDecision
    existing_concept_member_id: str | None
    duplicate_checks: JSONObject
    warnings: list[str]


def _as_uuid(value: str) -> UUID:
    return UUID(value)


def _uuid_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    msg = f"{field_name} is required"
    raise ValueError(msg)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_domain_context(value: str) -> str:
    return _normalize_required_text(value, field_name="domain_context").lower()


def _normalize_entity_type(value: str) -> str:
    return _normalize_required_text(value, field_name="entity_type").upper()


def _normalize_label(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="label")
    return " ".join(normalized.split())


def _normalize_alias_key(value: str) -> str:
    return _normalize_label(value).lower()


def _normalize_slug(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    parts = [part for part in normalized.split("-") if part]
    if not parts:
        msg = "connector_slug is required"
        raise ValueError(msg)
    return "-".join(parts)


def _manual_actor(actor: str) -> str:
    normalized = _normalize_required_text(actor, field_name="actor")
    if normalized.startswith(("manual:", "agent:", "system:")):
        return normalized
    return f"manual:{normalized}"


def resolve_ai_full_source_ref(
    *,
    request_source_ref: str | None,
    idempotency_key: str | None,
    actor: str,
) -> str | None:
    """Resolve actor-scoped source_ref/idempotency key for Phase 9 writes."""
    source_ref = _normalize_optional_text(request_source_ref)
    key = _normalize_optional_text(idempotency_key)
    if source_ref is not None and key is not None:
        msg = "Provide either source_ref or Idempotency-Key, not both"
        raise ValueError(msg)
    if source_ref is not None:
        return source_ref
    if key is not None:
        return f"idempotency-key:{_manual_actor(actor)}:{key}"
    return None


def _to_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_value(item) for item in value]
    return str(value)


def _model_payload(model: object) -> dict[str, object]:
    table = getattr(model, "__table__", None)
    if table is None:
        msg = "SQLAlchemy model is missing __table__ metadata"
        raise TypeError(msg)
    payload: dict[str, object] = {}
    for column in table.columns:
        value = getattr(model, column.name)
        payload[column.name] = str(value) if isinstance(value, UUID) else value
    return payload


def _snapshot_model(model: object) -> JSONObject:
    return {
        key: _to_json_value(value)
        for key, value in _model_payload(model).items()
        if key not in {"created_at", "updated_at"}
    }


def _hash_payload(payload: JSONObject) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _proposal_hash(model: ConceptProposalModel | GraphChangeProposalModel) -> str:
    snapshot = _snapshot_model(model)
    snapshot.pop("proposal_hash", None)
    return _hash_payload(snapshot)


def _concept_from_model(model: ConceptProposalModel) -> ConceptProposal:
    return ConceptProposal.model_validate(_model_payload(model))


def _graph_change_from_model(model: GraphChangeProposalModel) -> GraphChangeProposal:
    return GraphChangeProposal.model_validate(_model_payload(model))


def _ai_decision_from_model(model: AIDecisionModel) -> AIDecision:
    return AIDecision.model_validate(_model_payload(model))


def _connector_from_model(model: ConnectorProposalModel) -> ConnectorProposal:
    return ConnectorProposal.model_validate(_model_payload(model))


def _json_str(value: JSONValue | None, *, field_name: str) -> str:
    if isinstance(value, str):
        return _normalize_required_text(value, field_name=field_name)
    msg = f"{field_name} must be a string"
    raise ValueError(msg)


def _json_optional_str(value: JSONValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _normalize_optional_text(value)
    return None


def _json_float(value: JSONValue | None, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return default


def _json_mapping(value: JSONValue | None) -> JSONObject:
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    return {}


def _json_sequence(value: JSONValue | None) -> list[JSONValue]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_json_value(item) for item in value]
    return []


def _normalize_external_refs(external_refs: list[JSONObject]) -> list[JSONObject]:
    normalized_refs: list[JSONObject] = []
    seen: set[str] = set()
    for item in external_refs:
        namespace = _json_str(item.get("namespace"), field_name="external_ref.namespace")
        identifier = _json_str(item.get("identifier"), field_name="external_ref.identifier")
        normalized_namespace = namespace.strip().lower()
        normalized_identifier = identifier.strip()
        key = f"{normalized_namespace}:{normalized_identifier}".lower()
        if key in seen:
            continue
        seen.add(key)
        normalized_refs.append(
            {
                "namespace": normalized_namespace,
                "identifier": normalized_identifier,
                "key": key,
            },
        )
    return normalized_refs


def _external_ref_alias(ref: JSONObject) -> tuple[str, str, str]:
    namespace = _json_str(ref.get("namespace"), field_name="external_ref.namespace")
    identifier = _json_str(ref.get("identifier"), field_name="external_ref.identifier")
    label = f"{namespace}:{identifier}"
    return label, label.lower(), f"external_ref:{namespace.lower()}"


def _member_entity_type(member: ConceptMemberModel | ConceptMember) -> str | None:
    payload = getattr(member, "metadata_payload", None)
    if isinstance(member, ConceptMember):
        payload = member.metadata_payload
    if not isinstance(payload, Mapping):
        return None
    raw_value = payload.get("entity_type")
    if not isinstance(raw_value, str):
        return None
    return raw_value.strip().upper() or None


def _member_matches_entity_type(
    member: ConceptMemberModel | ConceptMember,
    *,
    entity_type: str,
) -> bool:
    member_entity_type = _member_entity_type(member)
    return member_entity_type is None or member_entity_type == entity_type



__all__ = [
    "ConceptResolution",
    "resolve_ai_full_source_ref",
]
