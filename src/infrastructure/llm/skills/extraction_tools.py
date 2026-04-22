"""Skill builders for extraction validation and transform lookup."""

from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from src.domain.value_objects.relation_types import normalize_relation_type
from src.infrastructure.ingestion.types import NormalizedObservation
from src.infrastructure.ingestion.validation.observation_validator import (
    ObservationValidator,
)
from src.infrastructure.llm.skills._extraction_relation_dictionary_helpers import (
    ensure_full_auto_relation_dictionary_entry,
    resolve_relation_mapping_candidate,
)
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Literal

    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.type_definitions.common import JSONObject, JSONValue, ResearchSpaceSettings
else:
    type JSONObject = dict[str, object]
    type JSONValue = object


_VALIDATE_TRIPLE_WRITE_LOCK = Lock()


def _resolve_relation_governance_mode(
    research_space_settings: ResearchSpaceSettings | None,
) -> Literal["HUMAN_IN_LOOP", "FULL_AUTO"]:
    if research_space_settings is None:
        return "HUMAN_IN_LOOP"
    raw_mode = research_space_settings.get("relation_governance_mode")
    if isinstance(raw_mode, str) and raw_mode.strip().upper() == "FULL_AUTO":
        return "FULL_AUTO"
    return "HUMAN_IN_LOOP"


def _to_json_payload(value: object) -> JSONObject:
    dump_method = getattr(value, "model_dump", None)
    if callable(dump_method):
        dumped = dump_method(mode="json")
        if isinstance(dumped, dict):
            return {
                str(key): to_json_value(payload_value)
                for key, payload_value in dumped.items()
            }
    return {"value": to_json_value(value)}


def make_validate_observation_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[str, JSONValue, str | None], JSONObject]:
    """Build a tool callable for observation validation."""
    validator = ObservationValidator(dictionary_service)

    def validate_observation(
        variable_id: str,
        value: JSONValue,
        unit: str | None = None,
    ) -> JSONObject:
        """
        Validate one observation candidate against dictionary constraints.

        Returns validity plus canonical normalization details when available.
        """
        normalized_variable_id = variable_id.strip()
        resolved_variable_id = normalized_variable_id
        existing_variable = dictionary_service.get_variable(normalized_variable_id)
        if existing_variable is None:
            resolved_variable = dictionary_service.resolve_synonym(
                normalized_variable_id,
            )
            if resolved_variable is not None:
                resolved_variable_id = resolved_variable.id

        normalized = validator.validate(
            NormalizedObservation(
                subject_anchor={},
                variable_id=resolved_variable_id,
                value=value,
                unit=unit,
                observed_at=None,
                provenance={},
            ),
        )
        if normalized is None:
            return {
                "valid": False,
                "variable_id": resolved_variable_id,
                "reason": "Observation failed dictionary validation",
            }

        return {
            "valid": True,
            "variable_id": resolved_variable_id,
            "value": to_json_value(normalized.value),
            "unit": normalized.unit,
        }

    return validate_observation


def make_validate_triple_tool(
    *,
    dictionary_service: DictionaryPort,
    research_space_settings: ResearchSpaceSettings | None = None,
    **_: object,
) -> Callable[[str, str, str], JSONObject]:
    """Build a tool callable for relation-triple validation."""
    relation_governance_mode = _resolve_relation_governance_mode(
        research_space_settings,
    )

    def validate_triple(  # noqa: PLR0911
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> JSONObject:
        """
        Validate a relation triple against dictionary relation constraints.
        """
        normalized_source_type = source_type.strip().upper()
        normalized_relation_type = normalize_relation_type(relation_type)
        normalized_target_type = target_type.strip().upper()
        if (
            not normalized_source_type
            or not normalized_relation_type
            or not normalized_target_type
        ):
            return {
                "allowed": False,
                "requires_evidence": True,
                "reason": "source_type, relation_type, and target_type are required",
            }
        allowed = dictionary_service.is_relation_allowed(
            source_type=normalized_source_type,
            relation_type=normalized_relation_type,
            target_type=normalized_target_type,
        )
        requires_evidence = dictionary_service.requires_evidence(
            source_type=normalized_source_type,
            relation_type=normalized_relation_type,
            target_type=normalized_target_type,
        )
        if allowed:
            return {
                "allowed": allowed,
                "requires_evidence": requires_evidence,
                "source_type": normalized_source_type,
                "relation_type": normalized_relation_type,
                "target_type": normalized_target_type,
                "reason": "allowed_by_dictionary_constraint",
            }
        if relation_governance_mode != "FULL_AUTO":
            return {
                "allowed": False,
                "requires_evidence": requires_evidence,
                "source_type": normalized_source_type,
                "relation_type": normalized_relation_type,
                "target_type": normalized_target_type,
                "reason": "relation_not_allowed_by_dictionary_constraint",
            }
        try:
            with _VALIDATE_TRIPLE_WRITE_LOCK:
                allowed_after_lock = dictionary_service.is_relation_allowed(
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                )
                if allowed_after_lock:
                    locked_requires_evidence = dictionary_service.requires_evidence(
                        source_type=normalized_source_type,
                        relation_type=normalized_relation_type,
                        target_type=normalized_target_type,
                    )
                    return {
                        "allowed": True,
                        "requires_evidence": locked_requires_evidence,
                        "source_type": normalized_source_type,
                        "relation_type": normalized_relation_type,
                        "target_type": normalized_target_type,
                        "relation_governance_mode": relation_governance_mode,
                        "dictionary_allowed": True,
                        "dictionary_requires_evidence": locked_requires_evidence,
                        "reason": "allowed_after_concurrent_dictionary_update",
                    }

                mapped_relation_type = resolve_relation_mapping_candidate(
                    dictionary_service=dictionary_service,
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                )
                if mapped_relation_type is not None:
                    mapped_requires_evidence = dictionary_service.requires_evidence(
                        source_type=normalized_source_type,
                        relation_type=mapped_relation_type,
                        target_type=normalized_target_type,
                    )
                    return {
                        "allowed": True,
                        "requires_evidence": mapped_requires_evidence,
                        "source_type": normalized_source_type,
                        "relation_type": mapped_relation_type,
                        "target_type": normalized_target_type,
                        "relation_governance_mode": relation_governance_mode,
                        "dictionary_allowed": False,
                        "dictionary_requires_evidence": requires_evidence,
                        "reason": "mapped_to_existing_relation_type",
                    }

                created, creation_reason = ensure_full_auto_relation_dictionary_entry(
                    dictionary_service=dictionary_service,
                    source_type=normalized_source_type,
                    relation_type=normalized_relation_type,
                    target_type=normalized_target_type,
                )
                if created:
                    final_requires_evidence = dictionary_service.requires_evidence(
                        source_type=normalized_source_type,
                        relation_type=normalized_relation_type,
                        target_type=normalized_target_type,
                    )
                    return {
                        "allowed": True,
                        "requires_evidence": final_requires_evidence,
                        "source_type": normalized_source_type,
                        "relation_type": normalized_relation_type,
                        "target_type": normalized_target_type,
                        "relation_governance_mode": relation_governance_mode,
                        "dictionary_allowed": False,
                        "dictionary_requires_evidence": requires_evidence,
                        "reason": creation_reason,
                    }
                return {
                    "allowed": False,
                    "requires_evidence": requires_evidence,
                    "source_type": normalized_source_type,
                    "relation_type": normalized_relation_type,
                    "target_type": normalized_target_type,
                    "relation_governance_mode": relation_governance_mode,
                    "dictionary_allowed": False,
                    "dictionary_requires_evidence": requires_evidence,
                    "reason": creation_reason,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "allowed": False,
                "requires_evidence": requires_evidence,
                "source_type": normalized_source_type,
                "relation_type": normalized_relation_type,
                "target_type": normalized_target_type,
                "relation_governance_mode": relation_governance_mode,
                "dictionary_allowed": False,
                "dictionary_requires_evidence": requires_evidence,
                "reason": f"dictionary_update_error:{type(exc).__name__}",
            }

    return validate_triple


def make_lookup_transform_tool(
    *,
    dictionary_service: DictionaryPort,
    **_: object,
) -> Callable[[str, str], JSONObject]:
    """Build a tool callable for transform lookup."""

    def lookup_transform(
        input_unit: str,
        output_unit: str,
    ) -> JSONObject:
        """
        Look up a registered transform between two units.
        """
        transform = dictionary_service.get_transform(
            input_unit,
            output_unit,
            require_production=True,
        )
        if transform is None:
            return {
                "found": False,
                "input_unit": input_unit,
                "output_unit": output_unit,
            }
        payload = _to_json_payload(transform)
        payload["found"] = True
        return payload

    return lookup_transform


__all__ = [
    "make_lookup_transform_tool",
    "make_validate_observation_tool",
    "make_validate_triple_tool",
]
