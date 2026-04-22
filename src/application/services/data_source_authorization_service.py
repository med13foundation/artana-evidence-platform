"""
Authorization service for data source operations.

Provides fine-grained access control for data source management operations,
ensuring users can only perform actions they're authorized for.
"""

from enum import Enum
from uuid import UUID

from src.domain.entities.source_template import SourceTemplate
from src.domain.entities.user_data_source import UserDataSource


class DataSourcePermission(Enum):
    """Permissions for data source operations."""

    # Source management
    CREATE_SOURCE = "create_source"
    READ_SOURCE = "read_source"
    UPDATE_SOURCE = "update_source"
    DELETE_SOURCE = "delete_source"
    ACTIVATE_SOURCE = "activate_source"
    DEACTIVATE_SOURCE = "deactivate_source"

    # Template management
    CREATE_TEMPLATE = "create_template"
    READ_TEMPLATE = "read_template"
    UPDATE_TEMPLATE = "update_template"
    DELETE_TEMPLATE = "delete_template"
    APPROVE_TEMPLATE = "approve_template"
    PUBLISH_TEMPLATE = "publish_template"

    # Ingestion operations
    TRIGGER_INGESTION = "trigger_ingestion"
    VIEW_INGESTION_LOGS = "view_ingestion_logs"
    CANCEL_INGESTION = "cancel_ingestion"

    # Administrative
    MANAGE_ALL_SOURCES = "manage_all_sources"
    MANAGE_ALL_TEMPLATES = "manage_all_templates"
    VIEW_ANALYTICS = "view_analytics"


class UserRole(Enum):
    """User roles with associated permissions."""

    ANONYMOUS = "anonymous"  # No authentication
    READER = "reader"  # Can read public data
    CONTRIBUTOR = "contributor"  # Can create and manage own sources
    CURATOR = "curator"  # Can approve sources and templates
    ADMIN = "admin"  # Full access


class DataSourceAuthorizationService:
    """
    Authorization service for data source operations.

    Implements fine-grained access control based on user roles and ownership,
    ensuring secure and appropriate access to data source functionality.
    """

    def __init__(self) -> None:
        """Initialize the authorization service."""
        self._role_permissions = self._build_role_permissions()

    def _build_role_permissions(self) -> dict[UserRole, set[DataSourcePermission]]:
        """Build the permission matrix for each role."""
        return {
            UserRole.ANONYMOUS: {
                DataSourcePermission.READ_TEMPLATE,  # Public templates only
            },
            UserRole.READER: {
                DataSourcePermission.READ_SOURCE,
                DataSourcePermission.READ_TEMPLATE,
                DataSourcePermission.VIEW_INGESTION_LOGS,
                DataSourcePermission.VIEW_ANALYTICS,
            },
            UserRole.CONTRIBUTOR: {
                DataSourcePermission.CREATE_SOURCE,
                DataSourcePermission.READ_SOURCE,
                DataSourcePermission.UPDATE_SOURCE,
                DataSourcePermission.DELETE_SOURCE,
                DataSourcePermission.ACTIVATE_SOURCE,
                DataSourcePermission.DEACTIVATE_SOURCE,
                DataSourcePermission.CREATE_TEMPLATE,
                DataSourcePermission.READ_TEMPLATE,
                DataSourcePermission.UPDATE_TEMPLATE,
                DataSourcePermission.DELETE_TEMPLATE,
                DataSourcePermission.TRIGGER_INGESTION,
                DataSourcePermission.VIEW_INGESTION_LOGS,
                DataSourcePermission.CANCEL_INGESTION,
            },
            UserRole.CURATOR: {
                DataSourcePermission.CREATE_SOURCE,
                DataSourcePermission.READ_SOURCE,
                DataSourcePermission.UPDATE_SOURCE,
                DataSourcePermission.DELETE_SOURCE,
                DataSourcePermission.ACTIVATE_SOURCE,
                DataSourcePermission.DEACTIVATE_SOURCE,
                DataSourcePermission.CREATE_TEMPLATE,
                DataSourcePermission.READ_TEMPLATE,
                DataSourcePermission.UPDATE_TEMPLATE,
                DataSourcePermission.DELETE_TEMPLATE,
                DataSourcePermission.APPROVE_TEMPLATE,
                DataSourcePermission.PUBLISH_TEMPLATE,
                DataSourcePermission.TRIGGER_INGESTION,
                DataSourcePermission.VIEW_INGESTION_LOGS,
                DataSourcePermission.CANCEL_INGESTION,
                DataSourcePermission.VIEW_ANALYTICS,
            },
            UserRole.ADMIN: set(DataSourcePermission),  # All permissions
        }

    def has_permission(
        self,
        _user_id: UUID | None,
        role: str,
        permission: DataSourcePermission,
    ) -> bool:
        """
        Check if a user has a specific permission.

        Args:
            user_id: The user ID (None for anonymous)
            role: The user's role string
            permission: The permission to check

        Returns:
            True if the user has the permission, False otherwise
        """
        user_role = self._parse_role(role)

        # Get permissions for the role
        role_permissions = self._role_permissions.get(user_role, set())

        return permission in role_permissions

    def can_manage_source(
        self,
        user_id: UUID | None,
        role: str,
        source: UserDataSource,
        permission: DataSourcePermission,
    ) -> bool:
        """
        Check if a user can perform an operation on a specific source.

        Args:
            user_id: The user ID
            role: The user's role string
            source: The data source
            permission: The permission to check

        Returns:
            True if the user can perform the operation, False otherwise
        """
        # First check if user has the permission
        if not self.has_permission(user_id, role, permission):
            return False

        # For ownership-based permissions, check if user owns the source
        ownership_required_permissions = {
            DataSourcePermission.UPDATE_SOURCE,
            DataSourcePermission.DELETE_SOURCE,
            DataSourcePermission.ACTIVATE_SOURCE,
            DataSourcePermission.DEACTIVATE_SOURCE,
        }

        if permission in ownership_required_permissions:
            return user_id is not None and source.owner_id == user_id

        # Admin can manage all sources
        if self._parse_role(role) == UserRole.ADMIN:
            return True

        # For read operations, allow if source is owned by user or if user has read permission
        if permission == DataSourcePermission.READ_SOURCE:
            return (
                user_id is None
                or source.owner_id == user_id
                or self.has_permission(user_id, role, permission)
            )

        return True

    def can_manage_template(
        self,
        user_id: UUID | None,
        role: str,
        template: SourceTemplate,
        permission: DataSourcePermission,
    ) -> bool:
        """
        Check if a user can perform an operation on a specific template.

        Args:
            user_id: The user ID
            role: The user's role string
            template: The source template
            permission: The permission to check

        Returns:
            True if the user can perform the operation, False otherwise
        """
        # First check if user has the permission
        if not self.has_permission(user_id, role, permission):
            return False

        user_role = self._parse_role(role)

        # Admin can manage all templates
        if user_role == UserRole.ADMIN:
            return True

        # For ownership-based permissions, check if user created the template
        ownership_required_permissions = {
            DataSourcePermission.UPDATE_TEMPLATE,
            DataSourcePermission.DELETE_TEMPLATE,
            DataSourcePermission.PUBLISH_TEMPLATE,
        }

        if permission in ownership_required_permissions:
            return user_id is not None and template.created_by == user_id

        # Curators can approve any template
        if (
            permission == DataSourcePermission.APPROVE_TEMPLATE
            and user_role == UserRole.CURATOR
        ):
            return True

        # For read operations, check template visibility
        if permission == DataSourcePermission.READ_TEMPLATE:
            return template.is_available(user_id)

        return True

    def can_create_source(self, user_id: UUID | None, role: str) -> bool:
        """
        Check if a user can create data sources.

        Args:
            user_id: The user ID
            role: The user's role string

        Returns:
            True if the user can create sources, False otherwise
        """
        return self.has_permission(user_id, role, DataSourcePermission.CREATE_SOURCE)

    def can_create_template(self, user_id: UUID | None, role: str) -> bool:
        """
        Check if a user can create templates.

        Args:
            user_id: The user ID
            role: The user's role string

        Returns:
            True if the user can create templates, False otherwise
        """
        return self.has_permission(user_id, role, DataSourcePermission.CREATE_TEMPLATE)

    def can_trigger_ingestion(
        self,
        user_id: UUID | None,
        role: str,
        source: UserDataSource,
    ) -> bool:
        """
        Check if a user can trigger ingestion for a source.

        Args:
            user_id: The user ID
            role: The user's role string
            source: The data source

        Returns:
            True if the user can trigger ingestion, False otherwise
        """
        if not self.has_permission(
            user_id,
            role,
            DataSourcePermission.TRIGGER_INGESTION,
        ):
            return False

        # Users can trigger ingestion for their own sources
        # Admins can trigger for any source
        return self._parse_role(role) == UserRole.ADMIN or (
            user_id is not None and source.owner_id == user_id
        )

    def filter_accessible_sources(
        self,
        user_id: UUID | None,
        role: str,
        sources: list[UserDataSource],
    ) -> list[UserDataSource]:
        """
        Filter a list of sources to only those the user can access.

        Args:
            user_id: The user ID
            role: The user's role string
            sources: List of sources to filter

        Returns:
            Filtered list of accessible sources
        """
        return [
            source
            for source in sources
            if self.can_manage_source(
                user_id,
                role,
                source,
                DataSourcePermission.READ_SOURCE,
            )
        ]

    def filter_accessible_templates(
        self,
        user_id: UUID | None,
        role: str,
        templates: list[SourceTemplate],
    ) -> list[SourceTemplate]:
        """
        Filter a list of templates to only those the user can access.

        Args:
            user_id: The user ID
            role: The user's role string
            templates: List of templates to filter

        Returns:
            Filtered list of accessible templates
        """
        return [
            template
            for template in templates
            if self.can_manage_template(
                user_id,
                role,
                template,
                DataSourcePermission.READ_TEMPLATE,
            )
        ]

    def _parse_role(self, role: str) -> UserRole:
        """
        Parse a role string into a UserRole enum.

        Args:
            role: The role string

        Returns:
            The corresponding UserRole enum value
        """
        role_mapping = {
            "anonymous": UserRole.ANONYMOUS,
            "read": UserRole.READER,
            "write": UserRole.CONTRIBUTOR,
            "admin": UserRole.ADMIN,
        }

        # Try to map the role, default to anonymous if unknown
        return role_mapping.get(role.lower(), UserRole.ANONYMOUS)

    def get_user_permissions(
        self,
        _user_id: UUID | None,
        role: str,
    ) -> set[DataSourcePermission]:
        """
        Get all permissions for a user.

        Args:
            user_id: The user ID
            role: The user's role string

        Returns:
            Set of permissions the user has
        """
        user_role = self._parse_role(role)
        return self._role_permissions.get(user_role, set[DataSourcePermission]())
