import type { QueryKey } from '@tanstack/react-query'
import type { DataSourceListParams } from '@/lib/api/data-sources'
import type { StorageConfigurationListParams } from '@/lib/api/storage'
import type { UserListParams } from '@/lib/api/users'

function normalizeUserParams(params: UserListParams = {}): Required<UserListParams> {
  return {
    skip: params.skip ?? 0,
    limit: params.limit ?? 100,
    role: params.role ?? '',
    status_filter: params.status_filter ?? '',
  }
}

function normalizeStorageParams(
  params: StorageConfigurationListParams = {},
): Required<StorageConfigurationListParams> {
  return {
    page: params.page ?? 1,
    per_page: params.per_page ?? 100,
    include_disabled: params.include_disabled ?? false,
  }
}

function normalizeDataSourceParams(
  params: Omit<DataSourceListParams, 'research_space_id'> = {},
): Required<Omit<DataSourceListParams, 'research_space_id'>> {
  return {
    page: params.page ?? 1,
    limit: params.limit ?? 100,
    status: params.status ?? '',
    source_type: params.source_type ?? '',
  }
}

export const queryKeys = {
  usersRoot: () => ['users'] as const,
  users: (params: UserListParams = {}) => ['users', normalizeUserParams(params)] as const,
  userStats: () => ['user-stats'] as const,
  maintenanceState: () => ['maintenance-state'] as const,
  availabilitySummaries: () => ['catalog-availability'] as const,
  storageConfigurationsRoot: () => ['storage-configurations'] as const,
  storageConfigurations: (params: StorageConfigurationListParams = {}) =>
    ['storage-configurations', normalizeStorageParams(params)] as const,
  storageOverview: () => ['storage-overview'] as const,
  spaceDataSourcesRoot: () => ['space-data-sources'] as const,
  spaceDataSources: (spaceId: string, params: Omit<DataSourceListParams, 'research_space_id'> = {}) =>
    ['space-data-sources', spaceId, normalizeDataSourceParams(params)] as const,
}

export function readUserParamsFromKey(queryKey: QueryKey): Required<UserListParams> | null {
  const [, rawParams] = queryKey
  if (
    !Array.isArray(queryKey) ||
    queryKey[0] !== 'users' ||
    typeof rawParams !== 'object' ||
    rawParams === null
  ) {
    return null
  }

  const params = rawParams as Partial<Required<UserListParams>>
  return normalizeUserParams(params)
}
