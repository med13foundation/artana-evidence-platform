import type { QueryClient } from '@tanstack/react-query'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { DataSourceListResponse } from '@/lib/api/data-sources'
import type { UserListResponse, UserPublic, UserStatisticsResponse } from '@/lib/api/users'
import { queryKeys, readUserParamsFromKey } from '@/lib/query/query-keys'

function statusMatches(user: UserPublic, statusFilter: string): boolean {
  return statusFilter.length === 0 || user.status === statusFilter
}

function roleMatches(user: UserPublic, role: string): boolean {
  return role.length === 0 || user.role === role
}

function adjustRoleCount(
  counts: Record<string, number>,
  role: UserPublic['role'],
  delta: number,
): Record<string, number> {
  const nextValue = Math.max((counts[role] ?? 0) + delta, 0)
  return {
    ...counts,
    [role]: nextValue,
  }
}

function updateStatusCount(
  stats: UserStatisticsResponse,
  status: UserPublic['status'],
  delta: number,
): UserStatisticsResponse {
  switch (status) {
    case 'active':
      return { ...stats, active_users: Math.max(stats.active_users + delta, 0) }
    case 'inactive':
      return { ...stats, inactive_users: Math.max(stats.inactive_users + delta, 0) }
    case 'suspended':
      return { ...stats, suspended_users: Math.max(stats.suspended_users + delta, 0) }
    case 'pending_verification':
      return {
        ...stats,
        pending_verification: Math.max(stats.pending_verification + delta, 0),
      }
  }
}

export function applyUserToStats(
  stats: UserStatisticsResponse,
  previousUser: UserPublic | null,
  nextUser: UserPublic | null,
): UserStatisticsResponse {
  let nextStats = { ...stats, by_role: { ...stats.by_role } }

  if (previousUser !== null) {
    nextStats = updateStatusCount(nextStats, previousUser.status, -1)
    nextStats = {
      ...nextStats,
      total_users: Math.max(nextStats.total_users - 1, 0),
      by_role: adjustRoleCount(nextStats.by_role, previousUser.role, -1),
    }
  }

  if (nextUser !== null) {
    nextStats = updateStatusCount(nextStats, nextUser.status, 1)
    nextStats = {
      ...nextStats,
      total_users: nextStats.total_users + 1,
      by_role: adjustRoleCount(nextStats.by_role, nextUser.role, 1),
    }
  }

  return nextStats
}

export function patchUserLists(
  queryClient: QueryClient,
  updater: (current: UserListResponse, params: Required<import('@/lib/api/users').UserListParams>) => UserListResponse,
): void {
  queryClient.getQueriesData<UserListResponse>({ queryKey: queryKeys.usersRoot() }).forEach(([queryKey, data]) => {
    if (data === undefined) {
      return
    }
    const params = readUserParamsFromKey(queryKey)
    if (params === null) {
      return
    }
    queryClient.setQueryData<UserListResponse>(queryKey, updater(data, params))
  })
}

export function upsertUserInLists(queryClient: QueryClient, user: UserPublic): void {
  patchUserLists(queryClient, (current, params) => {
    const existingUser = current.users.find((entry) => entry.id === user.id)
    const withoutUser = current.users.filter((entry) => entry.id !== user.id)
    const shouldInclude = roleMatches(user, params.role) && statusMatches(user, params.status_filter)

    const users = shouldInclude ? [user, ...withoutUser] : withoutUser
    const total = existingUser === undefined ? current.total + 1 : current.total

    return {
      ...current,
      users,
      total,
    }
  })
}

export function removeUserFromLists(queryClient: QueryClient, userId: string): void {
  patchUserLists(queryClient, (current) => {
    const didRemove = current.users.some((entry) => entry.id === userId)
    if (!didRemove) {
      return current
    }

    return {
      ...current,
      users: current.users.filter((entry) => entry.id !== userId),
      total: Math.max(current.total - 1, 0),
    }
  })
}

export function replaceUserInLists(queryClient: QueryClient, user: UserPublic): void {
  patchUserLists(queryClient, (current, params) => {
    const withoutUser = current.users.filter((entry) => entry.id !== user.id)
    const shouldInclude = roleMatches(user, params.role) && statusMatches(user, params.status_filter)

    return {
      ...current,
      users: shouldInclude ? [user, ...withoutUser] : withoutUser,
    }
  })
}

export function updateUserStatsCache(
  queryClient: QueryClient,
  previousUser: UserPublic | null,
  nextUser: UserPublic | null,
): void {
  queryClient.setQueryData<UserStatisticsResponse>(
    queryKeys.userStats(),
    (current) => (current === undefined ? current : applyUserToStats(current, previousUser, nextUser)),
  )
}

export function mergeAvailabilitySummary(
  current: DataSourceAvailability[],
  summary: DataSourceAvailability,
): DataSourceAvailability[] {
  const next = current.filter((entry) => entry.catalog_entry_id !== summary.catalog_entry_id)
  return [...next, summary]
}

export function mergeAvailabilitySummaries(
  current: DataSourceAvailability[],
  summaries: DataSourceAvailability[],
): DataSourceAvailability[] {
  return summaries.reduce(mergeAvailabilitySummary, current)
}

export function mergeSpaceDataSource(
  current: DataSourceListResponse,
  nextSource: import('@/types/data-source').DataSource,
): DataSourceListResponse {
  const withoutSource = current.items.filter((entry) => entry.id !== nextSource.id)
  return {
    ...current,
    items: [nextSource, ...withoutSource],
    total: current.items.some((entry) => entry.id === nextSource.id) ? current.total : current.total + 1,
  }
}

export function removeSpaceDataSource(
  current: DataSourceListResponse,
  sourceId: string,
): DataSourceListResponse {
  if (!current.items.some((entry) => entry.id === sourceId)) {
    return current
  }

  return {
    ...current,
    items: current.items.filter((entry) => entry.id !== sourceId),
    total: Math.max(current.total - 1, 0),
  }
}
