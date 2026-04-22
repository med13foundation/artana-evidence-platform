import { apiDelete, apiGet, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import type {
  TemplateCreatePayload,
  TemplateListResponse,
  TemplateResponse,
  TemplateScope,
  TemplateUpdatePayload,
} from '@/types/template'

export async function fetchTemplates(scope: TemplateScope = 'available', token?: string) {
  return apiGet<TemplateListResponse>(`/admin/templates?scope=${scope}`, { token })
}

export async function fetchTemplate(templateId: string, token?: string) {
  return apiGet<TemplateResponse>(`/admin/templates/${templateId}`, { token })
}

export async function createTemplate(payload: TemplateCreatePayload, token?: string) {
  return apiPost<TemplateResponse>('/admin/templates', payload, { token })
}

export async function updateTemplate({ templateId, data }: TemplateUpdatePayload, token?: string) {
  return apiPut<TemplateResponse>(`/admin/templates/${templateId}`, data, { token })
}

export async function deleteTemplate(templateId: string, token?: string) {
  return apiDelete<void>(`/admin/templates/${templateId}`, { token })
}

export async function publishTemplate(templateId: string, token?: string) {
  return apiPost<TemplateResponse>(`/admin/templates/${templateId}/public`, {}, { token })
}

export async function approveTemplate(templateId: string, token?: string) {
  return apiPost<TemplateResponse>(`/admin/templates/${templateId}/approve`, {}, { token })
}
