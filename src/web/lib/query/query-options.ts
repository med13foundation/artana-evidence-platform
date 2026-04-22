import { queryOptions } from '@tanstack/react-query'
import type { DataSourceListParams, DataSourceListResponse } from '@/lib/api/data-sources'
import type { StorageConfigurationListParams } from '@/lib/api/storage'
import type { UserListParams, UserListResponse, UserStatisticsResponse } from '@/lib/api/users'
import { queryKeys } from '@/lib/query/query-keys'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'

export function usersQueryOptions(
  params: UserListParams,
  initialData?: UserListResponse,
) {
  return queryOptions({
    queryKey: queryKeys.users(params),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchUsersQueryAction(params)
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}

export function userStatsQueryOptions(initialData?: UserStatisticsResponse) {
  return queryOptions({
    queryKey: queryKeys.userStats(),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchUserStatisticsQueryAction()
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}

export function maintenanceStateQueryOptions(initialData?: MaintenanceModeResponse) {
  return queryOptions({
    queryKey: queryKeys.maintenanceState(),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchMaintenanceStateQueryAction()
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}

export function availabilitySummariesQueryOptions(initialData?: DataSourceAvailability[]) {
  return queryOptions({
    queryKey: queryKeys.availabilitySummaries(),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchCatalogAvailabilitySummariesQueryAction()
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}

export function storageConfigurationsQueryOptions(
  params: StorageConfigurationListParams,
  initialData?: StorageConfigurationListResponse,
) {
  return queryOptions({
    queryKey: queryKeys.storageConfigurations(params),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchStorageConfigurationsQueryAction(params)
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}

export function storageOverviewQueryOptions(initialData?: StorageOverviewResponse) {
  return queryOptions({
    queryKey: queryKeys.storageOverview(),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchStorageOverviewQueryAction()
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}

export function spaceDataSourcesQueryOptions(
  spaceId: string,
  params: Omit<DataSourceListParams, 'research_space_id'> = {},
  initialData?: DataSourceListResponse,
) {
  return queryOptions({
    queryKey: queryKeys.spaceDataSources(spaceId, params),
    queryFn: async () => {
      const actions = await import('@/app/actions/admin-query')
      return actions.fetchSpaceDataSourcesQueryAction(spaceId, params)
    },
    ...(initialData !== undefined ? { initialData } : {}),
  })
}
