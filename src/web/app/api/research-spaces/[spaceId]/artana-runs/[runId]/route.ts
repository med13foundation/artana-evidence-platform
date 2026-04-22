import { randomUUID } from 'crypto'
import { NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'

import { resolveApiBaseUrl } from '@/lib/api/base-url'
import { getCloudRunServiceAuthorization } from '@/lib/api/cloud-run-service-auth'
import { authOptions } from '@/lib/auth'

const API_BASE_URL = resolveApiBaseUrl()

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface SpaceArtanaRunRouteContext {
  params: Promise<{
    spaceId: string
    runId: string
  }>
}

export async function GET(
  _request: Request,
  context: SpaceArtanaRunRouteContext,
): Promise<Response> {
  const session = await getServerSession(authOptions)
  const token = session?.user?.access_token
  if (!token) {
    return new NextResponse(JSON.stringify({ detail: 'Authentication required' }), {
      status: 401,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }

  const { spaceId, runId } = await context.params
  const upstreamUrl = new URL(
    `/research-spaces/${spaceId}/artana-runs/${encodeURIComponent(runId)}`,
    API_BASE_URL,
  )
  const serviceAuthorization = await getCloudRunServiceAuthorization(upstreamUrl)
  const upstreamHeaders: HeadersInit = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/json',
    'X-Request-ID': randomUUID(),
  }
  if (serviceAuthorization) {
    upstreamHeaders['X-Serverless-Authorization'] = serviceAuthorization
  }

  const upstream = await fetch(upstreamUrl, {
    method: 'GET',
    headers: upstreamHeaders,
    cache: 'no-store',
  })
  const responseBody = await upstream.text()
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  })
}
