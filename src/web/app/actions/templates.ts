"use server"

import { revalidatePath } from 'next/cache'
import {
  approveTemplate,
  createTemplate,
  deleteTemplate,
  publishTemplate,
  updateTemplate,
} from '@/lib/api/templates'
import type {
  TemplateCreatePayload,
  TemplateResponse,
  TemplateUpdatePayload,
} from '@/types/template'
import { getActionErrorMessage, requireAccessToken } from '@/app/actions/action-utils'

type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string }

function revalidateTemplates() {
  revalidatePath('/admin/data-sources/templates')
}

export async function createTemplateAction(
  payload: TemplateCreatePayload,
): Promise<ActionResult<TemplateResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await createTemplate(payload, token)
    revalidateTemplates()
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] createTemplate failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to create template'),
    }
  }
}

export async function updateTemplateAction(
  payload: TemplateUpdatePayload,
): Promise<ActionResult<TemplateResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await updateTemplate(payload, token)
    revalidateTemplates()
    revalidatePath(`/admin/data-sources/templates/${payload.templateId}`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] updateTemplate failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to update template'),
    }
  }
}

export async function deleteTemplateAction(
  templateId: string,
): Promise<ActionResult<{ id: string }>> {
  try {
    const token = await requireAccessToken()
    await deleteTemplate(templateId, token)
    revalidateTemplates()
    return { success: true, data: { id: templateId } }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] deleteTemplate failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to delete template'),
    }
  }
}

export async function approveTemplateAction(
  templateId: string,
): Promise<ActionResult<TemplateResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await approveTemplate(templateId, token)
    revalidateTemplates()
    revalidatePath(`/admin/data-sources/templates/${templateId}`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] approveTemplate failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to approve template'),
    }
  }
}

export async function publishTemplateAction(
  templateId: string,
): Promise<ActionResult<TemplateResponse>> {
  try {
    const token = await requireAccessToken()
    const response = await publishTemplate(templateId, token)
    revalidateTemplates()
    revalidatePath(`/admin/data-sources/templates/${templateId}`)
    return { success: true, data: response }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] publishTemplate failed:', error)
    }
    return {
      success: false,
      error: getActionErrorMessage(error, 'Failed to publish template'),
    }
  }
}
