"""
Unit conversion engine for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.ingestion.normalization.transform_runtime import (
    execute_transform,
)
from src.infrastructure.ingestion.types import MappedObservation, NormalizedObservation

if TYPE_CHECKING:
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.type_definitions.common import JSONValue


class UnitConverter:
    """
    Normalizes values and units using the TransformRegistry.
    """

    def __init__(self, dictionary_repository: DictionaryPort) -> None:
        self.dictionary_repo = dictionary_repository

    def normalize(self, observation: MappedObservation) -> NormalizedObservation:
        """
        Normalize the value and unit of an observation.
        """
        # If no unit is present, pass through as is (or apply default if variable def has one)
        if not observation.unit:
            return NormalizedObservation(
                subject_anchor=observation.subject_anchor,
                variable_id=observation.variable_id,
                value=observation.value,
                unit=None,
                observed_at=observation.observed_at,
                provenance=observation.provenance,
            )

        # Look up transform in the registry
        # We need to know the target unit. This usually comes from the VariableDefinition.
        # But here we don't have the VariableDefinition handy in the observation.
        # We should probably look it up.
        variable = self.dictionary_repo.get_variable(observation.variable_id)
        if not variable or not variable.preferred_unit:
            # No preferred unit, so we keep the original unit
            return NormalizedObservation(
                subject_anchor=observation.subject_anchor,
                variable_id=observation.variable_id,
                value=observation.value,
                unit=observation.unit,
                observed_at=observation.observed_at,
                provenance=observation.provenance,
            )

        target_unit = variable.preferred_unit

        if observation.unit == target_unit:
            return NormalizedObservation(
                subject_anchor=observation.subject_anchor,
                variable_id=observation.variable_id,
                value=observation.value,
                unit=target_unit,
                observed_at=observation.observed_at,
                provenance=observation.provenance,
            )

        # Look for a transform from source unit to target unit
        transform = self.dictionary_repo.get_transform(
            observation.unit,
            target_unit,
            require_production=True,
        )

        if transform:
            if isinstance(observation.value, bool) or not isinstance(
                observation.value,
                int | float,
            ):
                return NormalizedObservation(
                    subject_anchor=observation.subject_anchor,
                    variable_id=observation.variable_id,
                    value=observation.value,
                    unit=observation.unit,
                    observed_at=observation.observed_at,
                    provenance=observation.provenance,
                )
            transformed_value = self._execute_transform(
                transform.implementation_ref,
                observation.value,
            )
            return NormalizedObservation(
                subject_anchor=observation.subject_anchor,
                variable_id=observation.variable_id,
                value=transformed_value,
                unit=target_unit,
                observed_at=observation.observed_at,
                provenance=observation.provenance,
            )

        # If no transform found, return as is (or log warning)
        return NormalizedObservation(
            subject_anchor=observation.subject_anchor,
            variable_id=observation.variable_id,
            value=observation.value,
            unit=observation.unit,
            observed_at=observation.observed_at,
            provenance=observation.provenance,
        )

    def _execute_transform(self, _ref: str, value: JSONValue) -> JSONValue:
        return execute_transform(_ref, value)
