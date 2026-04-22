import { apiDelete, apiGet, apiPatch, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import { resolveGraphApiBaseUrl } from '@/lib/api/graph-base-url'
import type {
  KernelEntityCreateRequest,
  KernelEntityListResponse,
  KernelEntityResponse,
  KernelEntityUpdateRequest,
  KernelEntityUpsertResponse,
  KernelGraphDocumentRequest,
  KernelGraphDocumentResponse,
  KernelGraphExportResponse,
  KernelGraphSubgraphRequest,
  KernelGraphSubgraphResponse,
  KernelObservationCreateRequest,
  KernelObservationListResponse,
  KernelObservationResponse,
  ClaimEvidenceListResponse,
  CreateManualHypothesisRequest,
  ClaimRelationCreateRequest,
  ClaimRelationListResponse,
  ClaimRelationResponse,
  ClaimRelationReviewStatus,
  ClaimRelationType,
  ClaimRelationReviewUpdateRequest,
  ClaimParticipantBackfillRequest,
  ClaimParticipantBackfillResponse,
  ClaimParticipantCoverageResponse,
  ClaimParticipantListResponse,
  HypothesisListResponse,
  HypothesisResponse,
  KernelProvenanceListResponse,
  KernelProvenanceResponse,
  KernelRelationCreateRequest,
  RelationConflictListResponse,
  RelationClaimListResponse,
  RelationClaimResponse,
  RelationClaimTriageRequest,
  KernelRelationCurationUpdateRequest,
  KernelRelationListResponse,
  KernelRelationResponse,
  PipelineRunRequest,
  PipelineRunCancelResponse,
  PipelineRunComparisonResponse,
  PipelineRunCostReportResponse,
  PipelineRunCostSummaryResponse,
  PipelineRunResponse,
  PipelineRunSummaryEnvelopeResponse,
  PipelineRunTimingSummaryResponse,
  SourcePipelineRunsResponse,
  SourceWorkflowDocumentTraceResponse,
  SourceWorkflowEventsResponse,
  SourceWorkflowMonitorResponse,
  SourceWorkflowQueryTraceResponse,
  SpaceRunActiveSourcesResponse,
  SpaceSourceIngestionRunResponse,
} from '@/types/kernel'

const GRAPH_API_BASE_URL = resolveGraphApiBaseUrl()

export interface KernelEntityListParams {
  type?: string
  q?: string
  ids?: string[]
  offset?: number
  limit?: number
}

function withGraphApiOptions<TResponse>(
  options: ApiRequestOptions<TResponse>,
): ApiRequestOptions<TResponse> {
  return {
    ...options,
    baseURL: GRAPH_API_BASE_URL,
  }
}

function graphSpacePath(spaceId: string, path: string): string {
  return `/v1/spaces/${spaceId}${path}`
}

export async function fetchKernelEntities(
  spaceId: string,
  params: KernelEntityListParams,
  token?: string,
): Promise<KernelEntityListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelEntities')
  }

  const options: ApiRequestOptions<KernelEntityListResponse> = {
    token,
    params: {
      ...(params.type ? { type: params.type } : {}),
      ...(params.q ? { q: params.q } : {}),
      ...(params.ids && params.ids.length > 0 ? { ids: params.ids.join(',') } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelEntityListResponse>(
    graphSpacePath(spaceId, '/entities'),
    withGraphApiOptions(options),
  )
}

export async function createKernelEntity(
  spaceId: string,
  payload: KernelEntityCreateRequest,
  token?: string,
): Promise<KernelEntityUpsertResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createKernelEntity')
  }
  return apiPost<KernelEntityUpsertResponse>(
    graphSpacePath(spaceId, '/entities'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchKernelEntity(
  spaceId: string,
  entityId: string,
  token?: string,
): Promise<KernelEntityResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelEntity')
  }
  return apiGet<KernelEntityResponse>(
    graphSpacePath(spaceId, `/entities/${entityId}`),
    withGraphApiOptions({ token }),
  )
}

export async function updateKernelEntity(
  spaceId: string,
  entityId: string,
  payload: KernelEntityUpdateRequest,
  token?: string,
): Promise<KernelEntityResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateKernelEntity')
  }
  return apiPut<KernelEntityResponse>(
    graphSpacePath(spaceId, `/entities/${entityId}`),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function deleteKernelEntity(
  spaceId: string,
  entityId: string,
  token?: string,
): Promise<void> {
  if (!token) {
    throw new Error('Authentication token is required for deleteKernelEntity')
  }
  await apiDelete<void>(
    graphSpacePath(spaceId, `/entities/${entityId}`),
    withGraphApiOptions({ token }),
  )
}

export interface KernelObservationListParams {
  subject_id?: string
  variable_id?: string
  offset?: number
  limit?: number
}

export async function fetchKernelObservations(
  spaceId: string,
  params: KernelObservationListParams = {},
  token?: string,
): Promise<KernelObservationListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelObservations')
  }

  const options: ApiRequestOptions<KernelObservationListResponse> = {
    token,
    params: {
      ...(params.subject_id ? { subject_id: params.subject_id } : {}),
      ...(params.variable_id ? { variable_id: params.variable_id } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelObservationListResponse>(
    graphSpacePath(spaceId, '/observations'),
    withGraphApiOptions(options),
  )
}

export async function createKernelObservation(
  spaceId: string,
  payload: KernelObservationCreateRequest,
  token?: string,
): Promise<KernelObservationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createKernelObservation')
  }
  return apiPost<KernelObservationResponse>(
    graphSpacePath(spaceId, '/observations'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchKernelObservation(
  spaceId: string,
  observationId: string,
  token?: string,
): Promise<KernelObservationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelObservation')
  }
  return apiGet<KernelObservationResponse>(
    graphSpacePath(spaceId, `/observations/${observationId}`),
    withGraphApiOptions({ token }),
  )
}

export interface KernelRelationListParams {
  relation_type?: string
  curation_status?: string
  validation_state?: string
  source_document_id?: string
  certainty_band?: 'HIGH' | 'MEDIUM' | 'LOW'
  node_query?: string
  node_ids?: string[]
  offset?: number
  limit?: number
}

export async function fetchKernelRelations(
  spaceId: string,
  params: KernelRelationListParams = {},
  token?: string,
): Promise<KernelRelationListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelRelations')
  }

  const options: ApiRequestOptions<KernelRelationListResponse> = {
    token,
    params: {
      ...(params.relation_type ? { relation_type: params.relation_type } : {}),
      ...(params.curation_status ? { curation_status: params.curation_status } : {}),
      ...(params.validation_state ? { validation_state: params.validation_state } : {}),
      ...(params.source_document_id ? { source_document_id: params.source_document_id } : {}),
      ...(params.certainty_band ? { certainty_band: params.certainty_band } : {}),
      ...(params.node_query ? { node_query: params.node_query } : {}),
      ...(params.node_ids && params.node_ids.length > 0
        ? { node_ids: params.node_ids.join(',') }
        : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelRelationListResponse>(
    graphSpacePath(spaceId, '/relations'),
    withGraphApiOptions(options),
  )
}

export async function createKernelRelation(
  spaceId: string,
  payload: KernelRelationCreateRequest,
  token?: string,
): Promise<KernelRelationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createKernelRelation')
  }
  return apiPost<KernelRelationResponse>(
    graphSpacePath(spaceId, '/relations'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function updateKernelRelationCurationStatus(
  spaceId: string,
  relationId: string,
  payload: KernelRelationCurationUpdateRequest,
  token?: string,
): Promise<KernelRelationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateKernelRelationCurationStatus')
  }
  return apiPut<KernelRelationResponse>(
    graphSpacePath(spaceId, `/relations/${relationId}`),
    payload,
    withGraphApiOptions({ token }),
  )
}

export interface RelationClaimListParams {
  claim_status?: 'OPEN' | 'NEEDS_MAPPING' | 'REJECTED' | 'RESOLVED'
  validation_state?: string
  persistability?: 'PERSISTABLE' | 'NON_PERSISTABLE'
  polarity?: 'SUPPORT' | 'REFUTE' | 'UNCERTAIN' | 'HYPOTHESIS'
  source_document_id?: string
  relation_type?: string
  linked_relation_id?: string
  certainty_band?: 'HIGH' | 'MEDIUM' | 'LOW'
  offset?: number
  limit?: number
}

export async function fetchRelationClaims(
  spaceId: string,
  params: RelationClaimListParams = {},
  token?: string,
): Promise<RelationClaimListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRelationClaims')
  }

  const options: ApiRequestOptions<RelationClaimListResponse> = {
    token,
    params: {
      ...(params.claim_status ? { claim_status: params.claim_status } : {}),
      ...(params.validation_state ? { validation_state: params.validation_state } : {}),
      ...(params.persistability ? { persistability: params.persistability } : {}),
      ...(params.polarity ? { polarity: params.polarity } : {}),
      ...(params.source_document_id ? { source_document_id: params.source_document_id } : {}),
      ...(params.relation_type ? { relation_type: params.relation_type } : {}),
      ...(params.linked_relation_id ? { linked_relation_id: params.linked_relation_id } : {}),
      ...(params.certainty_band ? { certainty_band: params.certainty_band } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<RelationClaimListResponse>(
    graphSpacePath(spaceId, '/claims'),
    withGraphApiOptions(options),
  )
}

export interface HypothesisListParams {
  offset?: number
  limit?: number
}

export async function fetchHypotheses(
  spaceId: string,
  params: HypothesisListParams = {},
  token?: string,
): Promise<HypothesisListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchHypotheses')
  }
  const options: ApiRequestOptions<HypothesisListResponse> = {
    token,
    params: {
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }
  return apiGet<HypothesisListResponse>(
    graphSpacePath(spaceId, '/hypotheses'),
    withGraphApiOptions(options),
  )
}

export async function createManualHypothesis(
  spaceId: string,
  payload: CreateManualHypothesisRequest,
  token?: string,
): Promise<HypothesisResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createManualHypothesis')
  }
  return apiPost<HypothesisResponse>(
    graphSpacePath(spaceId, '/hypotheses/manual'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export interface ClaimRelationListParams {
  relation_type?: ClaimRelationType
  review_status?: ClaimRelationReviewStatus
  source_claim_id?: string
  target_claim_id?: string
  claim_id?: string
  offset?: number
  limit?: number
}

export async function fetchClaimRelations(
  spaceId: string,
  params: ClaimRelationListParams = {},
  token?: string,
): Promise<ClaimRelationListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchClaimRelations')
  }

  const options: ApiRequestOptions<ClaimRelationListResponse> = {
    token,
    params: {
      ...(params.relation_type ? { relation_type: params.relation_type } : {}),
      ...(params.review_status ? { review_status: params.review_status } : {}),
      ...(params.source_claim_id ? { source_claim_id: params.source_claim_id } : {}),
      ...(params.target_claim_id ? { target_claim_id: params.target_claim_id } : {}),
      ...(params.claim_id ? { claim_id: params.claim_id } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 100,
    },
  }

  return apiGet<ClaimRelationListResponse>(
    graphSpacePath(spaceId, '/claim-relations'),
    withGraphApiOptions(options),
  )
}

export async function createClaimRelation(
  spaceId: string,
  payload: ClaimRelationCreateRequest,
  token?: string,
): Promise<ClaimRelationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createClaimRelation')
  }

  return apiPost<ClaimRelationResponse>(
    graphSpacePath(spaceId, '/claim-relations'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function updateClaimRelationReview(
  spaceId: string,
  relationId: string,
  payload: ClaimRelationReviewUpdateRequest,
  token?: string,
): Promise<ClaimRelationResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateClaimRelationReview')
  }

  return apiPatch<ClaimRelationResponse>(
    graphSpacePath(spaceId, `/claim-relations/${relationId}`),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchClaimParticipants(
  spaceId: string,
  claimId: string,
  token?: string,
): Promise<ClaimParticipantListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchClaimParticipants')
  }
  return apiGet<ClaimParticipantListResponse>(
    graphSpacePath(spaceId, `/claims/${claimId}/participants`),
    withGraphApiOptions({ token }),
  )
}

export async function fetchClaimsByEntity(
  spaceId: string,
  entityId: string,
  params: { limit?: number; offset?: number } = {},
  token?: string,
): Promise<RelationClaimListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchClaimsByEntity')
  }
  return apiGet<RelationClaimListResponse>(
    graphSpacePath(spaceId, `/claims/by-entity/${entityId}`),
    withGraphApiOptions({
      token,
      params: {
        limit: params.limit ?? 20,
        offset: params.offset ?? 0,
      },
    }),
  )
}

export async function fetchClaimParticipantCoverage(
  spaceId: string,
  params: { limit?: number; offset?: number } = {},
  token?: string,
): Promise<ClaimParticipantCoverageResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchClaimParticipantCoverage')
  }
  return apiGet<ClaimParticipantCoverageResponse>(
    graphSpacePath(spaceId, '/claim-participants/coverage'),
    withGraphApiOptions({
      token,
      params: {
        limit: params.limit ?? 500,
        offset: params.offset ?? 0,
      },
    }),
  )
}

export async function runClaimParticipantBackfill(
  spaceId: string,
  payload: ClaimParticipantBackfillRequest,
  token?: string,
): Promise<ClaimParticipantBackfillResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runClaimParticipantBackfill')
  }
  return apiPost<ClaimParticipantBackfillResponse>(
    graphSpacePath(spaceId, '/claim-participants/backfill'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchRelationClaimEvidence(
  spaceId: string,
  claimId: string,
  token?: string,
): Promise<ClaimEvidenceListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRelationClaimEvidence')
  }
  return apiGet<ClaimEvidenceListResponse>(
    graphSpacePath(spaceId, `/claims/${claimId}/evidence`),
    withGraphApiOptions({ token }),
  )
}

export interface RelationConflictListParams {
  offset?: number
  limit?: number
}

export async function fetchRelationConflicts(
  spaceId: string,
  params: RelationConflictListParams = {},
  token?: string,
): Promise<RelationConflictListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchRelationConflicts')
  }
  const options: ApiRequestOptions<RelationConflictListResponse> = {
    token,
    params: {
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }
  return apiGet<RelationConflictListResponse>(
    graphSpacePath(spaceId, '/relations/conflicts'),
    withGraphApiOptions(options),
  )
}

export async function updateRelationClaimStatus(
  spaceId: string,
  claimId: string,
  payload: RelationClaimTriageRequest,
  token?: string,
): Promise<RelationClaimResponse> {
  if (!token) {
    throw new Error('Authentication token is required for updateRelationClaimStatus')
  }
  return apiPatch<RelationClaimResponse>(
    graphSpacePath(spaceId, `/claims/${claimId}`),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchKernelGraphExport(
  spaceId: string,
  token?: string,
): Promise<KernelGraphExportResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelGraphExport')
  }
  return apiGet<KernelGraphExportResponse>(
    graphSpacePath(spaceId, '/graph/export'),
    withGraphApiOptions({ token }),
  )
}

export async function fetchKernelSubgraph(
  spaceId: string,
  payload: KernelGraphSubgraphRequest,
  token?: string,
): Promise<KernelGraphSubgraphResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelSubgraph')
  }
  return apiPost<KernelGraphSubgraphResponse>(
    graphSpacePath(spaceId, '/graph/subgraph'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchKernelGraphDocument(
  spaceId: string,
  payload: KernelGraphDocumentRequest,
  token?: string,
): Promise<KernelGraphDocumentResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelGraphDocument')
  }
  return apiPost<KernelGraphDocumentResponse>(
    graphSpacePath(spaceId, '/graph/document'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function fetchKernelNeighborhood(
  spaceId: string,
  entityId: string,
  depth: number,
  token?: string,
): Promise<KernelGraphExportResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelNeighborhood')
  }
  const options: ApiRequestOptions<KernelGraphExportResponse> = {
    token,
    params: { depth },
  }
  return apiGet<KernelGraphExportResponse>(
    graphSpacePath(spaceId, `/graph/neighborhood/${entityId}`),
    withGraphApiOptions(options),
  )
}

export interface KernelProvenanceListParams {
  source_type?: string
  offset?: number
  limit?: number
}

export async function fetchKernelProvenance(
  spaceId: string,
  params: KernelProvenanceListParams = {},
  token?: string,
): Promise<KernelProvenanceListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelProvenance')
  }

  const options: ApiRequestOptions<KernelProvenanceListResponse> = {
    token,
    params: {
      ...(params.source_type ? { source_type: params.source_type } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    },
  }

  return apiGet<KernelProvenanceListResponse>(
    graphSpacePath(spaceId, '/provenance'),
    withGraphApiOptions(options),
  )
}

export async function fetchKernelProvenanceRecord(
  spaceId: string,
  provenanceId: string,
  token?: string,
): Promise<KernelProvenanceResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchKernelProvenanceRecord')
  }
  return apiGet<KernelProvenanceResponse>(
    graphSpacePath(spaceId, `/provenance/${provenanceId}`),
    withGraphApiOptions({ token }),
  )
}

export async function runAllActiveSpaceSourcesIngestion(
  spaceId: string,
  token?: string,
): Promise<SpaceRunActiveSourcesResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runAllActiveSpaceSourcesIngestion')
  }
  return apiPost<SpaceRunActiveSourcesResponse>(
    `/research-spaces/${spaceId}/ingest/run`,
    {},
    { token },
  )
}

export async function runSingleSpaceSourceIngestion(
  spaceId: string,
  sourceId: string,
  token?: string,
): Promise<SpaceSourceIngestionRunResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runSingleSpaceSourceIngestion')
  }
  return apiPost<SpaceSourceIngestionRunResponse>(
    `/research-spaces/${spaceId}/ingest/sources/${sourceId}/run`,
    {},
    { token },
  )
}

export async function runSpaceSourcePipeline(
  spaceId: string,
  payload: PipelineRunRequest,
  token?: string,
): Promise<PipelineRunResponse> {
  if (!token) {
    throw new Error('Authentication token is required for runSpaceSourcePipeline')
  }
  return apiPost<PipelineRunResponse>(
    `/research-spaces/${spaceId}/pipeline/run`,
    payload,
    {
      token,
      timeout: 0,
    },
  )
}

export async function cancelSpaceSourcePipelineRun(
  spaceId: string,
  sourceId: string,
  runId: string,
  token?: string,
): Promise<PipelineRunCancelResponse> {
  if (!token) {
    throw new Error('Authentication token is required for cancelSpaceSourcePipelineRun')
  }
  return apiPost<PipelineRunCancelResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${runId}/cancel`,
    {},
    { token },
  )
}

export interface SourcePipelineRunsParams {
  limit?: number
}

export async function fetchSourcePipelineRuns(
  spaceId: string,
  sourceId: string,
  params: SourcePipelineRunsParams = {},
  token?: string,
): Promise<SourcePipelineRunsResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourcePipelineRuns')
  }
  const options: ApiRequestOptions<SourcePipelineRunsResponse> = {
    token,
    params: {
      limit: params.limit ?? 50,
    },
  }
  return apiGet<SourcePipelineRunsResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs`,
    options,
  )
}

export interface SourceWorkflowMonitorParams {
  run_id?: string
  limit?: number
  include_graph?: boolean
}

export async function fetchSourceWorkflowMonitor(
  spaceId: string,
  sourceId: string,
  params: SourceWorkflowMonitorParams = {},
  token?: string,
): Promise<SourceWorkflowMonitorResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceWorkflowMonitor')
  }
  const options: ApiRequestOptions<SourceWorkflowMonitorResponse> = {
    token,
    params: {
      ...(params.run_id ? { run_id: params.run_id } : {}),
      limit: params.limit ?? 50,
      include_graph: params.include_graph ?? true,
    },
  }
  return apiGet<SourceWorkflowMonitorResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/workflow-monitor`,
    options,
  )
}

export interface SourceWorkflowEventsParams {
  run_id?: string
  limit?: number
  since?: string
  stage?: string
  level?: string
  scope_kind?: string
  scope_id?: string
  agent_kind?: string
}

export async function fetchSourceWorkflowEvents(
  spaceId: string,
  sourceId: string,
  params: SourceWorkflowEventsParams = {},
  token?: string,
): Promise<SourceWorkflowEventsResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceWorkflowEvents')
  }
  const options: ApiRequestOptions<SourceWorkflowEventsResponse> = {
    token,
    params: {
      ...(params.run_id ? { run_id: params.run_id } : {}),
      ...(params.since ? { since: params.since } : {}),
      ...(params.stage ? { stage: params.stage } : {}),
      ...(params.level ? { level: params.level } : {}),
      ...(params.scope_kind ? { scope_kind: params.scope_kind } : {}),
      ...(params.scope_id ? { scope_id: params.scope_id } : {}),
      ...(params.agent_kind ? { agent_kind: params.agent_kind } : {}),
      limit: params.limit ?? 200,
    },
  }
  return apiGet<SourceWorkflowEventsResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/workflow-events`,
    options,
  )
}

export async function fetchPipelineRunSummary(
  spaceId: string,
  sourceId: string,
  runId: string,
  token?: string,
): Promise<PipelineRunSummaryEnvelopeResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchPipelineRunSummary')
  }
  return apiGet<PipelineRunSummaryEnvelopeResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${encodeURIComponent(runId)}/summary`,
    { token },
  )
}

export async function fetchSourceWorkflowDocumentTrace(
  spaceId: string,
  sourceId: string,
  runId: string,
  documentId: string,
  token?: string,
): Promise<SourceWorkflowDocumentTraceResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceWorkflowDocumentTrace')
  }
  return apiGet<SourceWorkflowDocumentTraceResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(documentId)}/trace`,
    { token },
  )
}

export async function fetchSourceWorkflowQueryTrace(
  spaceId: string,
  sourceId: string,
  runId: string,
  token?: string,
): Promise<SourceWorkflowQueryTraceResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSourceWorkflowQueryTrace')
  }
  return apiGet<SourceWorkflowQueryTraceResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${encodeURIComponent(runId)}/query-trace`,
    { token },
  )
}

export async function fetchPipelineRunTimingSummary(
  spaceId: string,
  sourceId: string,
  runId: string,
  token?: string,
): Promise<PipelineRunTimingSummaryResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchPipelineRunTimingSummary')
  }
  return apiGet<PipelineRunTimingSummaryResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${encodeURIComponent(runId)}/timing`,
    { token },
  )
}

export async function fetchPipelineRunCostSummary(
  spaceId: string,
  sourceId: string,
  runId: string,
  token?: string,
): Promise<PipelineRunCostSummaryResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchPipelineRunCostSummary')
  }
  return apiGet<PipelineRunCostSummaryResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/${encodeURIComponent(runId)}/cost`,
    { token },
  )
}

export interface PipelineRunCostReportParams {
  source_type?: string
  user_id?: string
  date_from?: string
  date_to?: string
  limit?: number
}

export async function fetchPipelineRunCostReport(
  spaceId: string,
  params: PipelineRunCostReportParams = {},
  token?: string,
): Promise<PipelineRunCostReportResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchPipelineRunCostReport')
  }
  return apiGet<PipelineRunCostReportResponse>(
    `/research-spaces/${spaceId}/pipeline-run-costs`,
    {
      token,
      params: {
        ...(params.source_type ? { source_type: params.source_type } : {}),
        ...(params.user_id ? { user_id: params.user_id } : {}),
        ...(params.date_from ? { date_from: params.date_from } : {}),
        ...(params.date_to ? { date_to: params.date_to } : {}),
        limit: params.limit ?? 200,
      },
    },
  )
}

export async function fetchUserPipelineRunCostReport(
  spaceId: string,
  userId: string,
  params: Omit<PipelineRunCostReportParams, 'user_id'> = {},
  token?: string,
): Promise<PipelineRunCostReportResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchUserPipelineRunCostReport')
  }
  return apiGet<PipelineRunCostReportResponse>(
    `/research-spaces/${spaceId}/users/${encodeURIComponent(userId)}/pipeline-run-costs`,
    {
      token,
      params: {
        ...(params.source_type ? { source_type: params.source_type } : {}),
        ...(params.date_from ? { date_from: params.date_from } : {}),
        ...(params.date_to ? { date_to: params.date_to } : {}),
        limit: params.limit ?? 200,
      },
    },
  )
}

export async function fetchPipelineRunComparison(
  spaceId: string,
  sourceId: string,
  runA: string,
  runB: string,
  token?: string,
): Promise<PipelineRunComparisonResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchPipelineRunComparison')
  }
  return apiGet<PipelineRunComparisonResponse>(
    `/research-spaces/${spaceId}/sources/${sourceId}/pipeline-runs/compare`,
    {
      token,
      params: {
        run_a: runA,
        run_b: runB,
      },
    },
  )
}
