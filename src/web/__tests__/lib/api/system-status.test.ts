import { apiGet, apiPost } from '@/lib/api/client'
import {
  disableMaintenanceMode,
  enableMaintenanceMode,
  fetchMaintenanceState,
} from '@/lib/api/system-status'
import type {
  EnableMaintenanceRequest,
  MaintenanceModeResponse,
} from '@/types/system-status'

jest.mock('@/lib/api/client', () => ({
  apiGet: jest.fn(),
  apiPost: jest.fn(),
}))

const TOKEN = 'admin-token'

const mockMaintenanceResponse: MaintenanceModeResponse = {
  state: {
    is_active: false,
    message: null,
    activated_at: null,
    activated_by: null,
    last_updated_by: null,
    last_updated_at: null,
  },
}

describe('system-status api', () => {
  const mockApiGet = apiGet as jest.MockedFunction<typeof apiGet>
  const mockApiPost = apiPost as jest.MockedFunction<typeof apiPost>

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('fetchMaintenanceState calls maintenance endpoint', async () => {
    mockApiGet.mockResolvedValue(mockMaintenanceResponse)

    await fetchMaintenanceState(TOKEN)

    expect(mockApiGet).toHaveBeenCalledWith(
      '/admin/system/maintenance',
      { token: TOKEN },
    )
  })

  it('fetchMaintenanceState throws without token', async () => {
    await expect(fetchMaintenanceState()).rejects.toThrow(
      'Authentication token is required for maintenance operations',
    )
    expect(mockApiGet).not.toHaveBeenCalled()
  })

  it('enableMaintenanceMode posts payload', async () => {
    const payload: EnableMaintenanceRequest = {
      message: 'Maintenance window',
      force_logout_users: true,
    }
    mockApiPost.mockResolvedValue(mockMaintenanceResponse)

    await enableMaintenanceMode(payload, TOKEN)

    expect(mockApiPost).toHaveBeenCalledWith(
      '/admin/system/maintenance/enable',
      payload,
      { token: TOKEN },
    )
  })

  it('disableMaintenanceMode posts empty payload', async () => {
    mockApiPost.mockResolvedValue(mockMaintenanceResponse)

    await disableMaintenanceMode(TOKEN)

    expect(mockApiPost).toHaveBeenCalledWith(
      '/admin/system/maintenance/disable',
      {},
      { token: TOKEN },
    )
  })
})
