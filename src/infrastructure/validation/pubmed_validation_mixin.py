"""PubMed-specific validation helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.type_definitions.external_apis import (
    APIResponseValidationResult,
    ValidationIssue,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import JSONObject


class PubMedValidationMixin:
    QUALITY_LOW: float = 0.5
    QUALITY_HIGH: float = 0.7

    @classmethod
    def validate_pubmed_search_response(
        cls,
        data: JSONObject,
    ) -> APIResponseValidationResult:
        start_time = time.time()

        issues: list[ValidationIssue] = []

        # Check required fields
        if "esearchresult" not in data:
            issues.append(
                ValidationIssue(
                    field="esearchresult",
                    issue_type="missing",
                    message="esearchresult field is required",
                    severity="error",
                ),
            )

        # Check esearchresult structure
        if "esearchresult" in data:
            esearchresult = data["esearchresult"]
            if not isinstance(esearchresult, dict):
                issues.append(
                    ValidationIssue(
                        field="esearchresult",
                        issue_type="invalid",
                        message="esearchresult must be an object",
                        severity="error",
                    ),
                )
            # Check for idlist
            elif "idlist" not in esearchresult:
                issues.append(
                    ValidationIssue(
                        field="esearchresult.idlist",
                        issue_type="missing",
                        message="idlist is required in esearchresult",
                        severity="error",
                    ),
                )

        # Calculate data quality score
        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        total_checks = 3  # esearchresult, type check, idlist check
        data_quality_score = max(0.0, 1.0 - (error_count / total_checks))

        validation_time = (time.time() - start_time) * 1000

        return APIResponseValidationResult(
            is_valid=len([i for i in issues if i["severity"] == "error"]) == 0,
            issues=issues,
            data_quality_score=data_quality_score,
            sanitized_data=(data if data_quality_score > cls.QUALITY_LOW else None),
            validation_time_ms=validation_time,
        )

    @classmethod
    def validate_pubmed_article_response(
        cls,
        data: JSONObject,
    ) -> APIResponseValidationResult:
        start_time = time.time()

        issues: list[ValidationIssue] = []

        # PubMed ESummary returns a result object with article details
        if "result" not in data:
            issues.append(
                ValidationIssue(
                    field="result",
                    issue_type="missing",
                    message="result field is required",
                    severity="error",
                ),
            )

        # Check result structure
        if "result" in data and isinstance(data["result"], dict):
            result = data["result"]
            if not result:
                issues.append(
                    ValidationIssue(
                        field="result",
                        issue_type="invalid",
                        message="result object is empty",
                        severity="warning",
                    ),
                )
            # Check for uids array
            elif "uids" not in result:
                issues.append(
                    ValidationIssue(
                        field="result.uids",
                        issue_type="missing",
                        message="uids array is required",
                        severity="warning",
                    ),
                )
        elif "result" in data:
            issues.append(
                ValidationIssue(
                    field="result",
                    issue_type="invalid",
                    message="result must be an object",
                    severity="error",
                ),
            )

        # Calculate data quality score
        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        total_checks = 3  # result, type check, uids check
        data_quality_score = max(0.0, 1.0 - (error_count / total_checks))

        validation_time = (time.time() - start_time) * 1000

        return APIResponseValidationResult(
            is_valid=len([i for i in issues if i["severity"] == "error"]) == 0,
            issues=issues,
            data_quality_score=data_quality_score,
            sanitized_data=(data if data_quality_score > cls.QUALITY_HIGH else None),
            validation_time_ms=validation_time,
        )
