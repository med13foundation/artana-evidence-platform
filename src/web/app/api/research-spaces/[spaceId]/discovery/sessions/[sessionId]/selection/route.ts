import { NextResponse } from 'next/server'

import type { UpdateSelectionRequest } from '@/types/generated'

import {
  buildDiscoveryProxyHeaders,
  buildUpstreamUrl,
  readResponseBody,
  unauthorizedResponse,
} from '../../../_proxy'

interface DiscoverySelectionRouteContext {
  params: Promise<{
    spaceId: string
    sessionId: string
  }>
}

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(
  request: Request,
  context: DiscoverySelectionRouteContext,
): Promise<Response> {
  const { sessionId } = await context.params
  const upstreamUrl = buildUpstreamUrl(
    `/data-discovery/sessions/${encodeURIComponent(sessionId)}/selection`,
  )
  const upstreamHeaders = await buildDiscoveryProxyHeaders(upstreamUrl)
  if (!upstreamHeaders) {
    return unauthorizedResponse()
  }
  const payload = (await request.json()) as UpdateSelectionRequest

  const upstream = await fetch(upstreamUrl, {
    method: 'POST',
    headers: upstreamHeaders,
    body: JSON.stringify(payload),
    cache: 'no-store',
  })
  const responseBody = await readResponseBody(upstream)
  return new NextResponse(responseBody, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  })
}
