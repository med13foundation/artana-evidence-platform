describe('getCloudRunServiceAuthorization', () => {
  const originalEnv = {
    kService: process.env.K_SERVICE,
    kRevision: process.env.K_REVISION,
    kConfiguration: process.env.K_CONFIGURATION,
    enable: process.env.ARTANA_ENABLE_CLOUD_RUN_SERVICE_AUTH,
    disable: process.env.ARTANA_DISABLE_CLOUD_RUN_SERVICE_AUTH,
    audience: process.env.ARTANA_CLOUD_RUN_SERVICE_AUTH_AUDIENCE,
  }
  const originalFetch = global.fetch

  beforeEach(() => {
    jest.resetModules()
    delete process.env.K_SERVICE
    delete process.env.K_REVISION
    delete process.env.K_CONFIGURATION
    delete process.env.ARTANA_ENABLE_CLOUD_RUN_SERVICE_AUTH
    delete process.env.ARTANA_DISABLE_CLOUD_RUN_SERVICE_AUTH
    delete process.env.ARTANA_CLOUD_RUN_SERVICE_AUTH_AUDIENCE
    global.fetch = jest.fn()
  })

  afterAll(() => {
    process.env.K_SERVICE = originalEnv.kService
    process.env.K_REVISION = originalEnv.kRevision
    process.env.K_CONFIGURATION = originalEnv.kConfiguration
    process.env.ARTANA_ENABLE_CLOUD_RUN_SERVICE_AUTH = originalEnv.enable
    process.env.ARTANA_DISABLE_CLOUD_RUN_SERVICE_AUTH = originalEnv.disable
    process.env.ARTANA_CLOUD_RUN_SERVICE_AUTH_AUDIENCE = originalEnv.audience
    global.fetch = originalFetch
  })

  it('returns null outside Cloud Run runtime', async () => {
    const { getCloudRunServiceAuthorization } = await import(
      '@/lib/api/cloud-run-service-auth'
    )

    await expect(
      getCloudRunServiceAuthorization('https://artana-resource-library-staging.example.run.app'),
    ).resolves.toBeNull()
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('returns null for localhost targets even when service auth is enabled', async () => {
    process.env.K_SERVICE = 'artana-admin-staging'

    const { getCloudRunServiceAuthorization } = await import(
      '@/lib/api/cloud-run-service-auth'
    )

    await expect(
      getCloudRunServiceAuthorization('http://localhost:8080/auth/register'),
    ).resolves.toBeNull()
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('fetches and caches a Cloud Run identity token for remote targets', async () => {
    process.env.K_SERVICE = 'artana-admin-staging'
    const jwtPayload = Buffer.from(
      JSON.stringify({
        exp: Math.floor((Date.now() + 60 * 60 * 1000) / 1000),
      }),
      'utf8',
    )
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/g, '')
    const identityToken = `header.${jwtPayload}.signature`

    ;(global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      text: async () => identityToken,
    })

    const {
      clearCloudRunServiceAuthCache,
      getCloudRunServiceAuthorization,
    } = await import('@/lib/api/cloud-run-service-auth')

    const targetUrl = 'https://artana-resource-library-staging.example.run.app/auth/register'
    await expect(getCloudRunServiceAuthorization(targetUrl)).resolves.toBe(
      `Bearer ${identityToken}`,
    )
    await expect(getCloudRunServiceAuthorization(targetUrl)).resolves.toBe(
      `Bearer ${identityToken}`,
    )

    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch).toHaveBeenCalledWith(
      expect.objectContaining({
        href:
          'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=https%3A%2F%2Fartana-resource-library-staging.example.run.app&format=full',
      }),
      expect.objectContaining({
        headers: {
          'Metadata-Flavor': 'Google',
        },
        cache: 'no-store',
      }),
    )

    clearCloudRunServiceAuthCache()
  })
})
