// Navigation configuration for the Rail Navigation System
// Implements the navigation structure from docs/system_map.md

import {
  LayoutDashboard,
  FolderKanban,
  CloudDownload,
  ListChecks,
  Network,
  BookOpen,
  BarChart3,
  Users,
  Settings,
  Plus,
  ArrowLeft,
  type LucideIcon,
} from "lucide-react"
import { KnowledgeGraphIcon } from "@/components/icons/KnowledgeGraphIcon"
import type {
  NavItem,
  NavGroup,
  SidebarConfig,
  SidebarHeaderConfig,
  SidebarFooterConfig,
  SidebarUserInfo,
  BreadcrumbItem,
  DASHBOARD_ROUTES,
  SPACE_ROUTES,
  buildSpaceRoute,
} from "@/types/navigation"
import { UserRole } from "@/types/auth"
import type { ResearchSpace } from "@/types/research-space"
import { MembershipRole } from "@/types/research-space"
import { BRAND_LOGO_ALT } from "@/lib/branding"

// ============================================================================
// Navigation Item Builders
// ============================================================================

/**
 * Build dashboard-level navigation items
 * Shown when user is at /dashboard (no space context)
 */
export function buildDashboardNavItems(
  pathname: string,
  isAdmin: boolean
): NavGroup[] {
  const groups: NavGroup[] = [
    {
      label: "Navigation",
      items: [
        {
          id: "dashboard",
          title: "Dashboard",
          url: "/dashboard",
          icon: LayoutDashboard,
          isActive: pathname === "/dashboard",
        },
      ],
    },
  ]

  // Admin-only section
  if (isAdmin) {
    groups.push({
      label: "Administration",
      items: [
        {
          id: "admin-dictionary",
          title: "Dictionary",
          url: "/admin/dictionary",
          icon: BookOpen,
          isActive: pathname.startsWith("/admin/dictionary"),
          allowedRoles: [UserRole.ADMIN],
        },
        {
          id: "admin-audit",
          title: "Audit Logs",
          url: "/admin/audit",
          icon: ListChecks,
          isActive: pathname.startsWith("/admin/audit"),
          allowedRoles: [UserRole.ADMIN],
        },
        {
          id: "admin-artana-runs",
          title: "Artana Runs",
          url: "/admin/artana/runs",
          icon: BarChart3,
          isActive: pathname.startsWith("/admin/artana/runs"),
          allowedRoles: [UserRole.ADMIN],
        },
        {
          id: "admin-phi-access",
          title: "PHI Access",
          url: "/admin/phi-access",
          icon: Users,
          isActive: pathname.startsWith("/admin/phi-access"),
          allowedRoles: [UserRole.ADMIN],
        },
        {
          id: "admin-settings",
          title: "System Settings",
          url: "/system-settings",
          icon: Settings,
          isActive: pathname.startsWith("/system-settings"),
          allowedRoles: [UserRole.ADMIN],
        },
      ],
      allowedRoles: [UserRole.ADMIN],
    })
  }

  return groups
}

/**
 * Build space-scoped navigation items
 * Shown when user is within a research space (/spaces/:spaceId/*)
 */
export function buildSpaceNavItems(
  spaceId: string,
  pathname: string,
  userSpaceRole?: MembershipRole
): NavGroup[] {
  const isSpaceAdmin =
    userSpaceRole === MembershipRole.OWNER || userSpaceRole === MembershipRole.ADMIN

  const mainGroup: NavGroup = {
    label: "Space",
    items: [
      {
        id: "space-overview",
        title: "Overview",
        url: `/spaces/${spaceId}`,
        icon: LayoutDashboard,
        isActive: pathname === `/spaces/${spaceId}`,
      },
      {
        id: "data-sources",
        title: "Data Sources",
        url: `/spaces/${spaceId}/data-sources`,
        icon: CloudDownload,
        isActive: pathname.startsWith(`/spaces/${spaceId}/data-sources`),
      },
      {
        id: "data-curation",
        title: "Data Curation",
        url: `/spaces/${spaceId}/curation`,
        icon: ListChecks,
        isActive: pathname.startsWith(`/spaces/${spaceId}/curation`),
      },
      {
        id: "knowledge-graph",
        title: "Knowledge Graph",
        url: `/spaces/${spaceId}/knowledge-graph`,
        icon: KnowledgeGraphIcon,
        isActive: pathname.startsWith(`/spaces/${spaceId}/knowledge-graph`),
      },
      {
        id: "concepts",
        title: "Concepts",
        url: `/spaces/${spaceId}/concepts`,
        icon: Network,
        isActive: pathname.startsWith(`/spaces/${spaceId}/concepts`),
      },
      {
        id: "observations",
        title: "Observations",
        url: `/spaces/${spaceId}/observations`,
        icon: BarChart3,
        isActive: pathname.startsWith(`/spaces/${spaceId}/observations`),
      },
    ],
  }

  const groups: NavGroup[] = [mainGroup]

  // Space admin items
  if (isSpaceAdmin) {
    groups.push({
      label: "Space Admin",
      items: [
        {
          id: "members",
          title: "Members",
          url: `/spaces/${spaceId}/members`,
          icon: Users,
          isActive: pathname.startsWith(`/spaces/${spaceId}/members`),
        },
        {
          id: "space-settings",
          title: "Settings",
          url: `/spaces/${spaceId}/settings`,
          icon: Settings,
          isActive: pathname.startsWith(`/spaces/${spaceId}/settings`),
        },
      ],
    })
  }

  return groups
}

/**
 * Build secondary navigation items (shown at bottom of sidebar)
 */
export function buildSecondaryNavItems(
  pathname: string,
  context: "dashboard" | "space",
  spaceId?: string
): NavItem[] {
  const items: NavItem[] = []

  // "Back to Dashboard" link when in space context
  if (context === "space") {
    items.push({
      id: "back-to-dashboard",
      title: "Back to Dashboard",
      url: "/dashboard",
      icon: ArrowLeft,
      isActive: false,
    })
  }

  return items
}

// ============================================================================
// Sidebar Configuration Builders
// ============================================================================

/**
 * Build complete sidebar configuration for dashboard view
 */
export function buildDashboardSidebarConfig(
  user: SidebarUserInfo,
  spaces: ResearchSpace[],
  pathname: string
): SidebarConfig {
  const isAdmin = user.role === UserRole.ADMIN

  return {
    context: "dashboard",
    header: {
      logo: {
        src: "/logo.svg",
        alt: BRAND_LOGO_ALT,
        width: 32,
        height: 32,
      },
      showWorkspaceDropdown: true,
      currentSpace: null,
      availableSpaces: spaces,
    },
    mainNav: buildDashboardNavItems(pathname, isAdmin),
    secondaryNav: buildSecondaryNavItems(pathname, "dashboard"),
    footer: {
      user,
    },
  }
}

/**
 * Build complete sidebar configuration for space-scoped view
 */
export function buildSpaceSidebarConfig(
  user: SidebarUserInfo,
  currentSpace: ResearchSpace,
  allSpaces: ResearchSpace[],
  pathname: string,
  userSpaceRole?: MembershipRole
): SidebarConfig {
  return {
    context: "space",
    header: {
      logo: {
        src: "/logo.svg",
        alt: BRAND_LOGO_ALT,
        width: 32,
        height: 32,
      },
      showWorkspaceDropdown: true,
      currentSpace,
      availableSpaces: allSpaces,
    },
    mainNav: buildSpaceNavItems(currentSpace.id, pathname, userSpaceRole),
    secondaryNav: buildSecondaryNavItems(pathname, "space", currentSpace.id),
    footer: {
      user,
    },
  }
}

// ============================================================================
// Breadcrumb Builders
// ============================================================================

/**
 * Build breadcrumb items from current path
 */
export function buildBreadcrumbs(
  pathname: string,
  currentSpace?: ResearchSpace | null
): BreadcrumbItem[] {
  const segments = pathname.split("/").filter(Boolean)
  const items: BreadcrumbItem[] = []

  // Dashboard routes
  if (pathname === "/dashboard") {
    items.push({ label: "Dashboard", isCurrent: true })
    return items
  }

  // Space-scoped routes
  if (segments[0] === "spaces" && segments.length >= 2) {
    const spaceId = segments[1]
    const spaceName = currentSpace?.name || "Research Space"

    items.push({ label: "Dashboard", href: "/dashboard" })
    items.push({
      label: spaceName,
      href: `/spaces/${spaceId}`,
      isCurrent: segments.length === 2,
    })

    // Add sub-page breadcrumbs
    if (segments.length > 2) {
      const subPage = segments[2]
      const subPageLabels: Record<string, string> = {
        "data-sources": "Data Sources",
        curation: "Data Curation",
        "knowledge-graph": "Knowledge Graph",
        concepts: "Concepts",
        members: "Members",
        settings: "Settings",
      }

      items.push({
        label: subPageLabels[subPage] || subPage,
        isCurrent: segments.length === 3,
      })

      // Handle deeper routes (e.g., /data-sources/:id)
      if (segments.length > 3) {
        items.push({
          label: segments[3],
          isCurrent: true,
        })
      }
    }

    return items
  }

  // System settings route
  if (pathname.startsWith("/system-settings")) {
    items.push({ label: "Dashboard", href: "/dashboard" })
    items.push({ label: "System Settings", isCurrent: true })
    return items
  }

  // Admin routes (legacy)
  if (pathname.startsWith("/admin")) {
    items.push({ label: "Dashboard", href: "/dashboard" })
    items.push({ label: "Admin", href: "/admin" })

    if (segments.length > 1) {
      const adminPage = segments[1]
      const adminLabels: Record<string, string> = {
        settings: "System Settings",
        users: "User Management",
        "data-sources": "Data Sources",
        dictionary: "Dictionary",
        audit: "Audit Logs",
        "phi-access": "PHI Access",
      }
      items.push({
        label: adminLabels[adminPage] || adminPage,
        isCurrent: segments.length === 2,
      })

      // Handle deeper routes like /admin/data-sources/templates
      if (segments.length > 2) {
        const subPage = segments[2]
        const subPageLabels: Record<string, string> = {
          templates: "Templates",
        }
        items.push({
          label: subPageLabels[subPage] || subPage,
          isCurrent: true,
        })
      }
    }

    return items
  }

  // Default: parse path segments
  segments.forEach((segment, index) => {
    items.push({
      label: segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, " "),
      href: index < segments.length - 1 ? `/${segments.slice(0, index + 1).join("/")}` : undefined,
      isCurrent: index === segments.length - 1,
    })
  })

  return items
}

// ============================================================================
// Quick Actions for Sidebar
// ============================================================================

export interface QuickAction {
  id: string
  label: string
  icon: LucideIcon
  href?: string
  action?: () => void
  variant?: "default" | "primary" | "secondary"
}

/**
 * Build quick action buttons for sidebar
 */
export function buildQuickActions(
  context: "dashboard" | "space",
  spaceId?: string
): QuickAction[] {
  if (context === "dashboard") {
    return [
      {
        id: "create-space",
        label: "New Space",
        icon: Plus,
        href: "/spaces/new",
        variant: "primary",
      },
    ]
  }

  if (context === "space" && spaceId) {
    return [
      {
        id: "add-data-source",
        label: "Add Source",
        icon: Plus,
        href: `/spaces/${spaceId}/data-sources/new`,
        variant: "primary",
      },
    ]
  }

  return []
}
