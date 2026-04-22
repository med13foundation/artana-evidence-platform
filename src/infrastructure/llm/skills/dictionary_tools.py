"""Dictionary skill builders for tool-enabled entity-recognition agents."""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.type_definitions.common import JSONObject, ResearchSpaceSettings
else:
    type JSONObject = dict[str, object]
    type ResearchSpaceSettings = dict[str, object]


_MUTATION_TOOL_LOCK = threading.RLock()


def _model_to_json(model: object) -> JSONObject:
    dump_method = getattr(model, "model_dump", None)
    if not callable(dump_method):
        msg = "Expected a Pydantic model with model_dump()"
        raise TypeError(msg)
    payload = dump_method(mode="json")
    if not isinstance(payload, dict):
        msg = "Expected model_dump(mode='json') to return a dictionary"
        raise TypeError(msg)
    return {str(key): to_json_value(value) for key, value in payload.items()}


def _normalized_created_by(created_by: str | None) -> str:
    if created_by is None:
        return "agent:entity_recognition"
    normalized = created_by.strip()
    return normalized or "agent:entity_recognition"


def _constraints_payload(constraints: JSONObject | None) -> JSONObject | None:
    if constraints is None:
        return None
    return {str(key): to_json_value(value) for key, value in constraints.items()}


def _expected_properties_payload(
    expected_properties: JSONObject | None,
) -> JSONObject | None:
    if expected_properties is None:
        return None
    return {
        str(key): to_json_value(value) for key, value in expected_properties.items()
    }


def _normalized_string(value: object, *, default: str) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return default


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _optional_json_object(
    value: object | None,
    *,
    field_name: str,
) -> JSONObject | None:
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{field_name} must be a JSON object string when provided"
        raise TypeError(msg)
    normalized = value.strip()
    if not normalized:
        return None
    try:
        decoded = json.loads(normalized)
    except json.JSONDecodeError as exc:
        msg = f"{field_name} must be valid JSON text when provided"
        raise TypeError(msg) from exc
    if not isinstance(decoded, dict):
        msg = f"{field_name} must decode to a JSON object when provided"
        raise TypeError(msg)
    return {str(key): to_json_value(raw) for key, raw in decoded.items()}


def _variable_options(
    options: object | None,
) -> tuple[str, str, str | None, JSONObject | None, str | None]:
    parsed = _optional_json_object(options, field_name="options")
    if parsed is None:
        return ("general", "INTERNAL", None, None, None)
    raw_constraints = parsed.get("constraints")
    normalized_constraints: JSONObject | None
    if raw_constraints is None:
        normalized_constraints = None
    elif isinstance(raw_constraints, dict):
        normalized_constraints = {
            str(key): to_json_value(value) for key, value in raw_constraints.items()
        }
    else:
        msg = "options.constraints must be a JSON object when provided"
        raise TypeError(msg)
    return (
        _normalized_string(parsed.get("domain_context"), default="general"),
        _normalized_string(parsed.get("sensitivity"), default="INTERNAL"),
        _optional_string(parsed.get("preferred_unit")),
        _constraints_payload(normalized_constraints),
        _optional_string(parsed.get("description")),
    )


def make_dictionary_search_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[list[str], list[str] | None, str | None, int], list[JSONObject]]:
    """Build the dictionary_search tool callable."""

    def dictionary_search(
        terms: list[str],
        dimensions: list[str] | None = None,
        domain_context: str | None = None,
        limit: int = 25,
    ) -> list[JSONObject]:
        """
        Search dictionary entries by exact, synonym, fuzzy, and vector matching.

        Use this before creating new dictionary entries.
        """
        results = dictionary_service.dictionary_search(
            terms=terms,
            dimensions=dimensions,
            domain_context=domain_context,
            limit=limit,
        )
        return [_model_to_json(result) for result in results]

    return dictionary_search


def make_dictionary_search_by_domain_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[str, int], list[JSONObject]]:
    """Build the dictionary_search_by_domain tool callable."""

    def dictionary_search_by_domain(
        domain_context: str,
        limit: int = 50,
    ) -> list[JSONObject]:
        """
        List dictionary entries in a single domain context.

        Useful for domain-scoped discovery before creating new entries.
        """
        results = dictionary_service.dictionary_search_by_domain(
            domain_context=domain_context,
            limit=limit,
        )
        return [_model_to_json(result) for result in results]

    return dictionary_search_by_domain


def make_create_variable_tool(
    *,
    dictionary_service: DictionaryPort,
    created_by: str | None = None,
    source_ref: str | None = None,
    research_space_settings: ResearchSpaceSettings | None = None,
    **_: object,
) -> Callable[
    [str, str, str, str],
    JSONObject,
]:
    """Build the create_variable tool callable."""
    actor = _normalized_created_by(created_by)

    def create_variable(
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        options: str | None = None,
    ) -> JSONObject:
        """
        Create a new dictionary variable definition.

        Call this only after searching and confirming no good existing match.
        Pass optional fields as a JSON object string via `options`.
        """
        (
            domain_context,
            sensitivity,
            preferred_unit,
            constraints,
            description,
        ) = _variable_options(options)
        with _MUTATION_TOOL_LOCK:
            created = dictionary_service.create_variable(
                variable_id=variable_id,
                canonical_name=canonical_name,
                display_name=display_name,
                data_type=data_type,
                domain_context=domain_context,
                sensitivity=sensitivity,
                preferred_unit=preferred_unit,
                constraints=constraints,
                description=description,
                created_by=actor,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
        return _model_to_json(created)

    return create_variable


def make_create_synonym_tool(
    *,
    dictionary_service: DictionaryPort,
    created_by: str | None = None,
    source_ref: str | None = None,
    research_space_settings: ResearchSpaceSettings | None = None,
    **_: object,
) -> Callable[[str, str, str | None], JSONObject]:
    """Build the create_synonym tool callable."""
    actor = _normalized_created_by(created_by)

    def create_synonym(
        variable_id: str,
        synonym: str,
        source: str | None = None,
    ) -> JSONObject:
        """
        Register a synonym for an existing variable.

        Use this when a document field is an alias of an existing variable.
        """
        with _MUTATION_TOOL_LOCK:
            created = dictionary_service.create_synonym(
                variable_id=variable_id,
                synonym=synonym,
                source=source,
                created_by=actor,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
        return _model_to_json(created)

    return create_synonym


def make_create_entity_type_tool(
    *,
    dictionary_service: DictionaryPort,
    created_by: str | None = None,
    source_ref: str | None = None,
    research_space_settings: ResearchSpaceSettings | None = None,
    **_: object,
) -> Callable[[str, str, str, str, str | None, str | None], JSONObject]:
    """Build the create_entity_type tool callable."""
    actor = _normalized_created_by(created_by)

    def create_entity_type(  # noqa: PLR0913
        entity_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        external_ontology_ref: str | None = None,
        expected_properties: str | None = None,
    ) -> JSONObject:
        """
        Create a first-class dictionary entity type.

        Use only when the concept is absent from existing entity types.
        Pass expected_properties as a JSON object string when needed.
        """
        with _MUTATION_TOOL_LOCK:
            created = dictionary_service.create_entity_type(
                entity_type=entity_type,
                display_name=display_name,
                description=description,
                domain_context=domain_context,
                external_ontology_ref=external_ontology_ref,
                expected_properties=_expected_properties_payload(
                    _optional_json_object(
                        expected_properties,
                        field_name="expected_properties",
                    ),
                ),
                created_by=actor,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
        return _model_to_json(created)

    return create_entity_type


def make_create_relation_type_tool(
    *,
    dictionary_service: DictionaryPort,
    created_by: str | None = None,
    source_ref: str | None = None,
    research_space_settings: ResearchSpaceSettings | None = None,
    **_: object,
) -> Callable[..., JSONObject]:
    """Build the create_relation_type tool callable."""
    actor = _normalized_created_by(created_by)

    def create_relation_type(  # noqa: PLR0913
        relation_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        *,
        is_directional: bool = True,
        inverse_label: str | None = None,
    ) -> JSONObject:
        """
        Create a first-class dictionary relation type.

        Use only when no semantically equivalent relation type exists.
        """
        with _MUTATION_TOOL_LOCK:
            created = dictionary_service.create_relation_type(
                relation_type=relation_type,
                display_name=display_name,
                description=description,
                domain_context=domain_context,
                is_directional=is_directional,
                inverse_label=inverse_label,
                created_by=actor,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
        return _model_to_json(created)

    return create_relation_type


def make_create_relation_constraint_tool(
    *,
    dictionary_service: DictionaryPort,
    created_by: str | None = None,
    source_ref: str | None = None,
    research_space_settings: ResearchSpaceSettings | None = None,
    **_: object,
) -> Callable[..., JSONObject]:
    """Build the create_relation_constraint tool callable."""
    actor = _normalized_created_by(created_by)

    def create_relation_constraint(
        source_type: str,
        relation_type: str,
        target_type: str,
        *,
        is_allowed: bool = True,
        requires_evidence: bool = True,
    ) -> JSONObject:
        """
        Create an allowed relation triple constraint.

        Use this only after confirming the source/target entity and relation types.
        """
        with _MUTATION_TOOL_LOCK:
            created = dictionary_service.create_relation_constraint(
                source_type=source_type,
                relation_type=relation_type,
                target_type=target_type,
                is_allowed=is_allowed,
                requires_evidence=requires_evidence,
                created_by=actor,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
        return _model_to_json(created)

    return create_relation_constraint


__all__ = [
    "make_create_entity_type_tool",
    "make_create_relation_constraint_tool",
    "make_create_relation_type_tool",
    "make_create_synonym_tool",
    "make_create_variable_tool",
    "make_dictionary_search_by_domain_tool",
    "make_dictionary_search_tool",
]
