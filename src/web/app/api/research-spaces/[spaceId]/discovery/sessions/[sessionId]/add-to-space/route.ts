import { NextResponse } from 'next/server'

import type { AddToSpaceRequest } from '@/types/generated'

import {
  buildDiscoveryProxyHeaders,
  buildUpstreamUrl,
  readResponseBody,
  unauthorizedResponse,
} from '../../../_proxy'

interface DiscoveryAddToSpaceRouteContext {
  params: Promise<{
    spaceId: string
    sessionId: string
  }>
}

type AddToSpaceBatchRequest = {
  source_ids: string[]
}

type AddToSpaceBatchResponse = {
  added_count: number
  data_source_ids: string[]
}

type AddToSpaceSuccessResponse = {
  data_source_id: string
}

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(
  request: Request,
  context: DiscoveryAddToSpaceRouteContext,
): Promise<Response> {
  const { spaceId, sessionId } = await context.params
  const upstreamUrl = buildUpstreamUrl(
    `/data-discovery/sessions/${encodeURIComponent(sessionId)}/add-to-space`,
  )
  const upstreamHeaders = await buildDiscoveryProxyHeaders(upstreamUrl)
  if (!upstreamHeaders) {
    return unauthorizedResponse()
  }
  const payload = (await request.json()) as AddToSpaceBatchRequest

  const results = await Promise.all(
    payload.source_ids.map(async (sourceId) => {
      const upstreamPayload: AddToSpaceRequest = {
        catalog_entry_id: sourceId,
        research_space_id: spaceId,
        source_config: {},
      }
      const upstream = await fetch(upstreamUrl, {
        method: 'POST',
        headers: upstreamHeaders,
        body: JSON.stringify(upstreamPayload),
        cache: 'no-store',
      })
      const responseBody = await readResponseBody(upstream)
      return { upstream, responseBody }
    }),
  )

  const failed = results.find(({ upstream }) => !upstream.ok)
  if (failed) {
    return new NextResponse(failed.responseBody, {
      status: failed.upstream.status,
      headers: {
        'Content-Type': failed.upstream.headers.get('Content-Type') ?? 'application/json',
      },
    })
  }

  const dataSourceIds = results.flatMap(({ responseBody }) => {
    const parsed = JSON.parse(responseBody) as AddToSpaceSuccessResponse
    return typeof parsed.data_source_id === 'string' ? [parsed.data_source_id] : []
  })
  const responseBody = JSON.stringify({
    added_count: dataSourceIds.length,
    data_source_ids: dataSourceIds,
  } satisfies AddToSpaceBatchResponse)

  return new NextResponse(responseBody, {
    status: 201,
    headers: {
      'Content-Type': 'application/json',
    },
  })
}
