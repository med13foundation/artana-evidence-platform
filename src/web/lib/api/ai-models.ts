/**
 * API client for AI model configuration.
 */

import type { AvailableModelsResponse, ModelSpec } from '@/types/ai-models'

import { apiGet } from './client'

/**
 * Get all available AI models for data source configuration.
 */
export async function getAvailableModels(
  token?: string,
): Promise<AvailableModelsResponse> {
  return apiGet<AvailableModelsResponse>('/admin/ai-models', { token })
}

/**
 * Get models that support a specific capability.
 */
export async function getModelsForCapability(
  capability: string,
  token?: string,
): Promise<ModelSpec[]> {
  return apiGet<ModelSpec[]>(`/admin/ai-models/for-capability/${capability}`, {
    token,
  })
}
