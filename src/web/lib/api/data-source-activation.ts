import { apiClient, authHeaders } from '@/lib/api/client'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'

export type ActivationScope = 'global' | 'research_space'
export type PermissionLevel = 'blocked' | 'visible' | 'available'

export interface ActivationRule {
  id: string
  scope: ActivationScope
  permission_level: PermissionLevel
  research_space_id: string | null
  updated_by: string
  created_at: string
  updated_at: string
}

export interface DataSourceAvailability {
  catalog_entry_id: string
  effective_permission_level: PermissionLevel
  effective_is_active: boolean
  global_rule: ActivationRule | null
  project_rules: ActivationRule[]
}

export interface BulkActivationUpdateRequest {
  permission_level: PermissionLevel
  catalog_entry_ids?: string[]
}

export async function fetchAdminCatalogEntries(token?: string): Promise<SourceCatalogEntry[]> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.get<SourceCatalogEntry[]>('/admin/data-catalog', authHeaders(token))
  return response.data
}

export async function fetchCatalogAvailabilitySummaries(token?: string): Promise<DataSourceAvailability[]> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.get<DataSourceAvailability[]>(
    '/admin/data-catalog/availability',
    authHeaders(token),
  )
  return response.data
}

export async function fetchDataSourceAvailability(
  catalogEntryId: string,
  token?: string,
): Promise<DataSourceAvailability> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.get<DataSourceAvailability>(
    `/admin/data-catalog/${catalogEntryId}/availability`,
    authHeaders(token),
  )
  return response.data
}

export async function updateGlobalAvailability(
  catalogEntryId: string,
  permissionLevel: PermissionLevel,
  token?: string,
): Promise<DataSourceAvailability> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.put<DataSourceAvailability>(
    `/admin/data-catalog/${catalogEntryId}/availability/global`,
    { permission_level: permissionLevel },
    authHeaders(token),
  )
  return response.data
}

export async function clearGlobalAvailability(
  catalogEntryId: string,
  token?: string,
): Promise<DataSourceAvailability> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.delete<DataSourceAvailability>(
    `/admin/data-catalog/${catalogEntryId}/availability/global`,
    authHeaders(token),
  )
  return response.data
}

export async function updateProjectAvailability(
  catalogEntryId: string,
  researchSpaceId: string,
  permissionLevel: PermissionLevel,
  token?: string,
): Promise<DataSourceAvailability> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.put<DataSourceAvailability>(
    `/admin/data-catalog/${catalogEntryId}/availability/research-spaces/${researchSpaceId}`,
    { permission_level: permissionLevel },
    authHeaders(token),
  )
  return response.data
}

export async function clearProjectAvailability(
  catalogEntryId: string,
  researchSpaceId: string,
  token?: string,
): Promise<DataSourceAvailability> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.delete<DataSourceAvailability>(
    `/admin/data-catalog/${catalogEntryId}/availability/research-spaces/${researchSpaceId}`,
    authHeaders(token),
  )
  return response.data
}

export async function bulkUpdateGlobalAvailability(
  payload: BulkActivationUpdateRequest,
  token?: string,
): Promise<DataSourceAvailability[]> {
  if (!token) throw new Error('Authentication token is required')

  const response = await apiClient.put<DataSourceAvailability[]>(
    '/admin/data-catalog/availability/global',
    payload,
    authHeaders(token),
  )
  return response.data
}
