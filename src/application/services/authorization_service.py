"""
Authorization service for Artana Resource Library.

Handles permission checking, role-based access control, and resource authorization.
"""

from uuid import UUID

from src.domain.entities.user import User, UserRole
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.permission import (
    Permission,
    PermissionChecker,
    RolePermissions,
)
from src.type_definitions.authorization import (
    AccessCheckResponse,
    RoleCapabilitiesResponse,
    RolePermissionsSummary,
    SystemPermissionsSummary,
)


class AuthorizationError(Exception):
    """Base exception for authorization errors."""


class InsufficientPermissionsError(AuthorizationError):
    """Raised when user lacks required permissions."""


class ResourceNotFoundError(AuthorizationError):
    """Raised when requested resource doesn't exist."""


class AuthorizationService:
    """
    Service for handling authorization and permission checking.

    Implements role-based access control with fine-grained permissions.
    """

    def __init__(self, user_repository: UserRepository):
        """
        Initialize authorization service.

        Args:
            user_repository: User data access
        """
        self.user_repository = user_repository

    async def has_permission(self, user_id: UUID, permission: Permission) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User's unique identifier
            permission: Permission to check

        Returns:
            True if user has permission, False otherwise
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return False

        user_permissions = RolePermissions.get_permissions_for_role(user.role)
        return PermissionChecker.has_permission(user_permissions, permission)

    async def has_any_permission(
        self,
        user_id: UUID,
        permissions: list[Permission],
    ) -> bool:
        """
        Check if user has any of the required permissions.

        Args:
            user_id: User's unique identifier
            permissions: List of permissions to check

        Returns:
            True if user has at least one permission, False otherwise
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return False

        user_permissions = RolePermissions.get_permissions_for_role(user.role)
        return PermissionChecker.has_any_permission(user_permissions, permissions)

    async def has_all_permissions(
        self,
        user_id: UUID,
        permissions: list[Permission],
    ) -> bool:
        """
        Check if user has all required permissions.

        Args:
            user_id: User's unique identifier
            permissions: List of permissions to check

        Returns:
            True if user has all permissions, False otherwise
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return False

        user_permissions = RolePermissions.get_permissions_for_role(user.role)
        return PermissionChecker.has_all_permissions(user_permissions, permissions)

    async def get_user_permissions(self, user_id: UUID) -> list[Permission]:
        """
        Get all permissions for a user.

        Args:
            user_id: User's unique identifier

        Returns:
            List of user's permissions
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return []

        return RolePermissions.get_permissions_for_role(user.role)

    async def get_missing_permissions(
        self,
        user_id: UUID,
        required_permissions: list[Permission],
    ) -> list[Permission]:
        """
        Get permissions the user is missing.

        Args:
            user_id: User's unique identifier
            required_permissions: Required permissions

        Returns:
            List of missing permissions
        """
        user_permissions = await self.get_user_permissions(user_id)
        return PermissionChecker.get_missing_permissions(
            user_permissions,
            required_permissions,
        )

    async def require_permission(self, user_id: UUID, permission: Permission) -> None:
        """
        Require user to have a specific permission.

        Args:
            user_id: User's unique identifier
            permission: Required permission

        Raises:
            InsufficientPermissionsError: If user lacks permission
        """
        if not await self.has_permission(user_id, permission):
            msg = f"User lacks required permission: {permission.value}"
            raise InsufficientPermissionsError(msg)

    async def require_any_permission(
        self,
        user_id: UUID,
        permissions: list[Permission],
    ) -> None:
        """
        Require user to have any of the specified permissions.

        Args:
            user_id: User's unique identifier
            permissions: List of acceptable permissions

        Raises:
            InsufficientPermissionsError: If user lacks all permissions
        """
        if not await self.has_any_permission(user_id, permissions):
            perm_names = [p.value for p in permissions]
            msg = f"User lacks any of required permissions: {perm_names}"
            raise InsufficientPermissionsError(msg)

    async def require_all_permissions(
        self,
        user_id: UUID,
        permissions: list[Permission],
    ) -> None:
        """
        Require user to have all specified permissions.

        Args:
            user_id: User's unique identifier
            permissions: List of required permissions

        Raises:
            InsufficientPermissionsError: If user lacks any permission
        """
        if not await self.has_all_permissions(user_id, permissions):
            missing = await self.get_missing_permissions(user_id, permissions)
            missing_names = [p.value for p in missing]
            msg = f"User lacks required permissions: {missing_names}"
            raise InsufficientPermissionsError(msg)

    async def check_resource_access(
        self,
        user: User,
        resource_type: str,
        _resource_id: UUID | None,
        action: str,
    ) -> bool:
        """
        Check if user can perform action on specific resource.

        Args:
            user: User entity
            resource_type: Type of resource (e.g., "user", "datasource")
            resource_id: Specific resource ID (optional)
            action: Action to perform (e.g., "read", "update", "delete")

        Returns:
            True if access allowed, False otherwise
        """
        # Map resource+action to permission
        permission_map = {
            ("user", "create"): Permission.USER_CREATE,
            ("user", "read"): Permission.USER_READ,
            ("user", "update"): Permission.USER_UPDATE,
            ("user", "delete"): Permission.USER_DELETE,
            ("datasource", "create"): Permission.DATASOURCE_CREATE,
            ("datasource", "read"): Permission.DATASOURCE_READ,
            ("datasource", "update"): Permission.DATASOURCE_UPDATE,
            ("datasource", "delete"): Permission.DATASOURCE_DELETE,
            ("curation", "review"): Permission.CURATION_REVIEW,
            ("curation", "approve"): Permission.CURATION_APPROVE,
            ("curation", "reject"): Permission.CURATION_REJECT,
            ("audit", "read"): Permission.AUDIT_READ,
        }

        permission_key = (resource_type, action)
        required_permission = permission_map.get(permission_key)

        if not required_permission:
            # Unknown resource/action combination
            return False

        return await self.has_permission(user.id, required_permission)

    async def check_user_management_access(
        self,
        manager_user: User,
        target_user: User | None = None,
    ) -> bool:
        """
        Check if user can manage other users.

        Args:
            manager_user: User attempting to manage
            target_user: User being managed (optional)

        Returns:
            True if management is allowed
        """
        # Admins can manage anyone
        if manager_user.role == UserRole.ADMIN:
            return True

        # Non-admins cannot manage users
        if not target_user:
            return False

        # Users cannot manage users with higher or equal roles
        return RolePermissions.can_role_manage_role(manager_user.role, target_user.role)

    async def get_accessible_resources(
        self,
        user_id: UUID,
        resource_type: str,
        action: str,
    ) -> AccessCheckResponse:
        """
        Get information about what resources user can access.

        Args:
            user_id: User's unique identifier
            resource_type: Type of resource
            action: Action to check

        Returns:
            Access information dictionary
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return {"has_access": False, "reason": "User not found"}

        has_access = await self.check_resource_access(
            user,
            resource_type,
            None,  # General access check
            action,
        )

        permissions = await self.get_user_permissions(user_id)

        return {
            "has_access": has_access,
            "user_permissions": [p.value for p in permissions],
            "resource_type": resource_type,
            "action": action,
            "role_based_access": True,  # All access is currently role-based
        }

    async def validate_role_hierarchy(
        self,
        requesting_user: User,
        target_user: User | None = None,
    ) -> bool:
        """
        Validate that requesting user can perform actions on target user.

        This is a legacy method for backward compatibility.
        Use check_user_management_access instead.

        Args:
            requesting_user: User making the request
            target_user: Target user (optional)

        Returns:
            True if action is allowed
        """
        return await self.check_user_management_access(requesting_user, target_user)

    # Administrative methods

    async def get_role_capabilities(self, role: UserRole) -> RoleCapabilitiesResponse:
        """
        Get detailed information about a role's capabilities.

        Args:
            role: Role to analyze

        Returns:
            Dictionary with role capabilities
        """
        permissions = RolePermissions.get_permissions_for_role(role)
        hierarchy_level = RolePermissions.get_role_hierarchy()[role]

        # Get users with this role
        user_count = await self.user_repository.count_users(role=role.value)

        return {
            "role": role.value,
            "hierarchy_level": hierarchy_level,
            "permissions": [p.value for p in permissions],
            "permission_count": len(permissions),
            "user_count": user_count,
            "can_manage_higher_roles": role == UserRole.ADMIN,
            "can_manage_equal_roles": False,  # Current policy
        }

    async def get_system_permissions_summary(self) -> SystemPermissionsSummary:
        """
        Get summary of all permissions in the system.

        Returns:
            System permissions overview
        """
        all_permissions = Permission.__members__.values()
        roles = [r.value for r in UserRole]

        role_summaries: dict[str, RolePermissionsSummary] = {}
        for role in UserRole:
            permissions = RolePermissions.get_permissions_for_role(role)
            role_summaries[role.value] = {
                "permission_count": len(permissions),
                "permissions": [p.value for p in permissions],
            }

        return {
            "total_permissions": len(all_permissions),
            "total_roles": len(roles),
            "roles": role_summaries,
            "permissions_list": [p.value for p in all_permissions],
            "role_hierarchy": {
                r.value: RolePermissions.get_role_hierarchy()[r] for r in UserRole
            },
        }
