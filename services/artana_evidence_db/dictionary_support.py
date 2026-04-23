"""Service-local dictionary helper functions and contracts."""

from __future__ import annotations

import re
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import TYPE_CHECKING, ClassVar, Final

from artana_evidence_db.common_types import JSONObject, JSONValue
from jsonschema import Draft7Validator
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

_SUPPORTED_DATA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "INTEGER",
        "FLOAT",
        "STRING",
        "DATE",
        "CODED",
        "BOOLEAN",
        "JSON",
    },
)
_DATA_TYPE_ALIASES: Final[dict[str, str]] = {
    "TEXT": "STRING",
    "STR": "STRING",
    "INT": "INTEGER",
    "LONG": "INTEGER",
    "DOUBLE": "FLOAT",
    "DECIMAL": "FLOAT",
    "NUMBER": "FLOAT",
    "BOOL": "BOOLEAN",
    "OBJECT": "JSON",
    "MAP": "JSON",
    "DICT": "JSON",
    "STRUCT": "JSON",
    "ARRAY": "JSON",
    "LIST": "JSON",
}
_CONSTRAINT_SCHEMA_BY_DATA_TYPE: Final[dict[str, JSONObject]] = {
    "INTEGER": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min": {"type": "number"},
            "max": {"type": "number"},
            "precision": {"type": "integer", "minimum": 0},
        },
    },
    "FLOAT": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min": {"type": "number"},
            "max": {"type": "number"},
            "precision": {"type": "integer", "minimum": 0},
        },
    },
    "STRING": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min_length": {"type": "integer", "minimum": 0},
            "max_length": {"type": "integer", "minimum": 0},
            "pattern": {"type": "string"},
        },
    },
    "DATE": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "min_date": {"type": "string"},
            "max_date": {"type": "string"},
        },
    },
    "CODED": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "value_set_id": {"type": "string"},
            "allow_other": {"type": "boolean"},
        },
    },
    "BOOLEAN": {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    },
    "JSON": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "json_schema": {"type": "object"},
        },
    },
}


class DomainContextResolver:
    """Resolve domain context from explicit input, metadata, or source defaults."""

    PUBMED_DEFAULT_DOMAIN: ClassVar[str] = "clinical"
    CLINVAR_DEFAULT_DOMAIN: ClassVar[str] = "genomics"
    GENERAL_DEFAULT_DOMAIN: ClassVar[str] = "general"

    _SOURCE_TYPE_DEFAULTS: ClassVar[dict[str, str]] = {
        "pubmed": PUBMED_DEFAULT_DOMAIN,
        "clinvar": CLINVAR_DEFAULT_DOMAIN,
    }
    _METADATA_KEYS: ClassVar[tuple[str, ...]] = ("domain_context", "domain")

    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        """Normalize a domain context value into a canonical lower-case token."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, object] | None) -> str | None:
        """Extract a normalized domain context from metadata payload."""
        if metadata is None:
            return None
        for key in cls._METADATA_KEYS:
            raw_value = metadata.get(key)
            if not isinstance(raw_value, str):
                continue
            normalized = cls.normalize(raw_value)
            if normalized is not None:
                return normalized
        return None

    @classmethod
    def default_for_source_type(
        cls,
        source_type: str | None,
        *,
        fallback: str | None = GENERAL_DEFAULT_DOMAIN,
    ) -> str | None:
        """Return the default domain context for a source type."""
        normalized_source_type = cls.normalize(source_type)
        if normalized_source_type is None:
            return cls.normalize(fallback)
        source_default = cls._SOURCE_TYPE_DEFAULTS.get(normalized_source_type)
        if source_default is not None:
            return source_default
        return cls.normalize(fallback)

    @classmethod
    def resolve(
        cls,
        *,
        explicit_domain_context: str | None = None,
        metadata: Mapping[str, object] | None = None,
        source_type: str | None = None,
        ai_inference: Callable[[], str | None] | None = None,
        fallback: str | None = None,
    ) -> str | None:
        """Resolve a domain context via deterministic precedence rules."""
        explicit = cls.normalize(explicit_domain_context)
        if explicit is not None:
            return explicit

        from_metadata = cls.from_metadata(metadata)
        if from_metadata is not None:
            return from_metadata

        from_source_type = cls.default_for_source_type(source_type, fallback=None)
        if from_source_type is not None:
            return from_source_type

        if ai_inference is not None:
            ai_inferred = cls.normalize(ai_inference())
            if ai_inferred is not None:
                return ai_inferred

        return cls.normalize(fallback)


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


def normalize_dictionary_data_type(data_type: str) -> str:
    """Normalize a dictionary data type identifier."""
    normalized = data_type.strip().upper()
    if normalized in _SUPPORTED_DATA_TYPES:
        return normalized
    alias = _DATA_TYPE_ALIASES.get(normalized)
    if alias is not None:
        return alias
    if normalized.endswith(("_LIST", "_ARRAY")):
        return "JSON"
    return normalized


def get_constraint_schema_for_data_type(data_type: str) -> JSONObject:
    """Return the JSON schema payload for a dictionary data type."""
    normalized = normalize_dictionary_data_type(data_type)
    schema = _CONSTRAINT_SCHEMA_BY_DATA_TYPE.get(normalized)
    if schema is None:
        return {}
    return deepcopy(schema)


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
    "BooleanConstraints",
    "CodedConstraints",
    "ConstraintValue",
    "DateConstraints",
    "DomainContextResolver",
    "JsonConstraints",
    "NumericConstraints",
    "StringConstraints",
    "get_constraint_schema_for_data_type",
    "is_value_compatible_with_data_type",
    "normalize_dictionary_data_type",
    "validate_constraints_for_data_type",
    "value_satisfies_dictionary_constraints",
]
