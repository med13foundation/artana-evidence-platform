import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import {
  fetchMyMembership,
  fetchResearchSpace,
  fetchSpaceCurationQueue,
  fetchSpaceCurationStats,
  fetchSpaceOverview,
  fetchSpaceMembers,
} from '@/lib/api/research-spaces'
import { fetchDataSourcesBySpace } from '@/lib/api/data-sources'
import { fetchKernelEntities, fetchKernelRelations } from '@/lib/api/kernel'
import { canManageMembers } from '@/components/research-spaces/role-utils'
import { MembershipRole, type ResearchSpace, type ResearchSpaceMembership } from '@/types/research-space'
import { UserRole } from '@/types/auth'
import SpaceDetailClient from './space-detail-client'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { CurationQueueResponse, CurationStats } from '@/lib/api/research-spaces'
import type { KernelRelationResponse } from '@/types/kernel'

interface SpaceDetailPageProps {
  params: Promise<{
    spaceId: string
  }>
}

interface DistributionPoint {
  label: string
  count: number
}

type HttpErrorShape = {
  response?: {
    status?: number
  }
}

const RELATION_DISTRIBUTION_PAGE_SIZE = 200
const RELATION_DISTRIBUTION_MAX_RELATIONS = 1000
const RELATION_DISTRIBUTION_TOP_RELATION_TYPES = 8
const RELATION_DISTRIBUTION_TOP_NODES = 8

function getErrorStatusCode(error: unknown): number | null {
  if (typeof error !== 'object' || error === null) {
    return null
  }

  const httpError = error as HttpErrorShape
  const statusCode = httpError.response?.status
  return typeof statusCode === 'number' ? statusCode : null
}

function shouldUseLegacyOverviewFallback(statusCode: number | null): boolean {
  return statusCode === 403 || statusCode === 404 || statusCode === 422
}

async function fetchRelationSample(
  spaceId: string,
  token: string,
): Promise<KernelRelationResponse[]> {
  const sampled: KernelRelationResponse[] = []
  let offset = 0

  while (sampled.length < RELATION_DISTRIBUTION_MAX_RELATIONS) {
    const response = await fetchKernelRelations(
      spaceId,
      {
        offset,
        limit: RELATION_DISTRIBUTION_PAGE_SIZE,
      },
      token,
    )
    const batch = response.relations
    if (batch.length === 0) {
      break
    }
    sampled.push(...batch)
    if (batch.length < RELATION_DISTRIBUTION_PAGE_SIZE) {
      break
    }
    offset += RELATION_DISTRIBUTION_PAGE_SIZE
  }

  return sampled.slice(0, RELATION_DISTRIBUTION_MAX_RELATIONS)
}

function truncateLabel(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value
  }
  return `${value.slice(0, maxLength - 1)}…`
}

function buildRelationTypeDistribution(
  relations: KernelRelationResponse[],
): DistributionPoint[] {
  const relationTypeCounts = new Map<string, number>()
  for (const relation of relations) {
    const key = relation.relation_type.trim()
    relationTypeCounts.set(key, (relationTypeCounts.get(key) ?? 0) + 1)
  }

  return Array.from(relationTypeCounts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, RELATION_DISTRIBUTION_TOP_RELATION_TYPES)
    .map(([label, count]) => ({
      label: truncateLabel(label, 28),
      count,
    }))
}

async function buildNodeDistribution(
  spaceId: string,
  relations: KernelRelationResponse[],
  token: string,
): Promise<DistributionPoint[]> {
  const nodeCounts = new Map<string, number>()
  for (const relation of relations) {
    nodeCounts.set(relation.source_id, (nodeCounts.get(relation.source_id) ?? 0) + 1)
    nodeCounts.set(relation.target_id, (nodeCounts.get(relation.target_id) ?? 0) + 1)
  }

  const topNodeIds = Array.from(nodeCounts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, RELATION_DISTRIBUTION_TOP_NODES)
    .map(([nodeId]) => nodeId)

  if (topNodeIds.length === 0) {
    return []
  }

  const labelByNodeId: Record<string, string> = {}
  const topNodeIdsWithCounts = topNodeIds.map((nodeId) => ({
    nodeId,
    count: nodeCounts.get(nodeId) ?? 0,
  }))

  for (const { nodeId } of topNodeIdsWithCounts) {
    labelByNodeId[nodeId] = `Entity ${nodeId.slice(0, 8)}`
  }

  try {
    const entities = await fetchKernelEntities(
      spaceId,
      {
        ids: topNodeIds,
        offset: 0,
        limit: topNodeIds.length,
      },
      token,
    )
    for (const entity of entities.entities) {
      const resolved =
        entity.display_label && entity.display_label.trim().length > 0
          ? entity.display_label.trim()
          : entity.entity_type
      labelByNodeId[entity.id] = resolved
    }
  } catch (error) {
    console.warn('[SpaceDetailPage] Failed to fetch node labels in bulk', error)
  }

  const labelOccurrence = new Map<string, number>()
  for (const label of Object.values(labelByNodeId)) {
    labelOccurrence.set(label, (labelOccurrence.get(label) ?? 0) + 1)
  }

  return topNodeIdsWithCounts.map(({ nodeId, count }) => {
    const base = labelByNodeId[nodeId] ?? `Entity ${nodeId.slice(0, 8)}`
    const isDuplicate = (labelOccurrence.get(base) ?? 0) > 1
    const resolvedLabel = isDuplicate ? `${base} (${nodeId.slice(0, 4)})` : base
    return {
      label: truncateLabel(resolvedLabel, 26),
      count,
    }
  })
}

export default async function SpaceDetailPage({ params }: SpaceDetailPageProps) {
  const { spaceId } = await params
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token

  if (!session || !token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let space: ResearchSpace | null = null
  let memberships: ResearchSpaceMembership[] = []
  let membersError: string | null = null
  let dataSources: DataSourceListResponse | null = null
  let curationStats: CurationStats | null = null
  let curationQueue: CurationQueueResponse | null = null
  let hasSpaceAccess = false
  let canManageMembersFlag = false
  let canEditSpace = false
  let isOwner = false
  let showMembershipNotice = false
  let currentMembership: ResearchSpaceMembership | null = null
  let relationTypeDistribution: DistributionPoint[] = []
  let nodeDistribution: DistributionPoint[] = []
  let effectiveSpaceId = spaceId

  const [overviewResult, membersResult] = await Promise.allSettled([
    fetchSpaceOverview(spaceId, { data_source_limit: 5, queue_limit: 5 }, token),
    fetchSpaceMembers(spaceId, undefined, token),
  ])

  if (membersResult.status === 'fulfilled') {
    memberships = membersResult.value.memberships
  } else {
    membersError =
      membersResult.reason instanceof Error
        ? membersResult.reason.message
        : 'Unable to load members for this space.'
    console.error('[SpaceDetailPage] Failed to fetch members', membersResult.reason)
  }

  if (overviewResult.status === 'fulfilled') {
    const overview = overviewResult.value
    space = overview.space
    effectiveSpaceId = overview.space.id
    currentMembership = overview.membership
    dataSources = overview.data_sources
    curationStats = overview.curation_stats
    curationQueue = overview.curation_queue
    hasSpaceAccess = overview.access.has_space_access
    canManageMembersFlag = overview.access.can_manage_members
    canEditSpace = overview.access.can_edit_space
    isOwner = overview.access.is_owner
    showMembershipNotice = overview.access.show_membership_notice
  } else {
    const overviewStatusCode = getErrorStatusCode(overviewResult.reason)
    if (shouldUseLegacyOverviewFallback(overviewStatusCode)) {
      console.warn(
        '[SpaceDetailPage] Overview endpoint unavailable or access-limited, using legacy multi-call fallback',
      )
      try {
        space = await fetchResearchSpace(spaceId, token)
        effectiveSpaceId = space.id
      } catch (error) {
        console.error('[SpaceDetailPage] Failed to fetch research space', error)
      }
      try {
        currentMembership = await fetchMyMembership(effectiveSpaceId, token)
      } catch (error) {
        console.error('[SpaceDetailPage] Failed to fetch membership', error)
      }

      const isPlatformAdmin = session.user.role === UserRole.ADMIN
      hasSpaceAccess = isPlatformAdmin || Boolean(currentMembership)
      const matchedMembership = memberships.find(
        (membership) => membership.user_id === session.user.id,
      )
      const effectiveRole =
        matchedMembership?.role ??
        currentMembership?.role ??
        (isPlatformAdmin ? MembershipRole.ADMIN : MembershipRole.VIEWER)
      canManageMembersFlag = isPlatformAdmin || canManageMembers(effectiveRole)
      isOwner = effectiveRole === MembershipRole.OWNER
      canEditSpace = isOwner || isPlatformAdmin
      showMembershipNotice = !currentMembership && !isPlatformAdmin

      if (membersResult.status !== 'fulfilled' && effectiveSpaceId !== spaceId) {
        try {
          const membersResponse = await fetchSpaceMembers(effectiveSpaceId, undefined, token)
          memberships = membersResponse.memberships
          membersError = null
        } catch (error) {
          console.error('[SpaceDetailPage] Failed to refetch members by canonical id', error)
        }
      }

      if (hasSpaceAccess) {
        const [dataSourcesResult, curationStatsResult, curationQueueResult] =
          await Promise.allSettled([
            fetchDataSourcesBySpace(effectiveSpaceId, { page: 1, limit: 5 }, token),
            fetchSpaceCurationStats(effectiveSpaceId, token),
            fetchSpaceCurationQueue(effectiveSpaceId, { limit: 5 }, token),
          ])

        if (dataSourcesResult.status === 'fulfilled') {
          dataSources = dataSourcesResult.value
        } else {
          console.error('[SpaceDetailPage] Failed to fetch data sources', dataSourcesResult.reason)
        }

        if (curationStatsResult.status === 'fulfilled') {
          curationStats = curationStatsResult.value
        } else {
          console.error(
            '[SpaceDetailPage] Failed to fetch curation stats',
            curationStatsResult.reason,
          )
        }

        if (curationQueueResult.status === 'fulfilled') {
          curationQueue = curationQueueResult.value
        } else {
          console.error(
            '[SpaceDetailPage] Failed to fetch curation queue',
            curationQueueResult.reason,
          )
        }
      }
    } else {
      console.error('[SpaceDetailPage] Failed to fetch space overview', overviewResult.reason)
    }
  }

  if (hasSpaceAccess) {
    try {
      const sampledRelations = await fetchRelationSample(effectiveSpaceId, token)
      relationTypeDistribution = buildRelationTypeDistribution(sampledRelations)
      nodeDistribution = await buildNodeDistribution(effectiveSpaceId, sampledRelations, token)
    } catch (error) {
      console.error(
        '[SpaceDetailPage] Failed to fetch relation distributions',
        error,
      )
    }
  }

  return (
    <SpaceDetailClient
      spaceId={effectiveSpaceId}
      space={space}
      memberships={memberships}
      membersError={membersError}
      dataSources={dataSources}
      curationStats={curationStats}
      curationQueue={curationQueue}
      relationTypeDistribution={relationTypeDistribution}
      nodeDistribution={nodeDistribution}
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
