import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { buildPlaywrightSession, isPlaywrightE2EMode } from '@/lib/e2e/playwright-auth'
import { getPlaywrightSystemSettingsPageData } from '@/lib/e2e/playwright-fixtures'
import SystemSettingsClient from './system-settings-client'
import {
  fetchUsers,
  fetchUserStatistics,
  type UserListResponse,
  type UserStatisticsResponse,
} from '@/lib/api/users'
import { fetchStorageConfigurations, fetchStorageOverview } from '@/lib/api/storage'
import { fetchMaintenanceState } from '@/lib/api/system-status'
import { fetchResearchSpaces } from '@/lib/api/research-spaces'
import {
  fetchAdminCatalogEntries,
  fetchCatalogAvailabilitySummaries,
  type DataSourceAvailability,
} from '@/lib/api/data-source-activation'
import { INITIAL_USER_PARAMS } from './constants'
import type { StorageConfigurationListResponse, StorageOverviewResponse } from '@/types/storage'
import type { MaintenanceModeResponse } from '@/types/system-status'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { ResearchSpace } from '@/types/research-space'

export default async function SystemSettingsPage() {
  const isPlaywrightMode = isPlaywrightE2EMode()
  const session = isPlaywrightMode ? buildPlaywrightSession() : await getServerSession(authOptions)

  if (!session) {
    redirect('/auth/login?error=SessionExpired')
  }

  if (session.user?.role !== 'admin') {
    redirect('/dashboard?error=AdminOnly')
  }

  const token = session.user?.access_token
  if (!token) {
    redirect('/auth/login?error=SessionExpired')
  }

  let users: UserListResponse | null = null
  let userStats: UserStatisticsResponse | null = null
  let storageConfigurations: StorageConfigurationListResponse | null = null
  let storageOverview: StorageOverviewResponse | null = null
  let maintenanceState: MaintenanceModeResponse | null = null
  let catalogEntries: SourceCatalogEntry[] = []
  let availabilitySummaries: DataSourceAvailability[] = []
  let spaces: ResearchSpace[] = []
  if (isPlaywrightMode) {
    const fixtureData = getPlaywrightSystemSettingsPageData()
    users = fixtureData.users
    userStats = fixtureData.userStats
    storageConfigurations = fixtureData.storageConfigurations
    storageOverview = fixtureData.storageOverview
    maintenanceState = fixtureData.maintenanceState
    catalogEntries = fixtureData.catalogEntries
    availabilitySummaries = fixtureData.availabilitySummaries
    spaces = fixtureData.spaces
  } else {
    const [
      usersResult,
      userStatsResult,
      storageConfigurationsResult,
      storageOverviewResult,
      maintenanceStateResult,
      catalogEntriesResult,
      availabilitySummariesResult,
      researchSpacesResult,
    ] = await Promise.allSettled([
      fetchUsers(INITIAL_USER_PARAMS, token),
      fetchUserStatistics(token),
      fetchStorageConfigurations(
        { page: 1, per_page: 100, include_disabled: true },
        token,
      ),
      fetchStorageOverview(token),
      fetchMaintenanceState(token),
      fetchAdminCatalogEntries(token),
      fetchCatalogAvailabilitySummaries(token),
      fetchResearchSpaces({ limit: 100 }, token),
    ])

    if (usersResult.status === 'fulfilled') {
      users = usersResult.value
    } else {
      console.error('[SystemSettingsPage] Failed to fetch users:', usersResult.reason)
    }

    if (userStatsResult.status === 'fulfilled') {
      userStats = userStatsResult.value
    } else {
      console.error('[SystemSettingsPage] Failed to fetch user stats:', userStatsResult.reason)
    }

    if (storageConfigurationsResult.status === 'fulfilled') {
      storageConfigurations = storageConfigurationsResult.value
    } else {
      console.error(
        '[SystemSettingsPage] Failed to fetch storage configurations:',
        storageConfigurationsResult.reason,
      )
    }

    if (storageOverviewResult.status === 'fulfilled') {
      storageOverview = storageOverviewResult.value
    } else {
      console.error('[SystemSettingsPage] Failed to fetch storage overview:', storageOverviewResult.reason)
    }

    if (maintenanceStateResult.status === 'fulfilled') {
      maintenanceState = maintenanceStateResult.value
    } else {
      console.error(
        '[SystemSettingsPage] Failed to fetch maintenance state:',
        maintenanceStateResult.reason,
      )
    }

    if (catalogEntriesResult.status === 'fulfilled') {
      catalogEntries = catalogEntriesResult.value
    } else {
      console.error(
        '[SystemSettingsPage] Failed to fetch catalog entries:',
        catalogEntriesResult.reason,
      )
    }

    if (availabilitySummariesResult.status === 'fulfilled') {
      availabilitySummaries = availabilitySummariesResult.value
    } else {
      console.error(
        '[SystemSettingsPage] Failed to fetch catalog availability:',
        availabilitySummariesResult.reason,
      )
    }

    if (researchSpacesResult.status === 'fulfilled') {
      spaces = researchSpacesResult.value.spaces
    } else {
      console.error(
        '[SystemSettingsPage] Failed to fetch research spaces:',
        researchSpacesResult.reason,
      )
    }
  }

  return (
    <SystemSettingsClient
      initialParams={INITIAL_USER_PARAMS}
      users={users}
      userStats={userStats}
      storageConfigurations={storageConfigurations}
      storageOverview={storageOverview}
      maintenanceState={maintenanceState}
      catalogEntries={catalogEntries}
      availabilitySummaries={availabilitySummaries}
      spaces={spaces}
      currentUserId={session.user?.id ?? ''}
      isAdmin={session.user?.role === 'admin'}
    />
  )
}
