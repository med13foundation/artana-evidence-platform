'use client'

import { ResearchSpaceDetail } from '@/components/research-spaces/ResearchSpaceDetail'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { CurationQueueResponse, CurationStats } from '@/lib/api/research-spaces'
import type { ResearchSpace, ResearchSpaceMembership } from '@/types/research-space'

type SpaceAccess = {
  hasSpaceAccess: boolean
  canManageMembers: boolean
  canEditSpace: boolean
  isOwner: boolean
  showMembershipNotice: boolean
}

interface DistributionPoint {
  label: string
  count: number
}

interface SpaceDetailClientProps {
  spaceId: string
  space: ResearchSpace | null
  memberships: ResearchSpaceMembership[]
  membersError?: string | null
  dataSources: DataSourceListResponse | null
  curationStats: CurationStats | null
  curationQueue: CurationQueueResponse | null
  relationTypeDistribution: DistributionPoint[]
  nodeDistribution: DistributionPoint[]
  access: SpaceAccess
}

export default function SpaceDetailClient({
  spaceId,
  space,
  memberships,
  membersError,
  dataSources,
  curationStats,
  curationQueue,
  relationTypeDistribution,
  nodeDistribution,
  access,
}: SpaceDetailClientProps) {
  return (
    <div>
      <ResearchSpaceDetail
        spaceId={spaceId}
        space={space}
        memberships={memberships}
        membersError={membersError}
        dataSources={dataSources}
        curationStats={curationStats}
        curationQueue={curationQueue}
        relationTypeDistribution={relationTypeDistribution}
        nodeDistribution={nodeDistribution}
        access={access}
      />
    </div>
  )
}
