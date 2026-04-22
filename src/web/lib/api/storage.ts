import { apiDelete, apiGet, apiPost, apiPut } from '@/lib/api/client'
import type {
  CreateStorageConfigurationRequest,
  StorageConfigurationListResponse,
  StorageConfiguration,
  StorageHealthReport,
  StorageOperationRecord,
  StorageProviderTestResult,
  StorageUsageMetrics,
  UpdateStorageConfigurationRequest,
  StorageOverviewResponse,
} from '@/types/storage'

const withToken = (token?: string) => {
  if (!token) {
    throw new Error('Authentication token is required for storage admin operations')
  }
  return { token }
}

export interface StorageConfigurationListParams {
  page?: number
  per_page?: number
  include_disabled?: boolean
}

export async function fetchStorageConfigurations(
  params: StorageConfigurationListParams = {},
  token?: string,
) {
  const searchParams = new URLSearchParams()
  if (params.page) searchParams.set('page', params.page.toString())
  if (params.per_page) searchParams.set('per_page', params.per_page.toString())
  if (params.include_disabled) searchParams.set('include_disabled', 'true')
  const query = searchParams.toString()
  const path = query ? `/admin/storage/configurations?${query}` : '/admin/storage/configurations'
  return apiGet<StorageConfigurationListResponse>(path, withToken(token))
}

export async function createStorageConfiguration(
  payload: CreateStorageConfigurationRequest,
  token?: string,
) {
  return apiPost<StorageConfiguration>(
    '/admin/storage/configurations',
    payload,
    withToken(token),
  )
}

export async function updateStorageConfiguration(
  configurationId: string,
  payload: UpdateStorageConfigurationRequest,
  token?: string,
) {
  return apiPut<StorageConfiguration>(
    `/admin/storage/configurations/${configurationId}`,
    payload,
    withToken(token),
  )
}

export async function deleteStorageConfiguration(
  configurationId: string,
  force = false,
  token?: string,
) {
  const query = new URLSearchParams({ force: force ? 'true' : 'false' }).toString()
  return apiDelete<{ message: string }>(
    `/admin/storage/configurations/${configurationId}?${query}`,
    withToken(token),
  )
}

export async function testStorageConfiguration(configurationId: string, token?: string) {
  return apiPost<StorageProviderTestResult>(
    `/admin/storage/configurations/${configurationId}/test`,
    {},
    withToken(token),
  )
}

export async function fetchStorageMetrics(configurationId: string, token?: string) {
  return apiGet<StorageUsageMetrics | null>(
    `/admin/storage/configurations/${configurationId}/metrics`,
    withToken(token),
  )
}

export async function fetchStorageHealth(configurationId: string, token?: string) {
  return apiGet<StorageHealthReport | null>(
    `/admin/storage/configurations/${configurationId}/health`,
    withToken(token),
  )
}

export async function fetchStorageOperations(
  configurationId: string,
  limit: number,
  token?: string,
) {
  const params = new URLSearchParams({ limit: limit.toString() }).toString()
  return apiGet<StorageOperationRecord[]>(
    `/admin/storage/configurations/${configurationId}/operations?${params}`,
    withToken(token),
  )
}

export async function fetchStorageOverview(token?: string) {
  return apiGet<StorageOverviewResponse>('/admin/storage/stats', withToken(token))
}
