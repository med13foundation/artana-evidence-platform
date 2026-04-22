"""ClinVar-specific validation helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.type_definitions.external_apis import (
    ClinVarESearchResult,
    ClinVarSearchResponse,
    ClinVarSearchValidationResult,
    ClinVarVariantRecord,
    ClinVarVariantResponse,
    ClinVarVariantResultMap,
    ClinVarVariantValidationResult,
    ValidationIssue,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import JSONObject, JSONValue


class ClinVarValidationMixin:
    @staticmethod
    def validate_clinvar_search_response(
        data: JSONValue,
    ) -> ClinVarSearchValidationResult:
        start_time = time.time()

        issues: list[ValidationIssue] = []
        sanitized_data: ClinVarSearchResponse | None = None

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    field="root",
                    issue_type="invalid",
                    message="Response must be an object",
                    severity="error",
                ),
            )
            validation_time = (time.time() - start_time) * 1000
            return ClinVarSearchValidationResult(
                is_valid=False,
                issues=issues,
                data_quality_score=0.0,
                sanitized_data=None,
                validation_time_ms=validation_time,
            )

        payload: JSONObject = data

        required_fields = ["esearchresult", "header"]
        missing = [field for field in required_fields if field not in payload]
        issues.extend(
            [
                ValidationIssue(
                    field=field,
                    issue_type="missing",
                    message=f"Required field '{field}' is missing",
                    severity="error",
                )
                for field in missing
            ],
        )

        header_obj = payload.get("header")
        header_payload: JSONObject | None = (
            header_obj if isinstance(header_obj, dict) else None
        )
        if header_obj is not None and header_payload is None:
            issues.append(
                ValidationIssue(
                    field="header",
                    issue_type="invalid",
                    message="header must be an object",
                    severity="error",
                ),
            )

        esearch_section = payload.get("esearchresult")
        sanitized_esearch: ClinVarESearchResult | None = None

        if isinstance(esearch_section, dict):
            raw_idlist = esearch_section.get("idlist")
            if raw_idlist is None:
                issues.append(
                    ValidationIssue(
                        field="esearchresult.idlist",
                        issue_type="missing",
                        message="idlist is required in esearchresult",
                        severity="error",
                    ),
                )
            elif not isinstance(raw_idlist, list):
                issues.append(
                    ValidationIssue(
                        field="esearchresult.idlist",
                        issue_type="invalid",
                        message="idlist must be an array",
                        severity="error",
                    ),
                )
            else:
                id_list = [
                    str(identifier)
                    for identifier in raw_idlist
                    if isinstance(identifier, str | int)
                ]

                sanitized_esearch = {
                    "count": str(esearch_section.get("count", "0")),
                    "retmax": str(esearch_section.get("retmax", "0")),
                    "retstart": str(esearch_section.get("retstart", "0")),
                    "idlist": id_list,
                }

                query_translation = esearch_section.get("querytranslation")
                if isinstance(query_translation, str):
                    sanitized_esearch["querytranslation"] = query_translation

                translationset = esearch_section.get("translationset")
                if isinstance(translationset, list):
                    sanitized_esearch["translationset"] = [
                        entry for entry in translationset if isinstance(entry, dict)
                    ]

                translationstack = esearch_section.get("translationstack")
                if isinstance(translationstack, list):
                    sanitized_esearch["translationstack"] = [
                        entry for entry in translationstack if isinstance(entry, dict)
                    ]
        else:
            issues.append(
                ValidationIssue(
                    field="esearchresult",
                    issue_type="missing",
                    message="esearchresult field is required",
                    severity="error",
                ),
            )

        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        total_checks = len(required_fields) + 2
        data_quality_score = max(0.0, 1.0 - (error_count / total_checks))

        if error_count == 0 and header_payload and sanitized_esearch:
            sanitized_data = ClinVarSearchResponse(
                header=header_payload,
                esearchresult=sanitized_esearch,
            )

        validation_time = (time.time() - start_time) * 1000

        return ClinVarSearchValidationResult(
            is_valid=error_count == 0,
            issues=issues,
            data_quality_score=data_quality_score,
            sanitized_data=sanitized_data,
            validation_time_ms=validation_time,
        )

    @classmethod
    def validate_clinvar_variant_response(
        cls,
        data: JSONValue,
    ) -> ClinVarVariantValidationResult:
        start_time = time.time()

        issues: list[ValidationIssue] = []
        sanitized_data: ClinVarVariantResponse | None = None

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    field="root",
                    issue_type="invalid",
                    message="Response must be an object",
                    severity="error",
                ),
            )
            validation_time = (time.time() - start_time) * 1000
            return ClinVarVariantValidationResult(
                is_valid=False,
                issues=issues,
                data_quality_score=0.0,
                sanitized_data=None,
                validation_time_ms=validation_time,
            )

        header_issues, header_obj = cls._validate_header_section(
            data.get("header"),
        )
        issues.extend(header_issues)

        result_issues, result_map = cls._sanitize_variant_result(
            data.get("result"),
        )
        issues.extend(result_issues)

        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        total_checks = 2  # result and header checks
        data_quality_score = max(0.0, 1.0 - (error_count / total_checks))

        if error_count == 0 and header_obj and result_map is not None:
            sanitized_data = ClinVarVariantResponse(
                header=header_obj,
                result=result_map,
            )

        validation_time = (time.time() - start_time) * 1000

        return ClinVarVariantValidationResult(
            is_valid=error_count == 0,
            issues=issues,
            data_quality_score=data_quality_score,
            sanitized_data=sanitized_data,
            validation_time_ms=validation_time,
        )

    @staticmethod
    def _validate_header_section(
        header_obj: JSONValue,
    ) -> tuple[list[ValidationIssue], JSONObject | None]:
        issues: list[ValidationIssue] = []
        if header_obj is None:
            issues.append(
                ValidationIssue(
                    field="header",
                    issue_type="missing",
                    message="header field is required",
                    severity="warning",
                ),
            )
            return issues, None

        if not isinstance(header_obj, dict):
            issues.append(
                ValidationIssue(
                    field="header",
                    issue_type="invalid",
                    message="header must be an object",
                    severity="error",
                ),
            )
            return issues, None

        header_payload: JSONObject = header_obj
        return issues, header_payload

    @staticmethod
    def _sanitize_variant_record(
        record_value: JSONObject,
    ) -> ClinVarVariantRecord:
        record: ClinVarVariantRecord = {}
        for field_name in (
            "variation_id",
            "variation_name",
            "review_status",
            "last_updated",
        ):
            field_value = record_value.get(field_name)
            if isinstance(field_value, str | int):
                record[field_name] = str(field_value)

        for structured_field in (
            "gene",
            "condition",
            "clinical_significance",
            "interpretation",
        ):
            maybe_dict = record_value.get(structured_field)
            if isinstance(maybe_dict, dict):
                record[structured_field] = maybe_dict

        submissions = record_value.get("submissions")
        if isinstance(submissions, list):
            record["submissions"] = [
                submission for submission in submissions if isinstance(submission, dict)
            ]

        return record

    @classmethod
    def _sanitize_variant_result(
        cls,
        result_section: JSONValue,
    ) -> tuple[list[ValidationIssue], ClinVarVariantResultMap | None]:
        issues: list[ValidationIssue] = []
        if result_section is None:
            issues.append(
                ValidationIssue(
                    field="result",
                    issue_type="missing",
                    message="result field is required",
                    severity="error",
                ),
            )
            return issues, None

        if not isinstance(result_section, dict):
            issues.append(
                ValidationIssue(
                    field="result",
                    issue_type="invalid",
                    message="result must be an object",
                    severity="error",
                ),
            )
            return issues, None

        if not result_section:
            issues.append(
                ValidationIssue(
                    field="result",
                    issue_type="invalid",
                    message="result object is empty",
                    severity="warning",
                ),
            )

        sanitized_records: ClinVarVariantResultMap = {}
        for key, value in result_section.items():
            if key == "uids":
                if isinstance(value, list):
                    sanitized_records["uids"] = [
                        str(uid) for uid in value if isinstance(uid, str | int)
                    ]
                continue

            if not isinstance(value, dict):
                issues.append(
                    ValidationIssue(
                        field=f"result.{key}",
                        issue_type="invalid",
                        message="Variant entry must be an object",
                        severity="warning",
                    ),
                )
                continue

            sanitized_records[key] = cls._sanitize_variant_record(
                value,
            )

        return issues, sanitized_records or None
