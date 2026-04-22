"use server"

import { isPlaywrightE2EMode } from '@/lib/e2e/playwright-auth'
import {
  getPlaywrightAvailabilitySummaries,
  getPlaywrightMaintenanceState,
  getPlaywrightSpaceDataSources,
  getPlaywrightStorageConfigurations,
  getPlaywrightStorageOverview,
  getPlaywrightUserStatistics,
  listPlaywrightUsers,
} from '@/lib/e2e/playwright-fixtures'
import { fetchCatalogAvailabilitySummaries } from '@/lib/api/data-source-activation'
import { fetchDataSourcesBySpace, type DataSourceListParams, type DataSourceListResponse } from '@/lib/api/data-sources'
import { fetchStorageConfigurations, fetchStorageOverview, type StorageConfigurationListParams } from '@/lib/api/storage'
import { fetchMaintenanceState } from '@/lib/api/system-status'
import { fetchUsers, fetchUserStatistics, type UserListParams, type UserListResponse, type UserStatisticsResponse } from '@/lib/api/users'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import { requireAccessToken } from '@/app/actions/action-utils'

export async function fetchUsersQueryAction(params: UserListParams = {}): Promise<UserListResponse> {
  if (isPlaywrightE2EMode()) {
    return listPlaywrightUsers(params)
  }
  const token = await requireAccessToken()
  return fetchUsers(params, token)
}

export async function fetchUserStatisticsQueryAction(): Promise<UserStatisticsResponse> {
  if (isPlaywrightE2EMode()) {
    return getPlaywrightUserStatistics()
  }
  const token = await requireAccessToken()
  return fetchUserStatistics(token)
}

export async function fetchStorageConfigurationsQueryAction(
  params: StorageConfigurationListParams = {},
): Promise<StorageConfigurationListResponse> {
  if (isPlaywrightE2EMode()) {
    return getPlaywrightStorageConfigurations(params)
  }
  const token = await requireAccessToken()
  return fetchStorageConfigurations(params, token)
}

export async function fetchStorageOverviewQueryAction(): Promise<StorageOverviewResponse> {
  if (isPlaywrightE2EMode()) {
    return getPlaywrightStorageOverview()
  }
  const token = await requireAccessToken()
  return fetchStorageOverview(token)
}

export async function fetchMaintenanceStateQueryAction(): Promise<MaintenanceModeResponse> {
  if (isPlaywrightE2EMode()) {
    return getPlaywrightMaintenanceState()
  }
  const token = await requireAccessToken()
  return fetchMaintenanceState(token)
}

export async function fetchCatalogAvailabilitySummariesQueryAction(): Promise<DataSourceAvailability[]> {
  if (isPlaywrightE2EMode()) {
    return getPlaywrightAvailabilitySummaries()
  }
  const token = await requireAccessToken()
  return fetchCatalogAvailabilitySummaries(token)
}

export async function fetchSpaceDataSourcesQueryAction(
  spaceId: string,
  params: Omit<DataSourceListParams, 'research_space_id'> = {},
): Promise<DataSourceListResponse> {
  if (isPlaywrightE2EMode()) {
    return getPlaywrightSpaceDataSources(spaceId, params)
  }
  const token = await requireAccessToken()
  return fetchDataSourcesBySpace(spaceId, params, token)
}
