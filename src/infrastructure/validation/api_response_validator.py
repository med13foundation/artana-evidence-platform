"""
Runtime validation for external API responses.

Provides utilities to validate external API responses against expected schemas,
helping prevent runtime errors from malformed external data.
"""

import time

from src.type_definitions.common import JSONObject, JSONValue
from src.type_definitions.external_apis import (
    APIResponseValidationResult,
    ValidationIssue,
)

from .clinvar_validation_mixin import ClinVarValidationMixin
from .pubmed_validation_mixin import PubMedValidationMixin


class APIResponseValidator(ClinVarValidationMixin, PubMedValidationMixin):
    """
    Validator for external API responses.

    Provides runtime validation of API responses against expected schemas
    to catch data quality issues early and prevent downstream errors.
    """

    @classmethod
    def validate_generic_api_response(
        cls,
        data: JSONValue,
        required_fields: list[str],
        field_types: dict[str, type] | None = None,
    ) -> APIResponseValidationResult:
        start_time = time.time()

        issues: list[ValidationIssue] = []

        payload: JSONObject | None = data if isinstance(data, dict) else None

        if payload is None:
            issues.append(
                ValidationIssue(
                    field="root",
                    issue_type="invalid",
                    message="Response must be an object",
                    severity="error",
                ),
            )
            return APIResponseValidationResult(
                is_valid=False,
                issues=issues,
                data_quality_score=0.0,
                sanitized_data=None,
                validation_time_ms=(time.time() - start_time) * 1000,
            )

        # Check required fields
        issues.extend(
            [
                ValidationIssue(
                    field=field,
                    issue_type="missing",
                    message=f"Required field '{field}' is missing",
                    severity="error",
                )
                for field in required_fields
                if field not in payload
            ],
        )

        # Check field types if specified
        if field_types:
            issues.extend(
                [
                    ValidationIssue(
                        field=field,
                        issue_type="invalid",
                        message=(
                            f"Field '{field}' must be of type {expected_type.__name__}"
                        ),
                        severity="error",
                    )
                    for field, expected_type in field_types.items()
                    if (
                        field in payload
                        and not isinstance(payload[field], expected_type)
                    )
                ],
            )

        # Calculate data quality score
        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        total_checks = len(required_fields) + (len(field_types) if field_types else 0)
        data_quality_score = max(0.0, 1.0 - (error_count / max(total_checks, 1)))

        validation_time = (time.time() - start_time) * 1000

        return APIResponseValidationResult(
            is_valid=len([i for i in issues if i["severity"] == "error"]) == 0,
            issues=issues,
            data_quality_score=data_quality_score,
            sanitized_data=payload if data_quality_score > cls.QUALITY_MEDIUM else None,
            validation_time_ms=validation_time,
        )

    # Quality thresholds
    QUALITY_LOW: float = 0.5
    QUALITY_MEDIUM: float = 0.6
    QUALITY_HIGH: float = 0.7
    QUALITY_VERY_HIGH: float = 0.8
