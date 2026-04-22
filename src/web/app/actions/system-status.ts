"use server"

import { revalidatePath } from 'next/cache'
import { disableMaintenanceMode, enableMaintenanceMode } from '@/lib/api/system-status'
import type { EnableMaintenanceRequest, MaintenanceModeResponse } from '@/types/system-status'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

export async function enableMaintenanceAction(
  payload: EnableMaintenanceRequest,
): Promise<ActionResult<MaintenanceModeResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await enableMaintenanceMode(payload, token)
    revalidatePath('/system-settings')
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] enableMaintenance failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to enable maintenance mode'),
    }
  }
}

export async function disableMaintenanceAction(): Promise<ActionResult<MaintenanceModeResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await disableMaintenanceMode(token)
    revalidatePath('/system-settings')
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] disableMaintenance failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to disable maintenance mode'),
    }
  }
}
