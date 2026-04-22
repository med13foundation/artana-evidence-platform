import { getServerSession } from 'next-auth'

import { GET as getSpaceWorkflowStream } from '@/app/api/research-spaces/[spaceId]/workflow-stream/route'
import { GET as getSourceWorkflowStream } from '@/app/api/research-spaces/[spaceId]/sources/[sourceId]/workflow-stream/route'

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

jest.mock('@/lib/auth', () => ({
  authOptions: {},
}))

describe('workflow stream proxy routes', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('returns 401 when no session token is present', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue(null)
    const request = new Request('http://localhost/api/research-spaces/space-1/workflow-stream')

    const response = await getSpaceWorkflowStream(request, {
      params: Promise.resolve({ spaceId: 'space-1' }),
    })

    expect(response.status).toBe(401)
  })

  it('proxies space stream response with SSE headers', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { access_token: 'token-1' },
    })
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'text/event-stream' }),
      body: 'event: heartbeat\ndata: {"ok":true}\n\n',
    } as unknown as Response)
    const request = new Request(
      'http://localhost/api/research-spaces/space-1/workflow-stream?source_ids=source-1',
    )

    const response = await getSpaceWorkflowStream(request, {
      params: Promise.resolve({ spaceId: 'space-1' }),
    })

    expect(response.status).toBe(200)
    expect(response.headers.get('Content-Type')).toBe('text/event-stream')
    expect(response.headers.get('X-Accel-Buffering')).toBe('no')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [upstreamUrl, upstreamInit] = fetchSpy.mock.calls[0]
    expect(String(upstreamUrl)).toContain('/research-spaces/space-1/workflow-stream')
    expect(String(upstreamUrl)).toContain('source_ids=source-1')
    expect((upstreamInit as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer token-1',
      Accept: 'text/event-stream',
    })
  })

  it('proxies source stream response with SSE headers', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { access_token: 'token-1' },
    })
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'text/event-stream' }),
      body: 'event: heartbeat\ndata: {"ok":true}\n\n',
    } as unknown as Response)
    const request = new Request(
      'http://localhost/api/research-spaces/space-1/sources/source-1/workflow-stream?run_id=run-1',
    )

    const response = await getSourceWorkflowStream(request, {
      params: Promise.resolve({ spaceId: 'space-1', sourceId: 'source-1' }),
    })

    expect(response.status).toBe(200)
    expect(response.headers.get('Content-Type')).toBe('text/event-stream')
    expect(response.headers.get('X-Accel-Buffering')).toBe('no')
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [upstreamUrl, upstreamInit] = fetchSpy.mock.calls[0]
    expect(String(upstreamUrl)).toContain('/research-spaces/space-1/sources/source-1/workflow-stream')
    expect(String(upstreamUrl)).toContain('run_id=run-1')
    expect((upstreamInit as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer token-1',
      Accept: 'text/event-stream',
    })
  })
})
