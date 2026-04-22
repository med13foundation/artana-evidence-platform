import { apiGet, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'

export interface SourceCatalogAvailabilityRequest {
  is_active: boolean
}

export interface SpaceSourceAvailabilityRequest {
  enabled_source_ids: string[]
}

export async function fetchSourceCatalogAdmin(
  token?: string,
): Promise<SourceCatalogEntry[]> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceCatalogAdmin')
  }

  return apiGet<SourceCatalogEntry[]>('/admin/source-catalog', { token })
}

export async function updateSourceCatalogAvailability(
  catalogEntryId: string,
  payload: SourceCatalogAvailabilityRequest,
  token?: string,
): Promise<SourceCatalogEntry> {
  if (!token) {
    throw new Error('Authentication token is required for updateSourceCatalogAvailability')
  }

  return apiPut<SourceCatalogEntry>(
    `/admin/source-catalog/${catalogEntryId}/availability`,
    payload,
    { token },
  )
}

export async function fetchSpaceSourceAvailability(
  spaceId: string,
  token?: string,
): Promise<SpaceSourceAvailabilityRequest> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceSourceAvailability')
  }

  return apiGet<SpaceSourceAvailabilityRequest>(
    `/admin/research-spaces/${spaceId}/source-availability`,
    { token },
  )
}

export async function updateSpaceSourceAvailability(
  spaceId: string,
  payload: SpaceSourceAvailabilityRequest,
  token?: string,
): Promise<SpaceSourceAvailabilityRequest> {
  if (!token) {
    throw new Error('Authentication token is required for updateSpaceSourceAvailability')
  }

  return apiPut<SpaceSourceAvailabilityRequest>(
    `/admin/research-spaces/${spaceId}/source-availability`,
    payload,
    { token },
  )
}
