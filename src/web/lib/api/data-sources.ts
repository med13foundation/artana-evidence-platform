import { apiClient, authHeaders } from './client'
import type {
  DataSource,
  DataSourceIngestionSchedule,
  IngestionIdempotencyMetadata,
  IngestionJobMetadata,
  IngestionQueryGenerationMetadata,
  ScheduleFrequency,
} from '@/types/data-source'
import type { JSONObject } from '@/types/generated'

export interface DataSourceListParams {
  page?: number
  limit?: number
  status?: string
  source_type?: string
  research_space_id?: string
}

export interface DataSourceListResponse {
  items: DataSource[]
  total: number
  page: number
  limit: number
  has_next: boolean
  has_prev: boolean
}

export interface ScheduleConfigurationPayload {
  enabled: boolean
  frequency: ScheduleFrequency
  start_time?: string | null
  timezone: string
  cron_expression?: string | null
}

export interface UpdateDataSourcePayload {
  name?: string
  description?: string
  status?: 'draft' | 'active' | 'inactive' | 'error' | 'pending_review' | 'archived'
  config?: Record<string, unknown>
  ingestion_schedule?: ScheduleConfigurationPayload
}

export interface ScheduledJobResponse {
  job_id: string
  source_id: string
  next_run_at: string
  frequency: ScheduleFrequency
  cron_expression?: string | null
}

export interface ScheduleConfigurationResponse {
  ingestion_schedule: DataSourceIngestionSchedule
  scheduled_job?: ScheduledJobResponse | null
}

export interface DataSourceAiTestLink {
  label: string
  url: string
}

export interface DataSourceAiTestFinding {
  title: string
  pubmed_id?: string | null
  doi?: string | null
  pmc_id?: string | null
  publication_date?: string | null
  journal?: string | null
  links: DataSourceAiTestLink[]
}

export interface AgentRunTableSummary {
  table_name: string
  row_count: number
  latest_created_at?: string | null
  sample_rows?: JSONObject[]
}

export interface DataSourceAiTestResult {
  source_id: string
  model?: string | null
  success: boolean
  message: string
  executed_query?: string | null
  search_terms: string[]
  fetched_records: number
  sample_size: number
  findings: DataSourceAiTestFinding[]
  checked_at: string
  agent_run_id?: string | null
  agent_run_tables?: AgentRunTableSummary[]
}

export interface IngestionJobHistoryItem {
  id: string
  status: string
  trigger: string
  started_at: string | null
  completed_at: string | null
  records_processed: number
  records_failed: number
  records_skipped: number
  bytes_processed: number
  executed_query?: string | null
  query_generation?: IngestionQueryGenerationMetadata | null
  idempotency?: IngestionIdempotencyMetadata | null
  metadata_typed?: IngestionJobMetadata | null
  metadata?: JSONObject
}

export interface IngestionJobHistoryResponse {
  source_id: string
  items: IngestionJobHistoryItem[]
}

const DATA_SOURCE_LIST_TIMEOUT_MS = 60000

export async function fetchDataSources(
  params: DataSourceListParams = {},
  token?: string,
): Promise<DataSourceListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchDataSources')
  }

  const response = await apiClient.get<DataSourceListResponse>(
    '/admin/data-sources',
    {
      params,
      ...authHeaders(token),
      timeout: DATA_SOURCE_LIST_TIMEOUT_MS,
    },
  )

  return response.data
}

export async function fetchDataSourcesBySpace(
  spaceId: string,
  params: Omit<DataSourceListParams, 'research_space_id'> = {},
  token?: string,
): Promise<DataSourceListResponse> {
  return fetchDataSources({ ...params, research_space_id: spaceId }, token)
}

export async function createDataSource(
  data: {
    name: string
    description?: string
    source_type: string
    config: Record<string, unknown>
    tags?: string[]
    research_space_id?: string
  },
  token?: string,
): Promise<DataSource> {
  if (!token) {
    throw new Error('Authentication token is required for createDataSource')
  }

  const response = await apiClient.post<DataSource>(
    '/admin/data-sources',
    data,
    authHeaders(token),
  )

  return response.data
}

export async function createDataSourceInSpace(
  spaceId: string,
  data: Omit<Parameters<typeof createDataSource>[0], 'research_space_id'>,
  token?: string,
): Promise<DataSource> {
  if (!token) {
    throw new Error('Authentication token is required for createDataSourceInSpace')
  }

  const response = await apiClient.post<DataSource>(
    `/research-spaces/${spaceId}/data-sources`,
    data,
    authHeaders(token),
  )

  const source = response.data
  if (!source.id || source.research_space_id !== spaceId) {
    throw new Error('Invalid space-scoped data source response payload')
  }

  return source
}

export async function configureDataSourceSchedule(
  sourceId: string,
  payload: ScheduleConfigurationPayload,
  token?: string,
): Promise<ScheduleConfigurationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for configureDataSourceSchedule')
  }

  const response = await apiClient.put<ScheduleConfigurationResponse>(
    `/admin/data-sources/${sourceId}/schedule`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function updateDataSource(
  sourceId: string,
  payload: UpdateDataSourcePayload,
  token?: string,
): Promise<DataSource> {
  if (!token) {
    throw new Error('Authentication token is required for updateDataSource')
  }

  const response = await apiClient.put<DataSource>(
    `/admin/data-sources/${sourceId}`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function testDataSourceAiConfiguration(
  sourceId: string,
  token?: string,
): Promise<DataSourceAiTestResult> {
  if (!token) {
    throw new Error('Authentication token is required for testDataSourceAiConfiguration')
  }

  // AI test can take a while with reasoning models (GPT-5 has 180s backend timeout)
  // Use a longer timeout than the default 15s
  const response = await apiClient.post<DataSourceAiTestResult>(
    `/admin/data-sources/${sourceId}/ai/test`,
    {},
    {
      ...authHeaders(token),
      timeout: 200000, // 200 seconds for AI reasoning models
    },
  )
  return response.data
}

export async function fetchIngestionJobHistory(
  sourceId: string,
  token?: string,
  params: { limit?: number } = {},
): Promise<IngestionJobHistoryResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchIngestionJobHistory')
  }
  const response = await apiClient.get<IngestionJobHistoryResponse>(
    `/admin/data-sources/${sourceId}/ingestion-jobs`,
    {
      params,
      ...authHeaders(token),
    },
  )
  return response.data
}

export async function deleteDataSource(
  sourceId: string,
  token?: string,
): Promise<void> {
  if (!token) {
    throw new Error('Authentication token is required for deleteDataSource')
  }

  await apiClient.delete(`/admin/data-sources/${sourceId}`, authHeaders(token))
}
