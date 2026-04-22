"use server"

import { revalidatePath } from 'next/cache'
import {
  bulkUpdateGlobalAvailability,
  clearGlobalAvailability,
  clearProjectAvailability,
  fetchDataSourceAvailability,
  updateGlobalAvailability,
  updateProjectAvailability,
} from '@/lib/api/data-source-activation'
import type {
  DataSourceAvailability,
  PermissionLevel,
  BulkActivationUpdateRequest,
} from '@/lib/api/data-source-activation'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateAvailability() {
  revalidatePath('/system-settings')
}

export async function fetchCatalogAvailabilityAction(
  catalogEntryId: string,
): Promise<ActionResult<DataSourceAvailability>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchDataSourceAvailability(catalogEntryId, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchCatalogAvailability failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load catalog availability'),
    }
  }
}

export async function updateGlobalAvailabilityAction(
  catalogEntryId: string,
  permissionLevel: PermissionLevel,
): Promise<ActionResult<DataSourceAvailability>> {
  try {
    const token = await requireAccessToken()
    const response = await updateGlobalAvailability(catalogEntryId, permissionLevel, token)
    revalidateAvailability()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateGlobalAvailability failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update global availability'),
    }
  }
}

export async function clearGlobalAvailabilityAction(
  catalogEntryId: string,
): Promise<ActionResult<DataSourceAvailability>> {
  try {
    const token = await requireAccessToken()
    const response = await clearGlobalAvailability(catalogEntryId, token)
    revalidateAvailability()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] clearGlobalAvailability failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to reset global availability'),
    }
  }
}

export async function updateProjectAvailabilityAction(
  catalogEntryId: string,
  researchSpaceId: string,
  permissionLevel: PermissionLevel,
): Promise<ActionResult<DataSourceAvailability>> {
  try {
    const token = await requireAccessToken()
    const response = await updateProjectAvailability(
      catalogEntryId,
      researchSpaceId,
      permissionLevel,
      token,
    )
    revalidateAvailability()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateProjectAvailability failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update research space permission'),
    }
  }
}

export async function clearProjectAvailabilityAction(
  catalogEntryId: string,
  researchSpaceId: string,
): Promise<ActionResult<DataSourceAvailability>> {
  try {
    const token = await requireAccessToken()
    const response = await clearProjectAvailability(catalogEntryId, researchSpaceId, token)
    revalidateAvailability()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] clearProjectAvailability failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to remove project override'),
    }
  }
}

export async function bulkUpdateGlobalAvailabilityAction(
  payload: BulkActivationUpdateRequest,
): Promise<ActionResult<DataSourceAvailability[]>> {
  try {
    const token = await requireAccessToken()
    const response = await bulkUpdateGlobalAvailability(payload, token)
    revalidateAvailability()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] bulkUpdateGlobalAvailability failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update availability'),
    }
  }
}
