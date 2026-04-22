import { apiGet, apiPatch, apiPost, apiPut, type ApiRequestOptions } from '@/lib/api/client'
import { resolveGraphApiBaseUrl } from '@/lib/api/graph-base-url'
import type {
  ConceptAliasCreateRequest,
  ConceptAliasListResponse,
  ConceptAliasResponse,
  ConceptDecisionListResponse,
  ConceptDecisionProposeRequest,
  ConceptDecisionResponse,
  ConceptDecisionStatus,
  ConceptDecisionStatusRequest,
  ConceptMemberCreateRequest,
  ConceptMemberListResponse,
  ConceptMemberResponse,
  ConceptPolicyResponse,
  ConceptPolicyUpsertRequest,
  ConceptSetCreateRequest,
  ConceptSetListResponse,
  ConceptSetResponse,
} from '@/types/concepts'

const GRAPH_API_BASE_URL = resolveGraphApiBaseUrl()

export interface ConceptSetListParams {
  include_inactive?: boolean
}

export interface ConceptMemberListParams {
  concept_set_id?: string
  include_inactive?: boolean
  offset?: number
  limit?: number
}

export interface ConceptAliasListParams {
  concept_member_id?: string
  include_inactive?: boolean
  offset?: number
  limit?: number
}

export interface ConceptDecisionListParams {
  decision_status?: ConceptDecisionStatus
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

export async function fetchSpaceConceptSets(
  spaceId: string,
  params: ConceptSetListParams = {},
  token?: string,
): Promise<ConceptSetListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceConceptSets')
  }

  const options: ApiRequestOptions<ConceptSetListResponse> = {
    token,
    params: {
      include_inactive: params.include_inactive ?? false,
    },
  }

  return apiGet<ConceptSetListResponse>(
    graphSpacePath(spaceId, '/concepts/sets'),
    withGraphApiOptions(options),
  )
}

export async function fetchSpaceConceptMembers(
  spaceId: string,
  params: ConceptMemberListParams = {},
  token?: string,
): Promise<ConceptMemberListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceConceptMembers')
  }

  const options: ApiRequestOptions<ConceptMemberListResponse> = {
    token,
    params: {
      ...(params.concept_set_id ? { concept_set_id: params.concept_set_id } : {}),
      include_inactive: params.include_inactive ?? false,
      offset: params.offset ?? 0,
      limit: params.limit ?? 100,
    },
  }

  return apiGet<ConceptMemberListResponse>(
    graphSpacePath(spaceId, '/concepts/members'),
    withGraphApiOptions(options),
  )
}

export async function fetchSpaceConceptAliases(
  spaceId: string,
  params: ConceptAliasListParams = {},
  token?: string,
): Promise<ConceptAliasListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceConceptAliases')
  }

  const options: ApiRequestOptions<ConceptAliasListResponse> = {
    token,
    params: {
      ...(params.concept_member_id ? { concept_member_id: params.concept_member_id } : {}),
      include_inactive: params.include_inactive ?? false,
      offset: params.offset ?? 0,
      limit: params.limit ?? 100,
    },
  }

  return apiGet<ConceptAliasListResponse>(
    graphSpacePath(spaceId, '/concepts/aliases'),
    withGraphApiOptions(options),
  )
}

export async function fetchSpaceConceptPolicy(
  spaceId: string,
  token?: string,
): Promise<ConceptPolicyResponse | null> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceConceptPolicy')
  }
  return apiGet<ConceptPolicyResponse | null>(
    graphSpacePath(spaceId, '/concepts/policy'),
    withGraphApiOptions({ token }),
  )
}

export async function fetchSpaceConceptDecisions(
  spaceId: string,
  params: ConceptDecisionListParams = {},
  token?: string,
): Promise<ConceptDecisionListResponse> {
  if (!token) {
    throw new Error('Authentication token is required for fetchSpaceConceptDecisions')
  }

  const options: ApiRequestOptions<ConceptDecisionListResponse> = {
    token,
    params: {
      ...(params.decision_status ? { decision_status: params.decision_status } : {}),
      offset: params.offset ?? 0,
      limit: params.limit ?? 100,
    },
  }

  return apiGet<ConceptDecisionListResponse>(
    graphSpacePath(spaceId, '/concepts/decisions'),
    withGraphApiOptions(options),
  )
}

export async function createSpaceConceptSet(
  spaceId: string,
  payload: ConceptSetCreateRequest,
  token?: string,
): Promise<ConceptSetResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createSpaceConceptSet')
  }
  return apiPost<ConceptSetResponse>(
    graphSpacePath(spaceId, '/concepts/sets'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function createSpaceConceptMember(
  spaceId: string,
  payload: ConceptMemberCreateRequest,
  token?: string,
): Promise<ConceptMemberResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createSpaceConceptMember')
  }
  return apiPost<ConceptMemberResponse>(
    graphSpacePath(spaceId, '/concepts/members'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function createSpaceConceptAlias(
  spaceId: string,
  payload: ConceptAliasCreateRequest,
  token?: string,
): Promise<ConceptAliasResponse> {
  if (!token) {
    throw new Error('Authentication token is required for createSpaceConceptAlias')
  }
  return apiPost<ConceptAliasResponse>(
    graphSpacePath(spaceId, '/concepts/aliases'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function upsertSpaceConceptPolicy(
  spaceId: string,
  payload: ConceptPolicyUpsertRequest,
  token?: string,
): Promise<ConceptPolicyResponse> {
  if (!token) {
    throw new Error('Authentication token is required for upsertSpaceConceptPolicy')
  }
  return apiPut<ConceptPolicyResponse>(
    graphSpacePath(spaceId, '/concepts/policy'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function proposeSpaceConceptDecision(
  spaceId: string,
  payload: ConceptDecisionProposeRequest,
  token?: string,
): Promise<ConceptDecisionResponse> {
  if (!token) {
    throw new Error('Authentication token is required for proposeSpaceConceptDecision')
  }
  return apiPost<ConceptDecisionResponse>(
    graphSpacePath(spaceId, '/concepts/decisions/propose'),
    payload,
    withGraphApiOptions({ token }),
  )
}

export async function setSpaceConceptDecisionStatus(
  spaceId: string,
  decisionId: string,
  payload: ConceptDecisionStatusRequest,
  token?: string,
): Promise<ConceptDecisionResponse> {
  if (!token) {
    throw new Error('Authentication token is required for setSpaceConceptDecisionStatus')
  }
  return apiPatch<ConceptDecisionResponse>(
    graphSpacePath(spaceId, `/concepts/decisions/${decisionId}/status`),
    payload,
    withGraphApiOptions({ token }),
  )
}
