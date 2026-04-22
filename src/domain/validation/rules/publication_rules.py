"""
Validation helpers for publication metadata.
"""

from __future__ import annotations

import re

from src.type_definitions.common import JSONObject, JSONValue
from src.type_definitions.json_utils import as_str

from .base_rules import (
    ValidationLevel,
    ValidationOutcome,
    ValidationRule,
    ValidationSeverity,
)

IssueDict = JSONObject


class PublicationValidationRules:
    """Validation utilities for publication entities."""

    _DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[\w.\-()/]+$")

    @staticmethod
    def validate_doi_format_and_accessibility(
        _placeholder: JSONValue,
        field: str = "doi",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            doi_value = as_str(value)
            if doi_value is None:
                return True, "", None
            if not doi_value.strip():
                return (
                    False,
                    "DOI is required",
                    "Provide a DOI in the format 10.xxxx/…",
                )
            if not PublicationValidationRules._DOI_PATTERN.fullmatch(doi_value):
                return (
                    False,
                    f"Invalid DOI format: {doi_value}",
                    "DOIs must start with 10.xxxx/",
                )
            return True, "", None

        return ValidationRule(
            field=field,
            rule="doi_format",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_author_information(
        _placeholder: JSONValue,
        field: str = "authors",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value in (None, []):
                return (
                    False,
                    "At least one author is required",
                    "Provide the author list",
                )
            if not isinstance(value, list):
                return (
                    False,
                    "Author list must contain dictionaries or strings",
                    "Provide structured author information",
                )

            for author in value:
                if isinstance(author, str):
                    if not author.strip():
                        return (
                            False,
                            "Author names cannot be empty",
                            "Provide the author's full name",
                        )
                elif isinstance(author, dict):
                    name = as_str(author.get("name"))
                    if not name or not name.strip():
                        return (
                            False,
                            "Author name is required",
                            "Provide the author's full name",
                        )
                else:
                    return (
                        False,
                        "Author entries must be strings or mappings",
                        "Provide structured author information",
                    )

            return True, "", None

        return ValidationRule(
            field=field,
            rule="author_information",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_publication_comprehensively(
        publication: JSONObject,
    ) -> list[IssueDict]:
        issues: list[IssueDict] = []

        rules = (
            PublicationValidationRules.validate_doi_format_and_accessibility(""),
            PublicationValidationRules.validate_author_information([]),
        )

        for rule in rules:
            is_valid, message, suggestion = rule.validator(publication.get(rule.field))
            if not is_valid:
                issues.append(
                    {
                        "field": rule.field,
                        "rule": rule.rule,
                        "message": message,
                        "suggestion": suggestion,
                        "severity": rule.severity.name.lower(),
                    },
                )

        pubmed_id = publication.get("pubmed_id")
        if pubmed_id and (not isinstance(pubmed_id, str) or not pubmed_id.isdigit()):
            issues.append(
                PublicationValidationRules._make_issue(
                    field="pubmed_id",
                    rule="pubmed_id_format",
                    message=f"Invalid PubMed identifier: {pubmed_id}",
                    severity=ValidationSeverity.ERROR,
                ),
            )

        if not publication.get("title"):
            issues.append(
                PublicationValidationRules._make_issue(
                    field="title",
                    rule="title_required",
                    message="Publication title is required",
                    severity=ValidationSeverity.ERROR,
                ),
            )

        return issues

    @staticmethod
    def _make_issue(
        *,
        field: str,
        rule: str,
        message: str,
        severity: ValidationSeverity,
        suggestion: str | None = None,
    ) -> IssueDict:
        return {
            "field": field,
            "rule": rule,
            "message": message,
            "suggestion": suggestion,
            "severity": severity.name.lower(),
        }


__all__ = ["PublicationValidationRules"]
