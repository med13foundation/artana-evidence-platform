"""Application service for typed graph observations."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Protocol

from artana_evidence_db.common_types import JSONValue
from artana_evidence_db.graph_core_models import KernelEntity, KernelObservation
from artana_evidence_db.kernel_domain_models import (
    TransformRegistry,
    VariableDefinition,
)
from artana_evidence_db.observation_value_support import (
    ObservationSlotKwargs,
    coerce_observation_value_for_data_type,
    normalize_observation_value_date,
)

logger = logging.getLogger(__name__)


class EntityRepositoryLike(Protocol):
    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        """Return one entity by ID."""


class DictionaryRepositoryLike(Protocol):
    def get_variable(self, variable_id: str) -> VariableDefinition | None:
        """Return one variable definition by ID."""

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
        *,
        require_production: bool,
    ) -> TransformRegistry | None:
        """Return one unit transform when available."""


class ObservationRepositoryLike(Protocol):
    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        subject_id: str,
        variable_id: str,
        value_numeric: float | None = None,
        value_text: str | None = None,
        value_date: datetime | None = None,
        value_coded: str | None = None,
        value_boolean: bool | None = None,
        value_json: JSONValue | None = None,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> KernelObservation:
        """Create one observation row."""

    def create_batch(self, observations: list[dict[str, object]]) -> int:
        """Bulk-create observation rows."""

    def get_by_id(self, observation_id: str) -> KernelObservation | None:
        """Return one observation by ID."""

    def find_by_subject(
        self,
        subject_id: str,
        *,
        variable_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        """List observations for one subject."""

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        """List observations for one research space."""

    def delete(self, observation_id: str) -> bool:
        """Delete one observation."""

    def delete_by_provenance(self, provenance_id: str) -> int:
        """Delete observations linked to one provenance record."""


class KernelObservationService:
    """Validate, normalize, and persist typed observations."""

    def __init__(
        self,
        observation_repo: ObservationRepositoryLike,
        entity_repo: EntityRepositoryLike,
        dictionary_repo: DictionaryRepositoryLike,
    ) -> None:
        self._observations = observation_repo
        self._entities = entity_repo
        self._dictionary = dictionary_repo

    def _ensure_subject_in_space(
        self,
        *,
        research_space_id: str,
        subject_id: str,
    ) -> None:
        subject = self._entities.get_by_id(subject_id)
        if subject is None:
            msg = f"Subject entity {subject_id} not found"
            raise ValueError(msg)
        if str(subject.research_space_id) != str(research_space_id):
            msg = (
                f"Subject entity {subject_id} is not in research space "
                f"{research_space_id}"
            )
            raise ValueError(msg)

    def _expected_slot_for_data_type(self, data_type: str) -> str:
        if data_type in ("INTEGER", "FLOAT"):
            return "value_numeric"
        mapping = {
            "STRING": "value_text",
            "DATE": "value_date",
            "DATETIME": "value_date",
            "CODED": "value_coded",
            "BOOLEAN": "value_boolean",
            "JSON": "value_json",
        }
        if data_type not in mapping:
            msg = f"Unsupported variable data_type: {data_type}"
            raise ValueError(msg)
        return mapping[data_type]

    def _coerce_value_for_data_type(
        self,
        *,
        variable_id: str,
        data_type: str,
        value: JSONValue | datetime | date,
    ) -> ObservationSlotKwargs:
        return coerce_observation_value_for_data_type(
            variable_id=variable_id,
            data_type=data_type,
            value=value,
        )

    def record_observation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        subject_id: str,
        variable_id: str,
        value_numeric: float | None = None,
        value_text: str | None = None,
        value_date: datetime | date | None = None,
        value_coded: str | None = None,
        value_boolean: bool | None = None,
        value_json: JSONValue | None = None,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> KernelObservation:
        self._ensure_subject_in_space(
            research_space_id=research_space_id,
            subject_id=subject_id,
        )

        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Unknown variable_id: {variable_id}"
            raise ValueError(msg)

        data_type = variable.data_type
        normalised_value_date = normalize_observation_value_date(value_date)
        expected_slot = self._expected_slot_for_data_type(data_type)

        slot_values: dict[str, object | None] = {
            "value_numeric": value_numeric,
            "value_text": value_text,
            "value_date": normalised_value_date,
            "value_coded": value_coded,
            "value_boolean": value_boolean,
            "value_json": value_json,
        }
        populated_slots = [
            key for key, value in slot_values.items() if value is not None
        ]
        if len(populated_slots) != 1:
            msg = (
                "Observations must populate exactly one value slot "
                f"(got {len(populated_slots)})"
            )
            raise ValueError(msg)

        if populated_slots[0] != expected_slot:
            msg = (
                f"Variable {variable_id} expects {expected_slot} "
                f"but got {populated_slots[0]}"
            )
            raise ValueError(msg)

        if (
            data_type == "INTEGER"
            and value_numeric is not None
            and (
                isinstance(value_numeric, bool) or not float(value_numeric).is_integer()
            )
        ):
            msg = f"Variable {variable_id} expects an integer numeric value"
            raise ValueError(msg)

        normalised_unit = unit
        if unit and variable.preferred_unit and unit != variable.preferred_unit:
            transform = self._dictionary.get_transform(
                unit,
                variable.preferred_unit,
                require_production=True,
            )
            if transform:
                normalised_unit = variable.preferred_unit
                logger.debug(
                    "Normalised unit %s → %s for variable %s",
                    unit,
                    normalised_unit,
                    variable_id,
                )

        return self._observations.create(
            research_space_id=research_space_id,
            subject_id=subject_id,
            variable_id=variable_id,
            value_numeric=value_numeric,
            value_text=value_text,
            value_date=normalised_value_date,
            value_coded=value_coded,
            value_boolean=value_boolean,
            value_json=value_json,
            unit=normalised_unit,
            observed_at=observed_at,
            provenance_id=provenance_id,
            confidence=confidence,
        )

    def record_observation_value(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        subject_id: str,
        variable_id: str,
        value: JSONValue | datetime | date,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> KernelObservation:
        variable = self._dictionary.get_variable(variable_id)
        if variable is None:
            msg = f"Unknown variable_id: {variable_id}"
            raise ValueError(msg)

        slot_kwargs = self._coerce_value_for_data_type(
            variable_id=variable_id,
            data_type=variable.data_type,
            value=value,
        )
        return self.record_observation(
            research_space_id=research_space_id,
            subject_id=subject_id,
            variable_id=variable_id,
            unit=unit,
            observed_at=observed_at,
            provenance_id=provenance_id,
            confidence=confidence,
            **slot_kwargs,
        )

    def record_batch(self, observations: list[dict[str, object]]) -> int:
        return self._observations.create_batch(observations)

    def get_observation(self, observation_id: str) -> KernelObservation | None:
        return self._observations.get_by_id(observation_id)

    def get_subject_observations(
        self,
        subject_id: str,
        *,
        variable_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        return self._observations.find_by_subject(
            subject_id,
            variable_id=variable_id,
            limit=limit,
            offset=offset,
        )

    def get_research_space_observations(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        return self._observations.find_by_research_space(
            research_space_id,
            limit=limit,
            offset=offset,
        )

    def delete_observation(self, observation_id: str) -> bool:
        return self._observations.delete(observation_id)

    def rollback_provenance(self, provenance_id: str) -> int:
        return self._observations.delete_by_provenance(provenance_id)


__all__ = ["KernelObservationService"]
