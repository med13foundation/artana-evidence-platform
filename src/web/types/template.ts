"use client"

import type { SourceType } from '@/types/data-source'

export type TemplateScope = 'available' | 'public' | 'mine'

export type TemplateCategory =
  | 'clinical'
  | 'research'
  | 'literature'
  | 'genomic'
  | 'phenotypic'
  | 'ontology'
  | 'other'

export interface TemplateResponse {
  id: string
  created_by: string
  name: string
  description: string
  category: TemplateCategory
  source_type: SourceType
  schema_definition: Record<string, unknown>
  validation_rules: TemplateValidationRule[]
  ui_config: Record<string, unknown>
  is_public: boolean
  is_approved: boolean
  approval_required: boolean
  usage_count: number
  success_rate: number
  created_at: string
  updated_at: string
  approved_at?: string | null
  tags: string[]
  version: string
  compatibility_version: string
}

export interface TemplateListResponse {
  templates: TemplateResponse[]
  total: number
  page: number
  limit: number
  scope: TemplateScope
}

export interface TemplateCreatePayload {
  name: string
  description?: string
  category?: TemplateCategory
  source_type: SourceType
  schema_definition: Record<string, unknown>
  validation_rules?: TemplateValidationRule[]
  ui_config?: Record<string, unknown>
  tags?: string[]
  is_public?: boolean
}

export interface TemplateUpdatePayload {
  templateId: string
  data: {
    name?: string | null
    description?: string | null
    category?: TemplateCategory | null
    schema_definition?: Record<string, unknown> | null
    validation_rules?: TemplateValidationRule[] | null
    ui_config?: Record<string, unknown> | null
    tags?: string[] | null
  }
}

export interface TemplateValidationRule {
  field: string
  rule_type: string
  parameters: Record<string, unknown>
  error_message: string
}
