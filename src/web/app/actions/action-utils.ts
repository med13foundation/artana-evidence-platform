import type { AxiosError } from 'axios'
import { getServerSession } from 'next-auth'
import { buildPlaywrightSession, isPlaywrightE2EMode, isSessionExpired } from '@/lib/e2e/playwright-auth'
import { authOptions } from '@/lib/auth'

type IssueObject = {
  msg: string
  loc?: unknown
}

type MessageDetailObject = {
  message: string
  code?: string
}

function isIssueObject(value: unknown): value is IssueObject {
  return (
    typeof value === 'object' &&
    value !== null &&
    'msg' in value &&
    typeof (value as IssueObject).msg === 'string'
  )
}

function isMessageDetailObject(value: unknown): value is MessageDetailObject {
  return (
    typeof value === 'object' &&
    value !== null &&
    'message' in value &&
    typeof (value as MessageDetailObject).message === 'string'
  )
}

function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail
  }
  if (isMessageDetailObject(detail)) {
    if (typeof detail.code === 'string' && detail.code.trim().length > 0) {
      return `${detail.code}: ${detail.message}`
    }
    return detail.message
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

export function getActionErrorMessage(error: unknown, fallback: string): string {
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

export function getActionErrorStatus(error: unknown): number | undefined {
  const axiosError = error as AxiosError
  const status = axiosError.response?.status
  return typeof status === 'number' ? status : undefined
}

export async function requireAccessToken(): Promise<string> {
  const session = isPlaywrightE2EMode()
    ? buildPlaywrightSession()
    : await getServerSession(authOptions)
  const token = session?.user?.access_token
  const isExpired = isSessionExpired(session)
  if (!token || isExpired) {
    throw new Error('Session expired')
  }
  return token
}
