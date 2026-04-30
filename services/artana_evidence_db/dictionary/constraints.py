"""Dictionary constraint models and schema validation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.dictionary.schemas import (
    _SUPPORTED_DATA_TYPES,
    normalize_dictionary_data_type,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _BaseConstraints(BaseModel):
    """Base model for dictionary constraints with strict key enforcement."""

    model_config = ConfigDict(extra="forbid")


class NumericConstraints(_BaseConstraints):
    """Constraints for INTEGER/FLOAT variables."""

    min: float | None = None
    max: float | None = None
    precision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> NumericConstraints:
        if (
            self.min is not None
            and self.max is not None
            and float(self.min) > float(self.max)
        ):
            msg = "min must be less than or equal to max"
            raise ValueError(msg)
        return self


class StringConstraints(_BaseConstraints):
    """Constraints for STRING variables."""

    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    pattern: str | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> StringConstraints:
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            msg = "min_length must be less than or equal to max_length"
            raise ValueError(msg)
        return self


class CodedConstraints(_BaseConstraints):
    """Constraints for CODED variables."""

    value_set_id: str | None = Field(default=None, min_length=1, max_length=64)
    allow_other: bool = False


def _parse_iso_temporal(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        msg = "ISO-8601 value cannot be empty"
        raise ValueError(msg)

    with_offset = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(with_offset)
    except ValueError:
        parsed_date = date.fromisoformat(normalized)
        parsed = datetime.combine(parsed_date, datetime.min.time())

    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


class DateConstraints(_BaseConstraints):
    """Constraints for DATE variables."""

    min_date: str | None = None
    max_date: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> DateConstraints:
        parsed_min = (
            _parse_iso_temporal(self.min_date) if self.min_date is not None else None
        )
        parsed_max = (
            _parse_iso_temporal(self.max_date) if self.max_date is not None else None
        )
        if (
            parsed_min is not None
            and parsed_max is not None
            and parsed_min > parsed_max
        ):
            msg = "min_date must be less than or equal to max_date"
            raise ValueError(msg)
        return self


class BooleanConstraints(_BaseConstraints):
    """Constraints for BOOLEAN variables."""


class JsonConstraints(_BaseConstraints):
    """Constraints for JSON variables."""

    json_schema: JSONObject | None = None


_CONSTRAINT_MODEL_BY_DATA_TYPE: Final[dict[str, type[_BaseConstraints]]] = {
    "INTEGER": NumericConstraints,
    "FLOAT": NumericConstraints,
    "STRING": StringConstraints,
    "DATE": DateConstraints,
    "CODED": CodedConstraints,
    "BOOLEAN": BooleanConstraints,
    "JSON": JsonConstraints,
}

type ConstraintValue = JSONValue | date | datetime


def _compile_constraints_model(
    *,
    data_type: str,
    constraints: JSONObject | None,
    allow_legacy_allowed_values: bool,
) -> tuple[str, _BaseConstraints, tuple[str, ...] | None]:
    normalized_data_type = normalize_dictionary_data_type(data_type)
    if normalized_data_type not in _SUPPORTED_DATA_TYPES:
        msg = f"Unsupported data_type '{data_type}'"
        raise ValueError(msg)

    payload = constraints or {}
    payload_without_legacy_allowed_values = payload
    legacy_allowed_values: tuple[str, ...] | None = None
    if (
        allow_legacy_allowed_values
        and normalized_data_type in {"STRING", "CODED"}
        and "allowed_values" in payload
    ):
        raw_allowed_values = payload.get("allowed_values")
        if not isinstance(raw_allowed_values, list) or not all(
            isinstance(item, str) for item in raw_allowed_values
        ):
            msg = (
                f"Invalid constraints for data_type '{normalized_data_type}': "
                "'allowed_values' must be a list[str]"
            )
            raise ValueError(msg)
        legacy_allowed_values = tuple(raw_allowed_values)
        payload_without_legacy_allowed_values = {
            str(key): value for key, value in payload.items() if key != "allowed_values"
        }

    model_type = _CONSTRAINT_MODEL_BY_DATA_TYPE.get(normalized_data_type)
    if model_type is None:
        msg = f"Unsupported data_type '{normalized_data_type}'"
        raise ValueError(msg)

    try:
        validated = model_type.model_validate(payload_without_legacy_allowed_values)
    except ValidationError as exc:
        msg = f"Invalid constraints for data_type '{normalized_data_type}': {exc}"
        raise ValueError(msg) from exc

    return normalized_data_type, validated, legacy_allowed_values


def validate_constraints_for_data_type(
    *,
    data_type: str,
    constraints: JSONObject | None,
) -> JSONObject:
    """Validate and normalize dictionary variable constraints by data type."""
    _, validated, _ = _compile_constraints_model(
        data_type=data_type,
        constraints=constraints,
        allow_legacy_allowed_values=False,
    )
    dumped = validated.model_dump(mode="json", exclude_none=True)
    return {str(key): value for key, value in dumped.items()}


__all__ = [
    "BooleanConstraints",
    "CodedConstraints",
    "ConstraintValue",
    "DateConstraints",
    "JsonConstraints",
    "NumericConstraints",
    "StringConstraints",
    "_BaseConstraints",
    "_CONSTRAINT_MODEL_BY_DATA_TYPE",
    "_compile_constraints_model",
    "_parse_iso_temporal",
    "validate_constraints_for_data_type",
]
