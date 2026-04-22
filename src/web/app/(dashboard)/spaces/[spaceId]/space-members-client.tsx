'use client'

import { ResearchSpaceDetail } from '@/components/research-spaces/ResearchSpaceDetail'
import { PageHero } from '@/components/ui/composition-patterns'
import type { ResearchSpace, ResearchSpaceMembership } from '@/types/research-space'

interface SpaceMembersClientProps {
  spaceId: string
  space: ResearchSpace | null
  memberships: ResearchSpaceMembership[]
  membersError?: string | null
  access: {
    hasSpaceAccess: boolean
    canManageMembers: boolean
    canEditSpace: boolean
    isOwner: boolean
    showMembershipNotice: boolean
  }
}

export default function SpaceMembersClient({
  spaceId,
  space,
  memberships,
  membersError,
  access,
}: SpaceMembersClientProps) {
  return (
    <div className="space-y-6">
      <PageHero
        title="Team Management"
        description="Invite collaborators, assign roles, and manage membership for this research space."
        variant="research"
      />
      <ResearchSpaceDetail
        spaceId={spaceId}
        space={space}
        memberships={memberships}
        membersError={membersError}
        dataSources={null}
        curationStats={null}
        curationQueue={null}
        relationTypeDistribution={[]}
        nodeDistribution={[]}
        access={access}
        defaultTab="members"
      />
    </div>
  )
}
