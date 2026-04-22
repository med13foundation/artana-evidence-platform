"use client"

import * as React from "react"
import { usePathname } from "next/navigation"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
  SidebarSeparator,
} from "@/components/ui/sidebar"
import { WorkspaceDropdown } from "./WorkspaceDropdown"
import { NavMain } from "./NavMain"
import { NavSpaces } from "./NavSpaces"
import { NavSecondary } from "./NavSecondary"
import { NavUser } from "./NavUser"
import type { ResearchSpace } from "@/types/research-space"
import type { SidebarUserInfo } from "@/types/navigation"
import { MembershipRole } from "@/types/research-space"
import { BRAND_LOGO_ALT } from "@/lib/branding"
import {
  buildDashboardNavItems,
  buildSpaceNavItems,
  buildSecondaryNavItems,
} from "@/lib/navigation-config"
import { extractSpaceIdFromPath, getSidebarContextFromPath } from "@/types/navigation"
import { UserRole } from "@/types/auth"

interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  /** Current user information */
  user: SidebarUserInfo
  /** Available research spaces */
  spaces: ResearchSpace[]
  /** Currently selected space (if in space context) */
  currentSpace?: ResearchSpace | null
  /** User's role in the current space */
  userSpaceRole?: MembershipRole
}

export function AppSidebar({
  user,
  spaces,
  currentSpace,
  userSpaceRole,
  ...props
}: AppSidebarProps) {
  const pathname = usePathname()
  const context = getSidebarContextFromPath(pathname)
  const isAdmin = user.role === UserRole.ADMIN
  const resolvedUserSpaceRole = React.useMemo<MembershipRole | undefined>(() => {
    if (userSpaceRole) {
      return userSpaceRole
    }
    if (currentSpace?.owner_id === user.id) {
      return MembershipRole.OWNER
    }
    if (isAdmin) {
      return MembershipRole.ADMIN
    }
    return undefined
  }, [currentSpace?.owner_id, isAdmin, user.id, userSpaceRole])

  // Build navigation items based on context
  const mainNavGroups = React.useMemo(() => {
    if (context === "space" && currentSpace) {
      return buildSpaceNavItems(currentSpace.id, pathname, resolvedUserSpaceRole)
    }
    return buildDashboardNavItems(pathname, isAdmin)
  }, [context, currentSpace, pathname, isAdmin, resolvedUserSpaceRole])

  const secondaryNavItems = React.useMemo(() => {
    return buildSecondaryNavItems(
      pathname,
      context,
      currentSpace?.id
    )
  }, [pathname, context, currentSpace?.id])

  const logoConfig = {
    src: "/logo.svg",
    alt: BRAND_LOGO_ALT,
    width: 24,
    height: 24,
  }

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <WorkspaceDropdown
          currentSpace={currentSpace || null}
          spaces={spaces}
          logo={logoConfig}
        />
      </SidebarHeader>

      <SidebarContent>
        {/* Main navigation */}
        <NavMain groups={mainNavGroups} />

        {/* Research spaces list (dashboard context only) */}
        {context === "dashboard" && (
          <>
            <SidebarSeparator />
            <NavSpaces spaces={spaces} maxVisible={5} />
          </>
        )}

        {/* Secondary navigation (e.g., "Back to Dashboard") */}
        {secondaryNavItems.length > 0 && (
          <>
            <SidebarSeparator className="mt-auto" />
            <NavSecondary items={secondaryNavItems} />
          </>
        )}
      </SidebarContent>

      <SidebarFooter>
        <NavUser user={user} />
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  )
}
