import { randomUUID } from 'crypto'
import { NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'

import { resolveApiBaseUrl } from '@/lib/api/base-url'
import { getCloudRunServiceAuthorization } from '@/lib/api/cloud-run-service-auth'
import { authOptions } from '@/lib/auth'

const API_BASE_URL = resolveApiBaseUrl()

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function buildDiscoveryProxyHeaders(
  upstreamUrl: URL,
): Promise<HeadersInit | null> {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token
  if (!token) {
    return null
  }

  const serviceAuthorization = await getCloudRunServiceAuthorization(upstreamUrl)
  const upstreamHeaders: HeadersInit = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'X-Request-ID': randomUUID(),
  }
  if (serviceAuthorization) {
    upstreamHeaders['X-Serverless-Authorization'] = serviceAuthorization
  }

  return upstreamHeaders
}

export function unauthorizedResponse(): NextResponse {
  return new NextResponse(JSON.stringify({ detail: 'Authentication required' }), {
    status: 401,
    headers: {
      'Content-Type': 'application/json',
    },
  })
}

export function buildUpstreamUrl(pathname: string): URL {
  return new URL(pathname, API_BASE_URL)
}

export async function readResponseBody(response: Response): Promise<string> {
  return response.text()
}
