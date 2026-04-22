"""
Authorization-related typed contracts.
"""

from __future__ import annotations

from typing import TypedDict


class AccessCheckResponse(TypedDict, total=False):
    """Structured response for resource access checks."""

    has_access: bool
    user_permissions: list[str]
    resource_type: str
    action: str
    role_based_access: bool
    reason: str


class RoleCapabilitiesResponse(TypedDict):
    """Structured response describing a role's capabilities."""

    role: str
    hierarchy_level: int
    permissions: list[str]
    permission_count: int
    user_count: int
    can_manage_higher_roles: bool
    can_manage_equal_roles: bool


class RolePermissionsSummary(TypedDict):
    """Summary of permissions associated with a role."""

    permission_count: int
    permissions: list[str]


class SystemPermissionsSummary(TypedDict):
    """System-wide permission summary payload."""

    total_permissions: int
    total_roles: int
    roles: dict[str, RolePermissionsSummary]
    permissions_list: list[str]
    role_hierarchy: dict[str, int]


__all__ = [
    "AccessCheckResponse",
    "RoleCapabilitiesResponse",
    "RolePermissionsSummary",
    "SystemPermissionsSummary",
]
