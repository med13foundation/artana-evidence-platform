"""Shared contracts and normalization helpers for dictionary proposals."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, TypeAlias, cast
from uuid import UUID

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.kernel_dictionary_models import DictionaryProposalModel
from artana_evidence_db.kernel_domain_models import (
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    RelationConstraint,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
)

ProposalStatus = Literal[
    "SUBMITTED",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
]
ProposalType = Literal[
    "DOMAIN_CONTEXT",
    "ENTITY_TYPE",
    "VARIABLE",
    "RELATION_TYPE",
    "RELATION_CONSTRAINT",
    "RELATION_SYNONYM",
    "VALUE_SET",
    "VALUE_SET_ITEM",
]
ConstraintProfile = Literal["EXPECTED", "ALLOWED", "REVIEW_ONLY", "FORBIDDEN"]
AppliedDictionaryObject: TypeAlias = (
    DictionaryDomainContext
    | DictionaryEntityType
    | VariableDefinition
    | DictionaryRelationType
    | RelationConstraint
    | DictionaryRelationSynonym
    | ValueSet
    | ValueSetItem
)

_VALID_CONSTRAINT_PROFILES: frozenset[str] = frozenset(
    {"EXPECTED", "ALLOWED", "REVIEW_ONLY", "FORBIDDEN"},
)
REVIEWABLE_PROPOSAL_STATUSES: frozenset[str] = frozenset(
    {"SUBMITTED", "CHANGES_REQUESTED"},
)
_PROPOSAL_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "id",
    "proposal_type",
    "status",
    "source_type",
    "entity_type",
    "relation_type",
    "target_type",
    "value_set_id",
    "variable_id",
    "canonical_name",
    "data_type",
    "preferred_unit",
    "constraints",
    "sensitivity",
    "code",
    "synonym",
    "source",
    "display_name",
    "description",
    "name",
    "display_label",
    "domain_context",
    "external_ontology_ref",
    "external_ref",
    "expected_properties",
    "synonyms",
    "is_directional",
    "inverse_label",
    "is_extensible",
    "sort_order",
    "is_active_value",
    "is_allowed",
    "requires_evidence",
    "profile",
    "rationale",
    "evidence_payload",
    "proposed_by",
    "reviewed_by",
    "reviewed_at",
    "decision_reason",
    "merge_target_type",
    "merge_target_id",
    "applied_domain_context_id",
    "applied_entity_type_id",
    "applied_variable_id",
    "applied_relation_type_id",
    "applied_relation_synonym_id",
    "applied_value_set_id",
    "applied_value_set_item_id",
    "applied_constraint_id",
    "source_ref",
    "created_at",
    "updated_at",
)


def _to_json_value(value: object) -> JSONValue:  # noqa: PLR0911
    """Convert proposal values into changelog-safe JSON."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, set):
        return [_to_json_value(item) for item in sorted(value, key=str)]
    return str(value)


def snapshot_proposal_model(model: DictionaryProposalModel) -> JSONObject:
    """Build a JSON snapshot for proposal lifecycle audit history."""
    return {
        field_name: _to_json_value(getattr(model, field_name))
        for field_name in _PROPOSAL_SNAPSHOT_FIELDS
    }


def normalize_actor(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = "actor is required"
        raise ValueError(msg)
    return normalized


def normalize_dictionary_id(value: str, *, field_name: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return normalized


def normalize_domain_context(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        msg = "domain_context is required"
        raise ValueError(msg)
    return normalized


def normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return normalized


def normalize_source_ref(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_profile(value: str) -> ConstraintProfile:
    normalized = value.strip().upper()
    if normalized not in _VALID_CONSTRAINT_PROFILES:
        msg = "profile must be one of EXPECTED, ALLOWED, REVIEW_ONLY, or FORBIDDEN"
        raise ValueError(msg)
    return cast("ConstraintProfile", normalized)


__all__ = [
    "AppliedDictionaryObject",
    "ConstraintProfile",
    "ProposalStatus",
    "ProposalType",
    "REVIEWABLE_PROPOSAL_STATUSES",
    "normalize_actor",
    "normalize_dictionary_id",
    "normalize_domain_context",
    "normalize_optional_text",
    "normalize_profile",
    "normalize_required_text",
    "normalize_source_ref",
    "snapshot_proposal_model",
]
