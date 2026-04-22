"use server"

import { revalidatePath } from 'next/cache'
import { getAvailableModels, getModelsForCapability } from '@/lib/api/ai-models'
import {
  configureDataSourceSchedule,
  createDataSourceInSpace,
  deleteDataSource,
  fetchIngestionJobHistory,
  testDataSourceAiConfiguration,
  updateDataSource,
} from '@/lib/api/data-sources'
import type {
  DataSource,
} from '@/types/data-source'
import type {
  DataSourceAiTestResult,
  IngestionJobHistoryResponse,
  ScheduleConfigurationPayload,
  ScheduleConfigurationResponse,
  UpdateDataSourcePayload,
} from '@/lib/api/data-sources'
import type { AvailableModelsResponse, ModelSpec } from '@/types/ai-models'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidatePaths(paths: string[]) {
  paths.forEach((path) => revalidatePath(path))
}

function getSpacePaths(spaceId?: string | null): string[] {
  if (!spaceId) {
    return []
  }
  return [`/spaces/${spaceId}/data-sources`, `/spaces/${spaceId}`]
}

export async function createDataSourceInSpaceAction(
  spaceId: string,
  payload: {
    name: string
    description?: string
    source_type: string
    config: Record<string, unknown>
    tags?: string[]
  },
): Promise<ActionResult<DataSource>> {
  try {
    const token = await requireAccessToken()
    const source = await createDataSourceInSpace(spaceId, payload, token)
    revalidatePaths(getSpacePaths(spaceId))
    return { success: true, data: source }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createDataSourceInSpace failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create data source'),
    }
  }
}

export async function updateDataSourceAction(
  sourceId: string,
  payload: UpdateDataSourcePayload,
  spaceId?: string | null,
): Promise<ActionResult<DataSource>> {
  try {
    const token = await requireAccessToken()
    const source = await updateDataSource(sourceId, payload, token)
    revalidatePaths(getSpacePaths(spaceId))
    return { success: true, data: source }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateDataSource failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update data source'),
    }
  }
}

export async function configureDataSourceScheduleAction(
  sourceId: string,
  payload: ScheduleConfigurationPayload,
  spaceId?: string | null,
): Promise<ActionResult<ScheduleConfigurationResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await configureDataSourceSchedule(sourceId, payload, token)
    revalidatePaths(getSpacePaths(spaceId))
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] configureDataSourceSchedule failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to configure ingestion schedule'),
    }
  }
}

export async function testDataSourceAiConfigurationAction(
  sourceId: string,
): Promise<ActionResult<DataSourceAiTestResult>> {
  try {
    const token = await requireAccessToken()
    const result = await testDataSourceAiConfiguration(sourceId, token)
    return { success: true, data: result }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] testDataSourceAiConfiguration failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Unable to test AI configuration'),
    }
  }
}

export async function deleteDataSourceAction(
  sourceId: string,
  spaceId?: string | null,
): Promise<ActionResult<{ id: string }>> {
  try {
    const token = await requireAccessToken()
    await deleteDataSource(sourceId, token)
    revalidatePaths(getSpacePaths(spaceId))
    return { success: true, data: { id: sourceId } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteDataSource failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete data source'),
    }
  }
}

export async function fetchIngestionJobHistoryAction(
  sourceId: string,
  limit = 10,
): Promise<ActionResult<IngestionJobHistoryResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await fetchIngestionJobHistory(sourceId, token, { limit })
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchIngestionJobHistory failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load ingestion history'),
    }
  }
}

export async function fetchAvailableModelsAction(): Promise<ActionResult<AvailableModelsResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await getAvailableModels(token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchAvailableModelsAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load available models'),
    }
  }
}

export async function fetchModelsForCapabilityAction(
  capability: string,
): Promise<ActionResult<ModelSpec[]>> {
  try {
    const token = await requireAccessToken()
    const response = await getModelsForCapability(capability, token)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] fetchModelsForCapabilityAction failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to load models for capability'),
    }
  }
}
