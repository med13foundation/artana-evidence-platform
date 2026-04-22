"""Service-local graph access and tenancy semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GraphAccessRole(str, Enum):
    """Ordered access roles understood by the graph service."""

    VIEWER = "viewer"
    RESEARCHER = "researcher"
    CURATOR = "curator"
    ADMIN = "admin"
    OWNER = "owner"


_GRAPH_ACCESS_ROLE_HIERARCHY = {
    GraphAccessRole.VIEWER: 1,
    GraphAccessRole.RESEARCHER: 2,
    GraphAccessRole.CURATOR: 3,
    GraphAccessRole.ADMIN: 4,
    GraphAccessRole.OWNER: 5,
}


@dataclass(frozen=True, slots=True)
class GraphPrincipal:
    """Authenticated principal evaluated by graph-service access policies."""

    subject_id: str
    is_platform_admin: bool = False


@dataclass(frozen=True, slots=True)
class GraphAccessDecision:
    """Outcome of a graph-service access evaluation."""

    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class GraphTenant:
    """Tenant or space scope evaluated by graph-service policies."""

    tenant_id: str


@dataclass(frozen=True, slots=True)
class GraphTenantMembership:
    """One principal's membership context inside a tenant or space scope."""

    tenant: GraphTenant
    membership_role: GraphAccessRole | None = None


@dataclass(frozen=True, slots=True)
class GraphRlsSessionContext:
    """Portable RLS session settings derived from graph-service auth decisions."""

    current_user_id: str | None
    has_phi_access: bool = False
    is_admin: bool = False
    bypass_rls: bool = False


def evaluate_graph_admin_access(principal: GraphPrincipal) -> GraphAccessDecision:
    """Evaluate whether one principal can access graph control-plane operations."""
    if principal.is_platform_admin:
        return GraphAccessDecision(allowed=True, reason="platform_admin")
    return GraphAccessDecision(allowed=False, reason="platform_admin_required")


def evaluate_graph_space_access(
    *,
    principal: GraphPrincipal,
    membership_role: GraphAccessRole | None,
    required_role: GraphAccessRole = GraphAccessRole.VIEWER,
) -> GraphAccessDecision:
    """Evaluate graph-space access for one principal and required role."""
    admin_decision = evaluate_graph_admin_access(principal)
    if admin_decision.allowed:
        return admin_decision

    if membership_role is None:
        return GraphAccessDecision(allowed=False, reason="not_a_member")

    if (
        _GRAPH_ACCESS_ROLE_HIERARCHY[membership_role]
        < _GRAPH_ACCESS_ROLE_HIERARCHY[required_role]
    ):
        return GraphAccessDecision(allowed=False, reason="insufficient_role")

    return GraphAccessDecision(allowed=True, reason="role_satisfied")


def evaluate_graph_tenant_access(
    *,
    principal: GraphPrincipal,
    tenant_membership: GraphTenantMembership,
    required_role: GraphAccessRole = GraphAccessRole.VIEWER,
) -> GraphAccessDecision:
    """Evaluate access for one principal inside one tenant or space scope."""
    return evaluate_graph_space_access(
        principal=principal,
        membership_role=tenant_membership.membership_role,
        required_role=required_role,
    )


def create_graph_rls_session_context(
    *,
    principal: GraphPrincipal,
    bypass_rls: bool = False,
) -> GraphRlsSessionContext:
    """Build the RLS session settings implied by one authenticated principal."""
    return GraphRlsSessionContext(
        current_user_id=principal.subject_id,
        has_phi_access=principal.is_platform_admin,
        is_admin=principal.is_platform_admin,
        bypass_rls=bypass_rls,
    )


__all__ = [
    "GraphAccessDecision",
    "GraphAccessRole",
    "GraphPrincipal",
    "GraphRlsSessionContext",
    "GraphTenant",
    "GraphTenantMembership",
    "create_graph_rls_session_context",
    "evaluate_graph_admin_access",
    "evaluate_graph_space_access",
    "evaluate_graph_tenant_access",
]
