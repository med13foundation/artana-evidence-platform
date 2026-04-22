/**
 * TypeScript types for AI model configuration.
 *
 * These types mirror the backend Pydantic models for the AI models API.
 */

export type ModelCostTier = 'low' | 'medium' | 'high'

export type ModelCapability =
  | 'query_generation'
  | 'evidence_extraction'
  | 'curation'
  | 'judge'

export interface ModelSpec {
  model_id: string
  display_name: string
  provider: string
  capabilities: ModelCapability[]
  cost_tier: ModelCostTier
  is_reasoning_model: boolean
  is_default: boolean
}

export interface AvailableModelsResponse {
  models: ModelSpec[]
  default_query_model: string
}
