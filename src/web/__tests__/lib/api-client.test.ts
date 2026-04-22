import type { AxiosError, AxiosRequestConfig, AxiosResponse } from 'axios'
import {
  createCancelableRequest,
  shouldRetryRequest,
  type CancelableRequest,
} from '@/lib/api/client'

const buildAxiosError = (params: {
  status?: number
  code?: string
  retryCount?: number
  message?: string
}): AxiosError => {
  const config = {
    url: '/test',
    __retryCount: params.retryCount,
  } as AxiosRequestConfig & { __retryCount?: number }

  const response = params.status
    ? ({
        status: params.status,
        statusText: 'error',
        headers: {},
        config,
        data: {},
      } as AxiosResponse)
    : undefined

  return {
    name: 'AxiosError',
    message: params.message ?? 'boom',
    config,
    code: params.code,
    response,
    isAxiosError: true,
    toJSON: () => ({}),
  } as AxiosError
}

describe('shouldRetryRequest', () => {
  it('returns true for retryable server status codes', () => {
    const error = buildAxiosError({ status: 503, retryCount: 0 })
    expect(shouldRetryRequest(error)).toBe(true)
  })

  it('returns false for non-retryable status codes', () => {
    const error = buildAxiosError({ status: 400, retryCount: 0 })
    expect(shouldRetryRequest(error)).toBe(false)
  })

  it('returns false when retry attempts exhausted', () => {
    const error = buildAxiosError({ status: 503, retryCount: 3 })
    expect(shouldRetryRequest(error)).toBe(false)
  })

  it('retries on transient network error codes', () => {
    const error = buildAxiosError({ code: 'ECONNABORTED', retryCount: 0 })
    expect(shouldRetryRequest(error)).toBe(true)
  })

  it('retries on connection reset errors', () => {
    const error = buildAxiosError({ code: 'ECONNRESET', retryCount: 0 })
    expect(shouldRetryRequest(error)).toBe(true)
  })

  it('retries when socket hang up message is returned without an error code', () => {
    const error = buildAxiosError({ message: 'socket hang up', retryCount: 0 })
    expect(shouldRetryRequest(error)).toBe(true)
  })
})

describe('createCancelableRequest', () => {
  it('aborts the request when cancel is invoked', async () => {
    const request: CancelableRequest<string> = createCancelableRequest(
      async (signal) =>
        new Promise((resolve, reject) => {
          if (signal.aborted) {
            reject(new Error('aborted'))
            return
          }
          signal.addEventListener('abort', () => reject(new Error('aborted')))
          setTimeout(() => resolve('ok'), 10)
        }),
    )

    request.cancel()

    await expect(request.promise).rejects.toThrow('aborted')
    expect(request.signal.aborted).toBe(true)
  })
})
