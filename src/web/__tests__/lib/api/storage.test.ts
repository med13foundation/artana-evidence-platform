import {
  apiDelete,
  apiGet,
  apiPost,
  apiPut,
} from '@/lib/api/client'
import {
  createStorageConfiguration,
  deleteStorageConfiguration,
  fetchStorageConfigurations,
  fetchStorageHealth,
  fetchStorageMetrics,
  fetchStorageOperations,
  fetchStorageOverview,
  testStorageConfiguration,
  updateStorageConfiguration,
} from '@/lib/api/storage'
import type {
  CreateStorageConfigurationRequest,
  StorageConfiguration,
  StorageConfigurationListResponse,
  StorageHealthReport,
  StorageOverviewResponse,
  StorageProviderTestResult,
  StorageUsageMetrics,
  UpdateStorageConfigurationRequest,
} from '@/types/storage'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
  apiPut: jest.fn(),
  apiDelete: jest.fn(),
}))

const TOKEN = 'admin-token'

const mockConfiguration: StorageConfiguration = {
  id: 'config-1',
  name: 'Local storage',
  provider: 'local_filesystem',
  config: {
    provider: 'local_filesystem',
    base_path: '/data/storage',
    create_directories: true,
    expose_file_urls: false,
  },
  enabled: true,
  supported_capabilities: ['read', 'write'],
  default_use_cases: ['raw_source'],
  metadata: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

const mockListResponse: StorageConfigurationListResponse = {
  data: [mockConfiguration],
  total: 1,
  page: 1,
  per_page: 100,
}

const mockOverviewResponse: StorageOverviewResponse = {
  generated_at: new Date().toISOString(),
  totals: {
    total_configurations: 1,
    enabled_configurations: 1,
    disabled_configurations: 0,
    healthy_configurations: 1,
    degraded_configurations: 0,
    offline_configurations: 0,
    total_files: 0,
    total_size_bytes: 0,
    average_error_rate: 0,
  },
  configurations: [],
}

const mockMetrics: StorageUsageMetrics = {
  configuration_id: mockConfiguration.id,
  total_files: 0,
  total_size_bytes: 0,
}

const mockHealth: StorageHealthReport = {
  configuration_id: mockConfiguration.id,
  provider: mockConfiguration.provider,
  status: 'healthy',
  last_checked_at: new Date().toISOString(),
  details: {},
}

const mockTestResult: StorageProviderTestResult = {
  configuration_id: mockConfiguration.id,
  provider: mockConfiguration.provider,
  success: true,
  checked_at: new Date().toISOString(),
  capabilities: ['read', 'write'],
  metadata: {},
}

describe('storage api', () => {
  const mockApiGet = apiGet as jest.MockedFunction<typeof apiGet>
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>
  const mockApiPut = apiPut as jest.MockedFunction<typeof apiPut>
  const mockApiDelete = apiDelete as jest.MockedFunction<typeof apiDelete>

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('fetchStorageConfigurations builds query and includes token', async () => {
    mockApiGet.mockResolvedValue(mockListResponse)

    await fetchStorageConfigurations(
      { page: 1, per_page: 100, include_disabled: true },
      TOKEN,
    )

    expect(mockApiGet).toHaveBeenCalledWith(
      '/admin/storage/configurations?page=1&per_page=100&include_disabled=true',
      { token: TOKEN },
    )
  })

  it('fetchStorageConfigurations throws without token', async () => {
    await expect(fetchStorageConfigurations()).rejects.toThrow(
      'Authentication token is required for storage admin operations',
    )
    expect(mockApiGet).not.toHaveBeenCalled()
  })

  it('createStorageConfiguration posts payload', async () => {
    const payload: CreateStorageConfigurationRequest = {
      name: 'New storage',
      provider: 'local_filesystem',
      config: {
        provider: 'local_filesystem',
        base_path: '/data/new',
        create_directories: true,
        expose_file_urls: true,
      },
      default_use_cases: ['raw_source'],
    }
    mockApiPost.mockResolvedValue(mockConfiguration)

    await createStorageConfiguration(payload, TOKEN)

    expect(mockApiPost).toHaveBeenCalledWith(
      '/admin/storage/configurations',
      payload,
      { token: TOKEN },
    )
  })

  it('updateStorageConfiguration updates payload', async () => {
    const payload: UpdateStorageConfigurationRequest = {
      name: 'Updated storage',
      enabled: false,
    }
    mockApiPut.mockResolvedValue(mockConfiguration)

    await updateStorageConfiguration(mockConfiguration.id, payload, TOKEN)

    expect(mockApiPut).toHaveBeenCalledWith(
      `/admin/storage/configurations/${mockConfiguration.id}`,
      payload,
      { token: TOKEN },
    )
  })

  it('deleteStorageConfiguration includes force flag', async () => {
    mockApiDelete.mockResolvedValue({ message: 'deleted' })

    await deleteStorageConfiguration(mockConfiguration.id, true, TOKEN)

    expect(mockApiDelete).toHaveBeenCalledWith(
      `/admin/storage/configurations/${mockConfiguration.id}?force=true`,
      { token: TOKEN },
    )
  })

  it('testStorageConfiguration posts empty payload', async () => {
    mockApiPost.mockResolvedValue(mockTestResult)

    await testStorageConfiguration(mockConfiguration.id, TOKEN)

    expect(mockApiPost).toHaveBeenCalledWith(
      `/admin/storage/configurations/${mockConfiguration.id}/test`,
      {},
      { token: TOKEN },
    )
  })

  it('fetchStorageMetrics hits metrics endpoint', async () => {
    mockApiGet.mockResolvedValue(mockMetrics)

    await fetchStorageMetrics(mockConfiguration.id, TOKEN)

    expect(mockApiGet).toHaveBeenCalledWith(
      `/admin/storage/configurations/${mockConfiguration.id}/metrics`,
      { token: TOKEN },
    )
  })

  it('fetchStorageHealth hits health endpoint', async () => {
    mockApiGet.mockResolvedValue(mockHealth)

    await fetchStorageHealth(mockConfiguration.id, TOKEN)

    expect(mockApiGet).toHaveBeenCalledWith(
      `/admin/storage/configurations/${mockConfiguration.id}/health`,
      { token: TOKEN },
    )
  })

  it('fetchStorageOperations includes limit param', async () => {
    mockApiGet.mockResolvedValue([])

    await fetchStorageOperations(mockConfiguration.id, 25, TOKEN)

    expect(mockApiGet).toHaveBeenCalledWith(
      `/admin/storage/configurations/${mockConfiguration.id}/operations?limit=25`,
      { token: TOKEN },
    )
  })

  it('fetchStorageOverview requests stats endpoint', async () => {
    mockApiGet.mockResolvedValue(mockOverviewResponse)

    await fetchStorageOverview(TOKEN)

    expect(mockApiGet).toHaveBeenCalledWith(
      '/admin/storage/stats',
      { token: TOKEN },
    )
  })
})
