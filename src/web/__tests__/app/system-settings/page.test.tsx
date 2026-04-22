import type { ReactElement } from 'react'
import SystemSettingsPage from '@/app/(dashboard)/system-settings/page'
import { INITIAL_USER_PARAMS } from '@/app/(dashboard)/system-settings/constants'
import { fetchUsers, fetchUserStatistics } from '@/lib/api/users'
import { fetchStorageConfigurations, fetchStorageOverview } from '@/lib/api/storage'
import { fetchMaintenanceState } from '@/lib/api/system-status'
import { fetchResearchSpaces } from '@/lib/api/research-spaces'
import {
  fetchAdminCatalogEntries,
  fetchCatalogAvailabilitySummaries,
} from '@/lib/api/data-source-activation'
import { getServerSession } from 'next-auth'

jest.mock('next-auth', () => ({
  getServerSession: jest.fn(),
}))

const redirectMock = jest.fn()

jest.mock('next/navigation', () => ({
  redirect: (...args: unknown[]) => redirectMock(...args),
}))

jest.mock('@/lib/api/users', () => ({
  fetchUsers: jest.fn(),
  fetchUserStatistics: jest.fn(),
}))
jest.mock('@/lib/api/storage', () => ({
  fetchStorageConfigurations: jest.fn(),
  fetchStorageOverview: jest.fn(),
}))
jest.mock('@/lib/api/system-status', () => ({
  fetchMaintenanceState: jest.fn(),
}))
jest.mock('@/lib/api/research-spaces', () => ({
  fetchResearchSpaces: jest.fn(),
}))
jest.mock('@/lib/api/data-source-activation', () => ({
  fetchAdminCatalogEntries: jest.fn(),
  fetchCatalogAvailabilitySummaries: jest.fn(),
}))

const ADMIN_SESSION = {
  user: {
    id: 'admin-1',
    role: 'admin',
    access_token: 'admin-token',
  },
}

describe('SystemSettingsPage (server)', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('redirects to login when no session is found', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue(null)
    redirectMock.mockImplementation(() => {
      throw new Error('redirect')
    })

    await expect(SystemSettingsPage()).rejects.toThrow('redirect')
    expect(redirectMock).toHaveBeenCalledWith('/auth/login?error=SessionExpired')
  })

  it('redirects non-admin users to the dashboard', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { id: 'user-123', role: 'researcher', access_token: 'token' },
    })
    redirectMock.mockImplementation(() => {
      throw new Error('redirect')
    })

    await expect(SystemSettingsPage()).rejects.toThrow('redirect')
    expect(redirectMock).toHaveBeenCalledWith('/dashboard?error=AdminOnly')
  })

  it('redirects when admin session lacks an access token', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue({
      user: { id: 'admin-no-token', role: 'admin' },
    })
    redirectMock.mockImplementation(() => {
      throw new Error('redirect')
    })

    await expect(SystemSettingsPage()).rejects.toThrow('redirect')
    expect(redirectMock).toHaveBeenCalledWith('/auth/login?error=SessionExpired')
  })

  it('prefetches data and renders when admin session is valid', async () => {
    ;(getServerSession as jest.Mock).mockResolvedValue(ADMIN_SESSION)
    ;(fetchUsers as jest.Mock).mockResolvedValue({ users: [], total: 0, skip: 0, limit: 25 })
    ;(fetchUserStatistics as jest.Mock).mockResolvedValue({
      total_users: 0,
      active_users: 0,
      inactive_users: 0,
      suspended_users: 0,
      pending_verification: 0,
      by_role: {},
      recent_registrations: 0,
      recent_logins: 0,
    })
    ;(fetchStorageConfigurations as jest.Mock).mockResolvedValue({
      data: [],
      total: 0,
      page: 1,
      per_page: 100,
    })
    ;(fetchStorageOverview as jest.Mock).mockResolvedValue({
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
    })
    ;(fetchMaintenanceState as jest.Mock).mockResolvedValue({
      state: {
        is_active: false,
        message: null,
        activated_at: null,
        activated_by: null,
        last_updated_by: null,
        last_updated_at: null,
      },
    })
    ;(fetchAdminCatalogEntries as jest.Mock).mockResolvedValue([])
    ;(fetchCatalogAvailabilitySummaries as jest.Mock).mockResolvedValue([])
    ;(fetchResearchSpaces as jest.Mock).mockResolvedValue({
      spaces: [],
      total: 0,
      skip: 0,
      limit: 100,
    })
    redirectMock.mockImplementation(() => undefined)

    const result = (await SystemSettingsPage()) as ReactElement

    expect(redirectMock).not.toHaveBeenCalled()
    expect(fetchUsers).toHaveBeenCalledWith(INITIAL_USER_PARAMS, 'admin-token')
    expect(fetchUserStatistics).toHaveBeenCalledWith('admin-token')
    expect(fetchStorageConfigurations).toHaveBeenCalledWith(
      { page: 1, per_page: 100, include_disabled: true },
      'admin-token',
    )
    expect(fetchStorageOverview).toHaveBeenCalledWith('admin-token')
    expect(fetchMaintenanceState).toHaveBeenCalledWith('admin-token')
    expect(fetchAdminCatalogEntries).toHaveBeenCalledWith('admin-token')
    expect(fetchCatalogAvailabilitySummaries).toHaveBeenCalledWith('admin-token')
    expect(fetchResearchSpaces).toHaveBeenCalledWith({ limit: 100 }, 'admin-token')
    expect(result).toBeTruthy()
  })
})
