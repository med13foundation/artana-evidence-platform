describe('resolveGraphApiBaseUrl', () => {
  const env = process.env as Record<string, string | undefined>
  const originalGraphApiBaseUrl = process.env.GRAPH_API_BASE_URL
  const originalInternalGraphApiUrl = process.env.INTERNAL_GRAPH_API_URL
  const originalNextPublicGraphApiUrl = process.env.NEXT_PUBLIC_GRAPH_API_URL
  const originalNextAuthUrl = process.env.NEXTAUTH_URL
  const originalNodeEnv = process.env.NODE_ENV

  beforeEach(() => {
    jest.resetModules()
    delete process.env.GRAPH_API_BASE_URL
    delete process.env.INTERNAL_GRAPH_API_URL
    delete process.env.NEXT_PUBLIC_GRAPH_API_URL
    delete process.env.NEXTAUTH_URL
  })

  afterAll(() => {
    process.env.GRAPH_API_BASE_URL = originalGraphApiBaseUrl
    process.env.INTERNAL_GRAPH_API_URL = originalInternalGraphApiUrl
    process.env.NEXT_PUBLIC_GRAPH_API_URL = originalNextPublicGraphApiUrl
    process.env.NEXTAUTH_URL = originalNextAuthUrl
    env.NODE_ENV = originalNodeEnv
  })

  it('prefers runtime GRAPH_API_BASE_URL over public graph API env vars', async () => {
    process.env.GRAPH_API_BASE_URL = 'https://runtime-graph.example.com'
    process.env.NEXT_PUBLIC_GRAPH_API_URL = 'http://localhost:8090'

    const { resolveGraphApiBaseUrl } = await import('@/lib/api/graph-base-url')

    expect(resolveGraphApiBaseUrl()).toBe('https://runtime-graph.example.com')
  })

  it('falls back to NEXT_PUBLIC_GRAPH_API_URL when runtime graph env vars are absent', async () => {
    process.env.NEXT_PUBLIC_GRAPH_API_URL = 'https://public-graph.example.com'

    const { resolveGraphApiBaseUrl } = await import('@/lib/api/graph-base-url')

    expect(resolveGraphApiBaseUrl()).toBe('https://public-graph.example.com')
  })

  it('ignores a localhost public graph API URL in the browser when running on a remote admin host', async () => {
    const { resolveBrowserGraphApiBaseUrl } = await import('@/lib/api/graph-base-url')

    expect(
      resolveBrowserGraphApiBaseUrl(
        'artana-admin-staging-722972042617.us-central1.run.app',
        'http://localhost:8090',
      ),
    ).toBe(
      'https://artana-evidence-db-staging-722972042617.us-central1.run.app',
    )
  })

  it('infers the graph API hostname from NEXTAUTH_URL when no explicit graph API URL is set', async () => {
    process.env.NEXTAUTH_URL =
      'https://artana-admin-staging-722972042617.us-central1.run.app'

    const { resolveGraphApiBaseUrl } = await import('@/lib/api/graph-base-url')

    expect(resolveGraphApiBaseUrl()).toBe(
      'https://artana-evidence-db-staging-722972042617.us-central1.run.app',
    )
  })

  it('falls back to the local graph service port when no graph API config exists', async () => {
    const { resolveGraphApiBaseUrl } = await import('@/lib/api/graph-base-url')

    expect(resolveGraphApiBaseUrl()).toBe('http://localhost:8090')
  })

  it('requires explicit graph API config outside local development', async () => {
    env.NODE_ENV = 'production'

    const { resolveGraphApiBaseUrl } = await import('@/lib/api/graph-base-url')

    expect(() => resolveGraphApiBaseUrl()).toThrow(
      'NEXT_PUBLIC_GRAPH_API_URL is required outside local development',
    )
  })
})
