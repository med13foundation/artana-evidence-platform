"""
Application service for source template management.

Orchestrates template operations including creation, approval workflow,
usage tracking, and community template management.
"""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.source_template import (
    SourceTemplate,
    TemplateCategory,
    TemplateUIConfig,
    ValidationRule,
)
from src.domain.entities.user_data_source import SourceType
from src.domain.repositories.source_template_repository import SourceTemplateRepository
from src.type_definitions.common import JSONObject

TEMPLATE_NAME_MAX_LEN = 200
MAX_TAGS = 10
MAX_TAG_LENGTH = 50


class CreateTemplateRequest(BaseModel):
    """Request model for creating a new template."""

    creator_id: UUID
    name: str = Field(max_length=TEMPLATE_NAME_MAX_LEN)
    description: str
    category: TemplateCategory
    source_type: SourceType
    schema_definition: JSONObject
    validation_rules: list[ValidationRule] = Field(default_factory=list)
    ui_config: TemplateUIConfig = Field(default_factory=TemplateUIConfig)
    tags: list[str] = Field(default_factory=list)
    is_public: bool = False  # noqa: FBT001, FBT002

    model_config = ConfigDict(arbitrary_types_allowed=True)


class UpdateTemplateRequest(BaseModel):
    """Request model for updating a template."""

    name: str | None = Field(default=None, max_length=TEMPLATE_NAME_MAX_LEN)
    description: str | None = None
    category: TemplateCategory | None = None
    schema_definition: JSONObject | None = None
    validation_rules: list[ValidationRule] | None = None
    ui_config: TemplateUIConfig | None = None
    tags: list[str] | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class TemplateManagementService:
    """
    Application service for source template management.

    Handles template lifecycle, approval workflows, usage tracking,
    and community template features.
    """

    def __init__(self, template_repository: SourceTemplateRepository):
        """
        Initialize the template management service.

        Args:
            template_repository: Repository for source templates
        """
        self._template_repository = template_repository

    def create_template(self, request: CreateTemplateRequest) -> SourceTemplate:
        """
        Create a new source template.

        Args:
            request: Creation request with template details

        Returns:
            The created SourceTemplate entity

        Raises:
            ValueError: If validation fails
        """
        # Validate request
        self._validate_template_request(request)

        # Create the template entity
        template = SourceTemplate(
            id=uuid4(),
            created_by=request.creator_id,
            name=request.name,
            description=request.description,
            category=request.category,
            source_type=request.source_type,
            schema_definition=request.schema_definition,
            validation_rules=request.validation_rules,
            ui_config=request.ui_config,
            is_public=request.is_public,
            tags=request.tags or [],
            approved_at=None,
        )

        # Save to repository
        return self._template_repository.save(template)

    def get_template(self, template_id: UUID) -> SourceTemplate | None:
        """
        Get a template by ID.

        Args:
            template_id: The template ID

        Returns:
            The SourceTemplate if found, None otherwise
        """
        return self._template_repository.find_by_id(template_id)

    def get_user_templates(
        self,
        creator_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Get all templates created by a user.

        Args:
            creator_id: The creator ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of user's templates
        """
        return self._template_repository.find_by_creator(creator_id, skip, limit)

    def get_public_templates(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Get all public templates.

        Args:
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of public templates
        """
        return self._template_repository.find_public_templates(skip, limit)

    def get_templates_by_category(
        self,
        category: TemplateCategory,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Get templates by category.

        Args:
            category: The category to filter by
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of templates in the category
        """
        return self._template_repository.find_by_category(category, skip, limit)

    def get_templates_by_type(
        self,
        source_type: SourceType,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Get templates by source type.

        Args:
            source_type: The source type to filter by
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of templates for the source type
        """
        return self._template_repository.find_by_source_type(source_type, skip, limit)

    def get_approved_templates(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Get all approved templates.

        Args:
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of approved templates
        """
        return self._template_repository.find_approved_templates(skip, limit)

    def get_available_templates(
        self,
        user_id: UUID | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Get templates available to a user.

        Args:
            user_id: The user ID (None for anonymous)
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of available templates
        """
        return self._template_repository.find_available_for_user(user_id, skip, limit)

    def update_template(
        self,
        template_id: UUID,
        request: UpdateTemplateRequest,
        user_id: UUID,
    ) -> SourceTemplate | None:
        """
        Update a template.

        Args:
            template_id: The template ID
            request: Update request
            user_id: The user making the request (for authorization)

        Returns:
            The updated SourceTemplate if successful, None if not found or not authorized
        """
        template = self._template_repository.find_by_id(template_id)
        if not template or template.created_by != user_id:
            return None

        # Apply updates
        updated_template = template
        if request.name is not None:
            updated_template = updated_template.model_copy(
                update={"name": request.name},
            )
        if request.description is not None:
            updated_template = updated_template.model_copy(
                update={"description": request.description},
            )
        if request.category is not None:
            updated_template = updated_template.model_copy(
                update={"category": request.category},
            )
        if request.schema_definition is not None:
            updated_template = updated_template.update_schema(request.schema_definition)
        if request.validation_rules is not None:
            updated_template = updated_template.model_copy(
                update={"validation_rules": request.validation_rules},
            )
        if request.ui_config is not None:
            updated_template = updated_template.model_copy(
                update={"ui_config": request.ui_config},
            )
        if request.tags is not None:
            updated_template = updated_template.model_copy(
                update={"tags": request.tags},
            )

        return self._template_repository.save(updated_template)

    def delete_template(self, template_id: UUID, user_id: UUID) -> bool:
        """
        Delete a template.

        Args:
            template_id: The template ID
            user_id: The user making the request (for authorization)

        Returns:
            True if deleted, False if not found or not authorized
        """
        template = self._template_repository.find_by_id(template_id)
        if not template or template.created_by != user_id:
            return False

        return self._template_repository.delete(template_id)

    def approve_template(
        self,
        template_id: UUID,
        _approver_id: UUID,
    ) -> SourceTemplate | None:
        """
        Approve a template for general use.

        Args:
            template_id: The template ID
            approver_id: The user approving the template

        Returns:
            The approved template if successful
        """
        return self._template_repository.approve_template(template_id)

    def make_template_public(
        self,
        template_id: UUID,
        user_id: UUID,
    ) -> SourceTemplate | None:
        """
        Make a template publicly available.

        Args:
            template_id: The template ID
            user_id: The user making the request (for authorization)

        Returns:
            The updated template if successful
        """
        template = self._template_repository.find_by_id(template_id)
        if not template or template.created_by != user_id:
            return None

        return self._template_repository.make_public(template_id)

    def increment_usage(self, template_id: UUID) -> SourceTemplate | None:
        """
        Increment usage count for a template.

        Args:
            template_id: The template ID

        Returns:
            The updated template if found
        """
        return self._template_repository.increment_usage(template_id)

    def update_success_rate(
        self,
        template_id: UUID,
        success_rate: float,
    ) -> SourceTemplate | None:
        """
        Update success rate for a template.

        Args:
            template_id: The template ID
            success_rate: The new success rate (0.0 to 1.0)

        Returns:
            The updated template if found
        """
        return self._template_repository.update_success_rate(template_id, success_rate)

    def search_templates(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[SourceTemplate]:
        """
        Search templates by name.

        Args:
            query: Search query
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching templates
        """
        return self._template_repository.search_by_name(query, skip, limit)

    def get_popular_templates(self, limit: int = 10) -> list[SourceTemplate]:
        """
        Get the most popular templates.

        Args:
            limit: Maximum number of templates

        Returns:
            List of popular templates
        """
        return self._template_repository.get_popular_templates(limit)

    def get_template_statistics(self) -> JSONObject:
        """
        Get overall statistics about templates.

        Returns:
            Dictionary with various statistics
        """
        return self._template_repository.get_template_statistics()

    def _validate_template_request(self, request: CreateTemplateRequest) -> None:
        """
        Validate a template creation request.

        Args:
            request: The request to validate

        Raises:
            ValueError: If validation fails
        """
        if not request.name.strip():
            msg = "Template name cannot be empty"
            raise ValueError(msg)

        if len(request.name) > TEMPLATE_NAME_MAX_LEN:
            msg = "Template name cannot exceed 200 characters"
            raise ValueError(msg)

        if not request.schema_definition:
            msg = "Schema definition is required"
            raise ValueError(msg)

        # schema_definition is typed as dict; structural checks handled elsewhere

        # Validate validation rules
        for rule in request.validation_rules:
            if not rule.field or not rule.rule_type:
                msg = "Validation rules must have field and rule_type"
                raise ValueError(msg)

        # Validate tags
        if len(request.tags) > MAX_TAGS:
            msg = "Maximum 10 tags allowed"
            raise ValueError(msg)

        for tag in request.tags:
            if len(tag) > MAX_TAG_LENGTH:
                msg = "Tag length cannot exceed 50 characters"
                raise ValueError(msg)
