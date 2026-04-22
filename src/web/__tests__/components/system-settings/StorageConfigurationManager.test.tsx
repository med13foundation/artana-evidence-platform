import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StorageConfigurationManager } from '@/components/system-settings/StorageConfigurationManager'
import type {
  StorageConfiguration,
  StorageConfigurationListResponse,
  StorageOverviewResponse,
} from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'

const mockCreateStorageConfigurationAction = jest.fn()
const mockUpdateStorageConfigurationAction = jest.fn()
const mockTestStorageConfigurationAction = jest.fn()
const mockDeleteStorageConfigurationAction = jest.fn()

const originalBetaFlag = process.env.NEXT_PUBLIC_STORAGE_DASHBOARD_BETA

jest.mock('@/app/actions/storage', () => ({
  createStorageConfigurationAction: (...args: unknown[]) =>
    mockCreateStorageConfigurationAction(...args),
  updateStorageConfigurationAction: (...args: unknown[]) =>
    mockUpdateStorageConfigurationAction(...args),
  testStorageConfigurationAction: (...args: unknown[]) =>
    mockTestStorageConfigurationAction(...args),
  deleteStorageConfigurationAction: (...args: unknown[]) =>
    mockDeleteStorageConfigurationAction(...args),
}))

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}))

const baseConfigurations: StorageConfigurationListResponse = {
  data: [],
  total: 0,
  page: 1,
  per_page: 100,
}

const baseOverview: StorageOverviewResponse = {
  generated_at: new Date().toISOString(),
  totals: {
    total_configurations: 0,
    enabled_configurations: 0,
    disabled_configurations: 0,
    healthy_configurations: 0,
    degraded_configurations: 0,
    offline_configurations: 0,
    total_files: 0,
    total_size_bytes: 0,
    average_error_rate: 0,
  },
  configurations: [],
}

const activeMaintenance: MaintenanceModeResponse = {
  state: {
    is_active: true,
    message: null,
    activated_at: new Date().toISOString(),
    activated_by: null,
    last_updated_by: null,
    last_updated_at: new Date().toISOString(),
  },
}

const inactiveMaintenance: MaintenanceModeResponse = {
  state: {
    is_active: false,
    message: null,
    activated_at: null,
    activated_by: null,
    last_updated_by: null,
    last_updated_at: null,
  },
}

const renderManager = ({
  configurations = baseConfigurations,
  overview = baseOverview,
  maintenanceState = activeMaintenance,
}: {
  configurations?: StorageConfigurationListResponse | null
  overview?: StorageOverviewResponse | null
  maintenanceState?: MaintenanceModeResponse | null
} = {}) =>
  {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })

    return render(
      <QueryClientProvider client={queryClient}>
        <StorageConfigurationManager
          configurations={configurations}
          overview={overview}
          maintenanceState={maintenanceState}
        />
      </QueryClientProvider>,
    )
  }

describe('StorageConfigurationManager', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockCreateStorageConfigurationAction.mockResolvedValue({
      success: true,
      data: {
        id: 'cfg-new',
        name: 'Local Archive',
        provider: 'local_filesystem',
        config: {
          provider: 'local_filesystem',
          base_path: '/var/artana/storage',
          create_directories: true,
          expose_file_urls: false,
        },
        enabled: true,
        supported_capabilities: ['pdf'],
        default_use_cases: ['pdf'],
        metadata: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    })
    mockUpdateStorageConfigurationAction.mockResolvedValue({ success: true, data: {} })
    mockTestStorageConfigurationAction.mockResolvedValue({
      success: true,
      data: { success: true, message: 'ok' },
    })
    mockDeleteStorageConfigurationAction.mockResolvedValue({ success: true, data: { message: 'ok' } })
    process.env.NEXT_PUBLIC_STORAGE_DASHBOARD_BETA = 'true'
  })

  afterAll(() => {
    if (originalBetaFlag === undefined) {
      delete process.env.NEXT_PUBLIC_STORAGE_DASHBOARD_BETA
    } else {
      process.env.NEXT_PUBLIC_STORAGE_DASHBOARD_BETA = originalBetaFlag
    }
  })

  it('renders empty state when no configurations are available', () => {
    renderManager()
    expect(screen.getByText(/No storage configurations found/i)).toBeInTheDocument()
  })

  it('submits the new configuration form', async () => {
    const user = userEvent.setup()
    renderManager()

    await user.click(screen.getByRole('button', { name: /Add Configuration/i }))
    const nameInput = screen.getByLabelText(/Name/i)
    await user.clear(nameInput)
    await user.type(nameInput, 'Local Archive')

    await user.click(screen.getByRole('button', { name: /Create Configuration/i }))

    await waitFor(() => {
      expect(mockCreateStorageConfigurationAction).toHaveBeenCalledWith({
        name: 'Local Archive',
        provider: 'local_filesystem',
        default_use_cases: ['pdf'],
        enabled: true,
        config: {
          provider: 'local_filesystem',
          base_path: '/var/artana/storage',
          create_directories: true,
          expose_file_urls: false,
        },
      })
    })
  })

  it('tests an existing configuration connection', async () => {
    const user = userEvent.setup()
    const configuration: StorageConfiguration = {
      id: 'cfg-1',
      name: 'Primary Storage',
      provider: 'local_filesystem',
      config: {
        provider: 'local_filesystem',
        base_path: '/var/lib/artana',
        create_directories: true,
        expose_file_urls: false,
      },
      enabled: true,
      supported_capabilities: ['pdf', 'export'],
      default_use_cases: ['pdf'],
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    renderManager({
      configurations: {
        data: [configuration],
        total: 1,
        page: 1,
        per_page: 100,
      },
      overview: {
        ...baseOverview,
        configurations: [
          {
            configuration,
            usage: {
              configuration_id: 'cfg-1',
              total_files: 5,
              total_size_bytes: 1024,
              last_operation_at: new Date().toISOString(),
              error_rate: 0,
            },
            health: {
              configuration_id: 'cfg-1',
              provider: 'local_filesystem',
              status: 'healthy',
              last_checked_at: new Date().toISOString(),
              details: {},
            },
          },
        ],
      },
    })

    await user.click(screen.getByRole('button', { name: /Test Connection/i }))

    expect(mockTestStorageConfigurationAction).toHaveBeenCalledWith('cfg-1')
  })

  it('blocks toggling when maintenance mode is disabled and backend has usage', async () => {
    const user = userEvent.setup()
    const configuration: StorageConfiguration = {
      id: 'cfg-1',
      name: 'Primary Storage',
      provider: 'local_filesystem',
      config: {
        provider: 'local_filesystem',
        base_path: '/tmp',
        create_directories: true,
        expose_file_urls: false,
      },
      enabled: true,
      supported_capabilities: ['pdf'],
      default_use_cases: ['pdf'],
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    renderManager({
      configurations: {
        data: [configuration],
        total: 1,
        page: 1,
        per_page: 100,
      },
      overview: {
        ...baseOverview,
        configurations: [
          {
            configuration,
            usage: {
              configuration_id: 'cfg-1',
              total_files: 10,
              total_size_bytes: 1024,
              last_operation_at: new Date().toISOString(),
              error_rate: 0,
            },
            health: null,
          },
        ],
      },
      maintenanceState: inactiveMaintenance,
    })

    const toggle = screen.getByRole('switch', { name: /enabled/i })
    await user.click(toggle)

    expect(mockUpdateStorageConfigurationAction).not.toHaveBeenCalled()
  })

  it('shows maintenance confirmation when editing base path without maintenance', async () => {
    const user = userEvent.setup()
    const configuration: StorageConfiguration = {
      id: 'cfg-1',
      name: 'Primary Storage',
      provider: 'local_filesystem',
      config: {
        provider: 'local_filesystem',
        base_path: '/var/artana/storage',
        create_directories: true,
        expose_file_urls: false,
      },
      enabled: true,
      supported_capabilities: ['pdf'],
      default_use_cases: ['pdf'],
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }

    renderManager({
      configurations: {
        data: [configuration],
        total: 1,
        page: 1,
        per_page: 100,
      },
      maintenanceState: inactiveMaintenance,
    })

    await user.click(screen.getByRole('button', { name: /Add Configuration/i }))
    await user.clear(screen.getByLabelText(/Name/i))
    await user.type(screen.getByLabelText(/Name/i), 'Updated Storage')
    await user.clear(screen.getByLabelText(/Base Path/i))
    await user.type(screen.getByLabelText(/Base Path/i), '/tmp/archive')

    await user.click(screen.getByRole('button', { name: /Create Configuration/i }))

    expect(await screen.findByText(/Enable maintenance mode first/i)).toBeInTheDocument()
  })
})
