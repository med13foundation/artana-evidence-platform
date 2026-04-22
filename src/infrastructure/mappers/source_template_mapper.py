"""
Mapper for SourceTemplate entities and database models.

Provides bidirectional conversion between domain SourceTemplate
objects and their SQLAlchemy representations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.source_template import (
    SourceTemplate,
    TemplateCategory,
    TemplateUIConfig,
    ValidationRule,
)
from src.domain.entities.user_data_source import SourceType
from src.models.database.source_template import (
    SourceTemplateModel,
    SourceTypeEnum,
    TemplateCategoryEnum,
)

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds")


class SourceTemplateMapper:
    """Bidirectional mapper for SourceTemplate entities."""

    @staticmethod
    def to_domain(model: SourceTemplateModel) -> SourceTemplate:
        """Convert a SQLAlchemy model to a domain entity."""
        schema_definition: JSONObject = model.schema_definition or {}
        validation_rules = [
            ValidationRule.model_validate(rule)
            for rule in (model.validation_rules or [])
        ]
        ui_config = TemplateUIConfig.model_validate(model.ui_config or {})

        approved_at = _parse_datetime(model.approved_at)

        return SourceTemplate(
            id=UUID(str(model.id)),
            created_by=UUID(model.created_by),
            name=model.name,
            description=model.description,
            category=TemplateCategory(model.category.value),
            source_type=SourceType(model.source_type.value),
            schema_definition=schema_definition,
            validation_rules=validation_rules,
            ui_config=ui_config,
            is_public=model.is_public,
            is_approved=model.is_approved,
            approval_required=model.approval_required,
            usage_count=model.usage_count,
            success_rate=model.success_rate or 0.0,
            created_at=model.created_at,
            updated_at=model.updated_at,
            approved_at=approved_at,
            tags=model.tags or [],
            version=model.version,
            compatibility_version=model.compatibility_version,
        )

    @staticmethod
    def to_model(entity: SourceTemplate) -> SourceTemplateModel:
        """Convert a domain entity to a SQLAlchemy model."""
        return SourceTemplateModel(
            id=str(entity.id),
            created_by=str(entity.created_by),
            name=entity.name,
            description=entity.description,
            category=TemplateCategoryEnum(entity.category.value),
            source_type=SourceTypeEnum(entity.source_type.value),
            schema_definition=entity.schema_definition,
            validation_rules=[rule.model_dump() for rule in entity.validation_rules],
            ui_config=entity.ui_config.model_dump(),
            is_public=entity.is_public,
            is_approved=entity.is_approved,
            approval_required=entity.approval_required,
            usage_count=entity.usage_count,
            success_rate=entity.success_rate,
            approved_at=_format_datetime(entity.approved_at),
            tags=entity.tags,
            version=entity.version,
            compatibility_version=entity.compatibility_version,
        )

    @staticmethod
    def update_model(model: SourceTemplateModel, entity: SourceTemplate) -> None:
        """Update an existing SQLAlchemy model from a domain entity."""
        model.name = entity.name
        model.description = entity.description
        model.category = TemplateCategoryEnum(entity.category.value)
        model.source_type = SourceTypeEnum(entity.source_type.value)
        model.schema_definition = entity.schema_definition
        model.validation_rules = [rule.model_dump() for rule in entity.validation_rules]
        model.ui_config = entity.ui_config.model_dump()
        model.is_public = entity.is_public
        model.is_approved = entity.is_approved
        model.approval_required = entity.approval_required
        model.usage_count = entity.usage_count
        model.success_rate = entity.success_rate
        model.approved_at = _format_datetime(entity.approved_at)
        model.tags = entity.tags
        model.version = entity.version
        model.compatibility_version = entity.compatibility_version
