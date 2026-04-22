// Navigation types for the Rail Navigation System
// Following strict type safety - no `any` types per project guidelines

import type { LucideIcon } from "lucide-react"
import type { UserRole } from "./auth"
import type { ResearchSpace } from "./research-space"

// ============================================================================
// Core Navigation Types
// ============================================================================

/**
 * Represents the current sidebar state
 */
export type SidebarState = "expanded" | "collapsed"

/**
 * Sidebar view context - determines which navigation items are shown
 * - dashboard: Top-level view showing research spaces list
 * - space: Space-scoped view showing space-specific navigation
 */
export type SidebarViewContext = "dashboard" | "space"

/**
 * Individual navigation item configuration
 */
export interface NavItem {
  /** Unique identifier for the navigation item */
  id: string
  /** Display title for the navigation item */
  title: string
  /** URL path to navigate to */
  url: string
  /** Lucide icon component to display */
  icon: LucideIcon
  /** Whether this item is currently active */
  isActive?: boolean
  /** Roles allowed to see this item (empty = all roles) */
  allowedRoles?: UserRole[]
  /** Badge text to display (e.g., count) */
  badge?: string | number
  /** Whether to show a notification dot */
  hasNotification?: boolean
  /** Nested sub-items for collapsible sections */
  items?: NavSubItem[]
}

/**
 * Nested navigation sub-item configuration
 */
export interface NavSubItem {
  /** Display title for the sub-item */
  title: string
  /** URL path to navigate to */
  url: string
  /** Whether this sub-item is currently active */
  isActive?: boolean
  /** Roles allowed to see this item (empty = all roles) */
  allowedRoles?: UserRole[]
}

/**
 * Navigation group configuration
 */
export interface NavGroup {
  /** Group label (optional, can be hidden) */
  label?: string
  /** Navigation items in this group */
  items: NavItem[]
  /** Roles allowed to see this group */
  allowedRoles?: UserRole[]
}

// ============================================================================
// Sidebar Configuration Types
// ============================================================================

/**
 * Complete sidebar configuration for a given context
 */
export interface SidebarConfig {
  /** The current view context */
  context: SidebarViewContext
  /** Header configuration */
  header: SidebarHeaderConfig
  /** Main navigation groups */
  mainNav: NavGroup[]
  /** Secondary/utility navigation */
  secondaryNav?: NavItem[]
  /** Footer configuration */
  footer?: SidebarFooterConfig
}

/**
 * Sidebar header configuration
 */
export interface SidebarHeaderConfig {
  /** Logo or icon to display */
  logo: {
    src: string
    alt: string
    /** Width in pixels when sidebar is expanded */
    width: number
    /** Height in pixels */
    height: number
  }
  /** Whether to show workspace dropdown */
  showWorkspaceDropdown: boolean
  /** Current workspace/space info (if in space context) */
  currentSpace?: ResearchSpace | null
  /** Available spaces for the dropdown */
  availableSpaces?: ResearchSpace[]
}

/**
 * Sidebar footer configuration
 */
export interface SidebarFooterConfig {
  /** User information for the user menu */
  user: SidebarUserInfo
  /** Additional footer items */
  items?: NavItem[]
}

/**
 * User information displayed in sidebar
 */
export interface SidebarUserInfo {
  id: string
  name: string
  email: string
  avatar?: string
  role: UserRole
}

// ============================================================================
// Breadcrumb Types
// ============================================================================

/**
 * Individual breadcrumb item
 */
export interface BreadcrumbItem {
  /** Display label */
  label: string
  /** URL to navigate to (undefined = current page) */
  href?: string
  /** Whether this is the current page */
  isCurrent?: boolean
}

/**
 * Breadcrumb configuration for a page
 */
export interface BreadcrumbConfig {
  /** List of breadcrumb items */
  items: BreadcrumbItem[]
  /** Whether to show home icon at start */
  showHome?: boolean
}

// ============================================================================
// Command Palette Types (Phase 4)
// ============================================================================

/**
 * Command palette search result item
 */
export interface CommandItem {
  /** Unique identifier */
  id: string
  /** Display title */
  title: string
  /** Optional description */
  description?: string
  /** Category for grouping */
  category: CommandCategory
  /** Icon to display */
  icon?: LucideIcon
  /** URL to navigate to */
  url?: string
  /** Action to execute (if not navigating) */
  action?: () => void
  /** Keyboard shortcut (e.g., "⌘K") */
  shortcut?: string
  /** Roles allowed to see this command */
  allowedRoles?: UserRole[]
}

/**
 * Categories for command palette results
 */
export type CommandCategory =
  | "navigation"
  | "spaces"
  | "data-sources"
  | "entities"
  | "settings"
  | "actions"

/**
 * Command palette group
 */
export interface CommandGroup {
  /** Group heading */
  heading: string
  /** Items in this group */
  items: CommandItem[]
}

// ============================================================================
// Route Constants
// ============================================================================

/**
 * Dashboard-level routes (no space context)
 */
export const DASHBOARD_ROUTES = {
  HOME: "/dashboard",
  SPACES: "/dashboard/spaces",
  CREATE_SPACE: "/dashboard/spaces/new",
  ADMIN_SETTINGS: "/admin/settings",
  PROFILE: "/profile",
} as const

/**
 * Space-scoped routes (with :spaceId parameter)
 * Use buildSpaceRoute() to construct actual URLs
 */
export const SPACE_ROUTES = {
  OVERVIEW: "/spaces/:spaceId",
  DATA_SOURCES: "/spaces/:spaceId/data-sources",
  DATA_CURATION: "/spaces/:spaceId/curation",
  KNOWLEDGE_GRAPH: "/spaces/:spaceId/graph",
  CONCEPTS: "/spaces/:spaceId/concepts",
  MEMBERS: "/spaces/:spaceId/members",
  SETTINGS: "/spaces/:spaceId/settings",
} as const

// ============================================================================
// Type Guards
// ============================================================================

/**
 * Type guard to check if user has required role for navigation item
 */
export function hasRequiredRole(
  userRole: UserRole,
  allowedRoles?: UserRole[]
): boolean {
  if (!allowedRoles || allowedRoles.length === 0) {
    return true
  }
  return allowedRoles.includes(userRole)
}

/**
 * Type guard to check if navigation item has sub-items
 */
export function hasSubItems(item: NavItem): item is NavItem & { items: NavSubItem[] } {
  return Boolean(item.items && item.items.length > 0)
}

// ============================================================================
// Route Builders
// ============================================================================

/**
 * Build a space-scoped route URL
 */
export function buildSpaceRoute(
  route: (typeof SPACE_ROUTES)[keyof typeof SPACE_ROUTES],
  spaceId: string
): string {
  return route.replace(":spaceId", spaceId)
}

/**
 * Extract space ID from current path
 */
export function extractSpaceIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/spaces\/([^/]+)/)
  return match ? match[1] : null
}

/**
 * Determine sidebar context from current path
 */
export function getSidebarContextFromPath(pathname: string): SidebarViewContext {
  if (pathname.startsWith("/spaces/") && extractSpaceIdFromPath(pathname)) {
    return "space"
  }
  return "dashboard"
}
