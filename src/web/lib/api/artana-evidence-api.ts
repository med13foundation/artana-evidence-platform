import { apiPost } from '@/lib/api/client'
import { resolveArtanaEvidenceApiBaseUrl } from '@/lib/api/harness-base-url'
import type {
  GenerateHypothesesRequest,
  GenerateHypothesesResponse,
  GraphSearchRequest,
  GraphSearchResponse,
} from '@/types/kernel'

const ARTANA_EVIDENCE_API_BASE_URL = resolveArtanaEvidenceApiBaseUrl()

function artanaEvidenceApiSpacePath(spaceId: string, path: string): string {
  return `/v1/spaces/${spaceId}${path}`
}

interface HarnessHypothesisRunPayload {
  run: {
    id: string
    input_payload: {
      seed_entity_ids?: unknown
    }
  }
  candidate_count: number
  errors: string[]
}

interface HarnessGraphSearchRunPayload {
  result: GraphSearchResponse
}

export async function generateHypotheses(
  spaceId: string,
  payload: GenerateHypothesesRequest,
  token?: string,
): Promise<GenerateHypothesesResponse> {
  if (!token) {
    throw new Error('Authentication token is required for generateHypotheses')
  }

  const response = await apiPost<HarnessHypothesisRunPayload>(
    artanaEvidenceApiSpacePath(spaceId, '/agents/hypotheses/runs'),
    payload,
    {
      token,
      timeout: 0,
      baseURL: ARTANA_EVIDENCE_API_BASE_URL,
    },
  )

  const rawSeedEntityIds = response.run.input_payload.seed_entity_ids
  const requestedSeedCount = Array.isArray(rawSeedEntityIds)
    ? rawSeedEntityIds.filter((value): value is string => typeof value === 'string').length
    : 0

  return {
    run_id: response.run.id,
    requested_seed_count: requestedSeedCount,
    used_seed_count: requestedSeedCount,
    candidates_seen: response.candidate_count,
    created_count: response.candidate_count,
    deduped_count: 0,
    errors: response.errors,
    hypotheses: [],
  }
}

export async function searchKernelGraph(
  spaceId: string,
  payload: GraphSearchRequest,
  token?: string,
): Promise<GraphSearchResponse> {
  if (!token) {
    throw new Error('Authentication token is required for searchKernelGraph')
  }

  const { force_agent: _forceAgent, ...harnessPayload } = payload
  return (
    await apiPost<HarnessGraphSearchRunPayload>(
      artanaEvidenceApiSpacePath(spaceId, '/agents/graph-search/runs'),
      harnessPayload,
      {
        token,
        baseURL: ARTANA_EVIDENCE_API_BASE_URL,
      },
    )
  ).result
}
