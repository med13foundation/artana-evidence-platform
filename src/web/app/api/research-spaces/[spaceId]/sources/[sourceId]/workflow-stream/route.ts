import { randomUUID } from 'crypto'
import { NextResponse } from 'next/server'
import { getServerSession } from 'next-auth'

import { authOptions } from '@/lib/auth'
import { resolveApiBaseUrl } from '@/lib/api/base-url'
import { getCloudRunServiceAuthorization } from '@/lib/api/cloud-run-service-auth'

const API_BASE_URL = resolveApiBaseUrl()

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

interface WorkflowStreamRouteContext {
  params: Promise<{
    spaceId: string
    sourceId: string
  }>
}

export async function GET(
  request: Request,
  context: WorkflowStreamRouteContext,
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

  const { spaceId, sourceId } = await context.params
  const upstreamUrl = new URL(
    `/research-spaces/${spaceId}/sources/${sourceId}/workflow-stream`,
    API_BASE_URL,
  )
  const requestUrl = new URL(request.url)
  requestUrl.searchParams.forEach((value, key) => {
    upstreamUrl.searchParams.append(key, value)
  })
  const serviceAuthorization = await getCloudRunServiceAuthorization(upstreamUrl)

  const upstreamHeaders: HeadersInit = {
    Authorization: `Bearer ${token}`,
    Accept: 'text/event-stream',
    'X-Request-ID': randomUUID(),
    Connection: 'keep-alive',
  }
  if (serviceAuthorization) {
    upstreamHeaders['X-Serverless-Authorization'] = serviceAuthorization
  }

  const upstream = await fetch(upstreamUrl, {
    method: 'GET',
    headers: upstreamHeaders,
    cache: 'no-store',
  })
  if (!upstream.ok) {
    const errorBody = await upstream.text()
    return new NextResponse(errorBody || 'Workflow stream proxy failed', {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') ?? 'text/plain',
      },
    })
  }
  if (upstream.body === null) {
    return new NextResponse('Workflow stream body unavailable', { status: 502 })
  }

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  })
}
