import 'server-only'

import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosRequestConfig,
  type AxiosResponse,
} from 'axios'
import { handleAuthError } from '@/lib/auth-error-handler'
import { resolveApiBaseUrl } from '@/lib/api/base-url'
import { getCloudRunServiceAuthorization } from '@/lib/api/cloud-run-service-auth'
const MAX_RETRY_ATTEMPTS = 3
const BASE_RETRY_DELAY_MS = 250
const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504])
const RETRYABLE_ERROR_CODES = new Set(['ECONNABORTED', 'ETIMEDOUT', 'ECONNRESET', 'EPIPE'])

const API_BASE_URL = resolveApiBaseUrl()

type RetryableConfig<T = unknown> = AxiosRequestConfig<T> & {
  __retryCount?: number
}

const delay = (ms: number) =>
  new Promise((resolve) => {
    setTimeout(resolve, ms)
  })

const generateRequestId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }

  return Math.random().toString(36).slice(2)
}

const calculateRetryDelay = (attempt: number) =>
  BASE_RETRY_DELAY_MS * 2 ** (attempt - 1)

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
  // Backend API calls are direct and should not traverse environment proxies.
  // This avoids Node.js DEP0169 warnings from proxy-from-env/url.parse on Node 24+.
  proxy: false,
})

apiClient.interceptors.request.use(async (config) => {
  const headers = AxiosHeaders.from(config.headers ?? {})

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (!headers.has('X-Request-ID')) {
    headers.set('X-Request-ID', generateRequestId())
  }

  const requestUrl = new URL(config.url ?? '', config.baseURL ?? API_BASE_URL)
  const serviceAuthorization = await getCloudRunServiceAuthorization(requestUrl)
  if (serviceAuthorization && !headers.has('X-Serverless-Authorization')) {
    // Preserve application-level Authorization headers for the API while
    // satisfying Cloud Run's service invoker check with a separate header.
    headers.set('X-Serverless-Authorization', serviceAuthorization)
  }

  config.headers = headers
  return config
})

export function shouldRetryRequest(error: AxiosError) {
  const config = error.config as RetryableConfig | undefined
  if (!config || config.signal?.aborted) {
    return false
  }

  const currentAttempts = config.__retryCount ?? 0
  if (currentAttempts >= MAX_RETRY_ATTEMPTS) {
    return false
  }

  const errorCode = error.code ?? ''
  const normalizedMessage = error.message.toLowerCase()
  const hasRetryableCode = RETRYABLE_ERROR_CODES.has(errorCode)
  const hasRetryableMessage =
    normalizedMessage.includes('socket hang up') ||
    normalizedMessage.includes('network error')

  if (hasRetryableCode || hasRetryableMessage) {
    return true
  }

  const status = error.response?.status
  return typeof status === 'number' && RETRYABLE_STATUS_CODES.has(status)
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config as RetryableConfig | undefined

    if (shouldRetryRequest(error) && config) {
      config.__retryCount = (config.__retryCount ?? 0) + 1
      const backoff = calculateRetryDelay(config.__retryCount)
      await delay(backoff)
      return apiClient.request(config)
    }

    if (error.response?.status === 401) {
      const errorDetail = error.response?.data?.detail || error.message

      if (process.env.NODE_ENV === 'development') {
        console.error('API request failed with 401 Unauthorized', {
          url: error.config?.url,
          message: errorDetail,
        })
      }

      await handleAuthError(errorDetail)
    }
    return Promise.reject(error)
  }
)

export function authHeaders(token?: string) {
  if (!token) {
    console.warn('[authHeaders] API call attempted without authentication token')
    throw new Error('Authentication token is required')
  }

  if (typeof token !== 'string') {
    console.error('[authHeaders] Token is not a string', {
      tokenType: typeof token,
      tokenValue: token,
      tokenStringified: JSON.stringify(token),
    })
    throw new Error(`Invalid token type: expected string, got ${typeof token}`)
  }

  if (token.length === 0) {
    console.error('[authHeaders] Token is empty string')
    throw new Error('Token cannot be empty')
  }

  const tokenParts = token.split('.')
  if (tokenParts.length !== 3) {
    console.error('[authHeaders] Invalid token format - expected JWT with 3 parts', {
      tokenLength: token.length,
      tokenPreview: token.substring(0, 50),
      partsCount: tokenParts.length,
      tokenType: typeof token,
    })
    throw new Error(`Invalid token format: expected JWT with 3 parts, got ${tokenParts.length}`)
  }

  return {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  }
}

export function withAuthenticatedRequest<T>(
  token: string | undefined,
  callback: (headers: ReturnType<typeof authHeaders>) => Promise<T>,
) {
  if (!token) {
    return Promise.reject(new Error('Authentication token is required'))
  }
  return callback(authHeaders(token))
}

type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface ApiRequestOptions<TResponse> extends Omit<AxiosRequestConfig<TResponse>, 'url' | 'method' | 'data'> {
  token?: string
}

function buildRequestConfig<TResponse>(
  method: HttpMethod,
  url: string,
  options?: ApiRequestOptions<TResponse>,
  data?: unknown,
): AxiosRequestConfig<TResponse> {
  const headers = { ...(options?.headers ?? {}) }

  if (options?.token) {
    Object.assign(headers, authHeaders(options.token).headers)
  }

  return {
    ...options,
    method,
    url,
    data: data as AxiosRequestConfig<TResponse>['data'],
    headers,
  }
}

async function sendRequest<TResponse>(
  method: HttpMethod,
  url: string,
  options?: ApiRequestOptions<TResponse>,
  data?: unknown,
): Promise<TResponse> {
  const config = buildRequestConfig<TResponse>(method, url, options, data)
  const response: AxiosResponse<TResponse> = await apiClient.request<TResponse>(config)
  return response.data
}

export const apiGet = <TResponse>(
  url: string,
  options?: ApiRequestOptions<TResponse>,
) => sendRequest<TResponse>('GET', url, options)

export const apiPost = <TResponse>(
  url: string,
  payload: unknown,
  options?: ApiRequestOptions<TResponse>,
) => sendRequest<TResponse>('POST', url, options, payload)

export const apiPut = <TResponse>(
  url: string,
  payload: unknown,
  options?: ApiRequestOptions<TResponse>,
) => sendRequest<TResponse>('PUT', url, options, payload)

export const apiPatch = <TResponse>(
  url: string,
  payload: unknown,
  options?: ApiRequestOptions<TResponse>,
) => sendRequest<TResponse>('PATCH', url, options, payload)

export const apiDelete = <TResponse>(
  url: string,
  options?: ApiRequestOptions<TResponse>,
) => sendRequest<TResponse>('DELETE', url, options)

export interface CancelableRequest<TResponse> {
  promise: Promise<TResponse>
  cancel: () => void
  signal: AbortSignal
}

export function createCancelableRequest<TResponse>(
  executor: (signal: AbortSignal) => Promise<TResponse>,
): CancelableRequest<TResponse> {
  const controller = new AbortController()
  const promise = executor(controller.signal)

  return {
    promise,
    signal: controller.signal,
    cancel: () => controller.abort(),
  }
}
