"""Dictionary value compatibility and constraint checks."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.dictionary.constraints import (
    ConstraintValue,
    DateConstraints,
    JsonConstraints,
    NumericConstraints,
    StringConstraints,
    _compile_constraints_model,
    _parse_iso_temporal,
)
from artana_evidence_db.dictionary.schemas import normalize_dictionary_data_type
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError


def _normalize_temporal_value(value: ConstraintValue) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return None


def _count_decimal_places(value: float) -> int:
    try:
        decimal_value = Decimal(str(value)).normalize()
    except InvalidOperation:
        return 0
    exponent = decimal_value.as_tuple().exponent
    if not isinstance(exponent, int):
        return 0
    return max(0, -exponent)


def _is_json_compatible_value(value: ConstraintValue) -> bool:
    if value is None:
        return True
    if isinstance(value, bool | str | int):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return all(_is_json_compatible_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_compatible_value(item)
            for key, item in value.items()
        )
    return False


def is_value_compatible_with_data_type(  # noqa: PLR0911
    *,
    data_type: str,
    value: ConstraintValue,
) -> bool:
    """Return whether a candidate observation value matches the dictionary data type."""
    if value is None:
        return False

    normalized_data_type = normalize_dictionary_data_type(data_type)

    if normalized_data_type == "INTEGER":
        return isinstance(value, int) and not isinstance(value, bool)
    if normalized_data_type == "FLOAT":
        if not isinstance(value, int | float) or isinstance(value, bool):
            return False
        return isfinite(float(value))
    if normalized_data_type == "BOOLEAN":
        return isinstance(value, bool)
    if normalized_data_type in {"STRING", "CODED"}:
        return isinstance(value, str)
    if normalized_data_type == "DATE":
        return isinstance(value, date | datetime)
    if normalized_data_type == "JSON":
        return _is_json_compatible_value(value)
    return False


def _numeric_value_satisfies_constraints(
    *,
    value: ConstraintValue,
    constraints: NumericConstraints,
) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    numeric_value = float(value)
    if not isfinite(numeric_value):
        return False
    if constraints.min is not None and numeric_value < float(constraints.min):
        return False
    if constraints.max is not None and numeric_value > float(constraints.max):
        return False
    if constraints.precision is None:
        return True
    return _count_decimal_places(float(value)) <= constraints.precision


def _string_value_satisfies_constraints(
    *,
    value: ConstraintValue,
    constraints: StringConstraints,
) -> bool:
    if not isinstance(value, str):
        return False
    if constraints.min_length is not None and len(value) < constraints.min_length:
        return False
    if constraints.max_length is not None and len(value) > constraints.max_length:
        return False
    if constraints.pattern is not None:
        try:
            if re.fullmatch(constraints.pattern, value) is None:
                return False
        except re.error:
            return False
    return True


def _date_value_satisfies_constraints(
    *,
    value: ConstraintValue,
    constraints: DateConstraints,
) -> bool:
    normalized_value = _normalize_temporal_value(value)
    if normalized_value is None:
        return False
    if constraints.min_date is not None and normalized_value < _parse_iso_temporal(
        constraints.min_date,
    ):
        return False
    if constraints.max_date is None:
        return True
    return normalized_value <= _parse_iso_temporal(constraints.max_date)


def _json_value_satisfies_constraints(
    *,
    value: ConstraintValue,
    constraints: JsonConstraints,
) -> bool:
    if not _is_json_compatible_value(value):
        return False

    if constraints.json_schema is None:
        return True

    try:
        Draft7Validator.check_schema(constraints.json_schema)
        Draft7Validator(constraints.json_schema).validate(value)
    except (SchemaError, JSONSchemaValidationError):
        return False
    return True


def value_satisfies_dictionary_constraints(  # noqa: PLR0911
    *,
    data_type: str,
    constraints: JSONObject | None,
    value: ConstraintValue,
    allow_legacy_allowed_values: bool = True,
) -> bool:
    """Evaluate whether a value satisfies dictionary data-type constraints."""
    try:
        normalized_data_type, compiled_constraints, legacy_allowed_values = (
            _compile_constraints_model(
                data_type=data_type,
                constraints=constraints,
                allow_legacy_allowed_values=allow_legacy_allowed_values,
            )
        )
    except ValueError:
        return False

    if not is_value_compatible_with_data_type(
        data_type=normalized_data_type,
        value=value,
    ):
        return False

    if legacy_allowed_values is not None:
        if not isinstance(value, str):
            return False
        return value in legacy_allowed_values

    if isinstance(compiled_constraints, NumericConstraints):
        return _numeric_value_satisfies_constraints(
            value=value,
            constraints=compiled_constraints,
        )
    if isinstance(compiled_constraints, StringConstraints):
        return _string_value_satisfies_constraints(
            value=value,
            constraints=compiled_constraints,
        )
    if isinstance(compiled_constraints, DateConstraints):
        return _date_value_satisfies_constraints(
            value=value,
            constraints=compiled_constraints,
        )
    if isinstance(compiled_constraints, JsonConstraints):
        return _json_value_satisfies_constraints(
            value=value,
            constraints=compiled_constraints,
        )
    return True


__all__ = [
    "_count_decimal_places",
    "_date_value_satisfies_constraints",
    "_is_json_compatible_value",
    "_json_value_satisfies_constraints",
    "_normalize_temporal_value",
    "_numeric_value_satisfies_constraints",
    "_string_value_satisfies_constraints",
    "is_value_compatible_with_data_type",
    "value_satisfies_dictionary_constraints",
]
