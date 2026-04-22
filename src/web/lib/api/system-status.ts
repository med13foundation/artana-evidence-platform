import { apiGet, apiPost } from '@/lib/api/client'
import type {
  EnableMaintenanceRequest,
  MaintenanceModeResponse,
} from '@/types/system-status'

const withToken = (token?: string) => {
  if (!token) {
    throw new Error('Authentication token is required for maintenance operations')
  }
  return { token }
}

export async function fetchMaintenanceState(token?: string) {
  return apiGet<MaintenanceModeResponse>(
    '/admin/system/maintenance',
    withToken(token),
  )
}

export async function enableMaintenanceMode(
  payload: EnableMaintenanceRequest,
  token?: string,
) {
  return apiPost<MaintenanceModeResponse>(
    '/admin/system/maintenance/enable',
    payload,
    withToken(token),
  )
}

export async function disableMaintenanceMode(token?: string) {
  return apiPost<MaintenanceModeResponse>(
    '/admin/system/maintenance/disable',
    {},
    withToken(token),
  )
}
