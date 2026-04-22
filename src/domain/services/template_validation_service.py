"""
Domain service for template validation and instantiation.

Handles validation of source templates against schemas, instantiation of
templates into concrete configurations, and quality assurance checks.
"""

from pydantic import BaseModel

from src.domain.entities.source_template import SourceTemplate
from src.domain.entities.user_data_source import (
    SourceConfiguration,
    SourceType,
)
from src.domain.services.template_validation_helpers import (
    JSONSchema,
    TemplateParameters,
    TemplateValidationHelpersMixin,
)


class TemplateValidationResult(BaseModel):
    """Result of template validation."""

    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []


class TemplateInstantiationResult(BaseModel):
    """Result of template instantiation."""

    success: bool
    configuration: SourceConfiguration | None = None
    errors: list[str] = []
    missing_parameters: list[str] = []


class TemplateValidationService(TemplateValidationHelpersMixin):
    """
    Domain service for template validation and instantiation.

    Provides validation of templates against JSON schemas, instantiation
    of templates with user parameters, and quality assurance checks.
    """

    def __init__(self) -> None:
        # Common JSON schemas for different data types
        self.schemas: dict[str, JSONSchema] = self._load_common_schemas()

    def _load_common_schemas(self) -> dict[str, JSONSchema]:
        return {
            "gene_variant": {
                "type": "object",
                "properties": {
                    "gene_symbol": {"type": "string", "minLength": 1},
                    "variant_id": {"type": "string"},
                    "chromosome": {"type": "string"},
                    "position": {"type": "integer", "minimum": 1},
                    "reference": {"type": "string"},
                    "alternate": {"type": "string"},
                    "clinical_significance": {
                        "type": "string",
                        "enum": [
                            "pathogenic",
                            "likely_pathogenic",
                            "uncertain",
                            "likely_benign",
                            "benign",
                        ],
                    },
                },
                "required": ["gene_symbol"],
            },
            "phenotype": {
                "type": "object",
                "properties": {
                    "phenotype_id": {"type": "string"},
                    "phenotype_name": {"type": "string", "minLength": 1},
                    "hpo_id": {"type": "string", "pattern": "^HP:\\d+$"},
                    "category": {"type": "string"},
                    "definition": {"type": "string"},
                },
                "required": ["phenotype_name"],
            },
            "publication": {
                "type": "object",
                "properties": {
                    "pmid": {"type": "string", "pattern": "^\\d+$"},
                    "title": {"type": "string", "minLength": 1},
                    "authors": {"type": "array", "items": {"type": "string"}},
                    "journal": {"type": "string"},
                    "year": {"type": "integer", "minimum": 1900, "maximum": 2100},
                    "doi": {"type": "string"},
                },
                "required": ["title"],
            },
        }

    def validate_template(self, template: SourceTemplate) -> TemplateValidationResult:
        errors = []
        warnings = []
        suggestions = []

        # Validate basic template structure
        if not template.name.strip():
            errors.append("Template name cannot be empty")

        if not template.schema_definition:
            errors.append("Schema definition is required")
        else:
            # Validate JSON schema
            schema_errors = self._validate_json_schema(template.schema_definition)
            errors.extend(schema_errors)

        # Validate source type
        if template.source_type not in [st.value for st in SourceType]:
            errors.append(f"Invalid source type: {template.source_type}")

        # Validate validation rules
        for i, rule in enumerate(template.validation_rules):
            rule_errors = self._validate_validation_rule(rule, i)
            errors.extend(rule_errors)

        # Validate UI configuration
        ui_errors = self._validate_ui_config(template.ui_config)
        errors.extend(ui_errors)

        # Generate warnings
        if not template.description.strip():
            warnings.append("Template description is recommended")

        if len(template.tags) == 0:
            warnings.append("Adding tags helps with template discovery")

        if not template.validation_rules:
            warnings.append("Consider adding validation rules for data quality")

        # Generate suggestions
        if template.source_type == "api":
            suggestions.append("Consider adding rate limiting configuration")
            suggestions.append("Add authentication method examples")

        if template.source_type == "file_upload":
            suggestions.append("Specify expected file formats and delimiters")
            suggestions.append("Add sample data examples")

        return TemplateValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )

    def instantiate_template(
        self,
        template: SourceTemplate,
        user_parameters: TemplateParameters,
    ) -> TemplateInstantiationResult:
        errors = []
        missing_parameters = []

        # Check for required parameters
        required_params = self._extract_required_parameters(template)

        normalized_parameters = dict(user_parameters)
        missing_parameters = [
            p for p in required_params if normalized_parameters.get(p) is None
        ]

        if missing_parameters:
            return TemplateInstantiationResult(
                success=False,
                missing_parameters=missing_parameters,
            )

        # Validate parameter values
        param_errors = self._validate_parameters(normalized_parameters, template)
        if param_errors:
            errors.extend(param_errors)

        if errors:
            return TemplateInstantiationResult(success=False, errors=errors)

        # Build configuration
        try:
            configuration = self._build_configuration(
                template,
                normalized_parameters,
            )
            return TemplateInstantiationResult(
                success=True,
                configuration=configuration,
            )
        except (ValueError, TypeError, KeyError) as e:
            return TemplateInstantiationResult(
                success=False,
                errors=[f"Configuration build error: {e!s}"],
            )
