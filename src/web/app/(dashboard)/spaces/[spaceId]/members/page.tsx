import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { fetchMyMembership, fetchResearchSpace, fetchSpaceMembers } from '@/lib/api/research-spaces'
import { canManageMembers } from '@/components/research-spaces/role-utils'
import { MembershipRole, type ResearchSpace, type ResearchSpaceMembership } from '@/types/research-space'
import { UserRole } from '@/types/auth'
import SpaceMembersClient from '../space-members-client'

interface SpaceMembersPageProps {
  params: Promise<{
    spaceId: string
  }>
}

export default async function SpaceMembersPage({ params }: SpaceMembersPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let space: ResearchSpace | null = null
  let memberships: ResearchSpaceMembership[] = []
  let membersError: string | null = null
  let currentMembership: ResearchSpaceMembership | null = null
  let effectiveSpaceId = spaceId

  try {
    space = await fetchResearchSpace(spaceId, token)
    effectiveSpaceId = space.id
  } catch (error) {
    console.error('[SpaceMembersPage] Failed to fetch research space', error)
  }

  const [membersResult, membershipResult] = await Promise.allSettled([
    fetchSpaceMembers(effectiveSpaceId, undefined, token),
    fetchMyMembership(effectiveSpaceId, token),
  ])

  if (membersResult.status === 'fulfilled') {
    memberships = membersResult.value.memberships
  } else {
    membersError =
      membersResult.reason instanceof Error
        ? membersResult.reason.message
        : 'Unable to load members for this space.'
    console.error('[SpaceMembersPage] Failed to fetch members', membersResult.reason)
  }

  if (membershipResult.status === 'fulfilled') {
    currentMembership = membershipResult.value
  } else {
    console.error('[SpaceMembersPage] Failed to fetch membership', membershipResult.reason)
  }

  const isPlatformAdmin = session.user.role === UserRole.ADMIN
  const hasSpaceAccess = isPlatformAdmin || Boolean(currentMembership)
  const matchedMembership = memberships.find(
    (membership) => membership.user_id === session.user.id,
  )
  const effectiveRole =
    matchedMembership?.role ??
    currentMembership?.role ??
    (isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER)
  const canManageMembersFlag = isPlatformAdmin || canManageMembers(effectiveRole)
  const isOwner = effectiveRole === MembershipRole.OWNER
  const canEditSpace = isOwner || isPlatformAdmin
  const showMembershipNotice = !currentMembership && !isPlatformAdmin

  return (
    <SpaceMembersClient
      spaceId={effectiveSpaceId}
      space={space}
      memberships={memberships}
      membersError={membersError}
      access={{
        hasSpaceAccess,
        canManageMembers: canManageMembersFlag,
        canEditSpace,
        isOwner,
        showMembershipNotice,
      }}
    />
  )
}
