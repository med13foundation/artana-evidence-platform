"use server"

import type { AxiosError } from 'axios'
import { apiClient } from '@/lib/api/client'
import type { ForgotPasswordRequest, RegisterRequest } from '@/types/auth'

interface GenericSuccessResponse {
  message: string
}

type AuthActionResult =
  | { success: true; message: string }
  | { success: false; error: string }

type IssueObject = {
  msg: string
  loc?: unknown
}

function isIssueObject(value: unknown): value is IssueObject {
  return (
    typeof value === 'object' &&
    value !== null &&
    'msg' in value &&
    typeof (value as IssueObject).msg === 'string'
  )
}

function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail
  }
  if (isIssueObject(detail)) {
    const location = Array.isArray(detail.loc) ? detail.loc.join('.') : ''
    return location ? `${location}: ${detail.msg}` : detail.msg
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue) => formatErrorDetail(issue))
      .filter((value): value is string => Boolean(value))
    return messages.length > 0 ? messages.join('; ') : null
  }
  return null
}

function getErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<{ detail?: unknown }>
  const detail = axiosError.response?.data?.detail
  const formatted = formatErrorDetail(detail)
  if (formatted) {
    return formatted
  }
  if (axiosError?.message) {
    return axiosError.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return fallback
}

export async function registerUser(payload: RegisterRequest): Promise<AuthActionResult> {
  try {
    const response = await apiClient.post<GenericSuccessResponse>('/auth/register', payload)
    return { success: true, message: response.data.message }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] registerUser failed:', error)
    }
    return { success: false, error: getErrorMessage(error, 'Registration failed') }
  }
}

export async function requestPasswordReset(email: string): Promise<AuthActionResult> {
  const payload: ForgotPasswordRequest = { email }
  try {
    const response = await apiClient.post<GenericSuccessResponse>('/auth/forgot-password', payload)
    return { success: true, message: response.data.message }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== 'test') {
      console.error('[ServerAction] requestPasswordReset failed:', error)
    }
    return { success: false, error: getErrorMessage(error, 'Failed to send reset email') }
  }
}
