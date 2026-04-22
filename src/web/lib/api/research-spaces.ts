import { apiClient, authHeaders } from '@/lib/api/client'
import type { AxiosError } from 'axios'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type {
  CreateSpaceRequest,
  InvitableUserSearchResponse,
  InviteMemberRequest,
  MembershipListResponse,
  ResearchSpace,
  ResearchSpaceListResponse,
  ResearchSpaceMembership,
  UpdateMemberRoleRequest,
  UpdateSpaceRequest,
} from '@/types/research-space'

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function getAxiosStatus(error: unknown): number | null {
  if (typeof error !== 'object' || error === null) {
    return null
  }
  const axiosError = error as AxiosError
  const status = axiosError.response?.status
  return typeof status === 'number' ? status : null
}

function isUuidLike(value: string): boolean {
  return UUID_PATTERN.test(value)
}

function isResearchSpacePayload(value: unknown): value is ResearchSpace {
  if (typeof value !== 'object' || value === null) {
    return false
  }

  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.id === 'string' &&
    typeof candidate.slug === 'string' &&
    typeof candidate.name === 'string' &&
    typeof candidate.owner_id === 'string'
  )
}

/**
 * Research Spaces API client functions
 * All functions require authentication token
 */

export async function fetchResearchSpaces(
  params?: {
    skip?: number
    limit?: number
    owner_id?: string
  },
  token?: string,
): Promise<ResearchSpaceListResponse> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.get<ResearchSpaceListResponse>(
    '/research-spaces',
    {
      params,
      ...authHeaders(token),
    },
  )
  return resp.data
}

export async function fetchResearchSpace(
  spaceId: string,
  token?: string,
): Promise<ResearchSpace> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const normalizedSpaceId = spaceId.trim()
  try {
    const resp = await apiClient.get<ResearchSpace>(
      `/research-spaces/${normalizedSpaceId}`,
      authHeaders(token),
    )
    return resp.data
  } catch (error) {
    const statusCode = getAxiosStatus(error)
    const isPathResolutionError = statusCode === 404 || statusCode === 422
    if (!isPathResolutionError || isUuidLike(normalizedSpaceId)) {
      throw error
    }

    try {
      const slugResp = await apiClient.get<ResearchSpace>(
        `/research-spaces/slug/${encodeURIComponent(normalizedSpaceId)}`,
        authHeaders(token),
      )
      return slugResp.data
    } catch (slugError) {
      const slugStatusCode = getAxiosStatus(slugError)
      const isSlugLookupUnavailable = slugStatusCode === 404 || slugStatusCode === 422
      if (!isSlugLookupUnavailable) {
        throw slugError
      }

      const spaces = await fetchResearchSpaces({ limit: 200 }, token)
      const matchedSpace = spaces.spaces.find(
        (space) => space.slug.toLowerCase() === normalizedSpaceId.toLowerCase(),
      )
      if (matchedSpace !== undefined) {
        return matchedSpace
      }
      throw error
    }
  }
}

export async function fetchResearchSpaceBySlug(
  slug: string,
  token?: string,
): Promise<ResearchSpace> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.get<ResearchSpace>(
    `/research-spaces/slug/${slug}`,
    authHeaders(token),
  )
  return resp.data
}

export interface SpaceOverviewAccess {
  has_space_access: boolean
  can_manage_members: boolean
  can_edit_space: boolean
  is_owner: boolean
  show_membership_notice: boolean
  effective_role: string
}

export interface SpaceOverviewCounts {
  member_count: number
  data_source_count: number
}

export interface SpaceOverviewResponse {
  space: ResearchSpace
  membership: ResearchSpaceMembership | null
  access: SpaceOverviewAccess
  counts: SpaceOverviewCounts
  data_sources: DataSourceListResponse
  curation_stats: CurationStats
  curation_queue: CurationQueueResponse
}

export async function fetchSpaceOverview(
  spaceId: string,
  params?: {
    data_source_limit?: number
    queue_limit?: number
  },
  token?: string,
): Promise<SpaceOverviewResponse> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.get<SpaceOverviewResponse>(
    `/research-spaces/${spaceId}/overview`,
    {
      params,
      ...authHeaders(token),
    },
  )
  return resp.data
}

export async function createResearchSpace(
  data: CreateSpaceRequest,
  token?: string,
): Promise<ResearchSpace> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.post<unknown>(
    '/research-spaces',
    data,
    authHeaders(token),
  )
  if (!isResearchSpacePayload(resp.data)) {
    throw new Error('Invalid research space response payload')
  }
  return resp.data
}

export async function updateResearchSpace(
  spaceId: string,
  data: UpdateSpaceRequest,
  token?: string,
): Promise<ResearchSpace> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.put<ResearchSpace>(
    `/research-spaces/${spaceId}`,
    data,
    authHeaders(token),
  )
  return resp.data
}

export async function deleteResearchSpace(
  spaceId: string,
  token?: string,
): Promise<void> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  await apiClient.delete(`/research-spaces/${spaceId}`, authHeaders(token))
}

// Membership API functions

export async function fetchSpaceMembers(
  spaceId: string,
  params?: {
    skip?: number
    limit?: number
  },
  token?: string,
): Promise<MembershipListResponse> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.get<MembershipListResponse>(
    `/research-spaces/${spaceId}/members`,
    {
      params,
      ...authHeaders(token),
    },
  )
  return resp.data
}

export async function searchInvitableUsers(
  spaceId: string,
  params: {
    query: string
    limit?: number
  },
  token?: string,
): Promise<InvitableUserSearchResponse> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.get<InvitableUserSearchResponse>(
    `/research-spaces/${spaceId}/members/search-users`,
    {
      params,
      ...authHeaders(token),
    },
  )
  return resp.data
}

export async function inviteMember(
  spaceId: string,
  data: InviteMemberRequest,
  token?: string,
): Promise<ResearchSpaceMembership> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.post<ResearchSpaceMembership>(
    `/research-spaces/${spaceId}/members`,
    data,
    authHeaders(token),
  )
  return resp.data
}

export async function updateMemberRole(
  spaceId: string,
  membershipId: string,
  data: UpdateMemberRoleRequest,
  token?: string,
): Promise<ResearchSpaceMembership> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.put<ResearchSpaceMembership>(
    `/research-spaces/${spaceId}/members/${membershipId}/role`,
    data,
    authHeaders(token),
  )
  return resp.data
}

export async function removeMember(
  spaceId: string,
  membershipId: string,
  token?: string,
): Promise<void> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  await apiClient.delete(
    `/research-spaces/${spaceId}/members/${membershipId}`,
    authHeaders(token),
  )
}

export async function acceptInvitation(
  membershipId: string,
  token?: string,
): Promise<ResearchSpaceMembership> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.post<ResearchSpaceMembership>(
    `/research-spaces/memberships/${membershipId}/accept`,
    {},
    authHeaders(token),
  )
  return resp.data
}

export async function fetchPendingInvitations(
  params?: {
    skip?: number
    limit?: number
  },
  token?: string,
): Promise<MembershipListResponse> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  const resp = await apiClient.get<MembershipListResponse>(
    '/research-spaces/memberships/pending',
    {
      params,
      ...authHeaders(token),
    },
  )
  return resp.data
}

export async function fetchMyMembership(
  spaceId: string,
  token?: string,
): Promise<ResearchSpaceMembership | null> {
  if (!token) {
    throw new Error('Authentication token is required')
  }

  try {
    const resp = await apiClient.get<ResearchSpaceMembership>(
      `/research-spaces/${spaceId}/membership/me`,
      authHeaders(token),
    )
    return resp.data
  } catch (error) {
    const axiosError = error as AxiosError
    const responseStatus = axiosError.response?.status
    const errorCode = axiosError.code
    const isTimeout = errorCode === 'ECONNABORTED'
    const isNetworkFailure = axiosError.response === undefined
    const isRecoverableBackendFailure =
      typeof responseStatus === 'number' && responseStatus >= 500
    if (
      responseStatus === 404 ||
      isTimeout ||
      isNetworkFailure ||
      isRecoverableBackendFailure
    ) {
      return null
    }
    throw error
  }
}

// Curation API functions

export interface CurationStats {
  total: number
  pending: number
  approved: number
  rejected: number
}

export interface CurationQueueItem {
  id: number
  entity_type: string
  entity_id: string
  status: string
  priority: string
  quality_score: number | null
  issues: number
  last_updated: string | null
}

export interface CurationQueueResponse {
  items: CurationQueueItem[]
  total: number
  skip: number
  limit: number
}

export async function fetchSpaceCurationStats(
  spaceId: string,
  token?: string,
): Promise<CurationStats> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  try {
    const resp = await apiClient.get<CurationStats>(
      `/research-spaces/${spaceId}/curation/stats`,
      authHeaders(token),
    )
    return resp.data
  } catch (error) {
    const axiosError = error as AxiosError
    if (axiosError.response?.status === 404 || axiosError.response?.status === 500) {
      return {
        total: 0,
        pending: 0,
        approved: 0,
        rejected: 0,
      }
    }
    throw error
  }
}

export async function fetchSpaceCurationQueue(
  spaceId: string,
  params?: {
    entity_type?: string
    status?: string
    priority?: string
    skip?: number
    limit?: number
  },
  token?: string,
): Promise<CurationQueueResponse> {
  if (!token) {
    throw new Error('Authentication token is required')
  }
  try {
    const resp = await apiClient.get<CurationQueueResponse>(
      `/research-spaces/${spaceId}/curation/queue`,
      {
        params,
        ...authHeaders(token),
      },
    )
    return resp.data
  } catch (error) {
    const axiosError = error as AxiosError
    if (axiosError.response?.status === 404 || axiosError.response?.status === 500) {
      return {
        items: [],
        total: 0,
        skip: params?.skip ?? 0,
        limit: params?.limit ?? 50,
      }
    }
    throw error
  }
}
