"""Shared observation value coercion for validation and persistence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TypedDict

from artana_evidence_db.common_types import JSONValue


class ObservationValueValidationError(ValueError):
    """Raised when an observation value does not match its variable type."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ObservationSlotKwargs(TypedDict, total=False):
    value_numeric: float
    value_text: str
    value_date: datetime | date
    value_coded: str
    value_boolean: bool
    value_json: JSONValue


def _parse_iso_date_value(raw: str) -> datetime | date:
    raw_norm = raw.strip()
    if raw_norm.endswith("Z"):
        raw_norm = f"{raw_norm[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw_norm)
    except ValueError:
        return date.fromisoformat(raw_norm)


def coerce_observation_value_for_data_type(
    *,
    variable_id: str,
    data_type: str,
    value: JSONValue | datetime | date,
) -> ObservationSlotKwargs:
    if value is None:
        raise ObservationValueValidationError(
            code="invalid_value_type",
            message=f"Observation value for variable {variable_id} cannot be null.",
        )

    if data_type in ("INTEGER", "FLOAT"):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=f"Variable {variable_id} expects a numeric value.",
            )
        numeric_value = float(value)
        if data_type == "INTEGER" and not numeric_value.is_integer():
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=f"Variable {variable_id} expects an integer numeric value.",
            )
        return {"value_numeric": numeric_value}

    if data_type == "BOOLEAN":
        if not isinstance(value, bool):
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=f"Variable {variable_id} expects a boolean value.",
            )
        return {"value_boolean": value}

    if data_type in ("DATE", "DATETIME"):
        if isinstance(value, datetime | date):
            return {"value_date": value}
        if not isinstance(value, str):
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=f"Variable {variable_id} expects a date/datetime value.",
            )
        try:
            return {"value_date": _parse_iso_date_value(value)}
        except ValueError as exc:
            raise ObservationValueValidationError(
                code="invalid_date_value",
                message=f"Invalid ISO date/datetime value: {value}",
            ) from exc

    if data_type == "STRING":
        if not isinstance(value, str):
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=f"Variable {variable_id} expects a string value.",
            )
        return {"value_text": value}

    if data_type == "CODED":
        if not isinstance(value, str):
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=f"Variable {variable_id} expects a coded (string) value.",
            )
        return {"value_coded": value}

    if data_type == "JSON":
        if isinstance(value, datetime | date):
            raise ObservationValueValidationError(
                code="invalid_value_type",
                message=(
                    f"Variable {variable_id} expects a JSON value, not a date/datetime."
                ),
            )
        return {"value_json": value}

    raise ObservationValueValidationError(
        code="invalid_value_type",
        message=f"Unsupported variable data_type: {data_type}",
    )


def normalize_observation_value_date(
    value_date: datetime | date | None,
) -> datetime | None:
    if value_date is None:
        return None
    if isinstance(value_date, datetime):
        return value_date
    return datetime(
        value_date.year,
        value_date.month,
        value_date.day,
        tzinfo=UTC,
    )


__all__ = [
    "ObservationSlotKwargs",
    "ObservationValueValidationError",
    "coerce_observation_value_for_data_type",
    "normalize_observation_value_date",
]
