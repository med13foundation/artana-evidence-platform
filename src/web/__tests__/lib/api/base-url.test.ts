describe('resolveApiBaseUrl', () => {
  const originalApiBaseUrl = process.env.API_BASE_URL
  const originalInternalApiUrl = process.env.INTERNAL_API_URL
  const originalNextPublicApiUrl = process.env.NEXT_PUBLIC_API_URL
  const originalNextAuthUrl = process.env.NEXTAUTH_URL

  beforeEach(() => {
    jest.resetModules()
    delete process.env.API_BASE_URL
    delete process.env.INTERNAL_API_URL
    delete process.env.NEXT_PUBLIC_API_URL
    delete process.env.NEXTAUTH_URL
  })

  afterAll(() => {
    process.env.API_BASE_URL = originalApiBaseUrl
    process.env.INTERNAL_API_URL = originalInternalApiUrl
    process.env.NEXT_PUBLIC_API_URL = originalNextPublicApiUrl
    process.env.NEXTAUTH_URL = originalNextAuthUrl
  })

  it('prefers runtime API_BASE_URL over baked NEXT_PUBLIC_API_URL', async () => {
    process.env.API_BASE_URL = 'https://runtime-api.example.com'
    process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8080'

    const { resolveApiBaseUrl } = await import('@/lib/api/base-url')

    expect(resolveApiBaseUrl()).toBe('https://runtime-api.example.com')
  })

  it('falls back to NEXT_PUBLIC_API_URL when runtime API env vars are absent', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://public-api.example.com'

    const { resolveApiBaseUrl } = await import('@/lib/api/base-url')

    expect(resolveApiBaseUrl()).toBe('https://public-api.example.com')
  })

  it('ignores a localhost public API URL in the browser when running on a remote admin host', async () => {
    const { resolveBrowserApiBaseUrl } = await import('@/lib/api/base-url')

    expect(
      resolveBrowserApiBaseUrl(
        'artana-admin-staging-722972042617.us-central1.run.app',
        'http://localhost:8080',
      ),
    ).toBe(
      'https://artana-resource-library-staging-722972042617.us-central1.run.app',
    )
  })

  it('infers the API hostname from NEXTAUTH_URL when no explicit API URL is set', async () => {
    process.env.NEXTAUTH_URL =
      'https://artana-admin-staging-722972042617.us-central1.run.app'

    const { resolveApiBaseUrl } = await import('@/lib/api/base-url')

    expect(resolveApiBaseUrl()).toBe(
      'https://artana-resource-library-staging-722972042617.us-central1.run.app',
    )
  })
})
