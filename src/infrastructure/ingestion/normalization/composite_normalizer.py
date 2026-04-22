"""
Composite normalizer for the ingestion pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.infrastructure.ingestion.types import NormalizedObservation

if TYPE_CHECKING:
    from src.infrastructure.ingestion.normalization.unit_converter import UnitConverter
    from src.infrastructure.ingestion.normalization.value_caster import ValueCaster
    from src.infrastructure.ingestion.types import MappedObservation


class CompositeNormalizer:
    """
    Chains multiple normalization steps.
    """

    def __init__(
        self,
        unit_converter: UnitConverter,
        value_caster: ValueCaster,
    ) -> None:
        self.unit_converter = unit_converter
        self.value_caster = value_caster

    def normalize(self, observation: MappedObservation) -> NormalizedObservation:
        # 1. Normalize Units
        normalized = self.unit_converter.normalize(observation)

        # 2. Cast Value types
        # ValueCaster.cast returns the casted value (Any) or None
        # We need to update the NormalizedObservation with this new value
        casted_value = self.value_caster.cast(
            # We can pass MappedObservation to cast, or NormalizedObservation?
            # ValueCaster expects MappedObservation in my previous implementation.
            # But here we have a NormalizedObservation from unit conversion.
            # NormalizedObservation has same fields as MappedObservation usually?
            # Let's check types.
            normalized,  # cast method needs to accept NormalizedObservation too or I assume compat
        )

        # Create new NormalizedObservation with casted value
        return NormalizedObservation(
            subject_anchor=normalized.subject_anchor,
            variable_id=normalized.variable_id,
            value=casted_value,
            unit=normalized.unit,
            observed_at=normalized.observed_at,
            provenance=normalized.provenance,
        )
