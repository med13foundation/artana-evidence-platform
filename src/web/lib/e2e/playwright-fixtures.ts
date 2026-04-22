import 'server-only'

import { MembershipRole, SpaceStatus, type ResearchSpace, type ResearchSpaceMembership } from '@/types/research-space'
import type { DataSourceAvailability } from '@/lib/api/data-source-activation'
import type { DataSourceListParams, DataSourceListResponse } from '@/lib/api/data-sources'
import type { SourceCatalogEntry } from '@/lib/types/data-discovery'
import type { UserListParams, UserListResponse, UserPublic, UserStatisticsResponse } from '@/lib/api/users'
import type {
  DataDiscoverySessionResponse,
  OrchestratedSessionState,
} from '@/types/generated'
import type {
  CreateStorageConfigurationRequest,
  StorageConfiguration,
  StorageConfigurationListResponse,
  StorageConfigurationStats,
  StorageHealthReport,
  StorageOverviewResponse,
  StorageProviderTestResult,
  StorageUsageMetrics,
  UpdateStorageConfigurationRequest,
} from '@/types/storage'
import type { EnableMaintenanceRequest, MaintenanceModeResponse } from '@/types/system-status'

type StorageFixtureState = {
  configs: Map<string, StorageConfiguration>
  metrics: Map<string, StorageUsageMetrics>
  health: Map<string, StorageHealthReport>
}

function cloneValue<T>(value: T): T {
  return structuredClone(value)
}

function nowIso(): string {
  return new Date().toISOString()
}

const PLAYWRIGHT_SPACE_ID = '11111111-1111-1111-1111-111111111111'
const PLAYWRIGHT_SPACE: ResearchSpace = {
  id: PLAYWRIGHT_SPACE_ID,
  slug: 'artana',
  name: 'Artana Research',
  description: 'Deterministic research space for Playwright E2E flows',
  owner_id: 'playwright-admin',
  status: SpaceStatus.ACTIVE,
  settings: {},
  tags: ['playwright', 'artana'],
  created_at: nowIso(),
  updated_at: nowIso(),
}

const PLAYWRIGHT_MEMBERSHIP: ResearchSpaceMembership = {
  id: 'membership-playwright-admin',
  space_id: PLAYWRIGHT_SPACE_ID,
  user_id: 'playwright-admin',
  role: MembershipRole.ADMIN,
  invited_by: null,
  invited_at: null,
  joined_at: nowIso(),
  is_active: true,
  created_at: nowIso(),
  updated_at: nowIso(),
}

const PLAYWRIGHT_USERS: UserPublic[] = [
  {
    id: 'playwright-admin',
    email: 'playwright@artana.dev',
    username: 'playwright-admin',
    full_name: 'Playwright Admin',
    role: 'admin',
    status: 'active',
    email_verified: true,
    last_login: nowIso(),
    created_at: nowIso(),
  },
]

const PLAYWRIGHT_CATALOG_ENTRIES: SourceCatalogEntry[] = [
  {
    id: 'pubmed-source',
    name: 'PubMed Clinical',
    category: 'Articles',
    subcategory: 'PubMed',
    description: 'Deterministic PubMed connector for Playwright discovery flows.',
    source_type: 'pubmed',
    param_type: 'gene',
    is_active: true,
    requires_auth: false,
    usage_count: 42,
    success_rate: 0.98,
    tags: ['pubmed', 'articles'],
    capabilities: {
      supports_date_range: true,
      supports_publication_types: true,
      supports_language_filter: true,
      supports_sort_options: true,
      supports_additional_terms: true,
      max_results_limit: 500,
    },
  },
  {
    id: 'clinvar-source',
    name: 'ClinVar Variants',
    category: 'Variants',
    subcategory: 'ClinVar',
    description: 'Deterministic ClinVar connector for Playwright discovery flows.',
    source_type: 'clinvar',
    param_type: 'gene',
    is_active: true,
    requires_auth: false,
    usage_count: 17,
    success_rate: 0.94,
    tags: ['clinvar', 'variants'],
    capabilities: {
      supports_sort_options: true,
      supports_variation_type: true,
      supports_clinical_significance: true,
      max_results_limit: 250,
    },
  },
]

const PLAYWRIGHT_AVAILABILITY_SUMMARIES: DataSourceAvailability[] =
  PLAYWRIGHT_CATALOG_ENTRIES.map((entry) => ({
    catalog_entry_id: entry.id,
    effective_permission_level: 'available',
    effective_is_active: true,
    global_rule: null,
    project_rules: [],
  }))

function createDiscoverySession(): DataDiscoverySessionResponse {
  return {
    id: 'playwright-discovery-session',
    owner_id: 'playwright-admin',
    research_space_id: null,
    name: 'Playwright Session',
    current_parameters: {
      gene_symbol: 'MED13',
      search_term: 'syndrome',
      date_from: null,
      date_to: null,
      publication_types: [],
      languages: [],
      sort_by: 'relevance',
      max_results: 25,
      additional_terms: null,
      variation_types: [],
      clinical_significance: [],
      is_reviewed: null,
      organism: null,
    },
    selected_sources: ['pubmed-source'],
    tested_sources: [],
    total_tests_run: 0,
    successful_tests: 0,
    is_active: true,
    created_at: nowIso(),
    updated_at: nowIso(),
    last_activity_at: nowIso(),
  }
}

function createStorageState(): StorageFixtureState {
  const localConfiguration: StorageConfiguration = {
    id: 'config-local',
    name: 'Local Vault',
    provider: 'local_filesystem',
    config: {
      provider: 'local_filesystem',
      base_path: '/var/artana/storage',
      create_directories: true,
      expose_file_urls: false,
    },
    enabled: true,
    supported_capabilities: ['pdf', 'export'],
    default_use_cases: ['pdf'],
    metadata: {},
    created_at: nowIso(),
    updated_at: nowIso(),
  }
  const localMetrics: StorageUsageMetrics = {
    configuration_id: localConfiguration.id,
    total_files: 0,
    total_size_bytes: 0,
    last_operation_at: nowIso(),
    error_rate: 0,
  }
  const localHealth: StorageHealthReport = {
    configuration_id: localConfiguration.id,
    provider: localConfiguration.provider,
    status: 'healthy',
    last_checked_at: nowIso(),
    details: {},
  }

  return {
    configs: new Map([[localConfiguration.id, localConfiguration]]),
    metrics: new Map([[localConfiguration.id, localMetrics]]),
    health: new Map([[localConfiguration.id, localHealth]]),
  }
}

let discoverySessionState = createDiscoverySession()
let storageState = createStorageState()
let storageIdSequence = 1
let maintenanceState: MaintenanceModeResponse = {
  state: {
    is_active: false,
    message: null,
    activated_at: null,
    activated_by: null,
    last_updated_by: 'playwright-admin',
    last_updated_at: nowIso(),
  },
}

function buildUserStatistics(users: UserPublic[]): UserStatisticsResponse {
  const byRole: Record<string, number> = {}
  let activeUsers = 0
  let inactiveUsers = 0
  let suspendedUsers = 0
  let pendingVerification = 0

  users.forEach((user) => {
    byRole[user.role] = (byRole[user.role] ?? 0) + 1
    switch (user.status) {
      case 'active':
        activeUsers += 1
        break
      case 'inactive':
        inactiveUsers += 1
        break
      case 'suspended':
        suspendedUsers += 1
        break
      case 'pending_verification':
        pendingVerification += 1
        break
      default:
        break
    }
  })

  return {
    total_users: users.length,
    active_users: activeUsers,
    inactive_users: inactiveUsers,
    suspended_users: suspendedUsers,
    pending_verification: pendingVerification,
    by_role: byRole,
    recent_registrations: users.length,
    recent_logins: activeUsers,
  }
}

function ensureStorageMetrics(configurationId: string): StorageUsageMetrics {
  const existing = storageState.metrics.get(configurationId)
  if (existing) {
    return existing
  }
  const metrics: StorageUsageMetrics = {
    configuration_id: configurationId,
    total_files: 0,
    total_size_bytes: 0,
    last_operation_at: nowIso(),
    error_rate: 0,
  }
  storageState.metrics.set(configurationId, metrics)
  return metrics
}

function ensureStorageHealth(
  configurationId: string,
  provider: StorageConfiguration['provider'],
): StorageHealthReport {
  const existing = storageState.health.get(configurationId)
  if (existing) {
    return existing
  }
  const health: StorageHealthReport = {
    configuration_id: configurationId,
    provider,
    status: 'healthy',
    last_checked_at: nowIso(),
    details: {},
  }
  storageState.health.set(configurationId, health)
  return health
}

function buildStorageOverview(): StorageOverviewResponse {
  const configurations: StorageConfigurationStats[] = []
  let enabledConfigurations = 0
  let disabledConfigurations = 0
  let healthyConfigurations = 0
  let degradedConfigurations = 0
  let offlineConfigurations = 0
  let totalFiles = 0
  let totalSizeBytes = 0
  const errorRates: number[] = []

  storageState.configs.forEach((configuration) => {
    const usage = ensureStorageMetrics(configuration.id)
    const health = ensureStorageHealth(configuration.id, configuration.provider)
    configurations.push({
      configuration: cloneValue(configuration),
      usage: cloneValue(usage),
      health: cloneValue(health),
    })

    if (configuration.enabled) {
      enabledConfigurations += 1
    } else {
      disabledConfigurations += 1
    }

    totalFiles += usage.total_files
    totalSizeBytes += usage.total_size_bytes
    if (typeof usage.error_rate === 'number') {
      errorRates.push(usage.error_rate)
    }

    switch (health.status) {
      case 'healthy':
        healthyConfigurations += 1
        break
      case 'degraded':
        degradedConfigurations += 1
        break
      case 'offline':
        offlineConfigurations += 1
        break
      default:
        break
    }
  })

  return {
    generated_at: nowIso(),
    totals: {
      total_configurations: configurations.length,
      enabled_configurations: enabledConfigurations,
      disabled_configurations: disabledConfigurations,
      healthy_configurations: healthyConfigurations,
      degraded_configurations: degradedConfigurations,
      offline_configurations: offlineConfigurations,
      total_files: totalFiles,
      total_size_bytes: totalSizeBytes,
      average_error_rate:
        errorRates.length > 0
          ? errorRates.reduce((sum, value) => sum + value, 0) / errorRates.length
          : null,
    },
    configurations,
  }
}

function buildDiscoveryState(
  session: DataDiscoverySessionResponse,
): OrchestratedSessionState {
  const selectedIds = new Set(session.selected_sources)
  const selectedEntries = PLAYWRIGHT_CATALOG_ENTRIES.filter((entry) => selectedIds.has(entry.id))
  const categoryCounts = selectedEntries.reduce<Record<string, number>>((accumulator, entry) => {
    accumulator[entry.category] = (accumulator[entry.category] ?? 0) + 1
    return accumulator
  }, {})
  const isValid = selectedEntries.length > 0

  return {
    session: cloneValue(session),
    capabilities: {
      supports_gene_search: true,
      supports_term_search: true,
      supported_parameters: ['gene_symbol', 'search_term'],
      max_results_limit: Math.max(
        ...selectedEntries.map((entry) => entry.capabilities.max_results_limit ?? 0),
        500,
      ),
    },
    validation: {
      is_valid: isValid,
      issues: isValid
        ? []
        : [
            {
              code: 'selection_required',
              message: 'Select at least one source before running discovery.',
              severity: 'error',
              field: 'selected_sources',
            },
          ],
    },
    view_context: {
      selected_count: selectedEntries.length,
      total_available: PLAYWRIGHT_CATALOG_ENTRIES.length,
      can_run_search: isValid,
      categories: categoryCounts,
    },
  }
}

function listStorageConfigurations(
  params: { include_disabled?: boolean; page?: number; per_page?: number } = {},
): StorageConfigurationListResponse {
  const includeDisabled = params.include_disabled === true
  const allConfigurations = Array.from(storageState.configs.values())
    .filter((configuration) => includeDisabled || configuration.enabled)
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
    .map((configuration) => cloneValue(configuration))

  return {
    data: allConfigurations,
    total: allConfigurations.length,
    page: params.page ?? 1,
    per_page: params.per_page ?? 100,
  }
}

export function getPlaywrightResearchSpaces(): ResearchSpace[] {
  return [cloneValue(PLAYWRIGHT_SPACE)]
}

export function getPlaywrightMembership(
  spaceId: string,
): ResearchSpaceMembership | null {
  return spaceId === PLAYWRIGHT_SPACE_ID ? cloneValue(PLAYWRIGHT_MEMBERSHIP) : null
}

export function getPlaywrightSystemSettingsPageData(): {
  users: UserListResponse
  userStats: UserStatisticsResponse
  storageConfigurations: StorageConfigurationListResponse
  storageOverview: StorageOverviewResponse
  maintenanceState: MaintenanceModeResponse
  catalogEntries: SourceCatalogEntry[]
  availabilitySummaries: DataSourceAvailability[]
  spaces: ResearchSpace[]
} {
  return {
    users: listPlaywrightUsers(),
    userStats: getPlaywrightUserStatistics(),
    storageConfigurations: listStorageConfigurations({ include_disabled: true, page: 1, per_page: 100 }),
    storageOverview: buildStorageOverview(),
    maintenanceState: getPlaywrightMaintenanceState(),
    catalogEntries: getPlaywrightCatalogEntries(),
    availabilitySummaries: getPlaywrightAvailabilitySummaries(),
    spaces: getPlaywrightResearchSpaces(),
  }
}

export function listPlaywrightUsers(params: UserListParams = {}): UserListResponse {
  const filteredUsers = PLAYWRIGHT_USERS.filter((user) => {
    if (params.role && user.role !== params.role) {
      return false
    }
    if (params.status_filter && user.status !== params.status_filter) {
      return false
    }
    return true
  })

  const skip = params.skip ?? 0
  const limit = params.limit ?? 100
  return {
    users: filteredUsers.slice(skip, skip + limit).map((user) => cloneValue(user)),
    total: filteredUsers.length,
    skip,
    limit,
  }
}

export function getPlaywrightUserStatistics(): UserStatisticsResponse {
  return buildUserStatistics(PLAYWRIGHT_USERS)
}

export function getPlaywrightCatalogEntries(): SourceCatalogEntry[] {
  return cloneValue(PLAYWRIGHT_CATALOG_ENTRIES)
}

export function getPlaywrightAvailabilitySummaries(): DataSourceAvailability[] {
  return cloneValue(PLAYWRIGHT_AVAILABILITY_SUMMARIES)
}

export function getPlaywrightSpaceDataSources(
  _spaceId: string,
  params: Omit<DataSourceListParams, 'research_space_id'> = {},
): DataSourceListResponse {
  return {
    items: [],
    total: 0,
    page: params.page ?? 1,
    limit: params.limit ?? 25,
    has_next: false,
    has_prev: false,
  }
}

export function getPlaywrightStorageConfigurations(
  params: { include_disabled?: boolean; page?: number; per_page?: number } = {},
): StorageConfigurationListResponse {
  return listStorageConfigurations(params)
}

export function getPlaywrightStorageOverview(): StorageOverviewResponse {
  return buildStorageOverview()
}

export function getPlaywrightMaintenanceState(): MaintenanceModeResponse {
  return cloneValue(maintenanceState)
}

export function enablePlaywrightMaintenance(
  payload: EnableMaintenanceRequest,
): MaintenanceModeResponse {
  maintenanceState = {
    state: {
      is_active: true,
      message: payload.message ?? null,
      activated_at: nowIso(),
      activated_by: 'playwright-admin',
      last_updated_by: 'playwright-admin',
      last_updated_at: nowIso(),
    },
  }
  return getPlaywrightMaintenanceState()
}

export function disablePlaywrightMaintenance(): MaintenanceModeResponse {
  maintenanceState = {
    state: {
      is_active: false,
      message: null,
      activated_at: null,
      activated_by: null,
      last_updated_by: 'playwright-admin',
      last_updated_at: nowIso(),
    },
  }
  return getPlaywrightMaintenanceState()
}

export function createPlaywrightStorageConfiguration(
  payload: CreateStorageConfigurationRequest,
): StorageConfiguration {
  storageIdSequence += 1
  const id = `config-${storageIdSequence}`
  const created: StorageConfiguration = {
    id,
    name: payload.name,
    provider: payload.provider,
    config: cloneValue(payload.config),
    enabled: payload.enabled ?? true,
    supported_capabilities:
      payload.supported_capabilities ?? cloneValue(payload.default_use_cases),
    default_use_cases: cloneValue(payload.default_use_cases),
    metadata: cloneValue(payload.metadata ?? {}),
    created_at: nowIso(),
    updated_at: nowIso(),
  }

  storageState.configs.set(id, created)
  storageState.metrics.set(id, {
    configuration_id: id,
    total_files: 0,
    total_size_bytes: 0,
    last_operation_at: nowIso(),
    error_rate: 0,
  })
  storageState.health.set(id, {
    configuration_id: id,
    provider: created.provider,
    status: 'healthy',
    last_checked_at: nowIso(),
    details: {},
  })
  return cloneValue(created)
}

export function updatePlaywrightStorageConfiguration(
  configurationId: string,
  payload: UpdateStorageConfigurationRequest,
): StorageConfiguration {
  const current = storageState.configs.get(configurationId)
  if (!current) {
    throw new Error('Storage configuration not found')
  }

  const updated: StorageConfiguration = {
    ...current,
    ...(payload.name !== undefined ? { name: payload.name } : {}),
    ...(payload.config !== undefined ? { config: cloneValue(payload.config) } : {}),
    ...(payload.enabled !== undefined ? { enabled: payload.enabled } : {}),
    ...(payload.supported_capabilities !== undefined
      ? { supported_capabilities: cloneValue(payload.supported_capabilities) }
      : {}),
    ...(payload.default_use_cases !== undefined
      ? { default_use_cases: cloneValue(payload.default_use_cases) }
      : {}),
    ...(payload.metadata !== undefined ? { metadata: cloneValue(payload.metadata) } : {}),
    updated_at: nowIso(),
  }
  storageState.configs.set(configurationId, updated)
  return cloneValue(updated)
}

export function deletePlaywrightStorageConfiguration(
  configurationId: string,
  force: boolean,
): { message: string } {
  const current = storageState.configs.get(configurationId)
  if (!current) {
    throw new Error('Storage configuration not found')
  }

  if (current.enabled && !force) {
    storageState.configs.set(configurationId, {
      ...current,
      enabled: false,
      updated_at: nowIso(),
    })
    return { message: 'Storage configuration disabled' }
  }

  storageState.configs.delete(configurationId)
  storageState.metrics.delete(configurationId)
  storageState.health.delete(configurationId)
  return { message: 'Storage configuration deleted' }
}

export function testPlaywrightStorageConfiguration(
  configurationId: string,
): StorageProviderTestResult {
  const configuration = storageState.configs.get(configurationId)
  if (!configuration) {
    throw new Error('Storage configuration not found')
  }

  const checkedAt = nowIso()
  storageState.health.set(configurationId, {
    configuration_id: configurationId,
    provider: configuration.provider,
    status: 'healthy',
    last_checked_at: checkedAt,
    details: { tested_by: 'playwright' },
  })

  return {
    configuration_id: configurationId,
    provider: configuration.provider,
    success: true,
    message: 'Connection verified',
    checked_at: checkedAt,
    capabilities: cloneValue(configuration.supported_capabilities),
    latency_ms: 150,
    metadata: { tested_by: 'playwright' },
  }
}

export function getPlaywrightStorageMetrics(
  configurationId: string,
): StorageUsageMetrics | null {
  const metrics = storageState.metrics.get(configurationId)
  return metrics ? cloneValue(metrics) : null
}

export function getPlaywrightStorageHealth(
  configurationId: string,
): StorageHealthReport | null {
  const health = storageState.health.get(configurationId)
  return health ? cloneValue(health) : null
}

export function getPlaywrightDataDiscoveryPageData(): {
  orchestratedState: OrchestratedSessionState
  catalog: SourceCatalogEntry[]
} {
  return {
    orchestratedState: buildDiscoveryState(discoverySessionState),
    catalog: getPlaywrightCatalogEntries(),
  }
}

export function getPlaywrightDiscoveryState(sessionId: string): OrchestratedSessionState {
  if (sessionId !== discoverySessionState.id) {
    throw new Error('Discovery session not found')
  }
  return buildDiscoveryState(discoverySessionState)
}

export function updatePlaywrightDiscoverySelection(
  sessionId: string,
  sourceIds: string[],
): OrchestratedSessionState {
  if (sessionId !== discoverySessionState.id) {
    throw new Error('Discovery session not found')
  }

  discoverySessionState = {
    ...discoverySessionState,
    selected_sources: cloneValue(sourceIds),
    updated_at: nowIso(),
    last_activity_at: nowIso(),
  }
  return buildDiscoveryState(discoverySessionState)
}
