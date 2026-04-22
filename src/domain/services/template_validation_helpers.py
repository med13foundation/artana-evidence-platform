"""Helper mixin for template validation service."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

import jsonschema

from src.domain.entities.user_data_source import SourceConfiguration

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.domain.entities.source_template import (
        SourceTemplate,
        TemplateUIConfig,
        ValidationRule,
    )
    from src.type_definitions.common import (
        AuthCredentials,
        JSONObject,
        JSONValue,
    )

PrimitiveAuthValue = str | int | float | bool | None

if TYPE_CHECKING:  # pragma: no cover - typing only
    TemplateParameters = Mapping[str, JSONValue]
    JSONSchema = JSONObject
else:  # Runtime fallbacks avoid importing heavy modules eagerly
    TemplateParameters = Mapping[str, object]
    JSONSchema = dict[str, object]


class TemplateValidationHelpersMixin:
    def _validate_json_schema(self, schema: JSONSchema) -> list[str]:
        errors = []

        try:
            if "type" not in schema:
                errors.append("Schema must specify a 'type' field")

            # Try to compile the schema
            jsonschema.Draft7Validator.check_schema(schema)

        except jsonschema.SchemaError as e:
            errors.append(f"Invalid JSON schema: {e!s}")

        return errors

    def _validate_validation_rule(self, rule: ValidationRule, index: int) -> list[str]:
        errors = []

        if not rule.field.strip():
            errors.append(f"Validation rule {index}: field cannot be empty")

        if not rule.rule_type.strip():
            errors.append(f"Validation rule {index}: rule_type cannot be empty")

        # Validate rule type is supported
        supported_types = [
            "required",
            "pattern",
            "range",
            "enum",
            "type",
            "cross_reference",
            "custom",
            "format",
        ]
        if rule.rule_type not in supported_types:
            errors.append(
                f"Validation rule {index}: unsupported rule_type '{rule.rule_type}'",
            )

        # Validate parameters based on rule type
        if rule.rule_type == "pattern" and "pattern" not in rule.parameters:
            errors.append(
                f"Validation rule {index}: pattern rules require 'pattern' parameter",
            )

        if (
            rule.rule_type == "range"
            and "min" not in rule.parameters
            and "max" not in rule.parameters
        ):
            errors.append(
                f"Validation rule {index}: range rules require 'min' or 'max' parameter",
            )

        return errors

    def _validate_ui_config(self, ui_config: TemplateUIConfig) -> list[str]:
        errors = []

        # Validate sections have required fields
        errors.extend(
            [
                "UI sections must have a 'name' field"
                for section in ui_config.sections
                if "name" not in section
            ],
        )

        # Validate field configurations (structure is JSON objects by contract)
        for _field_name, _field_config in ui_config.fields.items():
            # Additional deep validation can be added here as needed
            continue

        return errors

    def _extract_required_parameters(self, template: SourceTemplate) -> list[str]:
        required = []

        # Check UI configuration for required fields
        for field_name, field_config in template.ui_config.fields.items():
            if field_config.get("required", False):
                required.append(field_name)

        # Check schema for required fields
        schema_required_value = template.schema_definition.get("required", [])
        if isinstance(schema_required_value, list):
            required_fields = [
                field for field in schema_required_value if isinstance(field, str)
            ]
            required.extend(required_fields)

        return list(set(required))  # Remove duplicates

    def _validate_parameters(
        self,
        parameters: TemplateParameters,
        template: SourceTemplate,
    ) -> list[str]:
        errors = []
        normalized_parameters = dict(parameters)

        # Validate against schema
        try:
            jsonschema.validate(normalized_parameters, template.schema_definition)
        except jsonschema.ValidationError as e:
            errors.append(f"Parameter validation error: {e!s}")

        # Apply custom validation rules
        for rule in template.validation_rules:
            if rule.field in normalized_parameters:
                rule_value = normalized_parameters[rule.field]
                rule_errors = self._apply_validation_rule(rule_value, rule)
                errors.extend(rule_errors)

        return errors

    def _apply_validation_rule(  # noqa: C901, PLR0912
        self,
        value: JSONValue,
        rule: ValidationRule,
    ) -> list[str]:
        errors = []

        try:
            if rule.rule_type == "required":
                if value is None or (isinstance(value, str) and not value.strip()):
                    errors.append(
                        rule.error_message or f"Field '{rule.field}' is required",
                    )

            elif rule.rule_type == "pattern":
                pattern_value = rule.parameters.get("pattern")
                pattern = pattern_value if isinstance(pattern_value, str) else ""
                if pattern and not re.match(pattern, str(value)):
                    errors.append(
                        rule.error_message
                        or f"Field '{rule.field}' does not match pattern",
                    )

            elif rule.rule_type == "range":
                min_val = self._coerce_float_value(rule.parameters.get("min"))
                max_val = self._coerce_float_value(rule.parameters.get("max"))
                num_value = self._coerce_float_value(value)

                if num_value is None:
                    errors.append(
                        f"Field '{rule.field}' must be numeric for range validation",
                    )
                else:
                    if min_val is not None and num_value < min_val:
                        errors.append(
                            rule.error_message
                            or f"Field '{rule.field}' below minimum {min_val}",
                        )
                    if max_val is not None and num_value > max_val:
                        errors.append(
                            rule.error_message
                            or f"Field '{rule.field}' above maximum {max_val}",
                        )

            elif rule.rule_type == "enum":
                allowed_values_value = rule.parameters.get("values")
                allowed_values: list[JSONValue]
                if isinstance(allowed_values_value, list):
                    allowed_values = list(allowed_values_value)
                else:
                    allowed_values = []
                if value not in allowed_values:
                    errors.append(
                        rule.error_message
                        or f"Field '{rule.field}' must be one of: {allowed_values}",
                    )

            elif rule.rule_type == "type":
                expected_type_value = rule.parameters.get("type")
                expected_type = (
                    expected_type_value
                    if isinstance(expected_type_value, str)
                    else "string"
                )
                if not self._check_type(value, expected_type):
                    errors.append(
                        rule.error_message
                        or f"Field '{rule.field}' must be of type {expected_type}",
                    )

        except (ValueError, TypeError, re.error) as e:
            errors.append(f"Validation rule error for field '{rule.field}': {e!s}")

        return errors

    def _check_type(self, value: JSONValue, expected_type: str) -> bool:
        valid = True
        if expected_type == "string":
            valid = isinstance(value, str)
        elif expected_type == "integer":
            valid = isinstance(value, int)
        elif expected_type == "float":
            valid = isinstance(value, int | float)
        elif expected_type == "boolean":
            valid = isinstance(value, bool)
        elif expected_type == "array":
            valid = isinstance(value, list)
        elif expected_type == "object":
            valid = isinstance(value, dict)
        else:
            valid = True
        return valid

    def _build_configuration(
        self,
        template: SourceTemplate,
        parameters: TemplateParameters,
    ) -> SourceConfiguration:
        normalized_parameters = dict(parameters)
        metadata_payload = self._ensure_json_object(
            normalized_parameters.get("metadata"),
        )
        metadata_payload.update(
            {
                "template_id": str(template.id),
                "template_name": template.name,
                "validation_rules": [
                    rule.model_dump() for rule in template.validation_rules
                ],
            },
        )
        metadata = metadata_payload

        field_mapping = self._coerce_field_mapping(
            normalized_parameters.get("field_mapping"),
        )
        auth_credentials = self._coerce_auth_credentials(
            normalized_parameters.get("auth_credentials"),
        )

        return SourceConfiguration(
            url=self._coerce_str_value(normalized_parameters.get("url")) or "",
            file_path=self._coerce_str_value(normalized_parameters.get("file_path"))
            or "",
            format=self._coerce_str_value(normalized_parameters.get("format")) or "",
            requests_per_minute=self._coerce_int_value(
                normalized_parameters.get("requests_per_minute"),
            ),
            field_mapping=field_mapping or None,
            auth_type=self._coerce_str_value(normalized_parameters.get("auth_type")),
            auth_credentials=auth_credentials,
            metadata=metadata,
        )

    @staticmethod
    def _coerce_str_value(value: JSONValue | None) -> str | None:
        if isinstance(value, str):
            return value
        return None

    @staticmethod
    def _coerce_float_value(value: JSONValue | None) -> float | None:
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @classmethod
    def _coerce_int_value(cls, value: JSONValue | None) -> int | None:
        float_value = cls._coerce_float_value(value)
        if float_value is None:
            return None
        return int(float_value)

    @staticmethod
    def _ensure_json_object(value: JSONValue | None) -> dict[str, JSONValue]:
        if isinstance(value, dict):
            return dict(value)
        return {}

    @staticmethod
    def _coerce_field_mapping(value: JSONValue | None) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            key: val
            for key, val in value.items()
            if isinstance(key, str) and isinstance(val, str)
        }

    @staticmethod
    def _coerce_auth_credentials(
        value: JSONValue | None,
    ) -> AuthCredentials | None:
        if not isinstance(value, dict):
            return None
        normalized = {
            key: val
            for key, val in value.items()
            if isinstance(val, str | int | float | bool) or val is None
        }
        return normalized or None
