"use client"

import * as React from 'react'
import { useSession } from 'next-auth/react'
import { usePathname } from 'next/navigation'
import { Loader2 } from 'lucide-react'

import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'
import { useSpaceContext } from '@/components/space-context-provider'
import { AppSidebar } from './AppSidebar'
import { CollaborativeSidebar } from './CollaborativeSidebar'
import { GlobalHeader } from '../GlobalHeader'
import { extractSpaceIdFromPath } from '@/types/navigation'
import type { SidebarUserInfo } from '@/types/navigation'
import { UserRole } from '@/types/auth'
import { MembershipRole, type ResearchSpaceMembership } from '@/types/research-space'

interface SidebarWrapperProps {
  children: React.ReactNode
  currentMembership?: ResearchSpaceMembership | null
}

export function SidebarWrapper({ children, currentMembership }: SidebarWrapperProps) {
  const { data: session, status } = useSession()
  const { spaces, isLoading: spacesLoading } = useSpaceContext()
  const pathname = usePathname()
  const isKnowledgeGraphRoute = pathname.includes('/knowledge-graph')
  const isCurationRoute = pathname.includes('/curation')

  // Extract current space from URL if we're in a space context
  const spaceIdFromUrl = extractSpaceIdFromPath(pathname)
  const currentSpace = spaceIdFromUrl
    ? spaces.find((s) => s.id === spaceIdFromUrl) ?? null
    : null

  // Build user info for sidebar
  const userInfo: SidebarUserInfo | null = React.useMemo(() => {
    if (!session?.user) return null

    return {
      id: session.user.id || '',
      name: session.user.full_name || session.user.email || 'User',
      email: session.user.email || '',
      avatar: undefined, // Add avatar URL if available
      role: (session.user.role as UserRole) || UserRole.VIEWER,
    }
  }, [session?.user])

  const userSpaceRole = React.useMemo<MembershipRole | undefined>(() => {
    if (!currentSpace || !userInfo) {
      return undefined
    }
    const membershipRole = currentMembership?.role

    if (membershipRole) {
      return membershipRole
    }
    if (currentSpace.owner_id === userInfo.id) {
      return MembershipRole.OWNER
    }
    if (userInfo.role === UserRole.ADMIN) {
      return MembershipRole.ADMIN
    }
    return undefined
  }, [currentSpace, currentMembership?.role, userInfo])

  // Show loading state while session/spaces are loading
  if (status === 'loading' || spacesLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  // If no user info, still render layout (ProtectedRoute will handle redirect)
  if (!userInfo) {
    return (
      <div className="min-h-screen bg-background">
        {children}
      </div>
    )
  }

  return (
    <SidebarProvider>
      <AppSidebar
        user={userInfo}
        spaces={spaces}
        currentSpace={currentSpace}
        userSpaceRole={userSpaceRole}
      />
      <SidebarInset className="relative flex h-svh flex-col overflow-y-auto overflow-x-hidden">
        <GlobalHeader currentSpace={currentSpace} />
        <div
          className={
            isKnowledgeGraphRoute || isCurationRoute
              ? 'w-full flex-1 p-0'
              : 'mx-auto w-full max-w-[1200px] flex-1 p-brand-sm pt-0 md:p-brand-md md:pt-0 lg:p-brand-lg lg:pt-0'
          }
        >
          {children}
        </div>
      </SidebarInset>
      <CollaborativeSidebar />
    </SidebarProvider>
  )
}
