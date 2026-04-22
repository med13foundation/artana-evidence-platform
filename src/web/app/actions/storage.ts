"use server"

import { revalidatePath } from 'next/cache'
import { isPlaywrightE2EMode } from '@/lib/e2e/playwright-auth'
import {
  createPlaywrightStorageConfiguration,
  deletePlaywrightStorageConfiguration,
  getPlaywrightStorageHealth,
  getPlaywrightStorageMetrics,
  testPlaywrightStorageConfiguration,
  updatePlaywrightStorageConfiguration,
} from '@/lib/e2e/playwright-fixtures'
import {
  createStorageConfiguration,
  deleteStorageConfiguration,
  fetchStorageHealth,
  fetchStorageMetrics,
  testStorageConfiguration,
  updateStorageConfiguration,
} from '@/lib/api/storage'
import type {
  CreateStorageConfigurationRequest,
  StorageConfiguration,
  StorageHealthReport,
  StorageProviderTestResult,
  StorageUsageMetrics,
  UpdateStorageConfigurationRequest,
} from '@/types/storage'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateStorage() {
  revalidatePath('/system-settings')
}

export async function createStorageConfigurationAction(
  payload: CreateStorageConfigurationRequest,
): Promise<ActionResult<StorageConfiguration>> {
  try {
    if (isPlaywrightE2EMode()) {
      const response = createPlaywrightStorageConfiguration(payload)
      revalidateStorage()
      return { success: true, data: response }
    }
    const token = await requireAccessToken()
    const response = await createStorageConfiguration(payload, token)
    revalidateStorage()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createStorageConfiguration failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create storage configuration'),
    }
  }
}

export async function updateStorageConfigurationAction(
  configurationId: string,
  payload: UpdateStorageConfigurationRequest,
): Promise<ActionResult<StorageConfiguration>> {
  try {
    if (isPlaywrightE2EMode()) {
      const response = updatePlaywrightStorageConfiguration(configurationId, payload)
      revalidateStorage()
      return { success: true, data: response }
    }
    const token = await requireAccessToken()
    const response = await updateStorageConfiguration(configurationId, payload, token)
    revalidateStorage()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateStorageConfiguration failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update storage configuration'),
    }
  }
}

export async function deleteStorageConfigurationAction(
  configurationId: string,
  force: boolean,
): Promise<ActionResult<{ message: string }>> {
  try {
    if (isPlaywrightE2EMode()) {
      const response = deletePlaywrightStorageConfiguration(configurationId, force)
      revalidateStorage()
      return { success: true, data: response }
    }
    const token = await requireAccessToken()
    const response = await deleteStorageConfiguration(configurationId, force, token)
    revalidateStorage()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteStorageConfiguration failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete storage configuration'),
    }
  }
}

export async function testStorageConfigurationAction(
  configurationId: string,
): Promise<ActionResult<StorageProviderTestResult>> {
  try {
    if (isPlaywrightE2EMode()) {
      const response = testPlaywrightStorageConfiguration(configurationId)
      revalidateStorage()
      return { success: true, data: response }
    }
    const token = await requireAccessToken()
    const response = await testStorageConfiguration(configurationId, token)
    revalidateStorage()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] testStorageConfiguration failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to test storage configuration'),
    }
  }
}

export async function fetchStorageMetricsAction(
  configurationId: string,
): Promise<ActionResult<StorageUsageMetrics | null>> {
  try {
    if (isPlaywrightE2EMode()) {
      return { success: true, data: getPlaywrightStorageMetrics(configurationId) }
    }
    const token = await requireAccessToken()
    const response = await fetchStorageMetrics(configurationId, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchStorageMetrics failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load storage metrics'),
    }
  }
}

export async function fetchStorageHealthAction(
  configurationId: string,
): Promise<ActionResult<StorageHealthReport | null>> {
  try {
    if (isPlaywrightE2EMode()) {
      return { success: true, data: getPlaywrightStorageHealth(configurationId) }
    }
    const token = await requireAccessToken()
    const response = await fetchStorageHealth(configurationId, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchStorageHealth failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load storage health'),
    }
  }
}
