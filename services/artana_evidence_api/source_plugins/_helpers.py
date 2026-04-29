"""Small shared helpers for source plugin implementations."""

from __future__ import annotations

from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourcePluginMetadata,
    SourcePluginPlanningError,
    SourceQueryIntent,
    SourceReviewPolicy,
    SourceSearchInput,
)
from artana_evidence_api.source_registry import SourceDefinition
from artana_evidence_api.types.common import JSONObject, JSONValue
from pydantic import BaseModel


def metadata_from_definition(definition: SourceDefinition) -> SourcePluginMetadata:
    """Return plugin metadata derived from the public source definition."""

    return SourcePluginMetadata(
        source_key=definition.source_key,
        display_name=definition.display_name,
        description=definition.description,
        source_family=definition.source_family,
        capabilities=tuple(capability.value for capability in definition.capabilities),
        direct_search_supported=definition.direct_search_enabled,
        research_plan_supported=definition.research_plan_enabled,
        default_research_plan_enabled=definition.default_research_plan_enabled,
        live_network_required=definition.live_network_required,
        requires_credentials=definition.requires_credentials,
        credential_names=definition.credential_names,
        request_schema_ref=definition.request_schema_ref,
        result_schema_ref=definition.result_schema_ref,
        result_capture=definition.result_capture,
        proposal_flow=definition.proposal_flow,
    )


def planning_payload(payload: BaseModel) -> JSONObject:
    """Return the stable JSON payload shape emitted by plugin planning."""

    return {
        key: value
        for key, value in payload.model_dump(
            mode="json",
            exclude_defaults=True,
            exclude_none=True,
        ).items()
        if value not in (None, "", [], {})
    }


def required_text(
    value: str | None,
    *,
    source_key: str,
    field_name: str,
) -> str:
    """Return required non-empty text or raise a plugin planning error."""

    if value is not None and value.strip():
        return value.strip()
    msg = f"Model planner must provide {field_name} for {source_key}."
    raise SourcePluginPlanningError(msg)


def assert_intent_source_key(
    intent: SourceQueryIntent,
    *,
    source_key: str,
) -> None:
    """Fail closed when planning is routed to the wrong plugin."""

    if intent.source_key == source_key:
        return
    msg = f"{source_key} plugin cannot plan query for '{intent.source_key}'."
    raise SourcePluginPlanningError(msg)


def assert_search_source_key(
    search: SourceSearchInput,
    *,
    source_key: str,
    display_name: str,
) -> None:
    """Fail closed when execution is routed to the wrong plugin."""

    if search.source_key == source_key:
        return
    msg = (
        f"{display_name} plugin requires canonical source_key "
        f"'{source_key}', got '{search.source_key}'."
    )
    raise EvidenceSelectionSourceSearchError(msg)


def compact_json_object(payload: dict[str, JSONValue | None]) -> JSONObject:
    """Drop empty JSON values from a normalized source record."""

    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", [], {})
    }


def string_field(record: JSONObject, *keys: str) -> str | None:
    """Return the first non-empty string-like field from a source record."""

    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def json_value_field(record: JSONObject, *keys: str) -> JSONValue | None:
    """Return the first non-empty JSON field from a source record."""

    for key in keys:
        if key not in record:
            continue
        value = record[key]
        if value in (None, "", [], {}):
            continue
        return value
    return None


def identifier_fields(record: JSONObject) -> JSONObject:
    """Return provider identifier-looking fields from a source record."""

    identifier_suffixes = ("_id", "accession", "pmid", "nct_id")
    identifiers: JSONObject = {}
    for key, value in record.items():
        normalized = key.lower()
        if normalized == "id" or any(
            normalized == suffix or normalized.endswith(suffix)
            for suffix in identifier_suffixes
        ):
            identifiers[key] = value
    return identifiers


def normalized_extraction_payload(
    *,
    source_key: str,
    review_policy: SourceReviewPolicy,
    record: JSONObject,
) -> JSONObject:
    """Return reviewer-facing source extraction metadata."""

    extracted = {
        field: record[field]
        for field in review_policy.normalized_fields
        if field in record and record[field] not in (None, "", [], {})
    }
    return {
        "source_key": source_key,
        "evidence_role": review_policy.evidence_role,
        "identifiers": identifier_fields(record),
        "fields": extracted,
        "limitations": list(review_policy.limitations),
        "raw_record_preserved": True,
    }


def proposal_summary(
    *,
    source_key: str,
    review_policy: SourceReviewPolicy,
    selection_reason: str,
) -> str:
    """Return a standard source-specific proposal summary."""

    return (
        f"Selected {source_key} record is a {review_policy.evidence_role} "
        "and requires curator review before any graph promotion. "
        f"Reason: {selection_reason}"
    )


def review_item_summary(
    *,
    source_key: str,
    review_policy: SourceReviewPolicy,
    selection_reason: str,
) -> str:
    """Return a standard source-specific review-item summary."""

    limitations = " ".join(review_policy.limitations)
    return (
        f"Review the selected {source_key} record as "
        f"{review_policy.evidence_role}. {limitations} "
        f"Reason: {selection_reason}"
    )
