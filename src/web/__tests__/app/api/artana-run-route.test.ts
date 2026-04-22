import { getServerSession } from 'next-auth'

import { GET as getSpaceArtanaRun } from '@/app/api/research-spaces/[spaceId]/artana-runs/[runId]/route'

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

jest.mock('@/lib/auth', () => ({
  authOptions: {},
}))

describe('space Artana run proxy route', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('returns 401 when no session token is present', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue(null)
    const request = new Request('http://localhost/api/research-spaces/space-1/artana-runs/run-1')

    const response = await getSpaceArtanaRun(request, {
      params: Promise.resolve({ spaceId: 'space-1', runId: 'run-1' }),
    })

    expect(response.status).toBe(401)
  })

  it('proxies the research-space Artana trace response', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { access_token: 'token-1' },
    })
    const fetchSpy = jest.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      text: jest.fn().mockResolvedValue('{"run_id":"run-1"}'),
    } as unknown as Response)
    const request = new Request('http://localhost/api/research-spaces/space-1/artana-runs/run-1')

    const response = await getSpaceArtanaRun(request, {
      params: Promise.resolve({ spaceId: 'space-1', runId: 'run-1' }),
    })

    expect(response.status).toBe(200)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [upstreamUrl, upstreamInit] = fetchSpy.mock.calls[0]
    expect(String(upstreamUrl)).toContain('/research-spaces/space-1/artana-runs/run-1')
    expect((upstreamInit as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer token-1',
      Accept: 'application/json',
    })
  })
})
