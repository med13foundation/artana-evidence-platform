"""
Permission value objects for Artana Resource Library authorization system.

Defines permissions, roles, and access control rules using domain-driven design.
"""

from enum import Enum

from src.domain.entities.user import UserRole


class Permission(str, Enum):
    """
    System permissions enumeration.

    Each permission follows resource:action pattern for clarity.
    """

    # User management permissions
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # Data source permissions
    DATASOURCE_CREATE = "datasource:create"
    DATASOURCE_READ = "datasource:read"
    DATASOURCE_UPDATE = "datasource:update"
    DATASOURCE_DELETE = "datasource:delete"

    # Curation permissions
    CURATION_REVIEW = "curation:review"
    CURATION_APPROVE = "curation:approve"
    CURATION_REJECT = "curation:reject"

    # System administration permissions
    SYSTEM_ADMIN = "system:admin"
    AUDIT_READ = "audit:read"


class RolePermissions:
    """
    Maps user roles to permissions following principle of least privilege.

    This is the single source of truth for role-based access control.
    """

    @staticmethod
    def get_permissions_for_role(role: UserRole) -> list[Permission]:
        """
        Get all permissions for a given role.

        Args:
            role: User role

        Returns:
            List of permissions assigned to the role
        """
        role_permissions: dict[UserRole, list[Permission]] = {
            UserRole.ADMIN: [
                # User management
                Permission.USER_CREATE,
                Permission.USER_READ,
                Permission.USER_UPDATE,
                Permission.USER_DELETE,
                # Data source management
                Permission.DATASOURCE_CREATE,
                Permission.DATASOURCE_READ,
                Permission.DATASOURCE_UPDATE,
                Permission.DATASOURCE_DELETE,
                # Curation
                Permission.CURATION_REVIEW,
                Permission.CURATION_APPROVE,
                Permission.CURATION_REJECT,
                # System
                Permission.SYSTEM_ADMIN,
                Permission.AUDIT_READ,
            ],
            UserRole.CURATOR: [
                # Data source access (same as researcher plus update)
                Permission.DATASOURCE_READ,
                Permission.DATASOURCE_CREATE,
                Permission.DATASOURCE_UPDATE,
                # Curation workflow
                Permission.CURATION_REVIEW,
                Permission.CURATION_APPROVE,
                Permission.CURATION_REJECT,
            ],
            UserRole.RESEARCHER: [
                # Basic data source access
                Permission.DATASOURCE_READ,
                Permission.DATASOURCE_CREATE,
            ],
            UserRole.VIEWER: [
                # Read-only access
                Permission.DATASOURCE_READ,
            ],
        }

        return role_permissions.get(role, [])

    @staticmethod
    def get_role_hierarchy() -> dict[UserRole, int]:
        """
        Get role hierarchy levels for precedence checking.

        Higher numbers indicate higher privileges.
        """
        return {
            UserRole.VIEWER: 1,
            UserRole.RESEARCHER: 2,
            UserRole.CURATOR: 3,
            UserRole.ADMIN: 4,
        }

    @staticmethod
    def can_role_manage_role(manager_role: UserRole, target_role: UserRole) -> bool:
        """
        Check if a role can manage users of another role.

        Only curator and admin roles can manage users.
        Researchers and viewers cannot manage other users.

        Args:
            manager_role: Role attempting to manage
            target_role: Role being managed

        Returns:
            True if management is allowed
        """
        # Only curator and admin can manage users
        if manager_role not in [UserRole.CURATOR, UserRole.ADMIN]:
            return False

        # Cannot manage users with higher or equal privilege levels
        hierarchy = RolePermissions.get_role_hierarchy()
        return hierarchy[manager_role] > hierarchy[target_role]

    @staticmethod
    def get_all_permissions() -> list[Permission]:
        """Get all available permissions in the system."""
        return list(Permission)

    @staticmethod
    def validate_permission_hierarchy() -> bool:
        """
        Validate that permission assignments follow security principles.

        Returns:
            True if validation passes
        """
        # Ensure admin has all permissions
        admin_permissions = set(
            RolePermissions.get_permissions_for_role(UserRole.ADMIN),
        )
        all_permissions = set(RolePermissions.get_all_permissions())

        if admin_permissions != all_permissions:
            missing = all_permissions - admin_permissions
            message = f"Admin role missing permissions: {missing}"
            raise ValueError(message)

        # Ensure role hierarchy is maintained
        roles_by_level = sorted(
            [
                (level, role)
                for role, level in RolePermissions.get_role_hierarchy().items()
            ],
            key=lambda x: x[0],
        )

        for i, (_level, role) in enumerate(roles_by_level[:-1]):
            current_permissions = set(RolePermissions.get_permissions_for_role(role))
            next_role = roles_by_level[i + 1][1]
            next_permissions = set(RolePermissions.get_permissions_for_role(next_role))

            # Higher roles should have at least as many permissions
            if not next_permissions.issuperset(current_permissions):
                missing = current_permissions - next_permissions
                message = f"Role {next_role} missing permissions from {role}: {missing}"
                raise ValueError(message)

        return True


class PermissionChecker:
    """
    Utility class for permission checking operations.
    """

    @staticmethod
    def has_permission(
        user_permissions: list[Permission],
        required_permission: Permission,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_permissions: List of user's permissions
            required_permission: Required permission

        Returns:
            True if user has the permission
        """
        return required_permission in user_permissions

    @staticmethod
    def has_any_permission(
        user_permissions: list[Permission],
        required_permissions: list[Permission],
    ) -> bool:
        """
        Check if user has any of the required permissions.

        Args:
            user_permissions: List of user's permissions
            required_permissions: Required permissions

        Returns:
            True if user has at least one required permission
        """
        return any(perm in user_permissions for perm in required_permissions)

    @staticmethod
    def has_all_permissions(
        user_permissions: list[Permission],
        required_permissions: list[Permission],
    ) -> bool:
        """
        Check if user has all required permissions.

        Args:
            user_permissions: List of user's permissions
            required_permissions: Required permissions

        Returns:
            True if user has all required permissions
        """
        return all(perm in user_permissions for perm in required_permissions)

    @staticmethod
    def get_missing_permissions(
        user_permissions: list[Permission],
        required_permissions: list[Permission],
    ) -> list[Permission]:
        """
        Get permissions the user is missing.

        Args:
            user_permissions: List of user's permissions
            required_permissions: Required permissions

        Returns:
            List of missing permissions
        """
        user_perm_set = set(user_permissions)
        return [perm for perm in required_permissions if perm not in user_perm_set]
