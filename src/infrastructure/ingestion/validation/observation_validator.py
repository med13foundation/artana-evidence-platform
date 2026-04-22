"""
Observation validator for the ingestion pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from src.infrastructure.ingestion.types import NormalizedObservation
from src.type_definitions.dictionary import (
    CodedConstraints,
    is_value_compatible_with_data_type,
    value_satisfies_dictionary_constraints,
)

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import VariableDefinition
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.infrastructure.ingestion.types import IngestedValue
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class ObservationValidator:
    """
    Validates normalized observations against dictionary constraints.
    """

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def validate(
        self,
        observation: NormalizedObservation,
    ) -> NormalizedObservation | None:
        """
        Validate an observation against the variable definition constraints.
        """
        variable = self.dictionary_repo.get_variable(observation.variable_id)
        if not variable:
            logger.warning(
                "Variable %s not found in dictionary",
                observation.variable_id,
            )
            return None

        if not is_value_compatible_with_data_type(
            data_type=variable.data_type,
            value=observation.value,
        ):
            return None

        is_valid, normalized_coded_value = self._validate_constraints(
            observation.value,
            variable,
        )
        if not is_valid:
            return None

        if normalized_coded_value is None:
            return observation

        return NormalizedObservation(
            subject_anchor=observation.subject_anchor,
            variable_id=observation.variable_id,
            value=normalized_coded_value,
            unit=observation.unit,
            observed_at=observation.observed_at,
            provenance=observation.provenance,
        )

    def _validate_constraints(
        self,
        value: IngestedValue,
        variable: VariableDefinition,
    ) -> tuple[bool, str | None]:
        constraints = variable.constraints
        normalized_coded_value: str | None = None

        variable_data_type = variable.data_type
        variable_id = variable.id

        if variable_data_type == "CODED":
            coded_valid, normalized_coded_value = self._validate_coded_value_set(
                value=value,
                variable_id=variable_id,
                constraints=constraints,
            )
            if not coded_valid:
                return False, None

        value_for_constraints = (
            normalized_coded_value if normalized_coded_value is not None else value
        )

        if not value_satisfies_dictionary_constraints(
            data_type=variable_data_type,
            constraints=constraints,
            value=value_for_constraints,
        ):
            logger.warning(
                "Value failed dictionary constraint validation for variable %s",
                variable_id,
            )
            return False, None

        return True, normalized_coded_value

    @staticmethod
    def _resolve_coded_constraints(constraints: JSONObject) -> CodedConstraints | None:
        coded_payload: JSONObject = {}
        value_set_id = constraints.get("value_set_id")
        allow_other = constraints.get("allow_other")
        if value_set_id is not None:
            coded_payload["value_set_id"] = value_set_id
        if allow_other is not None:
            coded_payload["allow_other"] = allow_other
        try:
            return CodedConstraints.model_validate(coded_payload)
        except ValidationError:
            return None

    def _validate_coded_value_set(  # noqa: C901, PLR0911, PLR0912
        self,
        *,
        value: IngestedValue,
        variable_id: str,
        constraints: JSONObject,
    ) -> tuple[bool, str | None]:
        """
        Validate CODED values against active value-set items when configured.

        Returns:
            - (True, canonical_code) when matched by canonical code or synonym.
            - (True, None) when no value set exists for the variable.
            - (False, None) when value sets exist but no active match is found.
        """
        coded_constraints = self._resolve_coded_constraints(constraints)
        if coded_constraints is None:
            logger.warning(
                "Invalid CODED constraints for variable %s; rejecting observation",
                variable_id,
            )
            return False, None
        allow_other = coded_constraints.allow_other

        value_sets = self.dictionary_repo.list_value_sets(variable_id=variable_id)
        configured_value_set_id = coded_constraints.value_set_id
        if configured_value_set_id is not None:
            value_sets = [
                value_set
                for value_set in value_sets
                if value_set.id == configured_value_set_id
            ]

        if not value_sets:
            if configured_value_set_id is not None:
                logger.warning(
                    "Configured value_set_id %s for variable %s not found",
                    configured_value_set_id,
                    variable_id,
                )
                return allow_other, None
            return True, None

        active_value_sets = [
            value_set for value_set in value_sets if value_set.review_status == "ACTIVE"
        ]
        if not active_value_sets:
            if allow_other:
                return True, None
            logger.warning(
                "Variable %s has no active value set available for CODED validation",
                variable_id,
            )
            return False, None

        if not isinstance(value, str) or not value.strip():
            return False, None

        lookup_value = value.strip().casefold()
        for value_set in active_value_sets:
            items = self.dictionary_repo.list_value_set_items(
                value_set_id=value_set.id,
                include_inactive=False,
            )
            for item in items:
                if item.review_status != "ACTIVE":
                    continue
                if lookup_value == item.code.casefold():
                    return True, item.code
                for synonym in item.synonyms:
                    if lookup_value == synonym.casefold():
                        return True, item.code

        if allow_other:
            return True, None
        return False, None
