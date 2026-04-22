import { apiClient, authHeaders } from '@/lib/api/client'
import type {
  AddToSpaceRequest,
  CreatePubmedPresetRequest,
  CreateSessionRequest,
  DataDiscoverySession,
  DiscoveryPreset,
  DiscoverySearchJob,
  ExecuteTestRequest,
  PubmedDownloadRequest,
  QueryTestResult,
  SourceCatalogEntry,
  StorageOperationSummary,
  UpdateParametersRequest,
  RunPubmedSearchRequest,
} from '@/lib/types/data-discovery'

const DATA_DISCOVERY_BASE = '/data-discovery'

function requireToken(token?: string): asserts token is string {
  if (!token) {
    throw new Error('Authentication token is required for data discovery requests')
  }
}

export async function fetchSourceCatalog(
  token?: string,
  params?: { category?: string; search?: string; research_space_id?: string },
): Promise<SourceCatalogEntry[]> {
  requireToken(token)
  const response = await apiClient.get<SourceCatalogEntry[]>(`${DATA_DISCOVERY_BASE}/catalog`, {
    params,
    ...authHeaders(token),
  })
  return response.data
}

export async function fetchDataDiscoverySessions(token?: string): Promise<DataDiscoverySession[]> {
  requireToken(token)
  const response = await apiClient.get<DataDiscoverySession[]>(`${DATA_DISCOVERY_BASE}/sessions`, authHeaders(token))
  return response.data
}

export async function createDataDiscoverySession(
  payload: CreateSessionRequest,
  token?: string,
): Promise<DataDiscoverySession> {
  requireToken(token)
  const response = await apiClient.post<DataDiscoverySession>(
    `${DATA_DISCOVERY_BASE}/sessions`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function updateDataDiscoverySessionParameters(
  sessionId: string,
  payload: UpdateParametersRequest,
  token?: string,
): Promise<DataDiscoverySession> {
  requireToken(token)
  const response = await apiClient.put<DataDiscoverySession>(
    `${DATA_DISCOVERY_BASE}/sessions/${sessionId}/parameters`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function toggleDataDiscoverySourceSelection(
  sessionId: string,
  catalogEntryId: string,
  token?: string,
): Promise<DataDiscoverySession> {
  requireToken(token)
  const response = await apiClient.put<DataDiscoverySession>(
    `${DATA_DISCOVERY_BASE}/sessions/${sessionId}/sources/${catalogEntryId}/toggle`,
    {},
    authHeaders(token),
  )
  return response.data
}

export async function executeDataDiscoveryQueryTest(
  sessionId: string,
  payload: ExecuteTestRequest,
  token?: string,
): Promise<QueryTestResult> {
  requireToken(token)
  const response = await apiClient.post<QueryTestResult>(
    `${DATA_DISCOVERY_BASE}/sessions/${sessionId}/tests`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function fetchSessionTestResults(
  sessionId: string,
  token?: string,
): Promise<QueryTestResult[]> {
  requireToken(token)
  const response = await apiClient.get<QueryTestResult[]>(
    `${DATA_DISCOVERY_BASE}/sessions/${sessionId}/tests`,
    authHeaders(token),
  )
  return response.data
}

export async function addSourceToSpaceFromDiscovery(
  sessionId: string,
  payload: AddToSpaceRequest,
  token?: string,
): Promise<{ data_source_id: string; message: string }> {
  requireToken(token)
  const response = await apiClient.post<{ data_source_id: string; message: string }>(
    `${DATA_DISCOVERY_BASE}/sessions/${sessionId}/add-to-space`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function setDataDiscoverySelections(
  sessionId: string,
  sourceIds: string[],
  token?: string,
): Promise<DataDiscoverySession> {
  requireToken(token)
  const response = await apiClient.put<DataDiscoverySession>(
    `${DATA_DISCOVERY_BASE}/sessions/${sessionId}/selections`,
    { source_ids: sourceIds },
    authHeaders(token),
  )
  return response.data
}

export async function fetchPubmedPresets(
  token?: string,
  params?: { research_space_id?: string },
): Promise<DiscoveryPreset[]> {
  requireToken(token)
  const response = await apiClient.get<DiscoveryPreset[]>(`${DATA_DISCOVERY_BASE}/pubmed/presets`, {
    params,
    ...authHeaders(token),
  })
  return response.data
}

export async function createPubmedPreset(
  payload: CreatePubmedPresetRequest,
  token?: string,
): Promise<DiscoveryPreset> {
  requireToken(token)
  const response = await apiClient.post<DiscoveryPreset>(
    `${DATA_DISCOVERY_BASE}/pubmed/presets`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function deletePubmedPreset(presetId: string, token?: string): Promise<void> {
  requireToken(token)
  await apiClient.delete(`${DATA_DISCOVERY_BASE}/pubmed/presets/${presetId}`, authHeaders(token))
}

export async function runPubmedSearch(
  payload: RunPubmedSearchRequest,
  token?: string,
): Promise<DiscoverySearchJob> {
  requireToken(token)
  const response = await apiClient.post<DiscoverySearchJob>(
    `${DATA_DISCOVERY_BASE}/pubmed/search`,
    payload,
    authHeaders(token),
  )
  return response.data
}

export async function fetchPubmedSearchJob(jobId: string, token?: string): Promise<DiscoverySearchJob> {
  requireToken(token)
  const response = await apiClient.get<DiscoverySearchJob>(
    `${DATA_DISCOVERY_BASE}/pubmed/search/${jobId}`,
    authHeaders(token),
  )
  return response.data
}

export async function downloadPubmedPdf(
  payload: PubmedDownloadRequest,
  token?: string,
): Promise<StorageOperationSummary> {
  requireToken(token)
  const response = await apiClient.post<StorageOperationSummary>(
    `${DATA_DISCOVERY_BASE}/pubmed/download`,
    payload,
    authHeaders(token),
  )
  return response.data
}
