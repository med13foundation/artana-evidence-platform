"""
Domain entity for data source templates in Artana Resource Library.

Templates provide reusable configurations for common biomedical data sources,
enabling users to quickly set up sources with proven configurations.
"""

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.type_definitions.common import JSONObject, JSONValue

from .user_data_source import SourceType


class TemplateCategory(str, Enum):
    """Categories for organizing source templates."""

    CLINICAL = "clinical"
    RESEARCH = "research"
    LITERATURE = "literature"
    GENOMIC = "genomic"
    PHENOTYPIC = "phenotypic"
    ONTOLOGY = "ontology"
    OTHER = "other"


class ValidationRule(BaseModel):
    """Validation rule for template-based data sources."""

    field: str = Field(..., description="Field name to validate")
    rule_type: str = Field(..., description="Type of validation rule")
    parameters: dict[str, JSONValue] = Field(
        default_factory=dict,
        description="Rule parameters",
    )
    error_message: str = Field(..., description="Error message if validation fails")

    @field_validator("rule_type")
    @classmethod
    def validate_rule_type(cls, v: str) -> str:
        """Validate rule type is supported."""
        allowed_types = [
            "required",
            "pattern",
            "range",
            "enum",
            "type",
            "cross_reference",
            "custom",
            "format",
        ]
        if v not in allowed_types:
            msg = f"Rule type must be one of: {allowed_types}"
            raise ValueError(msg)
        return v


class TemplateUIConfig(BaseModel):
    """UI configuration for template forms."""

    sections: list[JSONObject] = Field(
        default_factory=list,
        description="Form sections",
    )
    fields: dict[str, JSONObject] = Field(
        default_factory=dict,
        description="Field configurations",
    )
    help_text: dict[str, str] = Field(
        default_factory=dict,
        description="Help text for fields",
    )
    examples: dict[str, str] = Field(default_factory=dict, description="Example values")

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, v: list[JSONObject]) -> list[JSONObject]:
        """Validate section configurations."""
        for section in v:
            if "name" not in section:
                msg = "Each section must have a 'name' field"
                raise ValueError(msg)
        return v


UpdatePayload = dict[str, object]


class SourceTemplate(BaseModel):
    """
    Domain entity representing a reusable data source template.

    Templates encapsulate proven configurations for common biomedical data sources,
    making it easy for users to set up new sources with validated settings.
    """

    model_config = ConfigDict(frozen=True)  # Immutable - changes create new instances

    # Identity
    id: UUID = Field(..., description="Unique identifier for the template")
    created_by: UUID = Field(..., description="User who created this template")

    # Basic information
    name: str = Field(..., min_length=1, max_length=200, description="Template name")
    description: str = Field("", max_length=1000, description="Detailed description")
    category: TemplateCategory = Field(
        default=TemplateCategory.OTHER,
        description="Template category",
    )

    # Template definition
    source_type: SourceType = Field(
        ...,
        description="Type of source this template supports",
    )
    schema_definition: JSONObject = Field(..., description="Expected data schema")
    validation_rules: list[ValidationRule] = Field(
        default_factory=list,
        description="Validation rules",
    )

    # UI configuration
    ui_config: TemplateUIConfig = Field(
        default_factory=TemplateUIConfig,
        description="UI form configuration",
    )

    # Governance
    is_public: bool = Field(
        default=False,
        description="Whether template is publicly available",
    )
    is_approved: bool = Field(
        default=False,
        description="Whether template has been approved",
    )
    approval_required: bool = Field(
        default=True,
        description="Whether approval is required for use",
    )

    # Usage statistics
    usage_count: int = Field(
        default=0,
        description="Number of times template has been used",
    )
    success_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Success rate of sources using this template",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When template was created",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When template was last updated",
    )
    approved_at: datetime | None = Field(
        None,
        description="When template was approved",
    )

    # Metadata
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for template discovery",
    )
    version: str = Field(default="1.0", description="Template version")
    compatibility_version: str = Field(
        default="1.0",
        description="Minimum system version required",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate template name."""
        if not v.strip():
            msg = "Template name cannot be empty or whitespace"
            raise ValueError(msg)
        return v.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags."""
        max_tags = 10
        if len(v) > max_tags:
            msg = "Maximum 10 tags allowed"
            raise ValueError(msg)
        return [tag.strip().lower() for tag in v if tag.strip()]

    @field_validator("schema_definition")
    @classmethod
    def validate_schema(cls, v: JSONObject) -> JSONObject:
        """Validate schema definition has required structure."""
        return v

    def is_available(self, user_id: UUID | None = None) -> bool:
        """Check if template is available for use by a specific user."""
        if not self.is_approved and self.approval_required:
            return False
        return self.is_public or (user_id == self.created_by)

    def _clone_with_updates(self, updates: UpdatePayload) -> "SourceTemplate":
        """Internal helper to maintain immutability with typed updates."""
        return self.model_copy(update=updates)

    def increment_usage(self) -> "SourceTemplate":
        """Create new instance with incremented usage count."""
        update_payload: UpdatePayload = {
            "usage_count": self.usage_count + 1,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def update_success_rate(self, new_rate: float) -> "SourceTemplate":
        """Create new instance with updated success rate."""
        update_payload: UpdatePayload = {
            "success_rate": new_rate,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def approve(self, _approved_by: UUID) -> "SourceTemplate":
        """Create new instance with approval status."""
        now = datetime.now(UTC)
        update_payload: UpdatePayload = {
            "is_approved": True,
            "approved_at": now,
            "updated_at": now,
        }
        return self._clone_with_updates(update_payload)

    def make_public(self) -> "SourceTemplate":
        """Create new instance as publicly available."""
        update_payload: UpdatePayload = {
            "is_public": True,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def update_schema(self, schema: JSONObject) -> "SourceTemplate":
        """Create new instance with updated schema."""
        update_payload: UpdatePayload = {
            "schema_definition": schema,
            "updated_at": datetime.now(UTC),
            "version": self._increment_version(),
        }
        return self._clone_with_updates(update_payload)

    def _increment_version(self) -> str:
        """Increment version number."""
        try:
            major, minor = self.version.split(".")
            return f"{major}.{int(minor) + 1}"
        except (ValueError, IndexError):
            return "1.0"

    @property
    def display_name(self) -> str:
        """Get formatted display name with version."""
        return f"{self.name} (v{self.version})"

    @property
    def approval_status(self) -> str:
        """Get human-readable approval status."""
        if self.is_approved:
            return "Approved"
        if self.approval_required:
            return "Pending Approval"
        return "No Approval Required"
