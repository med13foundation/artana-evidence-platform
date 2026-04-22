import { getServerSession } from 'next-auth'

import { POST as postAddToSpace } from '@/app/api/research-spaces/[spaceId]/discovery/sessions/[sessionId]/add-to-space/route'
import { POST as postSelection } from '@/app/api/research-spaces/[spaceId]/discovery/sessions/[sessionId]/selection/route'

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

jest.mock('@/lib/auth', () => ({
  authOptions: {},
}))

describe('space discovery proxy routes', () => {
  const buildJsonRequest = (body: unknown): Request =>
    ({
      json: jest.fn().mockResolvedValue(body),
    }) as unknown as Request

  beforeEach(() => {
    jest.clearAllMocks()
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('returns 401 for selection updates without a session token', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue(null)
    const request = buildJsonRequest({ source_ids: ['pubmed'] })

    const response = await postSelection(request, {
      params: Promise.resolve({ spaceId: 'space-1', sessionId: 'session-1' }),
    })

    expect(response.status).toBe(401)
  })

  it('proxies selection updates to the backend session endpoint', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { access_token: 'token-1' },
    })
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      status: 200,
      ok: true,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      text: jest.fn().mockResolvedValue('{"session":{"id":"session-1"}}'),
    } as unknown as Response)
    const request = buildJsonRequest({ source_ids: ['pubmed'] })

    const response = await postSelection(request, {
      params: Promise.resolve({ spaceId: 'space-1', sessionId: 'session-1' }),
    })

    expect(response.status).toBe(200)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [upstreamUrl, upstreamInit] = fetchSpy.mock.calls[0]
    expect(String(upstreamUrl)).toContain('/data-discovery/sessions/session-1/selection')
    expect((upstreamInit as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer token-1',
      Accept: 'application/json',
    })
  })

  it('aggregates add-to-space requests for multiple selected sources', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { access_token: 'token-1' },
    })
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      status: 201,
      ok: true,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      text: jest.fn().mockResolvedValue('{"data_source_id":"source-row-1"}'),
    } as unknown as Response)
    const request = buildJsonRequest({ source_ids: ['pubmed', 'clinvar'] })

    const response = await postAddToSpace(request, {
      params: Promise.resolve({ spaceId: 'space-1', sessionId: 'session-1' }),
    })

    expect(response.status).toBe(201)
    expect(fetchSpy).toHaveBeenCalledTimes(2)
  })
})
